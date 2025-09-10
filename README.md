# AstrBot Wallabag 插件

一个智能的 Wallabag 插件：自动监听消息中的 URL 并保存到 Wallabag 服务；也支持指令手动保存。

## 功能特性
- 自动保存：检测消息中的 http/https 链接并保存
- 手动保存：/wallabag save <URL> 快速入库
- 去重缓存：避免重复保存同一 URL（本地缓存）
- OAuth2 认证：自动获取/刷新访问令牌
- 可配置：超时、重试、用户代理、是否自动保存等

## 安装与启用
1. 依赖安装：在插件目录执行 pip install -r requirements.txt
2. 放置目录：将本插件目录置于 AstrBot/data/plugins/astrbot_plugin_wallabag/
3. WebUI 启用：在 AstrBot WebUI 的插件管理中启用本插件

## 配置说明（WebUI）
必填项：
- wallabag_url（示例：https://wallabag.example.com）
- client_id、client_secret（在 Wallabag 开发者页面创建）
- username、password

可选项：
- uto_save（默认 true）是否自动检测并保存 URL
- equest_timeout（默认 30）请求总超时（秒）
- cache_max_size（默认 1000）本地已保存 URL 缓存上限
- dvanced_settings.token_refresh_buffer（默认 60）刷新令牌缓冲（秒）
- dvanced_settings.max_retry_attempts（默认 3）失败重试次数
- dvanced_settings.retry_delay（默认 2）重试间隔（秒）
- dvanced_settings.user_agent 自定义 UA
- dvanced_settings.skip_ssl_verify（默认 false）跳过 SSL 验证（仅测试用途）

## 使用方法
- 查看帮助：/wallabag help 或 /wb
- 手动保存：/wallabag save https://example.com/article
- 自动保存：发送包含 URL 的消息后，机器人将提示“📎 自动保存: 标题...”

## 注意事项
- 仅处理以 http:// 或 https:// 开头的 URL
- 运行时数据存储于 data/wallabag/ 下（如 saved_urls.json），请勿提交到仓库
- 若认证失败，请检查配置；网络错误将按设置进行重试并记录日志

## 许可证
MIT
