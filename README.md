# TouchGal 游戏搜索插件

一个 AstrBot 插件，用于从 [TouchGal](https://www.touchgal.top) 和 [书音的图书馆](https://shionlib.com) 搜索游戏资源链接。

## ✨ 功能特性

- 🔍 **指令搜索**：通过 `/搜索 <游戏名>` 命令搜索资源
- 🤖 **自动搜索**：检测群聊中的资源请求，自动搜索并返回结果
- 🧰 **Agent 工具**：注册 `search_galgame_resources`，可供大模型按需调用
- 📦 **合并转发**：资源以合并转发消息形式发送，自动搜索会按 TouchGal 游戏拆成独立合并转发
- 🖼 **图片展示**：TouchGal 游戏横幅和书音封面会随推荐/资源一起展示
- 📚 **多站点支持**：同时显示 TouchGal 和书音的图书馆的搜索结果
- 🔐 **NSFW 支持**：一键开关即可搜索 NSFW 内容
- 🎯 **群聊过滤**：支持白名单/黑名单模式，控制自动搜索生效范围

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
| `shionlib_limit` | int | 3 | 返回的书音推荐数量 |
| `show_nsfw` | bool | false | 开启后可搜索 NSFW 内容 |
| `session_timeout` | int | 60 | 搜索会话超时时间（秒） |
| `auto_search_enabled` | bool | false | 启用自动搜索功能 |
| `auto_search_suggest_limit` | int | 5 | 自动搜索时显示的相关游戏推荐数量 |
| `auto_search_shionlib` | bool | true | 自动搜索时同时搜索书音 |
| `auto_search_silent` | bool | true | 静默模式（搜不到不回复） |
| `auto_search_pattern` | string | 正则表达式 | 自动搜索的匹配模式 |
| `auto_search_group_mode` | string | `blacklist` | 群聊过滤模式（whitelist/blacklist） |
| `auto_search_group_list` | list | `[]` | 群号列表，配合过滤模式使用 |

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

### Agent 工具

插件会注册 `search_galgame_resources` 工具，供 AstrBot Agent 在对话中搜索 Galgame 资源。

参数：
- `keyword`：游戏名称或搜索关键词

### 群聊过滤

通过 `auto_search_group_mode` 和 `auto_search_group_list` 配置可控制自动搜索的生效范围：

- **白名单模式**（`whitelist`）：只有列表中的群聊会触发自动搜索
- **黑名单模式**（`blacklist`）：列表中的群聊被屏蔽，其他群聊正常触发
- 列表为空时不启用任何过滤

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
🎮 共 2 个相关游戏
📦 共 5 个资源

━━ 游戏 1 ━━
🖼 https://cloud.touchgaloss.com/patch/xxx/banner/banner.avif
🎮 千恋万花
📦 共 2 个资源
▶ 点击访问
https://www.touchgal.top/xxxx

同一游戏的资源会跟在游戏信息后，作为该游戏合并转发内的独立节点。
```

## 📋 平台支持

| 平台 | 消息格式 | 说明 |
|------|----------|------|
| aiocqhttp（QQ） | 合并转发 | 完整支持，资源以合并转发消息展示 |
| Telegram/其他 | 单条消息 | 自动降级为单条文本消息，避免刷屏 |

> 💡 插件会自动检测平台类型并选择最合适的消息格式

## 📝 更新日志

查看完整更新日志请访问 [CHANGELOG.md](CHANGELOG.md)

## 📄 许可

MIT License
