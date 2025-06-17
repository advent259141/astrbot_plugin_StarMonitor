# GitHub Star Monitor

GitHub仓库星标监控插件，用于监控指定GitHub仓库的星标变化并实时推送通知。

## 功能特点

- 🌟 **实时监控**: 每分钟检查一次指定仓库的星标数量
- 📢 **即时通知**: 星标数量发生变化时立即推送通知
- 👤 **精确用户追踪**: 显示导致此次星标变动的具体用户信息
- 🎨 **精美图片通知**: 支持Playwright本地渲染的美观通知卡片，包含用户头像和详细信息
- 🔧 **灵活配置**: 支持监控多个仓库，可配置多个接收通知的会话
- 📊 **状态查看**: 提供命令查看当前所有监控仓库的星标状态
- 🧪 **测试功能**: 支持发送测试消息验证通知功能
- 🔑 **认证支持**: 支持GitHub Token认证，避免API限制并获取详细用户信息

## 安装说明

若要使用图片功能，请在Astrbot/astrbot目录下安装chromium

playwright install chromium

## 配置说明

插件支持以下配置项：

### repositories (必填)
要监控的GitHub仓库列表，支持多种格式：
- 完整URL: `https://github.com/owner/repo`
- 短格式: `owner/repo`
- 每行一个仓库

示例：
```
https://github.com/microsoft/vscode
facebook/react
google/tensorflow
```

### target_sessions (必填)
接收通知的目标会话列表。需要填写会话的unified_msg_origin。

**获取会话ID的方法：**
1. 在目标群组或私聊中发送任意消息给机器人
2. 查看AstrBot日志，找到对应的unified_msg_origin
3. 将该ID添加到配置中

### github_token (强烈推荐)
GitHub Personal Access Token，用于避免API限制：
- **未认证**: 60次请求/小时
- **已认证**: 5000次请求/小时

**创建Token步骤：**
1. 进入 GitHub Settings > Developer settings > Personal access tokens > Fine-grained tokens
2. 点击 "Generate new token"
3. 选择要监控的仓库或所有仓库
4. 权限设置：只需要 **Metadata: Read** 权限
5. 复制生成的Token到配置中

### check_interval (可选)
检查间隔时间，单位为秒：
- 有Token时建议：30-60秒
- 无Token时建议：120秒以上（避免触发限制）

### enable_startup_notification (可选)
是否在插件启动时发送通知，默认为true。

### enable_image_notification (推荐)
是否启用图片通知，默认为true。开启后将使用HTML渲染生成精美的通知卡片，包含：
- 渐变背景和现代化设计
- 用户头像（圆形显示）
- 详细的仓库信息和变动统计
- 最近操作用户的信息和时间
- 响应式布局和hover效果

**注意**: 需要配置GitHub Token才能获取用户详细信息。

## 使用方法

### 命令列表

- `/star_status` - 查看当前监控的仓库星标状态
- `/star_test` - 发送测试消息验证通知功能
- `/star_force_check` - 强制检查所有仓库
- `/star_rate_limit` - 检查GitHub API使用限制

## 通知示例

### 文本通知格式：
```
🌟 GitHub仓库星标变动提醒

📁 仓库: microsoft/vscode
📊 变动: +2
⭐ 当前星标数: 162847

👤 导致此次变动的用户:
• @user1 点了star (12-25 14:30)
• @user2 点了star (12-25 14:32)

🔗 仓库链接: https://github.com/microsoft/vscode
```

### 图片通知特点：
- 渐变背景和现代化设计
- 显示导致变动的用户头像（圆形）
- 详细的仓库信息和变动统计
- 用户操作时间显示
- 响应式布局设计

## 注意事项

1. **GitHub API限制**: GitHub API对未认证请求有速率限制，建议不要将检查间隔设置过小
2. **网络连接**: 需要确保AstrBot服务器能够访问GitHub API
3. **会话ID**: 确保正确配置target_sessions，否则无法收到通知
4. **仓库格式**: 确保仓库URL格式正确，支持公开仓库的监控

---

**免责声明**: 本插件仅用于学习和个人使用，请遵守GitHub的使用条款和API使用规范。