import re
import os
import json
import asyncio
import tempfile
import random
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

        # URL 缓存采用 FIFO：队列维护顺序，集合用于快速查找
        self._url_cache_queue: Deque[str] = deque()
        self._url_cache_set: Set[str] = set()

        # 串行化令牌刷新与缓存落盘，避免并发竞态
        self._token_lock = asyncio.Lock()
        self._cache_lock = asyncio.Lock()

        # URL 正则与清理配置（单一来源，避免重复匹配）
        self._url_pattern_core = r'https?://(?:[-\\w.]|(?:%[\\da-fA-F]{2}))+[/\\w\\.-]*\\??[/\\w\\.-=&%]*'
        # 非锚定：文本内提取
        self._url_in_text_regex = re.compile(self._url_pattern_core)
        # 锚定：格式校验
        self._url_validation_regex = re.compile(r'^' + self._url_pattern_core)
        # 可能黏在 URL 末尾的标点（ASCII + 常见全角标点，使用 Unicode 转义避免编码问题）
        self._trailing_punct = ",;:!?).\"'" + "\u3002\uFF0C\uFF1B\uFF1A\uFF01\uFF1F\uFF09\u3001\u300B\u300D\u201D\u2019"

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
        # 兜底保存缓存
        async with self._cache_lock:
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
        """保存缓存 URL（保持顺序，原子替换以降低损坏风险）"""
        cache_file = self.data_dir / "saved_urls.json"
        try:
            # 写入临时文件后原子替换，降低中断导致文件损坏的风险
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=str(self.data_dir), delete=False) as tf:
                json.dump(list(self._url_cache_queue), tf, ensure_ascii=False, indent=2)
                temp_name = tf.name
            os.replace(temp_name, cache_file)
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
            "- 自动保存消息中的 URL 至 Wallabag\n"
            "- 指令:\n"
            "  /wallabag help          显示此帮助\n"
            "  /wallabag save <URL>    手动保存指定 URL\n"
            "⚙️ 请在 WebUI 插件管理中完成配置\n"
        )
        yield event.plain_result(help_text)

    @wallabag_group.command("help")
    async def wallabag_help(self, event: AstrMessageEvent):
        """显示 Wallabag 插件帮助信息"""
        help_text = (
            "📚 Wallabag 插件\n"
            "- 自动保存消息中的 URL 至 Wallabag\n"
            "- 指令:\n"
            "  /wallabag help          显示此帮助\n"
            "  /wallabag save <URL>    手动保存指定 URL\n"
            "⚙️ 请在 WebUI 插件管理中完成配置\n"
        )
        yield event.plain_result(help_text)

    @wallabag_group.command("save")
    async def save_url(self, event: AstrMessageEvent, url: str):
        """手动保存 URL 到 Wallabag"""
        if not self._is_valid_url(url):
            yield event.plain_result("无效的 URL 格式")
            return

        try:
            result = await self._save_to_wallabag(url)
            if result:
                yield event.plain_result(
                    f"✅ 成功保存至 Wallabag\n📰 标题: {result.get('title', '未知')}\n⏱️ 阅读时间: {result.get('reading_time', 0)} 分钟"
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
        """监听所有消息，自动检测并保存 URL"""
        if not self.config.get('auto_save', True):
            return

        message_str = event.message_str.strip()
        # 简单跳过命令消息，避免与手动保存重复触发
        if message_str.startswith(('/wallabag', '/wb')):
            return

        urls = self._extract_urls(message_str)
        if not urls:
            return

        updated = False
        for url in urls:
            if self._cache_contains(url):
                continue
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

        # 仅在本条消息有新增 URL 时，统一落盘一次
        if updated:
            async with self._cache_lock:
                self._save_cache()

    def _extract_urls(self, text: str) -> List[str]:
        """从文本中提取 URL，去除尾随标点并去重（保持顺序）"""
        if not text:
            return []
        candidates = self._url_in_text_regex.findall(text)
        cleaned: List[str] = []
        seen: Set[str] = set()
        for raw in candidates:
            url = raw.rstrip(self._trailing_punct)
            if not url:
                continue
            if url not in seen:
                seen.add(url)
                cleaned.append(url)
        return cleaned

    def _is_valid_url(self, url: str) -> bool:
        """验证 URL 格式（用于手动保存等入口）"""
        if not url or not url.startswith(("http://", "https://")):
            return False
        return self._url_validation_regex.match(url) is not None

    async def _get_access_token(self) -> Optional[str]:
        """获取或刷新访问令牌"""
        now = asyncio.get_running_loop().time()
        if self.access_token and self.token_expires_at and now < self.token_expires_at:
            return self.access_token

        try:
            wallabag_url = self.config.get('wallabag_url', '').rstrip('/')
            # 发现常见误配路径时给出提示
            if 'index.php' in wallabag_url or wallabag_url.endswith('/app.php'):
                logger.warning("wallabag_url 包含 index.php/app.php，可能导致 API 路径错误，请仅填写站点根地址，例如 https://example.com")
            client_id = self.config.get('client_id', '')
            client_secret = self.config.get('client_secret', '')
            username = self.config.get('username', '')
            password = self.config.get('password', '')

            if not all([wallabag_url, client_id, client_secret, username, password]):
                raise ValueError("Wallabag 配置不完整，请检查参数")

            token_url = f"{wallabag_url}/oauth/v2/token"
            max_attempts = int(self._get_advanced('max_retry_attempts', 3))
            retry_delay = float(self._get_advanced('retry_delay', 2))
            jitter = float(self._get_advanced('retry_jitter', 0.5))

            async with self._token_lock:
                # 再次检查，避免在等待锁期间已被其他协程刷新
                now2 = asyncio.get_running_loop().time()
                if self.access_token and self.token_expires_at and now2 < self.token_expires_at:
                    return self.access_token

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
                        delay = retry_delay + random.uniform(0, jitter)
                        await asyncio.sleep(delay)
                return None

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"获取访问令牌网络异常: {e}")
            return None
        except (ValueError, KeyError, TypeError) as e:
            logger.error(f"获取访问令牌配置或解析错误: {e}")
            return None

    async def _save_to_wallabag(self, url: str) -> Optional[Dict]:
        """保存 URL 到 Wallabag"""
        token = await self._get_access_token()
        if not token:
            raise WallabagAuthError("无法获取访问令牌")

        wallabag_url = self.config.get('wallabag_url', '').rstrip('/')
        api_url = f"{wallabag_url}/api/entries.json"
        data = {'url': url}

        max_attempts = int(self._get_advanced('max_retry_attempts', 3))
        retry_delay = float(self._get_advanced('retry_delay', 2))
        jitter = float(self._get_advanced('retry_jitter', 0.5))

        for attempt in range(1, max_attempts + 1):
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json'
            }
            try:
                # 使用表单编码提交参数，兼容更多 wallabag 部署
                async with self.http_session.post(api_url, data=data, headers=headers) as response:
                    if response.status == 200:
                        try:
                            result = await response.json()
                        except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
                            logger.error(f"保存URL响应解析失败: {e}")
                            raise WallabagAPIError("响应解析失败", status=200)
                        # 语义校验：必须包含 id 或 url 等关键字段才判定为成功
                        if isinstance(result, dict) and ("id" in result or ("url" in result and result.get("url"))):
                            logger.info(f"成功保存URL: {url} (id={result.get('id')})")
                            return result
                        # 返回 200 但没有有效实体，视为失败以免误报成功
                        logger.error(f"保存URL返回内容异常，未包含有效实体: {result}")
                        raise WallabagAPIError("保存返回异常：无有效实体", status=200)
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
                delay = retry_delay + random.uniform(0, jitter)
                await asyncio.sleep(delay)

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
