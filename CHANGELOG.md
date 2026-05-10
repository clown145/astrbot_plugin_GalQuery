# Changelog

## v1.0.16
- fix: 修复 TouchGal 资源嵌套合并转发无法发送
  - 不再把 `Nodes` 放进 `Node.content`，避免生成 QQ/OneBot 不接受的嵌套消息段
  - 自动搜索中每个 TouchGal 游戏改为独立合并转发，游戏信息和该游戏资源在同一条转发内展示

## v1.0.15
- feat: 尝试 TouchGal 资源嵌套合并转发
  - 自动搜索中每个 TouchGal 游戏作为外层节点，资源作为该游戏节点内的嵌套转发
  - 保留文本平台的扁平降级展示

## v1.0.14
- feat: 自动搜索按 TouchGal 游戏分组展示资源
  - 搜到多个 TouchGal 游戏时，合并转发按“游戏信息 -> 该游戏资源”顺序排列
  - 保持单层合并转发结构，避免嵌套转发在 QQ 端不稳定

## v1.0.13
- feat: 增加 TouchGal 游戏图片展示
  - 从 TouchGal 搜索结果或详情页提取游戏 `banner` 图片
  - QQ 合并转发优先发送转换后的本地图片，转换失败时退回图片链接文本

## v1.0.12
- feat: 恢复书音封面图片展示
  - 基于 `t.shionlib.com` 真实图片地址，在合并转发节点中重新发送封面图片

## v1.0.11
- fix: 修正 `metadata.yaml` 插件名格式
  - 将 `name` 改为合法插件 ID `astrbot_plugin_galquery`
  - 将中文展示名移动到 `display_name`

## v1.0.10
- fix: 收窄书音封面图床修复范围，避免影响插件加载
  - 移除 1.0.9 新增的图片域名配置项
  - 仅在解析封面 URL 时将 `shionlib.com/game/` 修正为 `t.shionlib.com/game/`

## v1.0.9
- fix: 修正书音封面图真实图床域名
  - 将 `/game/.../cover/...` 封面路径解析到 `t.shionlib.com`
  - 兼容 Next.js 图片代理中的编码图源，避免生成不可下载的 `shionlib.com` 封面链接

## v1.0.8
- fix: 修复 QQ 合并转发中书音封面导致发送失败的问题
  - 避免在合并转发节点内直接发送 `.webp` 封面图
  - 改为展示封面链接，防止 aiocqhttp 返回 unsupported file type

## v1.0.7
- feat: 优化书音推荐展示
  - 为书音推荐结果增加封面图
  - 将 `shionlib_limit` 默认值从 `1` 调整为 `3`
- feat: 注册 Agent 工具
  - 新增 `search_galgame_resources` 工具，供大模型搜索 Galgame 资源
  - 复用现有 TouchGal 与书音搜索逻辑，返回非交互式文本结果

## v1.0.6
- fix: 修复 TouchGal 最近无法搜索的问题
  - 补充 `X-Requested-With: kun-fetch` 请求头，兼容站点新的来源校验
  - 调整搜索请求参数，兼容当前前端接口行为
  - 兼容 TouchGal 新的资源接口返回结构，恢复资源链接获取
- fix: 修复书音搜索结果标题偶发只显示首字的问题
  - 改为解析当前 Next.js 搜索页脚本数据，不再依赖旧的首页 HTML 正则
  - 兼容高亮标签和转义内容，恢复完整游戏标题提取

## v1.0.5
- feat: 添加群聊过滤功能
  - 新增 `auto_search_group_mode` 配置项：支持白名单/黑名单模式切换
  - 新增 `auto_search_group_list` 配置项：配置要过滤的群号列表
  - 白名单模式下，只有列表中的群聊会触发自动搜索
  - 黑名单模式下，列表中的群聊将被屏蔽

<details>
<summary>点击展开历史版本更新</summary>

## v1.0.4
- Update repository link in metadata.yaml

## v1.0.3
- feat: 添加插件文档并更新元数据配置
- 修复书音首页正则匹配
- 新增书音首页推荐功能
- 增加是否同时搜索书音的开关
- 优化图片下载逻辑：使用 URL 下载，增加超时时限

## v1.0.2
- 增加对其他平台的支持
- 添加 TouchGal 资源链接显示
- 增加书音的图书馆站点支持
- 移除 requests 依赖
- 优化显示效果和日志记录
- 多次修复和优化正则匹配规则
- 更新插件文档和版本号

## v1.0.0
- Initial commit & Add files via upload

</details>
