# TouchGal 游戏搜索插件

一个 AstrBot 插件，用于从 [TouchGal](https://www.touchgal.top) 和 [书音的图书馆](https://shionlib.com) 搜索游戏资源链接。

## ✨ 功能特性

- 🔍 **指令搜索**：通过 `/搜索 <游戏名>` 命令搜索资源
- 🤖 **自动搜索**：检测群聊中的资源请求，自动搜索并返回结果
- 📦 **合并转发**：资源以合并转发消息形式发送，每个资源独立展示
- 📚 **多站点支持**：同时显示 TouchGal 和书音的图书馆的搜索结果
- 🔐 **NSFW 支持**：一键开关即可搜索 NSFW 内容

## 📦 安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/clown145/astrbot_plugin_touchgal
```

## ⚙️ 配置说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `touchgal_domain` | string | `www.touchgal.top` | TouchGal 网站域名 |
| `shionlib_domain` | string | `shionlib.com` | 书音的图书馆网站域名 |
| `shionlib_enabled` | bool | true | 启用书音的图书馆推荐 |
| `shionlib_limit` | int | 1 | 返回的书音推荐数量 |
| `show_nsfw` | bool | false | 开启后可搜索 NSFW 内容 |
| `session_timeout` | int | 60 | 搜索会话超时时间（秒） |
| `auto_search_enabled` | bool | false | 启用自动搜索功能 |
| `auto_search_suggest_limit` | int | 5 | 自动搜索时显示的相关游戏推荐数量 |
| `auto_search_silent` | bool | true | 静默模式（搜不到不回复） |
| `auto_search_pattern` | string | 正则表达式 | 自动搜索的匹配模式 |

## 🎮 使用方法

### 指令搜索

```
/搜索 <游戏名称>
```

返回搜索结果列表后：
- 输入数字选择游戏
- 输入 `p` 下一页
- 输入 `q` 上一页
- 输入 `e` 退出搜索

### 自动搜索

启用 `auto_search_enabled` 后，群聊中发送以下句式会自动触发搜索：

- "有没有xxx资源"
- "求xxx"
- "谁有xxx"
- "大佬有没有xxx"
- ...

静默模式下只有搜到资源才会回复。

## 📱 消息格式预览

```
📚 书音的图书馆
━━━━━━━━━━
📍 shionlib.com

━━ 推荐 1 ━━
🎮 千恋＊万花
▶ 点击访问
https://shionlib.com/zh/game/708

📦 TouchGal 资源站
━━━━━━━━━━
📍 www.touchgal.top
🎮 千恋万花
📦 共 2 个资源

━━ 资源 1 ━━
📦 汉化组版本
▶ 下载链接
https://pan.baidu.com/xxx
```

## 📋 平台支持

- ✅ aiocqhttp（QQ 个人号）- 完整支持，包括合并转发消息
- ⚠️ 其他平台 - 基础功能可用，合并转发可能不支持

## 📄 许可

MIT License
