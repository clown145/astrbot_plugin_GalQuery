import json
import asyncio
import re
import requests
from typing import List, Dict, Optional
from urllib.parse import quote

# AstrBot 核心 API 导入
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.session_waiter import session_waiter, SessionController

@register("touchgal_search", "AI Assistant", "从 TouchGal 搜索游戏资源", "1.0.0")
class TouchGalPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.session_timeout = self.config.get("session_timeout", 60)
        self.domain = self.config.get("touchgal_domain", "www.touchgal.top")
        self.shionlib_enabled = self.config.get("shionlib_enabled", True)
        self.shionlib_domain = "shionlib.com"
        self.active_sessions: Dict[str, SessionController] = {}
        self.api_session = self.create_session()
        
        # 初始化日志
        auto_search = self.config.get("auto_search_enabled", False)
        logger.info(f"TouchGal 插件已加载 | 自动搜索: {'已启用' if auto_search else '未启用'} | 域名: {self.domain} | Shionlib: {'已启用' if self.shionlib_enabled else '未启用'}")

    def create_session(self) -> requests.Session:
        """创建一个包含通用请求头和自定义Cookie的 requests.Session 对象"""
        session = requests.Session()
        headers = {
            'accept': '*/*', 'accept-language': 'zh-CN,zh;q=0.9',
            'content-type': 'text/plain;charset=UTF-8', 'origin': f'https://{self.domain}',
            'priority': 'u=1, i', 'referer': f'https://{self.domain}/search',
            'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
            'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        }
        
        # 如果开启 NSFW 内容显示，添加对应的 cookie
        if self.config.get("show_nsfw", False):
            headers['cookie'] = 'kun-patch-setting-store|state|data|kunNsfwEnable=all'
            logger.info("TouchGal 插件已开启 NSFW 内容显示。")
            
        session.headers.update(headers)
        return session

    async def search_games_async(self, keyword: str, page: int = 1, limit: int = 10) -> List[dict]:
        """异步执行搜索游戏的网络请求"""
        def blocking_search():
            search_url = f'https://{self.domain}/api/search'
            query_list = [{"type": "keyword", "name": keyword}]
            query_string = json.dumps(query_list)
            payload = {
                "queryString": query_string, "limit": limit, "page": page,
                "searchOption": {"searchInIntroduction": False, "searchInAlias": True, "searchInTag": False},
                "selectedType": "all", "selectedLanguage": "all", "selectedPlatform": "all",
                "sortField": "resource_update_time", "sortOrder": "desc",
                "selectedYears": ["all"], "selectedMonths": ["all"]
            }
            try:
                response = self.api_session.post(search_url, data=json.dumps(payload), timeout=10)
                response.raise_for_status()
                search_results = response.json()
                return search_results.get('galgames', []) if isinstance(search_results, dict) else []
            except requests.RequestException as e:
                logger.error(f"TouchGal search failed: {e}")
                return []
        
        return await asyncio.to_thread(blocking_search)

    async def get_links_async(self, game_info: dict) -> List[dict]:
        """异步获取下载链接"""
        def blocking_get_links():
            patch_id = game_info.get('id')
            unique_id = game_info.get('uniqueId')
            if not patch_id or not unique_id:
                return []
            
            resource_url = f'https://{self.domain}/api/patch/resource?patchId={patch_id}'
            headers = self.api_session.headers.copy()
            headers.update({'referer': f'https://{self.domain}/{unique_id}'})
            try:
                response = self.api_session.get(resource_url, headers=headers, timeout=10)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, json.JSONDecodeError) as e:
                logger.error(f"TouchGal get links failed: {e}")
                return []
                
        return await asyncio.to_thread(blocking_get_links)

    async def search_shionlib_async(self, keyword: str, limit: int = 5) -> List[dict]:
        """
        从 shionlib.com 搜索游戏，返回游戏列表
        由于 shionlib 使用 SSR，需要解析 HTML 页面
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制
            
        Returns:
            游戏列表，每个元素包含 id, name, url
        """
        if not self.shionlib_enabled:
            return []
            
        def blocking_search():
            search_url = f'https://{self.shionlib_domain}/zh/search/game?q={quote(keyword)}'
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'zh-CN,zh;q=0.9',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
            }
            try:
                response = requests.get(search_url, headers=headers, timeout=10)
                response.raise_for_status()
                html_content = response.text
                
                # 解析 HTML 提取游戏信息
                # 匹配格式: <a href="/zh/game/708">...<h3>游戏名称</h3>...</a>
                games = []
                
                # 使用正则匹配游戏卡片链接和名称
                # 匹配 href="/zh/game/数字" 的链接
                link_pattern = r'href="(/zh/game/(\d+))"'
                links = re.findall(link_pattern, html_content)
                
                # 去重并获取游戏ID
                seen_ids = set()
                unique_links = []
                for href, game_id in links:
                    if game_id not in seen_ids:
                        seen_ids.add(game_id)
                        unique_links.append((href, game_id))
                
                # 尝试提取游戏名称（从周围的 HTML 内容中）
                for href, game_id in unique_links[:limit]:
                    # 尝试找到对应的游戏名称
                    # 常见模式: <a href="/zh/game/708">...<h3 class="...">游戏名称</h3>...</a>
                    name_pattern = rf'href="{re.escape(href)}"[^>]*>[\s\S]*?<(?:h[1-6]|p|span)[^>]*>([^<]+)<'
                    name_match = re.search(name_pattern, html_content)
                    
                    game_name = name_match.group(1).strip() if name_match else f"游戏 {game_id}"
                    
                    games.append({
                        'id': game_id,
                        'name': game_name,
                        'url': f'https://{self.shionlib_domain}{href}'
                    })
                
                return games
                
            except requests.RequestException as e:
                logger.error(f"Shionlib search failed: {e}")
                return []
            except Exception as e:
                logger.error(f"Shionlib parse error: {e}")
                return []
        
        return await asyncio.to_thread(blocking_search)

    @filter.command("搜索")
    async def search_command(self, event: AstrMessageEvent, keyword: str):
        '''
        搜索 TouchGal 上的游戏资源。
        
        用法:
            /搜索 <游戏名称>
        '''
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
        async def search_session_waiter(controller: SessionController, event: AstrMessageEvent):
            self.active_sessions[session_id] = controller
            user_input = event.message_str.strip()

            if user_input.startswith("搜索 "):
                new_keyword = user_input[len("搜索 "):].strip()
                if new_keyword:
                    await event.send(event.plain_result(f"好的，正在切换到新任务，搜索 '{new_keyword}'..."))
                    
                    session_state["keyword"] = new_keyword
                    session_state["page"] = 1
                    
                    new_games = await self.search_games_async(session_state["keyword"], page=session_state["page"])
                    if not new_games:
                        await event.send(event.plain_result(f"没有找到与 '{new_keyword}' 相关的游戏。"))
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

            if user_input_lower in ['p', 'q']:
                if user_input_lower == 'p':
                    session_state["page"] += 1
                elif user_input_lower == 'q':
                    if session_state["page"] > 1:
                        session_state["page"] -= 1
                    else:
                        await event.send(event.plain_result("已经是第一页了。"))
                        controller.keep(timeout=self.session_timeout, reset_timeout=True)
                        return

                await event.send(event.plain_result(f"正在获取第 {session_state['page']} 页..."))
                
                new_games = await self.search_games_async(session_state["keyword"], page=session_state["page"])
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

            elif user_input_lower == 'e':
                await event.send(event.plain_result("已退出搜索会话。现在您可以正常与我对话了。"))
                controller.stop()  # 停止会话
                return             # 立即返回

            elif user_input_lower.isdigit():
                try:
                    choice_idx = int(user_input_lower) - 1
                    if 0 <= choice_idx < len(session_state["current_games"]):
                        selected_game = session_state["current_games"][choice_idx]
                        await event.send(event.plain_result(f"已选择: {selected_game.get('name')}\n正在获取资源链接..."))
                        
                        resources = await self.get_links_async(selected_game)
                        if not resources:
                            await event.send(event.plain_result("未能获取到该游戏的资源链接。"))
                        else:
                            # 同时搜索 Shionlib
                            shionlib_games = await self.search_shionlib_async(session_state["keyword"], limit=5)
                            
                            # 使用合并转发消息发送资源
                            bot_uin = event.get_self_id()
                            nodes = self._build_forward_nodes(
                                selected_game.get('name', '未知游戏'), 
                                resources, 
                                bot_uin,
                                shionlib_games=shionlib_games
                            )
                            await event.send(event.chain_result(nodes))
                        
                        controller.stop()
                    else:
                        await event.send(event.plain_result("无效的序号，请输入列表中的数字。"))
                        controller.keep(timeout=self.session_timeout, reset_timeout=True)
                except ValueError:
                    await event.send(event.plain_result("无效输入，请输入一个数字。"))
                    controller.keep(timeout=self.session_timeout, reset_timeout=True)
            
            else:
                controller.keep(timeout=self.session_timeout, reset_timeout=True)

        try:
            initial_games = await self.search_games_async(session_state["keyword"], page=session_state["page"])
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

    def _build_forward_nodes(self, game_name: str, resources: List[dict], bot_uin: str = "10000", shionlib_games: Optional[List[dict]] = None):
        """
        将资源列表构建成一个合并转发消息。
        使用 Nodes 组件包装多个 Node，确保作为一条合并转发消息发送。
        
        Args:
            game_name: 游戏名称
            resources: 资源列表
            bot_uin: 机器人的 QQ 号，用于显示头像
            shionlib_games: Shionlib 搜索结果列表（可选）
        """
        from astrbot.api.message_components import Node, Nodes, Plain
        
        node_list = []
        
        # 第一个节点：Shionlib 搜索结果（如果有）
        if shionlib_games:
            shionlib_content = [Plain(f"📚 书音图书馆 - 相关游戏\n")]
            shionlib_content.append(Plain("━" * 10 + "\n\n"))
            for game in shionlib_games:
                shionlib_content.append(Plain(f"🎮 {game['name']}\n"))
                shionlib_content.append(Plain(f"🔗 {game['url']}\n\n"))
            
            node_list.append(Node(
                uin=bot_uin,
                content=shionlib_content
            ))
        
        # 第二个节点：TouchGal 标题信息
        title_content = [
            Plain(f"🎮 游戏名称: {game_name}\n"),
            Plain(f"📦 共找到 {len(resources)} 个资源\n"),
            Plain("━" * 10)
        ]
        node_list.append(Node(
            uin=bot_uin,
            content=title_content
        ))
        
        # 每个资源单独作为一个节点
        for idx, res in enumerate(resources, 1):
            content_parts = [
                Plain(f"📦 资源 {idx}: {res.get('name', '未知')}\n\n"),
                Plain(f"🔗 链接:\n{res.get('content', '无')}\n")
            ]
            
            password = res.get('password', '')
            code = res.get('code', '')
            note = res.get('note', '')
            
            if password:
                content_parts.append(Plain(f"\n🔐 解压密码: {password}"))
            if code:
                content_parts.append(Plain(f"\n📝 提取码: {code}"))
            if note:
                content_parts.append(Plain(f"\n💬 备注: {note}"))
            
            node_list.append(Node(
                uin=bot_uin,
                content=content_parts
            ))
        
        # 使用 Nodes 包装所有节点，确保作为一个合并转发消息发送
        return [Nodes(node_list)]

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
        
        logger.debug(f"TouchGal 正则匹配成功，捕获内容: {match.group(1) if match.lastindex else '无捕获组'}")
        
        # 提取并清理搜索关键词
        keyword = match.group(1).strip()
        
        # 清理干扰词，提取更精准的游戏名
        cleanup_patterns = [
            r'^(?:一个|一下|一份)\s*',  # 开头的量词
            r'^(?:那个|这个|个)\s*',  # 开头的指示词
            r'\s*(?:的资源|的游戏|资源|游戏|下载|链接|安装包|安卓|手机|手机端)$',  # 结尾的"资源"、"游戏"等
            r'\s*(?:谢谢|感谢|蟹蟹|thx|thanks|thank you).*$',  # 结尾的感谢词
            r'[！!？?，,。.~～、]+$',  # 结尾的标点符号
            r'的$',  # 结尾的"的"
        ]
        for cleanup in cleanup_patterns:
            keyword = re.sub(cleanup, '', keyword, flags=re.IGNORECASE).strip()
        
        # 移除所有非有效字符（只保留中英文、数字、常见符号）
        # 这会自动过滤掉所有emoji和特殊符号
        keyword = re.sub(r'[^\u4e00-\u9fff\u3040-\u30ff\w\s\-_./:;!?&+\'\"()（）【】《》]', '', keyword).strip()
        
        if not keyword or len(keyword) < 2:
            return  # 关键词太短，忽略
        
        logger.info(f"TouchGal 自动搜索触发，关键词: {keyword}")
        
        # 非静默模式：发送搜索提示
        if not silent_mode:
            yield event.plain_result(f"🔍 检测到资源请求，正在搜索「{keyword}」...")
        
        # 执行搜索
        games = await self.search_games_async(keyword, page=1, limit=1)
        
        if not games:
            # 静默模式：搜不到就不回复
            if not silent_mode:
                yield event.plain_result(f"😔 没有找到与「{keyword}」相关的游戏资源。")
                event.stop_event()
            return
        
        # 获取第一个结果
        first_game = games[0]
        game_name = first_game.get('name', '未知游戏')
        
        # 非静默模式：发送进度提示
        if not silent_mode:
            yield event.plain_result(f"✅ 找到游戏「{game_name}」，正在获取资源链接...")
        
        # 获取资源链接
        resources = await self.get_links_async(first_game)
        
        if not resources:
            # 静默模式：获取不到资源就不回复
            if not silent_mode:
                yield event.plain_result(f"😔 未能获取到「{game_name}」的资源链接。")
                event.stop_event()
            return
        
        # 同时搜索 Shionlib
        shionlib_games = await self.search_shionlib_async(keyword, limit=5)
        
        # 构建并发送合并转发消息
        bot_uin = event.get_self_id()
        nodes = self._build_forward_nodes(game_name, resources, bot_uin, shionlib_games=shionlib_games)
        
        yield event.chain_result(nodes)
        event.stop_event()