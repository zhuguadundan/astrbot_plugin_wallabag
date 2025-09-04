import re
import json
import asyncio
from typing import Optional, Dict, List, Any
from pathlib import Path

import aiohttp
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig


@register("wallabag", "AstrBot Developer", "自动监听URL并保存到Wallabag服务", "1.0.0")
class WallabagPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[float] = None
        self.saved_urls_cache: set = set()
        
        # 确保数据目录存在
        self.data_dir = Path("data/wallabag")
        self.data_dir.mkdir(exist_ok=True)
        
        # 加载缓存
        self._load_cache()

    async def initialize(self):
        """插件初始化方法"""
        self.http_session = aiohttp.ClientSession()
        logger.info("Wallabag插件初始化完成")

    async def terminate(self):
        """插件销毁方法"""
        if self.http_session:
            await self.http_session.close()
        self._save_cache()
        logger.info("Wallabag插件已停止")

    def _load_cache(self):
        """加载缓存的URL"""
        cache_file = self.data_dir / "saved_urls.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.saved_urls_cache = set(json.load(f))
                logger.info(f"已加载{len(self.saved_urls_cache)}个缓存的URL")
            except Exception as e:
                logger.error(f"加载缓存失败: {e}")
                self.saved_urls_cache = set()

    def _save_cache(self):
        """保存缓存的URL"""
        cache_file = self.data_dir / "saved_urls.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.saved_urls_cache), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    @filter.command("wallabag")
    async def wallabag_help(self, event: AstrMessageEvent):
        """显示Wallabag插件帮助信息"""
        help_text = """📚 Wallabag插件使用说明

🔗 自动保存URL：直接发送包含URL的消息，插件会自动保存到Wallabag

📝 可用指令：
• `/wallabag` - 显示此帮助信息
• `/wallabag save <URL>` - 手动保存指定URL

💡 配置请在WebUI插件管理页面进行"""
        yield event.plain_result(help_text)

    @filter.command("wallabag", alias={'wb'})
    @filter.command_group("wallabag")
    async def wallabag_group(self):
        """Wallabag指令组"""
        pass

    @wallabag_group.command("save")
    async def save_url(self, event: AstrMessageEvent, url: str):
        """手动保存URL到Wallabag"""
        if not self._is_valid_url(url):
            yield event.plain_result("❌ 无效的URL格式")
            return

        try:
            result = await self._save_to_wallabag(url)
            if result:
                yield event.plain_result(f"✅ 成功保存文章到Wallabag\n📰 标题: {result.get('title', '未知')}\n⏱️ 阅读时间: {result.get('reading_time', 0)}分钟")
            else:
                yield event.plain_result("❌ 保存失败，请检查配置和URL")
        except Exception as e:
            logger.error(f"手动保存URL失败: {e}")
            yield event.plain_result(f"❌ 保存失败: {str(e)}")

    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，自动检测并保存URL"""
        if not self.config.get('auto_save', True):
            return

        message_str = event.message_str.strip()
        urls = self._extract_urls(message_str)
        
        if urls:
            for url in urls:
                if url not in self.saved_urls_cache:
                    try:
                        result = await self._save_to_wallabag(url)
                        if result:
                            self.saved_urls_cache.add(url)
                            self._save_cache()
                            title = result.get('title', '未知')[:50]
                            await event.send(event.plain_result(f"📎 自动保存: {title}..."))
                    except Exception as e:
                        logger.error(f"自动保存URL失败: {e}")

    def _extract_urls(self, text: str) -> List[str]:
        """从文本中提取URL"""
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*\??[/\w\.-=&%]*'
        urls = re.findall(url_pattern, text)
        return [url for url in urls if self._is_valid_url(url)]

    def _is_valid_url(self, url: str) -> bool:
        """验证URL格式"""
        if not url or not url.startswith(('http://', 'https://')):
            return False
        
        # 基本URL格式验证
        url_pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*\??[/\w\.-=&%]*'
        return re.match(url_pattern, url) is not None

    async def _get_access_token(self) -> Optional[str]:
        """获取或刷新访问令牌"""
        if self.access_token and self.token_expires_at and asyncio.get_event_loop().time() < self.token_expires_at:
            return self.access_token

        try:
            wallabag_url = self.config.get('wallabag_url', '').rstrip('/')
            client_id = self.config.get('client_id', '')
            client_secret = self.config.get('client_secret', '')
            username = self.config.get('username', '')
            password = self.config.get('password', '')

            if not all([wallabag_url, client_id, client_secret, username, password]):
                raise ValueError("Wallabag配置不完整，请检查配置")

            token_url = f"{wallabag_url}/oauth/v2/token"
            
            if self.refresh_token:
                # 尝试使用refresh_token刷新
                data = {
                    'grant_type': 'refresh_token',
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'refresh_token': self.refresh_token
                }
            else:
                # 使用密码获取新token
                data = {
                    'grant_type': 'password',
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'username': username,
                    'password': password
                }

            async with self.http_session.post(token_url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data['access_token']
                    self.refresh_token = token_data.get('refresh_token')
                    self.token_expires_at = asyncio.get_event_loop().time() + token_data.get('expires_in', 3600) - 60
                    return self.access_token
                else:
                    error_text = await response.text()
                    logger.error(f"获取访问令牌失败: {response.status} - {error_text}")
                    return None

        except Exception as e:
            logger.error(f"获取访问令牌异常: {e}")
            return None

    async def _save_to_wallabag(self, url: str) -> Optional[Dict]:
        """保存URL到Wallabag"""
        token = await self._get_access_token()
        if not token:
            raise Exception("无法获取访问令牌")

        wallabag_url = self.config.get('wallabag_url', '').rstrip('/')
        api_url = f"{wallabag_url}/api/entries.json"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        data = {
            'url': url
        }

        try:
            async with self.http_session.post(api_url, json=data, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"成功保存URL: {url}")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"保存URL失败: {response.status} - {error_text}")
                    raise Exception(f"保存失败: {response.status}")
        except Exception as e:
            logger.error(f"保存URL异常: {e}")
            raise

    