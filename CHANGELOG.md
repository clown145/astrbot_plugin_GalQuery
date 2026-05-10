# Changelog

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
