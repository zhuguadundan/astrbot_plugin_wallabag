import re
import json
import asyncio
from typing import Optional, Dict, List, Deque, Set
from pathlib import Path
from collections import deque

import aiohttp
from aiohttp import ClientResponseError
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig


# ---- Plugin-specific exceptions ----
class WallabagError(Exception):
    """Base exception for Wallabag plugin errors."""


class WallabagConfigError(WallabagError):
    """Configuration is missing or invalid."""


class WallabagAuthError(WallabagError):
    """Authentication or token refresh failed."""


class WallabagAPIError(WallabagError):
    """Wallabag API error (non-2xx status or final failure)."""
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@register("wallabag", "AstrBot Developer", "自动监听URL并保存到Wallabag服务", "1.0.0")
class WallabagPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[float] = None
        # URL 缓存采用 FIFO：使用队列维护顺序，集合用于快速查重
        self._url_cache_queue: Deque[str] = deque()
        self._url_cache_set: Set[str] = set()

        # 确保数据目录存在
        try:
            self.data_dir = StarTools.get_data_dir()
        except (AttributeError, OSError, RuntimeError) as e:
            logger.warning(f"获取数据目录失败，使用默认路径 data/wallabag: {e}")
            self.data_dir = Path("data/wallabag")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 加载缓存（FIFO）
        self._load_cache()

    async def initialize(self):
        """插件初始化方法"""
        timeout = aiohttp.ClientTimeout(total=self.config.get('request_timeout', 30))
        user_agent = self._get_advanced('user_agent', 'AstrBot-Wallabag-Plugin/1.0.0')
        skip_ssl = self._get_advanced('skip_ssl_verify', False)
        connector = aiohttp.TCPConnector(ssl=False) if skip_ssl else None
        self.http_session = aiohttp.ClientSession(
            timeout=timeout,
            headers={'User-Agent': user_agent},
            connector=connector,
        )
        logger.info("Wallabag 插件初始化完成")

    async def terminate(self):
        """插件销毁方法"""
        if self.http_session:
            await self.http_session.close()
            self.http_session = None
        self._save_cache()
        logger.info("Wallabag 插件已停止")

    def _load_cache(self):
        """加载缓存的 URL（保持插入顺序，超出时按 FIFO 淘汰）"""
        cache_file = self.data_dir / "saved_urls.json"
        self._url_cache_queue.clear()
        self._url_cache_set.clear()
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    max_size = int(self.config.get('cache_max_size', 1000))
                    for url in data[-max_size:]:
                        if isinstance(url, str) and url not in self._url_cache_set:
                            self._url_cache_queue.append(url)
                            self._url_cache_set.add(url)
                logger.info(f"已加载 {len(self._url_cache_set)} 个缓存的 URL")
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"加载缓存失败: {e}")
                self._url_cache_queue.clear()
                self._url_cache_set.clear()

    def _save_cache(self):
        """保存缓存的 URL（保持顺序）"""
        cache_file = self.data_dir / "saved_urls.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(list(self._url_cache_queue), f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"保存缓存失败: {e}")

    def _cache_contains(self, url: str) -> bool:
        return url in self._url_cache_set

    def _cache_add(self, url: str):
        if url in self._url_cache_set:
            return
        self._url_cache_queue.append(url)
        self._url_cache_set.add(url)
        max_size = int(self.config.get('cache_max_size', 1000))
        while len(self._url_cache_queue) > max_size:
            try:
                old = self._url_cache_queue.popleft()
                self._url_cache_set.discard(old)
            except IndexError:
                break

    @filter.command_group("wallabag")
    def wallabag_group(self):
        """Wallabag 指令组"""
        pass

    @filter.command("wb")
    async def wb(self, event: AstrMessageEvent):
        """wb 别名命令，显示帮助"""
        help_text = (
            "📚 Wallabag 插件\n"
            "- 自动保存消息中的 URL 到 Wallabag\n"
            "- 指令:\n"
            "  /wallabag help          显示此帮助\n"
            "  /wallabag save <URL>    手动保存指定 URL\n"
            "⚙️ 请在 WebUI 插件管理中完成配置"
        )
        yield event.plain_result(help_text)

    @wallabag_group.command("help")
    async def wallabag_help(self, event: AstrMessageEvent):
        """显示 Wallabag 插件帮助信息"""
        help_text = (
            "📚 Wallabag 插件\n"
            "- 自动保存消息中的 URL 到 Wallabag\n"
            "- 指令:\n"
            "  /wallabag help          显示此帮助\n"
            "  /wallabag save <URL>    手动保存指定 URL\n"
            "⚙️ 请在 WebUI 插件管理中完成配置"
        )
        yield event.plain_result(help_text)

    @wallabag_group.command("save")
    async def save_url(self, event: AstrMessageEvent, url: str):
        """手动保存URL到Wallabag"""
        if not self._is_valid_url(url):
            yield event.plain_result("无效的 URL 格式")
            return

        try:
            result = await self._save_to_wallabag(url)
            if result:
                yield event.plain_result(
                    f"✅ 成功保存到 Wallabag\n📰 标题: {result.get('title', '未知')}\n⏱️ 阅读时间: {result.get('reading_time', 0)} 分钟"
                )
            else:
                yield event.plain_result("保存失败，请检查配置与 URL")
        except (aiohttp.ClientError, asyncio.TimeoutError, ClientResponseError) as e:
            logger.error(f"手动保存URL失败: {e}")
            yield event.plain_result(f"保存失败: {str(e)}")
        except WallabagAuthError as e:
            logger.error(f"手动保存URL认证失败: {e}")
            yield event.plain_result("保存失败：认证失败，请检查凭据或重试")
        except WallabagAPIError as e:
            logger.error(f"手动保存URL API 错误: {e}")
            yield event.plain_result("保存失败：服务端返回错误")
        except Exception as e:
            # 最后一层兜底，避免影响插件稳定性
            logger.exception(f"手动保存URL发生未知异常: {e}")
            yield event.plain_result("保存失败：发生未知错误")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，自动检测并保存URL"""
        if not self.config.get('auto_save', True):
            return

        message_str = event.message_str.strip()
        urls = self._extract_urls(message_str)

        if urls:
            updated = False
            for url in urls:
                if not self._cache_contains(url):
                    try:
                        result = await self._save_to_wallabag(url)
                        if result:
                            self._cache_add(url)
                            updated = True
                            title = result.get('title', '未知')[:50]
                            await event.send(event.plain_result(f"📎 自动保存: {title}..."))
                    except (aiohttp.ClientError, asyncio.TimeoutError, ClientResponseError) as e:
                        logger.error(f"自动保存URL失败: {e}")
                    except (WallabagAuthError, WallabagAPIError) as e:
                        logger.error(f"自动保存URL插件错误: {e}")
                    except Exception as e:
                        logger.exception(f"自动保存URL发生未知异常: {e}")

            if updated:
                self._save_cache()

    def _extract_urls(self, text: str) -> List[str]:
        """从文本中提取URL"""
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*\??[/\w\.-=&%]*'
        urls = re.findall(url_pattern, text)
        # 依赖一次性提取结果即可，避免二次正则验证的重复开销
        return urls

    def _is_valid_url(self, url: str) -> bool:
        """验证URL格式"""
        if not url or not url.startswith(('http://', 'https://')):
            return False

        # 基本URL格式验证
        url_pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*\??[/\w\.-=&%]*'
        return re.match(url_pattern, url) is not None

    async def _get_access_token(self) -> Optional[str]:
        """获取或刷新访问令牌"""
        now = asyncio.get_running_loop().time()
        if self.access_token and self.token_expires_at and now < self.token_expires_at:
            return self.access_token

        try:
            wallabag_url = self.config.get('wallabag_url', '').rstrip('/')
            client_id = self.config.get('client_id', '')
            client_secret = self.config.get('client_secret', '')
            username = self.config.get('username', '')
            password = self.config.get('password', '')

            if not all([wallabag_url, client_id, client_secret, username, password]):
                raise ValueError("Wallabag 配置不完整，请检查参数")

            token_url = f"{wallabag_url}/oauth/v2/token"
            max_attempts = int(self._get_advanced('max_retry_attempts', 3))
            retry_delay = float(self._get_advanced('retry_delay', 2))

            for attempt in range(1, max_attempts + 1):
                if self.refresh_token:
                    data = {
                        'grant_type': 'refresh_token',
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'refresh_token': self.refresh_token
                    }
                else:
                    data = {
                        'grant_type': 'password',
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'username': username,
                        'password': password
                    }

                try:
                    async with self.http_session.post(token_url, data=data) as response:
                        if response.status == 200:
                            token_data = await response.json()
                            self.access_token = token_data['access_token']
                            self.refresh_token = token_data.get('refresh_token')
                            buffer = float(self._get_advanced('token_refresh_buffer', 60))
                            expires_in = float(token_data.get('expires_in', 3600))
                            effective = max(10.0, expires_in - buffer)
                            self.token_expires_at = asyncio.get_running_loop().time() + effective
                            return self.access_token
                        else:
                            error_text = await response.text()
                            logger.error(f"获取访问令牌失败: {response.status} - {error_text}")
                except (aiohttp.ClientError, asyncio.TimeoutError, ClientResponseError, json.JSONDecodeError) as e:
                    logger.error(f"获取访问令牌异常 (尝试 {attempt}/{max_attempts}): {e}")

                if attempt < max_attempts:
                    await asyncio.sleep(retry_delay)
            return None

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"获取访问令牌网络异常: {e}")
            return None
        except (ValueError, KeyError, TypeError) as e:
            logger.error(f"获取访问令牌配置或解析错误: {e}")
            return None

    async def _save_to_wallabag(self, url: str) -> Optional[Dict]:
        """保存URL到Wallabag"""
        token = await self._get_access_token()
        if not token:
            raise WallabagAuthError("无法获取访问令牌")

        wallabag_url = self.config.get('wallabag_url', '').rstrip('/')
        api_url = f"{wallabag_url}/api/entries.json"
        data = {'url': url}

        max_attempts = int(self._get_advanced('max_retry_attempts', 3))
        retry_delay = float(self._get_advanced('retry_delay', 2))

        for attempt in range(1, max_attempts + 1):
            # 使用表单编码更兼容（不要显式设置 JSON Content-Type）
            headers = {
                'Authorization': f'Bearer {token}',
            }
            try:
                async with self.http_session.post(api_url, data=data, headers=headers) as response:
                    if response.status == 200:
                        try:
                            result = await response.json()
                        except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
                            logger.error(f"保存URL响应解析失败: {e}")
                            raise WallabagAPIError("响应解析失败", status=200)
                        # 仅当响应包含 id 或有效 url 字段时才视为成功，避免假阳性
                        if isinstance(result, dict) and ("id" in result or ("url" in result and result.get("url"))):
                            logger.info(f"成功保存URL: {url}")
                            return result
                        logger.error(f"保存URL返回内容异常，未包含有效实体: {result}")
                        return None
                    elif response.status == 401:
                        # 令牌过期，刷新一次并重试
                        logger.warning("访问被拒绝(401)，尝试刷新令牌后重试")
                        self.access_token = None
                        token = await self._get_access_token()
                        if not token:
                            raise WallabagAuthError("刷新令牌失败")
                        continue
                    elif 500 <= response.status < 600:
                        error_text = await response.text()
                        logger.error(f"服务端错误: {response.status} - {error_text}")
                        # 5xx 进行重试
                    else:
                        error_text = await response.text()
                        logger.error(f"保存URL失败: {response.status} - {error_text}")
                        raise WallabagAPIError(f"保存失败: {response.status}", status=response.status)
            except (aiohttp.ClientError, asyncio.TimeoutError, ClientResponseError) as e:
                logger.error(f"保存URL异常 (尝试 {attempt}/{max_attempts}): {e}")

            if attempt < max_attempts:
                await asyncio.sleep(retry_delay)

        raise WallabagAPIError("保存失败：已达最大重试次数")

    def _get_advanced(self, key: str, default=None):
        try:
            adv = self.config.get('advanced_settings', {})
            if not isinstance(adv, dict):
                logger.warning("高级设置 (advanced_settings) 格式不正确，应为字典")
                return default
            return adv.get(key, default)
        except Exception as e:
            # 兜底日志，避免静默失败
            logger.exception(f"获取高级设置 '{key}' 时发生未知错误: {e}")
            return default
