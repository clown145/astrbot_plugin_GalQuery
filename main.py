import json
import asyncio
import re
import html as html_lib
import hashlib
import os
import shutil
import tempfile
import aiohttp
from typing import List, Dict, Optional

# AstrBot 核心 API 导入
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.session_waiter import session_waiter, SessionController


@register("touchgal_search", "AI Assistant", "从 TouchGal 搜索游戏资源", "1.0.17")
class TouchGalPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.session_timeout = self.config.get("session_timeout", 60)
        self.domain = self.config.get("touchgal_domain", "www.touchgal.top")
        self.shionlib_domain = self.config.get("shionlib_domain", "shionlib.com")
        self.shionlib_image_domain = self._normalize_domain_config(
            self.config.get("shionlib_image_domain", "t.shionlib.com"),
            "t.shionlib.com",
        )
        self.shionlib_enabled = self.config.get("shionlib_enabled", True)
        self.shionlib_limit = self.config.get("shionlib_limit", 3)
        self.touchgal_resource_limit_per_game = (
            self._normalize_touchgal_resource_limit(
                self.config.get("touchgal_resource_limit_per_game", 3)
            )
        )
        self.active_sessions: Dict[str, SessionController] = {}

        # 初始化通用请求头
        self.headers = self._create_headers()

        # 群聊过滤配置
        self.group_mode = self.config.get("auto_search_group_mode", "blacklist")
        self.group_list = self.config.get("auto_search_group_list", [])

        # 初始化日志
        auto_search = self.config.get("auto_search_enabled", False)
        logger.info(
            f"TouchGal 插件已加载 | 自动搜索: {'已启用' if auto_search else '未启用'} | TouchGal: {self.domain} | Shionlib: {self.shionlib_domain}"
        )

    def _normalize_domain_config(self, value: object, default: str) -> str:
        """标准化配置中的域名，允许用户填写带协议的完整域名。"""
        domain = str(value or default).strip()
        domain = re.sub(r"^https?://", "", domain).strip("/")
        return domain or default

    def _normalize_touchgal_resource_limit(self, value: object) -> int:
        """标准化每个 TouchGal 游戏展示的资源数量，-1 表示全部。"""
        try:
            limit = int(value)
        except (TypeError, ValueError):
            return 3
        if limit == -1:
            return -1
        if limit < -1:
            return 3
        return limit

    def _create_headers(self) -> dict:
        """创建通用请求头"""
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "content-type": "text/plain;charset=UTF-8",
            "origin": f"https://{self.domain}",
            "priority": "u=1, i",
            "referer": f"https://{self.domain}/search",
            "x-requested-with": "kun-fetch",
            "sec-ch-ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        }

        # 如果开启 NSFW 内容显示，添加对应的 cookie
        if self.config.get("show_nsfw", False):
            headers["cookie"] = "kun-patch-setting-store|state|data|kunNsfwEnable=all"
            logger.info("TouchGal 插件已开启 NSFW 内容显示。")

        return headers

    async def search_games_async(
        self, keyword: str, page: int = 1, limit: int = 10
    ) -> List[dict]:
        """异步执行搜索游戏的网络请求（使用 aiohttp）"""
        search_url = f"https://{self.domain}/api/search"
        query_list = [{"type": "keyword", "mode": "include", "name": keyword}]
        query_string = json.dumps(query_list)
        payload = {
            "queryString": query_string,
            "limit": limit,
            "page": page,
            "searchOption": {
                "searchInIntroduction": False,
                "searchInAlias": True,
                "searchInTag": False,
            },
            "selectedType": "all",
            "selectedLanguage": "all",
            "selectedPlatform": "all",
            "sortField": "resource_update_time",
            "sortOrder": "desc",
            "selectedYears": ["all"],
            "selectedMonths": ["all"],
            "minRatingCount": 0,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    search_url,
                    data=json.dumps(payload),
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            f"TouchGal search failed with status: {response.status}"
                        )
                        return []
                    search_results = await response.json()
                    return (
                        search_results.get("galgames", [])
                        if isinstance(search_results, dict)
                        else []
                    )
        except asyncio.TimeoutError:
            logger.error("TouchGal search timeout")
            return []
        except Exception as e:
            logger.error(f"TouchGal search failed: {e}")
            return []

    async def get_links_async(self, game_info: dict) -> List[dict]:
        """异步获取下载链接（使用 aiohttp）"""
        patch_id = game_info.get("id")
        unique_id = game_info.get("uniqueId") or game_info.get("unique_id")
        if not patch_id or not unique_id:
            return []

        resource_url = f"https://{self.domain}/api/patch/resource?patchId={patch_id}"
        headers = self.headers.copy()
        headers["referer"] = f"https://{self.domain}/{unique_id}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    resource_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            f"TouchGal get links failed with status: {response.status}"
                        )
                        return []
                    return self._normalize_touchgal_resources(await response.json())
        except asyncio.TimeoutError:
            logger.error("TouchGal get links timeout")
            return []
        except Exception as e:
            logger.error(f"TouchGal get links failed: {e}")
            return []

    def _normalize_touchgal_resources(self, payload: object) -> List[dict]:
        """兼容 TouchGal 新旧资源接口，统一整理成插件原本使用的结构。"""
        if not isinstance(payload, list):
            return []

        resources = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            if "content" in item:
                resources.append(item)
                continue

            resource_name = (item.get("name") or "未知").strip()
            resource_note = (item.get("note") or "").strip()
            links = item.get("links")
            if not isinstance(links, list):
                continue

            for link in links:
                if not isinstance(link, dict):
                    continue

                content = (link.get("content") or "").strip()
                if not content:
                    continue

                link_name = resource_name
                size = (link.get("size") or "").strip()
                if size:
                    link_name = f"{resource_name} [{size}]"

                resources.append(
                    {
                        "name": link_name,
                        "content": content,
                        "password": (link.get("password") or "").strip(),
                        "code": (link.get("code") or "").strip(),
                        "note": resource_note,
                    }
                )

        return resources

    def _decode_json_string(self, value: str) -> str:
        """解码 Next.js 脚本中的 JSON 字符串片段。"""
        try:
            return json.loads(f'"{value}"')
        except json.JSONDecodeError:
            return value

    def _strip_html_tags(self, value: str) -> str:
        """移除标题中的高亮标签并反转义 HTML 实体。"""
        text = re.sub(r"<[^>]+>", "", value)
        return html_lib.unescape(text).strip()

    def _extract_shionlib_name_from_chunk(self, chunk: str) -> Optional[str]:
        """从单个 Next.js 数据块中提取游戏标题。"""
        alt_matches = re.findall(r'"alt":"((?:\\.|[^"\\])*)"', chunk)
        for raw_alt in reversed(alt_matches):
            alt = self._strip_html_tags(self._decode_json_string(raw_alt))
            if alt:
                return alt

        html_matches = re.findall(
            r'"dangerouslySetInnerHTML":\{"__html":"((?:\\.|[^"\\])*)"\}',
            chunk,
        )
        for raw_html in html_matches:
            title = self._strip_html_tags(self._decode_json_string(raw_html))
            if title:
                return title

        return None

    def _extract_shionlib_cover_from_chunk(self, chunk: str) -> Optional[str]:
        """从单个 Next.js 数据块中提取封面图链接。"""
        src_matches = re.findall(r'"src":"((?:\\.|[^"\\])*)"', chunk)
        for raw_src in src_matches:
            src = self._decode_json_string(raw_src).strip()
            if not src or "/cover/" not in src:
                continue

            if src.startswith("http://") or src.startswith("https://"):
                return src.replace(
                    f"https://{self.shionlib_domain}/game/",
                    f"https://{self.shionlib_image_domain}/game/",
                    1,
                )
            if src.lstrip("/").startswith("game/"):
                return f"https://{self.shionlib_image_domain}/{src.lstrip('/')}"
            return f"https://{self.shionlib_domain}/{src.lstrip('/')}"

        return None

    def _parse_shionlib_games(self, html: str, limit: int) -> List[dict]:
        """解析 Shionlib 当前 Next.js 搜索页中的游戏数据。"""
        games = []
        seen_ids = set()

        script_pattern = re.compile(
            r'<script>self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>',
            re.S,
        )

        for raw_chunk in script_pattern.findall(html):
            if "/zh/game/" not in raw_chunk:
                continue

            chunk = self._decode_json_string(raw_chunk)
            href_match = re.search(r'"href":"(/zh/game/(\d+))"', chunk)
            if not href_match:
                continue

            href, game_id = href_match.groups()
            if game_id in seen_ids:
                continue

            game_name = self._extract_shionlib_name_from_chunk(chunk)
            if not game_name:
                game_name = f"游戏 #{game_id}"
            cover_url = self._extract_shionlib_cover_from_chunk(chunk)

            games.append(
                {
                    "id": game_id,
                    "name": game_name,
                    "url": f"https://{self.shionlib_domain}{href}",
                    "cover": cover_url,
                }
            )
            seen_ids.add(game_id)

            if len(games) >= limit:
                break

        if games:
            return games

        fallback_pattern = re.compile(
            r'<a[^>]*href="(/zh/game/(\d+))"[^>]*>(.*?)</a>',
            re.S,
        )
        for href, game_id, content in fallback_pattern.findall(html):
            if game_id in seen_ids:
                continue

            game_name = self._strip_html_tags(content)
            if not game_name:
                continue

            games.append(
                {
                    "id": game_id,
                    "name": game_name,
                    "url": f"https://{self.shionlib_domain}{href}",
                    "cover": None,
                }
            )
            seen_ids.add(game_id)

            if len(games) >= limit:
                break

        return games

    async def search_shionlib_async(self, keyword: str, limit: int = 5) -> List[dict]:
        """
        异步搜索 Shionlib 资源站，返回游戏列表。

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制

        Returns:
            游戏列表 [{'id': '708', 'name': '千恋万花', 'url': 'https://shionlib.com/zh/game/708', 'cover': 'https://...'}, ...]
        """
        search_url = f"https://{self.shionlib_domain}/zh/search/game"
        params = {"q": keyword}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    search_url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            f"Shionlib 搜索请求失败，状态码: {response.status}"
                        )
                        return []

                    html = await response.text()
                    games = self._parse_shionlib_games(html, limit)

                    if not games:
                        logger.debug(f"Shionlib 未找到游戏结果: {keyword}")
                        return []

                    logger.debug(f"Shionlib 搜索到 {len(games)} 个结果: {keyword}")
                    return games

        except asyncio.TimeoutError:
            logger.warning(f"Shionlib 搜索超时: {keyword}")
            return []
        except Exception as e:
            logger.error(f"Shionlib 搜索异常: {e}")
            return []

    def _build_touchgal_game_url(self, game: dict) -> str:
        """构建 TouchGal 游戏详情页链接。"""
        unique_id = game.get("uniqueId") or game.get("unique_id") or ""
        return f"https://{self.domain}/{unique_id}" if unique_id else ""

    def _normalize_touchgal_image_url(self, value: object) -> Optional[str]:
        """标准化 TouchGal 图片链接。"""
        if not isinstance(value, str):
            return None

        image_url = html_lib.unescape(value).strip().strip('"').strip("'")
        if not image_url:
            return None

        if image_url.startswith("//"):
            image_url = f"https:{image_url}"
        elif image_url.startswith("/"):
            image_url = f"https://{self.domain}{image_url}"

        if not image_url.startswith(("http://", "https://")):
            return None

        lowered = image_url.lower().split("?", 1)[0]
        if lowered.endswith((".mp4", ".webm", ".mkv", ".avi", ".mov")):
            return None

        return image_url

    def _get_touchgal_image_url(self, game: Optional[dict]) -> Optional[str]:
        """从 TouchGal 游戏数据中提取封面/横幅图链接。"""
        if not isinstance(game, dict):
            return None

        for key in (
            "banner",
            "cover",
            "coverUrl",
            "cover_url",
            "image",
            "imageUrl",
            "image_url",
            "thumbnail",
            "poster",
        ):
            image_url = self._normalize_touchgal_image_url(game.get(key))
            if image_url:
                return image_url

        for key in ("images", "screenshots", "previews"):
            values = game.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict):
                    for item_key in ("url", "src", "image", "imageUrl"):
                        image_url = self._normalize_touchgal_image_url(
                            item.get(item_key)
                        )
                        if image_url:
                            return image_url
                else:
                    image_url = self._normalize_touchgal_image_url(item)
                    if image_url:
                        return image_url

        return None

    async def _fetch_touchgal_detail_image_async(self, game: dict) -> Optional[str]:
        """从 TouchGal 详情页兜底提取公开图片链接。"""
        game_url = self._build_touchgal_game_url(game)
        if not game_url:
            return None

        headers = self.headers.copy()
        headers.update(
            {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "content-type": "",
                "referer": f"https://{self.domain}/search",
            }
        )
        headers = {key: value for key, value in headers.items() if value}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    game_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        logger.debug(
                            f"TouchGal detail image fetch failed with status: {response.status}"
                        )
                        return None
                    html = await response.text()
        except asyncio.TimeoutError:
            logger.debug("TouchGal detail image fetch timeout")
            return None
        except Exception as e:
            logger.debug(f"TouchGal detail image fetch failed: {e}")
            return None

        patterns = (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'"banner":"((?:\\.|[^"\\])*)"',
            r'<img[^>]+src=["\']([^"\']+)["\']',
        )
        for pattern in patterns:
            for raw_url in re.findall(pattern, html):
                if "\\/" in raw_url or '\\"' in raw_url:
                    raw_url = self._decode_json_string(raw_url)
                image_url = self._normalize_touchgal_image_url(raw_url)
                if image_url and "touchgaloss.com" in image_url:
                    game["banner"] = image_url
                    return image_url

        return None

    async def _ensure_touchgal_image_url_async(
        self, game: Optional[dict]
    ) -> Optional[str]:
        """优先使用搜索接口图片，缺失时从详情页补齐。"""
        image_url = self._get_touchgal_image_url(game)
        if image_url or not isinstance(game, dict):
            return image_url
        return await self._fetch_touchgal_detail_image_async(game)

    def _get_touchgal_image_cache_dir(self) -> str:
        """返回 TouchGal 图片缓存目录。"""
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

            base_dir = get_astrbot_temp_path()
        except Exception:
            base_dir = tempfile.gettempdir()

        cache_dir = os.path.join(base_dir, "astrbot_plugin_galquery")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _image_request_headers(self, referer: str = "") -> dict:
        """构建下载 TouchGal 图片时使用的浏览器请求头。"""
        headers = {
            "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9",
            "user-agent": self.headers.get(
                "user-agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            ),
        }
        headers["referer"] = referer or f"https://{self.domain}/"
        return headers

    def _detect_image_kind(
        self, image_url: str, content_type: str, data: bytes
    ) -> Optional[str]:
        """根据内容特征判断图片格式。"""
        if data.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            return "gif"
        if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "webp"
        if len(data) > 12 and data[4:8] == b"ftyp" and b"avif" in data[8:16]:
            return "avif"

        lowered_type = content_type.lower()
        for kind in ("jpeg", "jpg", "png", "gif", "webp", "avif"):
            if kind in lowered_type:
                return "jpg" if kind == "jpeg" else kind

        lowered_url = image_url.lower().split("?", 1)[0]
        for kind in ("jpg", "jpeg", "png", "gif", "webp", "avif"):
            if lowered_url.endswith(f".{kind}"):
                return "jpg" if kind == "jpeg" else kind

        return None

    def _convert_image_with_pillow_sync(self, source_path: str, output_path: str) -> bool:
        """用 Pillow 将图片转为 QQ 更稳定的 JPEG。"""
        try:
            from PIL import Image as PillowImage
        except Exception:
            return False

        try:
            with PillowImage.open(source_path) as image:
                image.thumbnail((1280, 1280))
                if image.mode in ("RGBA", "LA"):
                    background = PillowImage.new("RGB", image.size, (255, 255, 255))
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                elif image.mode != "RGB":
                    image = image.convert("RGB")
                image.save(output_path, "JPEG", quality=88, optimize=True)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.debug(f"TouchGal image Pillow conversion failed: {e}")
            return False

    async def _convert_avif_with_decoder(
        self, source_path: str, output_path: str
    ) -> bool:
        """用系统 avifdec 兜底转换 AVIF。"""
        decoder = shutil.which("avifdec")
        if not decoder:
            return False

        try:
            process = await asyncio.create_subprocess_exec(
                decoder,
                source_path,
                output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(process.communicate(), timeout=20)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return False

            return (
                process.returncode == 0
                and os.path.exists(output_path)
                and os.path.getsize(output_path) > 0
            )
        except Exception as e:
            logger.debug(f"TouchGal image avifdec conversion failed: {e}")
            return False

    async def _prepare_touchgal_image_file(
        self, image_url: str, referer: str = ""
    ) -> Optional[str]:
        """下载并在必要时转换 TouchGal 图片，返回可发送的本地文件。"""
        if not image_url:
            return None

        cache_dir = self._get_touchgal_image_cache_dir()
        cache_key = hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:24]
        cached_jpg = os.path.join(cache_dir, f"touchgal_{cache_key}.jpg")
        cached_png = os.path.join(cache_dir, f"touchgal_{cache_key}.png")

        for cached_path in (cached_jpg, cached_png):
            if os.path.exists(cached_path) and os.path.getsize(cached_path) > 0:
                return cached_path

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    image_url,
                    headers=self._image_request_headers(referer),
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    data = await response.read()
                    if response.status != 200 or not data:
                        logger.debug(
                            f"TouchGal image download failed with status: {response.status}"
                        )
                        return None
                    content_type = response.headers.get("content-type", "")
        except asyncio.TimeoutError:
            logger.debug("TouchGal image download timeout")
            return None
        except Exception as e:
            logger.debug(f"TouchGal image download failed: {e}")
            return None

        if data.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            logger.debug("TouchGal image download returned HTML instead of image")
            return None

        image_kind = self._detect_image_kind(image_url, content_type, data)
        if image_kind in ("jpg", "png", "gif"):
            output_path = os.path.join(cache_dir, f"touchgal_{cache_key}.{image_kind}")
            with open(output_path, "wb") as file:
                file.write(data)
            return output_path

        raw_ext = image_kind or "img"
        raw_path = os.path.join(cache_dir, f"touchgal_{cache_key}.{raw_ext}")
        with open(raw_path, "wb") as file:
            file.write(data)

        if await asyncio.to_thread(
            self._convert_image_with_pillow_sync, raw_path, cached_jpg
        ):
            return cached_jpg

        if image_kind == "avif" and await self._convert_avif_with_decoder(
            raw_path, cached_png
        ):
            return cached_png

        logger.debug(f"TouchGal image cannot be converted: {image_url}")
        return None

    async def _append_touchgal_image_component(
        self,
        content: list,
        game: Optional[dict],
        Image,
        Plain,
    ) -> None:
        """向合并转发节点追加 TouchGal 图片，失败时追加图片链接。"""
        image_url = await self._ensure_touchgal_image_url_async(game)
        if not image_url:
            return

        referer = self._build_touchgal_game_url(game) if isinstance(game, dict) else ""
        image_path = await self._prepare_touchgal_image_file(image_url, referer)
        if image_path:
            content.append(Image.fromFileSystem(image_path))
            content.append(Plain("\n"))
            return

        content.append(Plain(f"🖼 {image_url}\n\n"))

    async def _build_touchgal_groups_async(
        self, games: List[dict]
    ) -> List[dict]:
        """为 TouchGal 搜索结果整理按游戏分组的资源数据。"""
        valid_games = [game for game in games if isinstance(game, dict)]
        if not valid_games:
            return []

        resource_results = await asyncio.gather(
            *(self.get_links_async(game) for game in valid_games),
            return_exceptions=True,
        )

        groups = []
        for game, resources in zip(valid_games, resource_results):
            if isinstance(resources, Exception):
                logger.warning(f"TouchGal get grouped resources failed: {resources}")
                resources = []
            if self.touchgal_resource_limit_per_game != -1:
                resources = resources[: self.touchgal_resource_limit_per_game]

            groups.append(
                {
                    "game": game,
                    "resources": resources,
                }
            )

        return groups

    async def _search_resources_for_agent(self, keyword: str) -> str:
        """执行一次非交互式搜索，供 Agent 工具调用。"""
        keyword = str(keyword or "").strip()
        if not keyword:
            return "搜索关键词不能为空。"

        games = await self.search_games_async(keyword, page=1, limit=5)
        shionlib_games = []
        if self.shionlib_enabled:
            shionlib_games = await self.search_shionlib_async(
                keyword,
                limit=self.shionlib_limit,
            )

        if not games and not shionlib_games:
            return f"没有找到与「{keyword}」相关的游戏资源。"

        resources = []
        selected_game = games[0] if games else None
        if selected_game:
            resources = await self.get_links_async(selected_game)

        game_name = selected_game.get("name", keyword) if selected_game else keyword
        touchgal_suggestions = games if len(games) > 1 else None
        message = self._build_single_message(
            game_name,
            resources,
            shionlib_games,
            touchgal_suggestions,
            selected_game,
        )

        if selected_game and not resources:
            touchgal_url = self._build_touchgal_game_url(selected_game)
            lines = [
                f"TouchGal 找到「{game_name}」，但未获取到资源链接。",
            ]
            if touchgal_url:
                lines.append(f"游戏页面: {touchgal_url}")
            if message:
                lines.extend(["", message])
            return "\n".join(lines).strip()

        return message or f"找到与「{keyword}」相关的结果，但没有可展示的资源链接。"

    @filter.llm_tool(name="search_galgame_resources")
    async def search_galgame_resources_tool(
        self,
        event: AstrMessageEvent,
        keyword: str,
    ) -> str:
        """搜索 Galgame 资源链接，优先返回 TouchGal 资源，并附带书音的图书馆推荐。

        Args:
            keyword(string): 要搜索的游戏名称或关键词。
        """
        return await self._search_resources_for_agent(keyword)

    @filter.command("搜索")
    async def search_command(self, event: AstrMessageEvent, keyword: str):
        """
        搜索 TouchGal 上的游戏资源。

        用法:
            /搜索 <游戏名称>
        """
        session_id = event.unified_msg_origin
        if session_id in self.active_sessions:
            try:
                self.active_sessions[session_id].stop()
            except Exception as e:
                logger.warning(f"Error stopping previous session for {session_id}: {e}")
            finally:
                del self.active_sessions[session_id]

        session_state = {"page": 1, "current_games": [], "keyword": keyword}

        yield event.plain_result(f"正在为 '{keyword}' 搜索，请稍候...")

        @session_waiter(timeout=self.session_timeout)
        async def search_session_waiter(
            controller: SessionController, event: AstrMessageEvent
        ):
            self.active_sessions[session_id] = controller
            user_input = event.message_str.strip()

            if user_input.startswith("搜索 "):
                new_keyword = user_input[len("搜索 ") :].strip()
                if new_keyword:
                    await event.send(
                        event.plain_result(
                            f"好的，正在切换到新任务，搜索 '{new_keyword}'..."
                        )
                    )

                    session_state["keyword"] = new_keyword
                    session_state["page"] = 1

                    new_games = await self.search_games_async(
                        session_state["keyword"], page=session_state["page"]
                    )
                    if not new_games:
                        await event.send(
                            event.plain_result(
                                f"没有找到与 '{new_keyword}' 相关的游戏。"
                            )
                        )
                    else:
                        session_state["current_games"] = new_games
                        response_text = "--- 请选择 ---\n"
                        for idx, game in enumerate(new_games):
                            response_text += f"  {idx + 1}. {game.get('name')}\n"
                        response_text += "-------\n请输入序号选择，'p' 下一页，'q' 上一页，'e' 退出搜索。\n提示：在退出前，您无法与机器人进行普通对话。"
                        await event.send(event.plain_result(response_text))

                    controller.keep(timeout=self.session_timeout, reset_timeout=True)
                    return

            user_input_lower = user_input.lower()

            if user_input_lower in ["p", "q"]:
                if user_input_lower == "p":
                    session_state["page"] += 1
                elif user_input_lower == "q":
                    if session_state["page"] > 1:
                        session_state["page"] -= 1
                    else:
                        await event.send(event.plain_result("已经是第一页了。"))
                        controller.keep(
                            timeout=self.session_timeout, reset_timeout=True
                        )
                        return

                await event.send(
                    event.plain_result(f"正在获取第 {session_state['page']} 页...")
                )

                new_games = await self.search_games_async(
                    session_state["keyword"], page=session_state["page"]
                )
                if not new_games:
                    await event.send(event.plain_result("没有更多结果了。"))
                    session_state["page"] -= 1
                else:
                    session_state["current_games"] = new_games
                    response_text = "--- 请选择 ---\n"
                    for idx, game in enumerate(new_games):
                        response_text += f"  {idx + 1}. {game.get('name')}\n"
                    response_text += "-------\n请输入序号选择，'p' 下一页，'q' 上一页，'e' 退出搜索。\n提示：在退出前，您无法与机器人进行普通对话。"
                    await event.send(event.plain_result(response_text))

                controller.keep(timeout=self.session_timeout, reset_timeout=True)

            elif user_input_lower == "e":
                await event.send(
                    event.plain_result("已退出搜索会话。现在您可以正常与我对话了。")
                )
                controller.stop()  # 停止会话
                return  # 立即返回

            elif user_input_lower.isdigit():
                try:
                    choice_idx = int(user_input_lower) - 1
                    if 0 <= choice_idx < len(session_state["current_games"]):
                        selected_game = session_state["current_games"][choice_idx]
                        await event.send(
                            event.plain_result(
                                f"已选择: {selected_game.get('name')}\n正在获取资源链接..."
                            )
                        )

                        resources = await self.get_links_async(selected_game)
                        if not resources:
                            await event.send(
                                event.plain_result("未能获取到该游戏的资源链接。")
                            )
                        else:
                            # 并行搜索 Shionlib
                            shionlib_games = []
                            if self.shionlib_enabled:
                                shionlib_games = await self.search_shionlib_async(
                                    selected_game.get("name", ""),
                                    limit=self.shionlib_limit,
                                )

                            # 智能选择发送方式
                            if self._is_forward_supported(event):
                                # QQ 平台：使用合并转发消息
                                bot_uin = event.get_self_id()
                                nodes = await self._build_forward_nodes(
                                    selected_game.get("name", "未知游戏"),
                                    resources,
                                    bot_uin,
                                    shionlib_games,
                                    touchgal_game=selected_game,
                                )
                                await event.send(event.chain_result(nodes))
                            else:
                                # 其他平台：发送单条消息
                                message_text = self._build_single_message(
                                    selected_game.get("name", "未知游戏"),
                                    resources,
                                    shionlib_games,
                                    touchgal_game=selected_game,
                                )
                                await event.send(event.plain_result(message_text))

                        controller.stop()
                    else:
                        await event.send(
                            event.plain_result("无效的序号，请输入列表中的数字。")
                        )
                        controller.keep(
                            timeout=self.session_timeout, reset_timeout=True
                        )
                except ValueError:
                    await event.send(event.plain_result("无效输入，请输入一个数字。"))
                    controller.keep(timeout=self.session_timeout, reset_timeout=True)

            else:
                controller.keep(timeout=self.session_timeout, reset_timeout=True)

        try:
            initial_games = await self.search_games_async(
                session_state["keyword"], page=session_state["page"]
            )
            if not initial_games:
                yield event.plain_result(f"没有找到与 '{keyword}' 相关的游戏。")
                return

            session_state["current_games"] = initial_games
            response_text = "--- 请选择 ---\n"
            for idx, game in enumerate(initial_games):
                response_text += f"  {idx + 1}. {game.get('name')}\n"
            response_text += "-------\n请输入序号选择，'p' 下一页，'q' 上一页，'e' 退出搜索。\n提示：在退出前，您无法与机器人进行普通对话。"
            yield event.plain_result(response_text)

            await search_session_waiter(event)

        except TimeoutError:
            pass
        except Exception as e:
            logger.error(f"TouchGal plugin error: {e}")
            yield event.plain_result(f"插件发生未知错误: {e}")
        finally:
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            event.stop_event()

    async def _build_forward_nodes(
        self,
        game_name: str,
        resources: List[dict],
        bot_uin: str = "10000",
        shionlib_games: Optional[List[dict]] = None,
        touchgal_suggestions: Optional[List[dict]] = None,
        touchgal_game: Optional[dict] = None,
        touchgal_groups: Optional[List[dict]] = None,
    ):
        """
        将资源列表构建成一个合并转发消息。
        使用 Nodes 组件包装多个 Node，确保作为一条合并转发消息发送。

        Args:
            game_name: 游戏名称
            resources: 资源列表
            bot_uin: 机器人的 QQ 号，用于显示头像
            shionlib_games: Shionlib 搜索结果列表（可选）
            touchgal_suggestions: TouchGal 推荐游戏列表（可选，自动搜索时使用）
            touchgal_game: TouchGal 当前选中的游戏（可选）
            touchgal_groups: TouchGal 游戏与资源分组（可选）
        """
        from astrbot.api.message_components import Image, Node, Nodes, Plain

        node_list = []

        # ========== Shionlib 资源推荐 ==========
        if shionlib_games:
            # 先发送 Shionlib 站点信息
            shionlib_header = [
                Plain("📚 书音的图书馆\n"),
                Plain("━━━━━━━━━━\n\n"),
                Plain(f"📍 {self.shionlib_domain}\n"),
            ]
            node_list.append(Node(uin=bot_uin, content=shionlib_header))

            # 每个游戏详情单独一个节点
            for idx, game in enumerate(shionlib_games, 1):
                game_content = [Plain(f"━━ 推荐 {idx} ━━\n\n")]
                if game.get("cover"):
                    game_content.append(Image.fromURL(game["cover"]))
                    game_content.append(Plain("\n"))
                game_content.extend(
                    [
                        Plain(f"🎮 {game['name']}\n\n"),
                        Plain("▶ 点击访问\n"),
                        Plain(f"{game['url']}"),
                    ]
                )
                node_list.append(Node(uin=bot_uin, content=game_content))

        # ========== TouchGal 游戏与资源分组 ==========
        if touchgal_groups:
            touchgal_total = len(touchgal_groups)
            resource_total = sum(
                len(group.get("resources") or [])
                for group in touchgal_groups
                if isinstance(group, dict)
            )
            touchgal_header = [
                Plain("📦 TouchGal 资源站\n"),
                Plain("━━━━━━━━━━\n\n"),
                Plain(f"📍 {self.domain}\n"),
                Plain(f"🎮 共 {touchgal_total} 个相关游戏\n"),
                Plain(f"📦 共 {resource_total} 个资源"),
            ]
            node_list.append(Node(uin=bot_uin, content=touchgal_header))

            for game_idx, group in enumerate(touchgal_groups, 1):
                if not isinstance(group, dict):
                    continue

                game = group.get("game") or {}
                group_resources = group.get("resources") or []
                game_url = self._build_touchgal_game_url(game)
                game_content = [Plain(f"━━ 游戏 {game_idx} ━━\n\n")]
                await self._append_touchgal_image_component(
                    game_content,
                    game,
                    Image,
                    Plain,
                )
                game_content.extend(
                    [
                        Plain(f"🎮 {game.get('name', '未知')}\n"),
                        Plain(f"📦 共 {len(group_resources)} 个资源\n\n"),
                        Plain("▶ 点击访问\n"),
                        Plain(f"{game_url}"),
                    ]
                )
                node_list.append(Node(uin=bot_uin, content=game_content))

                if not group_resources:
                    empty_content = [
                        Plain(f"━━ 游戏 {game_idx} / 资源 ━━\n\n"),
                        Plain("未获取到该游戏的资源链接。"),
                    ]
                    node_list.append(Node(uin=bot_uin, content=empty_content))
                    continue

                for res_idx, res in enumerate(group_resources, 1):
                    resource_content = [
                        Plain(f"━━ 游戏 {game_idx} / 资源 {res_idx} ━━\n\n"),
                        Plain(f"🎮 {game.get('name', '未知')}\n"),
                        Plain(f"📦 {res.get('name', '未知')}\n\n"),
                        Plain("▶ 下载链接\n"),
                        Plain(f"{res.get('content', '无')}"),
                    ]

                    password = res.get("password", "")
                    code = res.get("code", "")
                    note = res.get("note", "")

                    if password or code or note:
                        resource_content.append(Plain("\n\n"))
                    if password:
                        resource_content.append(Plain(f"🔐 密码: {password}\n"))
                    if code:
                        resource_content.append(Plain(f"📝 提取码: {code}\n"))
                    if note:
                        resource_content.append(Plain(f"💬 备注: {note}"))

                    node_list.append(Node(uin=bot_uin, content=resource_content))

        # ========== TouchGal 推荐游戏（自动搜索时显示） ==========
        elif touchgal_suggestions and len(touchgal_suggestions) > 1:
            # TouchGal 推荐站点信息
            suggest_header = [
                Plain("📦 TouchGal 相关推荐\n"),
                Plain("━━━━━━━━━━\n\n"),
                Plain(f"📍 {self.domain}\n"),
                Plain(f"🔍 找到 {len(touchgal_suggestions)} 个相关游戏"),
            ]
            node_list.append(Node(uin=bot_uin, content=suggest_header))

            # 每个推荐游戏单独一个节点
            for idx, game in enumerate(touchgal_suggestions, 1):
                game_url = self._build_touchgal_game_url(game)
                suggest_content = [
                    Plain(f"━━ 推荐 {idx} ━━\n\n"),
                ]
                await self._append_touchgal_image_component(
                    suggest_content,
                    game,
                    Image,
                    Plain,
                )
                suggest_content.extend(
                    [
                        Plain(f"🎮 {game.get('name', '未知')}\n\n"),
                        Plain("▶ 点击访问\n"),
                        Plain(f"{game_url}"),
                    ]
                )
                node_list.append(Node(uin=bot_uin, content=suggest_content))

        # ========== TouchGal 资源 ==========
        if resources and not touchgal_groups:
            current_game = touchgal_game
            if current_game is None and touchgal_suggestions:
                current_game = touchgal_suggestions[0]
            touchgal_header = [
                Plain("📦 TouchGal 资源站\n"),
                Plain("━━━━━━━━━━\n\n"),
            ]
            await self._append_touchgal_image_component(
                touchgal_header,
                current_game,
                Image,
                Plain,
            )
            touchgal_header.extend(
                [
                    Plain(f"📍 {self.domain}\n"),
                    Plain(f"🎮 {game_name}\n"),
                    Plain(f"📦 共 {len(resources)} 个资源"),
                ]
            )
            node_list.append(Node(uin=bot_uin, content=touchgal_header))

            # 每个资源单独作为一个节点
            for idx, res in enumerate(resources, 1):
                content_parts = [
                    Plain(f"━━ 资源 {idx} ━━\n\n"),
                    Plain(f"📦 {res.get('name', '未知')}\n\n"),
                    Plain("▶ 下载链接\n"),
                    Plain(f"{res.get('content', '无')}"),
                ]

                password = res.get("password", "")
                code = res.get("code", "")
                note = res.get("note", "")

                if password or code or note:
                    content_parts.append(Plain("\n\n"))
                if password:
                    content_parts.append(Plain(f"🔐 密码: {password}\n"))
                if code:
                    content_parts.append(Plain(f"📝 提取码: {code}\n"))
                if note:
                    content_parts.append(Plain(f"💬 备注: {note}"))

                node_list.append(Node(uin=bot_uin, content=content_parts))

        # 使用 Nodes 包装所有节点，确保作为一个合并转发消息发送
        return [Nodes(node_list)]

    def _build_single_message(
        self,
        game_name: str,
        resources: List[dict],
        shionlib_games: Optional[List[dict]] = None,
        touchgal_suggestions: Optional[List[dict]] = None,
        touchgal_game: Optional[dict] = None,
        touchgal_groups: Optional[List[dict]] = None,
    ) -> str:
        """
        构建单条消息文本（用于不支持合并转发的平台）

        Args:
            game_name: 游戏名称
            resources: 资源列表
            shionlib_games: Shionlib 搜索结果列表（可选）
            touchgal_suggestions: TouchGal 推荐游戏列表（可选）
            touchgal_game: TouchGal 当前选中的游戏（可选）
            touchgal_groups: TouchGal 游戏与资源分组（可选）

        Returns:
            格式化的消息文本
        """
        lines = []

        # ========== Shionlib 推荐 ==========
        if shionlib_games:
            lines.append(f"📚 书音的图书馆 ({self.shionlib_domain})")
            lines.append("━━━━━━━━━━")
            for game in shionlib_games:
                lines.append(f"🎮 {game['name']}")
                if game.get("cover"):
                    lines.append(f"🖼 {game['cover']}")
                lines.append(f"▶ {game['url']}")
            lines.append("")

        # ========== TouchGal 游戏与资源分组 ==========
        if touchgal_groups:
            resource_total = sum(
                len(group.get("resources") or [])
                for group in touchgal_groups
                if isinstance(group, dict)
            )
            lines.append(f"📦 TouchGal 资源站 ({self.domain})")
            lines.append("━━━━━━━━━━")
            lines.append(f"🎮 共 {len(touchgal_groups)} 个相关游戏 | 📦 共 {resource_total} 个资源")
            lines.append("")

            for game_idx, group in enumerate(touchgal_groups, 1):
                if not isinstance(group, dict):
                    continue

                game = group.get("game") or {}
                group_resources = group.get("resources") or []
                game_url = self._build_touchgal_game_url(game)
                image_url = self._get_touchgal_image_url(game)

                lines.append(f"━━ 游戏 {game_idx} ━━")
                lines.append(f"🎮 {game.get('name', '未知')}")
                if image_url:
                    lines.append(f"🖼 {image_url}")
                lines.append(f"▶ {game_url}")
                lines.append(f"📦 共 {len(group_resources)} 个资源")

                for res_idx, res in enumerate(group_resources, 1):
                    lines.append(f"━━ 游戏 {game_idx} / 资源 {res_idx} ━━")
                    lines.append(f"📦 {res.get('name', '未知')}")
                    lines.append(f"▶ {res.get('content', '无')}")

                    extras = []
                    if res.get("password"):
                        extras.append(f"🔐 密码: {res['password']}")
                    if res.get("code"):
                        extras.append(f"📝 提取码: {res['code']}")
                    if res.get("note"):
                        extras.append(f"💬 备注: {res['note']}")
                    if extras:
                        lines.append(" | ".join(extras))
                lines.append("")

        # ========== TouchGal 推荐 ==========
        elif touchgal_suggestions and len(touchgal_suggestions) > 1:
            lines.append(f"📦 TouchGal 相关推荐 ({self.domain})")
            lines.append("━━━━━━━━━━")
            for game in touchgal_suggestions:
                game_url = self._build_touchgal_game_url(game)
                lines.append(f"🎮 {game.get('name', '未知')}")
                image_url = self._get_touchgal_image_url(game)
                if image_url:
                    lines.append(f"🖼 {image_url}")
                lines.append(f"▶ {game_url}")
            lines.append("")

        # ========== TouchGal 资源 ==========
        if resources and not touchgal_groups:
            current_game = touchgal_game
            if current_game is None and touchgal_suggestions:
                current_game = touchgal_suggestions[0]
            image_url = self._get_touchgal_image_url(current_game)

            lines.append(f"📦 TouchGal 资源站 ({self.domain})")
            lines.append("━━━━━━━━━━")
            if image_url:
                lines.append(f"🖼 {image_url}")
            lines.append(f"🎮 {game_name} | 📦 共 {len(resources)} 个资源")
            lines.append("")

            for idx, res in enumerate(resources, 1):
                lines.append(f"━━ 资源 {idx} ━━")
                lines.append(f"📦 {res.get('name', '未知')}")
                lines.append(f"▶ {res.get('content', '无')}")

                extras = []
                if res.get("password"):
                    extras.append(f"🔐 密码: {res['password']}")
                if res.get("code"):
                    extras.append(f"📝 提取码: {res['code']}")
                if res.get("note"):
                    extras.append(f"💬 备注: {res['note']}")
                if extras:
                    lines.append(" | ".join(extras))
                lines.append("")

        return "\n".join(lines).strip()

    def _is_forward_supported(self, event: AstrMessageEvent) -> bool:
        """
        检测当前平台是否支持合并转发消息

        Returns:
            True 如果支持合并转发（aiocqhttp），否则 False
        """
        try:
            # 检查消息来源平台
            platform = getattr(event, "platform_name", None)
            if platform and "aiocqhttp" in platform.lower():
                return True

            # 备用检测：检查 message_obj 的类型
            msg_obj = getattr(event, "message_obj", None)
            if msg_obj:
                raw = getattr(msg_obj, "raw_message", None)
                # aiocqhttp 的原始消息通常是 dict 或特定格式
                if isinstance(raw, dict) and (
                    "message_type" in raw or "post_type" in raw
                ):
                    return True

            return False
        except Exception:
            return False

    def _should_process_group(self, event: AstrMessageEvent) -> bool:
        """
        检查当前群聊是否应该处理自动搜索

        Returns:
            True 如果应该处理，False 如果应该跳过
        """
        # 列表为空则不过滤
        if not self.group_list:
            return True

        # 获取群号
        group_id = getattr(event.message_obj, "group_id", None)
        if not group_id:
            return True  # 无法获取群号时默认处理

        group_id_str = str(group_id)
        in_list = group_id_str in [str(g) for g in self.group_list]

        if self.group_mode == "whitelist":
            return in_list  # 白名单：在列表中才处理
        else:
            return not in_list  # 黑名单：不在列表中才处理

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def auto_search_handler(self, event: AstrMessageEvent):
        """
        自动搜索处理器：监听群消息，通过正则匹配检测资源请求，
        自动搜索并以合并转发消息形式返回第一个结果的资源。
        """
        # 检查是否启用自动搜索
        auto_search_enabled = self.config.get("auto_search_enabled", False)
        if not auto_search_enabled:
            logger.debug("TouchGal 自动搜索未启用，跳过处理")
            return

        # 检查群聊过滤
        if not self._should_process_group(event):
            logger.debug(f"TouchGal 当前群聊被过滤，跳过自动搜索")
            return

        message = event.message_str.strip()
        if not message:
            return

        logger.debug(f"TouchGal 自动搜索已启用，收到群消息: {message[:50]}...")

        # 获取配置
        silent_mode = self.config.get("auto_search_silent", True)

        # 获取正则匹配模式（从配置读取）
        pattern = self.config.get("auto_search_pattern", "")

        # 空模式检查
        if not pattern:
            logger.warning("TouchGal 自动搜索正则模式为空，跳过处理")
            return

        try:
            match = re.search(pattern, message)
        except re.error as e:
            logger.error(f"TouchGal 自动搜索正则表达式错误: {e}")
            return

        if not match:
            logger.debug(f"TouchGal 消息未匹配正则模式")
            return

        logger.debug(
            f"TouchGal 正则匹配成功，捕获内容: {match.group(1) if match.lastindex else '无捕获组'}"
        )

        # 提取并清理搜索关键词
        keyword = match.group(1).strip()

        # 清理干扰词，提取更精准的游戏名
        cleanup_patterns = [
            r"^(?:一个|一下|一份)\s*",  # 开头的量词
            r"^(?:那个|这个|个)\s*",  # 开头的指示词
            r"\s*(?:的资源|的游戏|资源|游戏|下载|链接|安装包|安卓|手机|手机端)$",  # 结尾的"资源"、"游戏"等
            r"\s*(?:谢谢|感谢|蟹蟹|thx|thanks|thank you).*$",  # 结尾的感谢词
            r"[！!？?，,。.~～、]+$",  # 结尾的标点符号
            r"的$",  # 结尾的"的"
        ]
        for cleanup in cleanup_patterns:
            keyword = re.sub(cleanup, "", keyword, flags=re.IGNORECASE).strip()

        # 移除所有非有效字符（只保留中英文、数字、常见符号）
        # 这会自动过滤掉所有emoji和特殊符号
        keyword = re.sub(
            r"[^\u4e00-\u9fff\u3040-\u30ff\w\s\-_./:;!?&+\'\"()（）【】《》]",
            "",
            keyword,
        ).strip()

        if not keyword or len(keyword) < 2:
            return  # 关键词太短，忽略

        logger.info(f"TouchGal 自动搜索触发，关键词: {keyword}")

        # 非静默模式：发送搜索提示
        if not silent_mode:
            yield event.plain_result(f"🔍 检测到资源请求，正在搜索「{keyword}」...")

        # 获取推荐数量配置
        suggest_limit = self.config.get("auto_search_suggest_limit", 5)

        # 同时搜索 TouchGal 和 Shionlib（利用书音的模糊搜索）
        games = await self.search_games_async(keyword, page=1, limit=suggest_limit)

        # 检查自动搜索时是否开启书音搜索
        auto_search_shionlib = self.config.get("auto_search_shionlib", True)
        shionlib_games = []
        if self.shionlib_enabled and auto_search_shionlib:
            shionlib_games = await self.search_shionlib_async(
                keyword, limit=self.shionlib_limit
            )

        # 如果两边都没搜到，静默返回
        if not games and not shionlib_games:
            return

        # 准备数据
        game_name = None
        resources = []
        touchgal_suggestions = None
        first_game = None
        touchgal_groups = []

        # TouchGal 有结果
        if games:
            first_game = games[0]
            game_name = first_game.get("name", "未知游戏")
            touchgal_suggestions = games if len(games) > 1 else None

            # 非静默模式：发送进度提示
            if not silent_mode:
                yield event.plain_result(
                    f"✅ 找到 {len(games)} 个相关游戏，正在获取资源链接..."
                )

            touchgal_groups = await self._build_touchgal_groups_async(games)
            if self.touchgal_resource_limit_per_game != 0:
                touchgal_groups = [
                    group for group in touchgal_groups if group.get("resources")
                ]
            if touchgal_groups:
                first_game = touchgal_groups[0]["game"]
                game_name = first_game.get("name", "未知游戏")
                resources = touchgal_groups[0]["resources"]

        # 如果 TouchGal 没有资源但书音有结果，也发送
        if not touchgal_groups and not shionlib_games:
            if not silent_mode:
                yield event.plain_result(f"😔 未能获取到资源链接。")
                event.stop_event()
            return

        # 智能选择发送方式
        if self._is_forward_supported(event):
            # QQ 平台：使用合并转发消息
            bot_uin = event.get_self_id()
            nodes = await self._build_forward_nodes(
                game_name,
                resources,
                bot_uin,
                shionlib_games,
                touchgal_suggestions,
                first_game,
                touchgal_groups,
            )
            yield event.chain_result(nodes)
        else:
            # 其他平台：发送单条消息
            message_text = self._build_single_message(
                game_name,
                resources,
                shionlib_games,
                touchgal_suggestions,
                first_game,
                touchgal_groups,
            )
            yield event.plain_result(message_text)

        event.stop_event()
