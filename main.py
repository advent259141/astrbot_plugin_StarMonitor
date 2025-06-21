import asyncio
import json
import time
import os
from typing import Dict, Optional, List, Tuple
from datetime import datetime
import aiohttp
from playwright.async_api import async_playwright
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp


@register("astrbot_plugin_StarMonitor", "Jason.Joestar", "GitHub仓库星标监控插件", "1.0.0", "https://github.com/advent259141/astrbot_plugin_StarMonitor")
class GitHubStarMonitor(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.last_star_counts: Dict[str, int] = {}
        self.monitoring_task = None
        self.is_monitoring = False  # 添加监控状态标志
        
        # 启动监控任务
        asyncio.create_task(self.start_monitoring())
    async def start_monitoring(self):
        """启动监控任务"""
        try:
            # 等待一段时间再开始监控，确保插件完全加载
            await asyncio.sleep(10)
            logger.info("GitHub Star Monitor: 开始监控任务")
            
            # 发送启动通知
            if self.config.get("enable_startup_notification", True):
                await self.send_startup_notification()
            
            # 首次运行时初始化星标数据
            await self.init_star_counts()
            
            while True:
                try:
                    check_interval = self.config.get("check_interval", 60)
                    await self.check_repositories()
                    await asyncio.sleep(check_interval)
                except Exception as e:
                    logger.error(f"GitHub Star Monitor: 监控任务出错: {e}")
                    await asyncio.sleep(60)  # 出错后等待1分钟再重试
        except Exception as e:
            logger.error(f"GitHub Star Monitor: 启动监控任务失败: {e}")
    
    async def send_startup_notification(self):
        """发送启动通知"""
        repositories = self.config.get("repositories", [])
        target_sessions = self.config.get("target_sessions", [])
        
        if not target_sessions:
            return
        
        message = "🚀 GitHub星标监控插件已启动\n\n"
        if repositories:
            message += f"正在监控 {len(repositories)} 个仓库:\n"
            for repo_url in repositories[:5]:  # 最多显示5个
                repo_info = self.parse_github_url(repo_url)
                if repo_info:
                    owner, repo = repo_info
                    message += f"• {owner}/{repo}\n"
            if len(repositories) > 5:
                message += f"... 以及其他 {len(repositories) - 5} 个仓库\n"
        else:
            message += "⚠️ 未配置监控仓库\n"
        
        message += f"\n检查间隔: {self.config.get('check_interval', 60)} 秒"
        
        await self.send_notification(target_sessions, message)
    
    async def init_star_counts(self):
        """初始化星标数据"""
        repositories = self.config.get("repositories", [])
        
        for repo_url in repositories:
            repo_info = self.parse_github_url(repo_url)
            if not repo_info:
                continue
            
            owner, repo = repo_info
            repo_key = f"{owner}/{repo}"
            
            if repo_key not in self.last_star_counts:
                try:
                    current_stars = await self.get_repo_stars(owner, repo)
                    if current_stars is not None:
                        self.last_star_counts[repo_key] = current_stars
                        logger.info(f"GitHub Star Monitor: 初始化 {repo_key} 星标数: {current_stars}")
                except Exception as e:
                    logger.error(f"GitHub Star Monitor: 初始化 {repo_key} 星标数失败: {e}")
    async def check_repositories(self):
        """检查所有仓库的星标变化"""
        if self.is_monitoring:
            logger.debug("GitHub Star Monitor: 上一次检查还在进行中，跳过本次检查")
            return
        
        self.is_monitoring = True
        
        try:
            repositories = self.config.get("repositories", [])
            target_sessions = self.config.get("target_sessions", [])
            
            if not repositories:
                logger.debug("GitHub Star Monitor: 没有配置要监控的仓库")
                return
            
            if not target_sessions:
                logger.debug("GitHub Star Monitor: 没有配置目标会话")
                return
            
            for repo_url in repositories:
                try:
                    repo_info = self.parse_github_url(repo_url)
                    if not repo_info:
                        logger.warning(f"GitHub Star Monitor: 无效的GitHub仓库URL: {repo_url}")
                        continue
                    
                    owner, repo = repo_info
                    current_stars = await self.get_repo_stars(owner, repo)
                      if current_stars is None:
                        continue
                    repo_key = f"{owner}/{repo}"
                    last_stars = self.last_star_counts.get(repo_key)
                    
                    if last_stars is not None and current_stars != last_stars:
                        # 星标数量发生变化
                        change = current_stars - last_stars
                        
                        # 立即更新记录，防止重复通知
                        self.last_star_counts[repo_key] = current_stars
                        
                        # 检查是否达到1万star里程碑
                        is_milestone = await self.check_milestone_reached(last_stars, current_stars)
                        
                        # 获取导致此次变动的具体用户
                        change_users = await self.get_star_change_users(owner, repo, change)
                        
                        # 根据配置决定发送方式
                        enable_image = self.config.get("enable_image_notification", True)
                        github_token = self.config.get("github_token", "").strip()
                        
                        if is_milestone and enable_image and github_token:
                            # 创建特殊的庆祝图片
                            image_path = await self.create_milestone_celebration_image(
                                repo_key, current_stars, change_users
                            )
                            
                            if image_path:
                                # 发送庆祝图片通知
                                await self.send_image_notification(target_sessions, image_path)
                            else:
                                # 图片生成失败，发送庆祝文本通知
                                await self.send_milestone_text_notification(target_sessions, repo_key, current_stars, change_users)
                        elif enable_image and github_token:
                            # 创建通知图片
                            image_path = await self.create_star_notification_image(
                                repo_key, change, current_stars, change_users
                            )
                            
                            if image_path:
                                # 发送图片通知
                                await self.send_image_notification(target_sessions, image_path)
                            else:
                                # 图片生成失败，发送文本通知
                                await self.send_text_notification_with_users(target_sessions, repo_key, change, current_stars, change_users)
                        else:
                            # 发送文本通知
                            if is_milestone:
                                await self.send_milestone_text_notification(target_sessions, repo_key, current_stars, change_users)
                            else:
                                await self.send_text_notification_with_users(target_sessions, repo_key, change, current_stars, change_users)
                        
                        logger.info(f"GitHub Star Monitor: 检测到 {repo_key} 星标变动: {last_stars} -> {current_stars}")
                    else:
                        # 更新记录的星标数
                        self.last_star_counts[repo_key] = current_stars
                    
                except Exception as e:
                    logger.error(f"GitHub Star Monitor: 检查仓库 {repo_url} 时出错: {e}")
        finally:
            self.is_monitoring = False
    def parse_github_url(self, url: str) -> Optional[tuple]:
        """解析GitHub仓库URL，返回(owner, repo)"""
        try:
            # 移除URL中的协议和域名部分
            if url.startswith("https://github.com/"):
                path = url.replace("https://github.com/", "")
            elif url.startswith("http://github.com/"):
                path = url.replace("http://github.com/", "")
            elif url.startswith("github.com/"):
                path = url.replace("github.com/", "")
            else:
                # 假设输入的是 owner/repo 格式
                path = url
            
            # 移除末尾的 /
            path = path.rstrip("/")
            
            # 正确移除 .git 后缀
            if path.endswith(".git"):
                path = path[:-4]
            
            parts = path.split("/")
            if len(parts) >= 2:
                return parts[0], parts[1]
            return None
        except Exception:
            return None
    async def get_repo_stars(self, owner: str, repo: str) -> Optional[int]:
        """获取GitHub仓库的星标数"""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            
            # 准备请求头
            headers = {
                'User-Agent': 'AstrBot-GitHub-Star-Monitor/1.0.0',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 如果配置了GitHub Token，添加认证头
            github_token = self.config.get("github_token", "").strip()
            if github_token:
                headers['Authorization'] = f'Bearer {github_token}'
                logger.debug(f"GitHub Star Monitor: 使用认证请求访问 {owner}/{repo}")
            else:
                logger.debug(f"GitHub Star Monitor: 使用未认证请求访问 {owner}/{repo}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("stargazers_count", 0)
                    elif response.status == 401:
                        logger.error(f"GitHub Star Monitor: GitHub Token无效或已过期")
                        return None
                    elif response.status == 403:
                        # 检查是否是API限制
                        rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', 'unknown')
                        rate_limit_reset = response.headers.get('X-RateLimit-Reset', 'unknown')
                        if rate_limit_remaining == '0':
                            logger.warning(f"GitHub Star Monitor: GitHub API限制已耗尽，重置时间: {rate_limit_reset}")
                        else:
                            logger.warning(f"GitHub Star Monitor: GitHub API返回403，可能是权限不足")
                        return None
                    elif response.status == 404:
                        logger.warning(f"GitHub Star Monitor: 仓库 {owner}/{repo} 不存在或无法访问")
                        return None
                    else:
                        logger.warning(f"GitHub Star Monitor: GitHub API 返回状态码 {response.status}")
                        return None
        except asyncio.TimeoutError:
            logger.warning(f"GitHub Star Monitor: 获取 {owner}/{repo} 星标数超时")
            return None
        except Exception as e:
            logger.error(f"GitHub Star Monitor: 获取 {owner}/{repo} 星标数出错: {e}")
            return None
    async def send_notification(self, target_sessions: list, message: str):
        """发送通知到目标会话"""
        # 根据AstrBot文档，需要创建一个具有chain属性的对象
        class MessageChain:
            def __init__(self, chain):
                self.chain = chain
        
        message_chain = MessageChain([Comp.Plain(message)])
        
        for session_id in target_sessions:
            try:
                await self.context.send_message(session_id, message_chain)
                logger.info(f"GitHub Star Monitor: 已向会话 {session_id} 发送通知")
            except Exception as e:
                logger.error(f"GitHub Star Monitor: 向会话 {session_id} 发送通知失败: {e}")
    
    @filter.command("star_status")
    async def star_status(self, event: AstrMessageEvent):
        """查看当前监控的仓库星标状态"""
        repositories = self.config.get("repositories", [])
        
        if not repositories:
            yield event.plain_result("❌ 当前没有配置要监控的仓库")
            return
        
        status_text = "⭐ GitHub仓库星标监控状态\n\n"
        
        for repo_url in repositories:
            repo_info = self.parse_github_url(repo_url)
            if not repo_info:
                status_text += f"❌ 无效URL: {repo_url}\n"
                continue
            
            owner, repo = repo_info
            repo_key = f"{owner}/{repo}"
            
            try:
                current_stars = await self.get_repo_stars(owner, repo)
                if current_stars is not None:
                    status_text += f"🌟 {repo_key}: {current_stars} stars\n"
                else:
                    status_text += f"❌ {repo_key}: 获取失败\n"
            except Exception as e:
                status_text += f"❌ {repo_key}: 检查出错\n"
        
        yield event.plain_result(status_text.strip())
    
    @filter.command("star_test")
    async def star_test(self, event: AstrMessageEvent):
        """测试星标监控功能"""
        target_sessions = self.config.get("target_sessions", [])
        
        test_message = "🧪 这是一条测试消息\n\n"
        test_message += "如果您收到这条消息，说明GitHub星标监控插件的通知功能正常工作。\n"
        test_message += f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        
        if not target_sessions:
            yield event.plain_result("❌ 没有配置目标会话，无法发送测试消息")
            return
        
        await self.send_notification(target_sessions, test_message)
        yield event.plain_result(f"✅ 测试消息已发送到 {len(target_sessions)} 个目标会话")
    
    @filter.command("star_force_check")
    async def star_force_check(self, event: AstrMessageEvent):
        """强制检查所有仓库"""
        yield event.plain_result("🔄 开始强制检查所有仓库...")
        
        try:
            await self.check_repositories()
            yield event.plain_result("✅ 强制检查完成")
        except Exception as e:
            yield event.plain_result(f"❌ 强制检查失败: {e}")
    
    @filter.command("star_rate_limit")
    async def star_rate_limit(self, event: AstrMessageEvent):
        """检查GitHub API使用限制"""
        try:
            url = "https://api.github.com/rate_limit"
            
            # 准备请求头
            headers = {
                'User-Agent': 'AstrBot-GitHub-Star-Monitor/1.0.0',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 如果配置了GitHub Token，添加认证头
            github_token = self.config.get("github_token", "").strip()
            if github_token:
                headers['Authorization'] = f'Bearer {github_token}'
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        core_rate = data['resources']['core']
                        
                        rate_info = "📊 GitHub API 使用情况\n\n"
                        
                        if github_token:
                            rate_info += "🔑 认证状态: 已认证\n"
                        else:
                            rate_info += "🔓 认证状态: 未认证\n"
                        
                        rate_info += f"剩余请求: {core_rate['remaining']}/{core_rate['limit']}\n"
                        
                        # 计算重置时间
                        import datetime
                        reset_time = datetime.datetime.fromtimestamp(core_rate['reset'])
                        rate_info += f"重置时间: {reset_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        
                        # 计算百分比
                        used_percent = ((core_rate['limit'] - core_rate['remaining']) / core_rate['limit']) * 100
                        rate_info += f"使用百分比: {used_percent:.1f}%\n"
                        
                        if core_rate['remaining'] < 100:
                            rate_info += "\n⚠️ 剩余请求较少，建议配置GitHub Token"
                        
                        yield event.plain_result(rate_info)
                    else:
                        yield event.plain_result(f"❌ 无法获取API限制信息，状态码: {response.status}")
        except Exception as e:
            yield event.plain_result(f"❌ 检查API限制失败: {e}")
    async def get_recent_star_events(self, owner: str, repo: str) -> List[dict]:
        """获取最近的star事件"""
        github_token = self.config.get("github_token", "").strip()
        if not github_token:
            return []
        
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/events"
            
            headers = {
                'User-Agent': 'AstrBot-GitHub-Star-Monitor/1.0.0',
                'Accept': 'application/vnd.github.v3+json',
                'Authorization': f'Bearer {github_token}'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        events = await response.json()
                        # 只返回WatchEvent (star/unstar)
                        star_events = [event for event in events if event.get('type') == 'WatchEvent']
                        return star_events[:5]  # 返回最近5个star事件
                    else:
                        logger.warning(f"GitHub Star Monitor: 获取事件失败，状态码: {response.status}")
                        return []        except Exception as e:
            logger.error(f"GitHub Star Monitor: 获取star事件失败: {e}")
            return []
    
    async def download_avatar_base64(self, avatar_url: str) -> Optional[str]:
        """下载用户头像并转换为base64"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        avatar_data = await response.read()
                        import base64
                        return base64.b64encode(avatar_data).decode('utf-8')
        except Exception as e:
            logger.error(f"GitHub Star Monitor: 下载头像失败: {e}")
        return None
    
    async def create_star_notification_image(self, repo_key: str, change: int, current_stars: int, star_events: List[dict]) -> str:
        """创建星标变动通知图片 - 使用HTML渲染"""
        try:
            # 准备用户数据
            users_html = ""
            if star_events and len(star_events) > 0:
                for i, event in enumerate(star_events[:3]):  # 最多显示3个用户
                    user = event.get('actor', {})
                    username = user.get('login', '未知用户')
                    avatar_url = user.get('avatar_url', '')
                    
                    # 下载头像并转换为base64
                    avatar_base64 = ""
                    if avatar_url:
                        avatar_data = await self.download_avatar_base64(avatar_url)
                        if avatar_data:
                            avatar_base64 = f"data:image/png;base64,{avatar_data}"
                    
                    # 添加用户HTML
                    users_html += f"""
                    <div class="user-item">
                        <div class="avatar-container">
                            <img class="avatar" src="{avatar_base64 or 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNTAiIGhlaWdodD0iNTAiIHZpZXdCb3g9IjAgMCA1MCA1MCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPGNpcmNsZSBjeD0iMjUiIGN5PSIyNSIgcj0iMjUiIGZpbGw9IiNEREREREQiLz4KPHN2ZyB4PSIxNSIgeT0iMTUiIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSIjOTk5OTk5Ij4KPHA+VXNlcjwvcD4KPHN2Zz4KPC9zdmc+'}" alt="avatar" />
                        </div>
                        <div class="user-info">
                            <div class="username">@{username}</div>
                        </div>
                    </div>
                    """
            
            # 创建HTML模板
            html_template = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        margin: 0;
                        padding: 40px;
                        font-family: 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 520px;
                        box-sizing: border-box;
                    }}
                    .container {{
                        background: white;
                        border-radius: 20px;
                        padding: 40px;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.1);
                        max-width: 720px;
                        margin: 0 auto;
                    }}
                    .title {{
                        font-size: 32px;
                        font-weight: bold;
                        text-align: center;
                        color: #2c3e50;
                        margin-bottom: 30px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        gap: 10px;
                    }}
                    .repo-info {{
                        background: #f8f9fa;
                        border-radius: 12px;
                        padding: 20px;
                        margin-bottom: 25px;
                        border-left: 4px solid #667eea;
                    }}
                    .repo-name {{
                        font-size: 24px;
                        font-weight: bold;
                        color: #2c3e50;
                        margin-bottom: 10px;
                    }}
                    .stats {{
                        display: flex;
                        gap: 30px;
                        align-items: center;
                    }}
                    .stat-item {{
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }}
                    .change {{
                        font-size: 20px;
                        font-weight: bold;
                        color: {'#27ae60' if change > 0 else '#e74c3c'};
                    }}
                    .current-stars {{
                        font-size: 20px;
                        color: #2c3e50;
                    }}
                    .users-section {{
                        margin-top: 30px;
                    }}
                    .users-title {{
                        font-size: 20px;
                        font-weight: bold;
                        color: #2c3e50;
                        margin-bottom: 20px;
                    }}
                    .user-item {{
                        display: flex;
                        align-items: center;
                        gap: 15px;
                        padding: 15px;
                        background: #f8f9fa;
                        border-radius: 12px;
                        margin-bottom: 12px;
                        transition: transform 0.2s;
                    }}
                    .user-item:hover {{
                        transform: translateX(5px);
                    }}
                    .avatar-container {{
                        flex-shrink: 0;
                    }}
                    .avatar {{
                        width: 50px;
                        height: 50px;
                        border-radius: 50%;
                        border: 3px solid #667eea;
                        object-fit: cover;
                    }}
                    .user-info {{
                        flex: 1;
                    }}
                    .username {{                        font-size: 16px;
                        font-weight: 600;
                        color: #2c3e50;
                        margin-bottom: 4px;
                    }}
                    .star-icon {{
                        color: #f39c12;
                        font-size: 24px;
                    }}
                    .trend-icon {{
                        font-size: 18px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="title">
                        <span class="star-icon">🌟</span>
                        GitHub 星标变动提醒
                    </div>
                    
                    <div class="repo-info">
                        <div class="repo-name">{repo_key}</div>
                        <div class="stats">
                            <div class="stat-item">
                                <span class="trend-icon">{'📈' if change > 0 else '📉'}</span>
                                <span class="change">{'+' if change > 0 else ''}{change}</span>
                            </div>
                            <div class="stat-item">
                                <span>⭐</span>
                                <span class="current-stars">{current_stars} stars</span>
                            </div>
                        </div>
                    </div>
                    
                    {f'''
                    <div class="users-section">
                        <div class="users-title">👤 导致此次变动的用户</div>                        {users_html}
                    </div>
                    ''' if users_html else ''}
                </div>
            </body>
            </html>
            """
              # 使用本地Playwright渲染HTML为图片
            image_path = await self.render_html_to_image(html_template)
            return image_path
            
        except Exception as e:
            logger.error(f"GitHub Star Monitor: 创建通知图片失败: {e}")
            return ""

    async def create_milestone_celebration_image(self, repo_key: str, current_stars: int, star_events: List[dict]) -> str:
        """创建1万star里程碑庆祝图片"""
        try:
            # 准备第1万个star用户数据
            milestone_user_html = ""
            if star_events and len(star_events) > 0:
                event = star_events[0]  # 获取第一个用户（第1万个star）
                user = event.get('actor', {})
                username = user.get('login', '未知用户')
                avatar_url = user.get('avatar_url', '')
                
                # 下载头像并转换为base64
                avatar_base64 = ""
                if avatar_url:
                    avatar_data = await self.download_avatar_base64(avatar_url)
                    if avatar_data:
                        avatar_base64 = f"data:image/png;base64,{avatar_data}"
                
                milestone_user_html = f"""
                <div class="milestone-user">
                    <div class="milestone-avatar-container">
                        <img class="milestone-avatar" src="{avatar_base64 or 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iODAiIGhlaWdodD0iODAiIHZpZXdCb3g9IjAgMCA4MCA4MCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPGNpcmNsZSBjeD0iNDAiIGN5PSI0MCIgcj0iNDAiIGZpbGw9IiNEREREREQiLz4KPHN2ZyB4PSIyNSIgeT0iMjUiIHdpZHRoPSIzMCIgaGVpZ2h0PSIzMCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSIjOTk5OTk5Ij4KPHA+VXNlcjwvcD4KPHN2Zz4KPC9zdmc+'}" alt="milestone user avatar" />
                        <div class="crown">👑</div>
                    </div>
                    <div class="milestone-user-info">
                        <div class="milestone-username">@{username}</div>
                        <div class="milestone-label">第10,000个Star！</div>
                    </div>
                </div>
                """
            
            # 创建庆祝HTML模板
            html_template = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Fredoka+One:wght@400&display=swap');
                    
                    body {{
                        margin: 0;
                        padding: 40px;
                        font-family: 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
                        background: linear-gradient(135deg, #ff6b6b 0%, #ffd93d 25%, #6bcf7f 50%, #4d79ff 75%, #ff6b6b 100%);
                        background-size: 400% 400%;
                        animation: celebration-bg 4s ease infinite;
                        min-height: 600px;
                        box-sizing: border-box;
                        position: relative;
                    }}
                    
                    @keyframes celebration-bg {{
                        0% {{ background-position: 0% 50%; }}
                        50% {{ background-position: 100% 50%; }}
                        100% {{ background-position: 0% 50%; }}
                    }}
                    
                    .fireworks {{
                        position: absolute;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        pointer-events: none;
                        overflow: hidden;
                    }}
                    
                    .firework {{
                        position: absolute;
                        width: 4px;
                        height: 4px;
                        border-radius: 50%;
                        animation: firework-explode 2s ease-out infinite;
                    }}
                    
                    .firework:nth-child(1) {{ top: 20%; left: 15%; background: #ff6b6b; animation-delay: 0s; }}
                    .firework:nth-child(2) {{ top: 30%; left: 85%; background: #ffd93d; animation-delay: 0.5s; }}
                    .firework:nth-child(3) {{ top: 60%; left: 25%; background: #6bcf7f; animation-delay: 1s; }}
                    .firework:nth-child(4) {{ top: 50%; left: 75%; background: #4d79ff; animation-delay: 1.5s; }}
                    
                    @keyframes firework-explode {{
                        0% {{ transform: scale(0); opacity: 1; }}
                        50% {{ transform: scale(20); opacity: 0.8; }}
                        100% {{ transform: scale(40); opacity: 0; }}
                    }}
                    
                    .container {{
                        background: rgba(255, 255, 255, 0.95);
                        border-radius: 25px;
                        padding: 50px;
                        box-shadow: 0 30px 80px rgba(0,0,0,0.15);
                        max-width: 800px;
                        margin: 0 auto;
                        text-align: center;
                        position: relative;
                        backdrop-filter: blur(10px);
                    }}
                    
                    .celebration-title {{
                        font-family: 'Fredoka One', cursive;
                        font-size: 48px;
                        font-weight: bold;
                        background: linear-gradient(45deg, #ff6b6b, #ffd93d, #6bcf7f, #4d79ff);
                        background-size: 300% 300%;
                        background-clip: text;
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        animation: celebration-text 3s ease infinite;
                        margin-bottom: 20px;
                        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
                    }}
                    
                    @keyframes celebration-text {{
                        0% {{ background-position: 0% 50%; }}
                        50% {{ background-position: 100% 50%; }}
                        100% {{ background-position: 0% 50%; }}
                    }}
                    
                    .celebration-subtitle {{
                        font-size: 24px;
                        color: #2c3e50;
                        margin-bottom: 40px;
                        font-weight: 600;
                    }}
                    
                    .milestone-info {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        border-radius: 20px;
                        padding: 30px;
                        margin-bottom: 40px;
                        color: white;
                        position: relative;
                        overflow: hidden;
                    }}
                    
                    .milestone-info::before {{
                        content: '';
                        position: absolute;
                        top: -50%;
                        left: -50%;
                        width: 200%;
                        height: 200%;
                        background: repeating-linear-gradient(
                            45deg,
                            transparent,
                            transparent 10px,
                            rgba(255,255,255,0.1) 10px,
                            rgba(255,255,255,0.1) 20px
                        );
                        animation: shine 3s linear infinite;
                    }}
                    
                    @keyframes shine {{
                        0% {{ transform: translateX(-100%) translateY(-100%); }}
                        100% {{ transform: translateX(100%) translateY(100%); }}
                    }}
                    
                    .repo-name {{
                        font-size: 32px;
                        font-weight: bold;
                        margin-bottom: 15px;
                        position: relative;
                        z-index: 1;
                    }}
                    
                    .milestone-stars {{
                        font-size: 42px;
                        font-weight: bold;
                        margin-bottom: 10px;
                        position: relative;
                        z-index: 1;
                        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                    }}
                    
                    .milestone-message {{
                        font-size: 18px;
                        position: relative;
                        z-index: 1;
                    }}
                    
                    .milestone-user {{
                        background: linear-gradient(135deg, #ffd93d 0%, #ff6b6b 100%);
                        border-radius: 20px;
                        padding: 30px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        gap: 25px;
                        margin-bottom: 30px;
                        box-shadow: 0 15px 35px rgba(0,0,0,0.1);
                    }}
                    
                    .milestone-avatar-container {{
                        position: relative;
                    }}
                    
                    .milestone-avatar {{
                        width: 80px;
                        height: 80px;
                        border-radius: 50%;
                        border: 4px solid white;
                        object-fit: cover;
                        box-shadow: 0 8px 25px rgba(0,0,0,0.2);
                    }}
                    
                    .crown {{
                        position: absolute;
                        top: -15px;
                        right: -10px;
                        font-size: 24px;
                        animation: crown-bounce 2s ease infinite;
                    }}
                    
                    @keyframes crown-bounce {{
                        0%, 100% {{ transform: translateY(0) rotate(0deg); }}
                        50% {{ transform: translateY(-5px) rotate(10deg); }}
                    }}
                    
                    .milestone-user-info {{
                        text-align: left;
                    }}
                    
                    .milestone-username {{
                        font-size: 24px;
                        font-weight: bold;
                        color: white;
                        margin-bottom: 5px;
                        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
                    }}
                    
                    .milestone-label {{
                        font-size: 16px;
                        color: rgba(255,255,255,0.9);
                        font-weight: 600;
                    }}
                    
                    .celebration-footer {{
                        font-size: 18px;
                        color: #2c3e50;
                        font-weight: 600;
                        margin-top: 20px;
                    }}
                    
                    .emoji-rain {{
                        position: absolute;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        pointer-events: none;
                        overflow: hidden;
                    }}
                    
                    .emoji {{
                        position: absolute;
                        font-size: 20px;
                        animation: fall 3s linear infinite;
                    }}
                    
                    .emoji:nth-child(1) {{ left: 10%; animation-delay: 0s; }}
                    .emoji:nth-child(2) {{ left: 20%; animation-delay: 0.5s; }}
                    .emoji:nth-child(3) {{ left: 30%; animation-delay: 1s; }}
                    .emoji:nth-child(4) {{ left: 40%; animation-delay: 1.5s; }}
                    .emoji:nth-child(5) {{ left: 50%; animation-delay: 2s; }}
                    .emoji:nth-child(6) {{ left: 60%; animation-delay: 2.5s; }}
                    .emoji:nth-child(7) {{ left: 70%; animation-delay: 0.3s; }}
                    .emoji:nth-child(8) {{ left: 80%; animation-delay: 0.8s; }}
                    .emoji:nth-child(9) {{ left: 90%; animation-delay: 1.3s; }}
                    
                    @keyframes fall {{
                        0% {{ transform: translateY(-100px) rotate(0deg); opacity: 1; }}
                        100% {{ transform: translateY(calc(100vh + 100px)) rotate(360deg); opacity: 0; }}
                    }}
                </style>
            </head>
            <body>
                <div class="fireworks">
                    <div class="firework"></div>
                    <div class="firework"></div>
                    <div class="firework"></div>
                    <div class="firework"></div>
                </div>
                
                <div class="emoji-rain">
                    <div class="emoji">🎉</div>
                    <div class="emoji">🎊</div>
                    <div class="emoji">⭐</div>
                    <div class="emoji">🏆</div>
                    <div class="emoji">🎈</div>
                    <div class="emoji">✨</div>
                    <div class="emoji">🌟</div>
                    <div class="emoji">🎁</div>
                    <div class="emoji">🚀</div>
                </div>
                
                <div class="container">
                    <div class="celebration-title">
                        🎉 恭喜达成里程碑！🎉
                    </div>
                    
                    <div class="celebration-subtitle">
                        GitHub仓库突破1万星标！
                    </div>
                    
                    <div class="milestone-info">
                        <div class="repo-name">🏆 {repo_key}</div>
                        <div class="milestone-stars">⭐ {current_stars:,} Stars</div>
                        <div class="milestone-message">这是一个重要的里程碑时刻！</div>
                    </div>
                    
                    {milestone_user_html if milestone_user_html else ''}
                    
                    <div class="celebration-footer">
                        🎈 让我们继续努力，迈向下一个里程碑！🚀
                    </div>
                </div>
            </body>
            </html>
            """
            
            # 使用本地Playwright渲染HTML为图片
            image_path = await self.render_html_to_image(html_template)
            return image_path
            
        except Exception as e:
            logger.error(f"GitHub Star Monitor: 创建庆祝图片失败: {e}")
            return ""
    async def send_image_notification(self, target_sessions: list, image_path: str):
        """发送图片通知到目标会话"""
        class MessageChain:
            def __init__(self, chain):
                self.chain = chain
        
        # 使用本地文件路径
        message_chain = MessageChain([Comp.Image.fromFileSystem(image_path)])
        
        for session_id in target_sessions:
            try:
                await self.context.send_message(session_id, message_chain)
                logger.info(f"GitHub Star Monitor: 已向会话 {session_id} 发送图片通知")
            except Exception as e:
                logger.error(f"GitHub Star Monitor: 向会话 {session_id} 发送图片通知失败: {e}")
        
        # 清理临时图片文件
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
                logger.debug(f"GitHub Star Monitor: 已清理临时图片文件: {image_path}")
        except Exception as e:
            logger.warning(f"GitHub Star Monitor: 清理临时图片文件失败: {e}")

    async def terminate(self):
        """插件卸载时调用"""
        if self.monitoring_task:
            self.monitoring_task.cancel()
        logger.info("GitHub Star Monitor: 插件已停止")
    
    async def send_text_notification(self, target_sessions: list, repo_key: str, change: int, current_stars: int):
        """发送文本通知"""
        change_text = f"+{change}" if change > 0 else str(change)
        message = f"🌟 GitHub仓库星标变动提醒\n\n"
        message += f"仓库: {repo_key}\n"        message += f"变动: {change_text}\n"
        message += f"当前星标数: {current_stars}\n"
        message += f"仓库链接: https://github.com/{repo_key}"
        await self.send_notification(target_sessions, message)
    
    async def send_text_notification_with_users(self, target_sessions: list, repo_key: str, change: int, current_stars: int, change_users: List[dict]):
        """发送包含用户信息的文本通知"""
        change_text = f"+{change}" if change > 0 else str(change)
        action_text = "点了star" if change > 0 else "取消了star"
        
        message = f"🌟 GitHub仓库星标变动提醒\n\n"
        message += f"📁 仓库: {repo_key}\n"
        message += f"📊 变动: {change_text}\n"
        message += f"⭐ 当前星标数: {current_stars}\n"
        
        # 添加导致变动的用户信息
        if change_users:
            message += f"\n👤 导致此次变动的用户:\n"
            for i, event in enumerate(change_users):
                user = event.get('actor', {})
                username = user.get('login', '未知用户')
                message += f"• @{username} {action_text}\n"
        
        message += f"\n🔗 仓库链接: https://github.com/{repo_key}"
        await self.send_notification(target_sessions, message)

    async def check_milestone_reached(self, last_stars: int, current_stars: int) -> bool:
        """检查是否达到1万star里程碑"""
        milestone = 10000
        return last_stars < milestone <= current_stars

    async def send_milestone_text_notification(self, target_sessions: list, repo_key: str, current_stars: int, change_users: List[dict]):
        """发送里程碑庆祝文本通知"""
        message = f"🎉🎊 恭喜！GitHub仓库达到1万star里程碑！🎊🎉\n\n"
        message += f"🏆 仓库: {repo_key}\n"
        message += f"⭐ 当前星标数: {current_stars:,}\n"
        message += f"📈 这是一个重要的里程碑！\n"
        
        # 添加第1万个star用户信息
        if change_users:
            message += f"\n🌟 第1万个star来自:\n"
            for event in change_users[:1]:  # 只显示第一个用户
                user = event.get('actor', {})
                username = user.get('login', '未知用户')
                message += f"👤 @{username} - 感谢你的支持！\n"
        
        message += f"\n🔗 仓库链接: https://github.com/{repo_key}\n"
        message += f"🎈 让我们继续努力，迈向下一个里程碑！"
        
        await self.send_notification(target_sessions, message)

    async def render_html_to_image(self, html_content: str) -> str:
        """使用本地Playwright将HTML渲染为图片"""
        try:
            # 确保data目录存在
            if not os.path.exists("data"):
                os.makedirs("data")
            
            image_path = f"data/star_notification_{int(time.time())}.png"
            
            async with async_playwright() as p:
                # 启动浏览器
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # 设置视口大小
                await page.set_viewport_size({"width": 800, "height": 600})
                
                # 设置HTML内容
                await page.set_content(html_content)
                
                # 等待页面加载完成
                await page.wait_for_load_state('networkidle')
                
                # 截图
                await page.screenshot(
                    path=image_path,
                    full_page=True,
                    type='png'
                )
                
                await browser.close()
                
                logger.info(f"GitHub Star Monitor: 成功生成通知图片: {image_path}")
                return image_path
                
        except Exception as e:
            logger.error(f"GitHub Star Monitor: Playwright渲染失败: {e}")
            return ""
    
    async def get_star_change_users(self, owner: str, repo: str, change_count: int) -> List[dict]:
        """获取导致此次星标变动的具体用户"""
        github_token = self.config.get("github_token", "").strip()
        if not github_token:
            return []
        
        try:
            if change_count > 0:
                # 新增star：获取最新的stargazers
                # 首先获取总的star数量来计算最后一页
                repo_info = await self.get_repo_info(owner, repo)
                if not repo_info:
                    return []
                
                total_stars = repo_info.get('stargazers_count', 0)
                per_page = 100  # GitHub API最大值
                
                # 计算最后一页
                last_page = max(1, (total_stars + per_page - 1) // per_page)
                
                url = f"https://api.github.com/repos/{owner}/{repo}/stargazers"
                
                headers = {
                    'User-Agent': 'AstrBot-GitHub-Star-Monitor/1.0.0',
                    'Accept': 'application/vnd.github.v3.star+json',  # 包含时间戳信息
                    'Authorization': f'Bearer {github_token}'
                }
                
                # 获取最后一页的数据（包含最新的star用户）
                params = {
                    'per_page': per_page,
                    'page': last_page
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            stargazers = await response.json()
                            
                            # 获取最新的几个用户（根据变动数量）
                            latest_stargazers = stargazers[-abs(change_count):] if stargazers else []
                            
                            # 转换为事件格式以保持兼容性
                            result_events = []
                            for stargazer in latest_stargazers:
                                event = {
                                    'type': 'WatchEvent',
                                    'actor': stargazer.get('user', {}),
                                    'created_at': stargazer.get('starred_at', datetime.now().isoformat() + 'Z')
                                }
                                result_events.append(event)
                            
                            # 按时间排序，最新的在前
                            result_events.sort(key=lambda x: x.get('created_at', ''), reverse=True)
                            
                            logger.info(f"GitHub Star Monitor: 获取到 {len(result_events)} 个最新star用户")
                            return result_events
                        else:
                            logger.warning(f"GitHub Star Monitor: 获取stargazers失败，状态码: {response.status}")
                            return []
            else:
                # 取消star：使用events API尝试获取最近的unstar事件
                return await self.get_recent_unstar_events(owner, repo)
                
        except Exception as e:
            logger.error(f"GitHub Star Monitor: 获取变动用户失败: {e}")
            return []
    
    async def get_repo_info(self, owner: str, repo: str) -> Optional[dict]:
        """获取GitHub仓库的详细信息"""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            
            headers = {
                'User-Agent': 'AstrBot-GitHub-Star-Monitor/1.0.0',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            github_token = self.config.get("github_token", "").strip()
            if github_token:
                headers['Authorization'] = f'Bearer {github_token}'
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"GitHub Star Monitor: 获取仓库信息失败，状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"GitHub Star Monitor: 获取仓库信息失败: {e}")
            return None

    async def get_recent_unstar_events(self, owner: str, repo: str) -> List[dict]:
        """尝试获取最近的unstar事件（这个功能有限，GitHub API不直接支持）"""
        try:
            # 由于GitHub API的限制，我们只能通过events API尝试获取
            # 但events API只能获取到最近的事件，无法确保获取到具体的unstar用户
            url = f"https://api.github.com/repos/{owner}/{repo}/events"
            
            headers = {
                'User-Agent': 'AstrBot-GitHub-Star-Monitor/1.0.0',
                'Accept': 'application/vnd.github.v3+json',
                'Authorization': f'Bearer {self.config.get("github_token", "")}'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        events = await response.json()
                        # 查找最近的WatchEvent（包括star和unstar）
                        watch_events = []
                        for event in events:
                            if event.get('type') == 'WatchEvent':
                                # 注意：GitHub的WatchEvent主要记录star操作，unstar较难追踪
                                watch_events.append(event)
                        
                        logger.info(f"GitHub Star Monitor: 找到 {len(watch_events)} 个最近的watch事件（可能包含unstar）")
                        return watch_events[:1]  # 返回最近的1个事件作为可能的unstar用户
                    else:
                        logger.warning(f"GitHub Star Monitor: 获取事件失败，状态码: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"GitHub Star Monitor: 获取unstar事件失败: {e}")
            return []