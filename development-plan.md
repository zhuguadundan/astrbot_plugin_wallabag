# AstrBot Wallabag插件开发计划

## 项目概述
开发一个AstrBot插件，监听用户发送的URL消息，自动调用Wallabag API进行网页剪藏。

## 开发步骤

### 1. 插件基础架构搭建
- 创建插件目录结构
- 编写`metadata.yaml`配置文件，包含插件名称、作者、描述等信息
- 创建`main.py`主文件，实现基础插件类继承Star
- 创建`requirements.txt`文件，声明依赖（如aiohttp用于异步HTTP请求）

### 2. Wallabag API集成
- **认证模块**：
  - 实现OAuth2认证流程，获取access_token
  - 处理token过期和刷新机制
  - 支持client_id、client_secret、username、password配置

- **API封装模块**：
  - 封装Wallabag API调用（添加文章、获取文章列表、删除文章等）
  - 使用aiohttp实现异步HTTP请求
  - 完善的错误处理和响应解析

### 3. 消息监听与URL检测
- **消息监听器**：
  - 使用`@filter.event_message_type(filter.EventMessageType.ALL)`监听所有消息
  - 实现URL正则匹配检测（支持http/https协议）
  - 过滤重复URL和无效URL

- **指令功能**：
  - `/wallabag` - 显示帮助信息
  - `/wallabag save <url>` - 手动保存指定URL
  - `/wallabag list` - 查看已保存文章列表
  - `/wallabag delete <id>` - 删除指定文章

### 4. 配置管理系统
- **配置文件设计**：
  - 创建`_conf_schema.json`配置模式文件
  - 包含Wallabag服务器地址、认证信息等配置项
  - 支持配置热重载

- **配置项**：
  - `wallabag_url`: Wallabag服务器地址
  - `client_id`: OAuth客户端ID
  - `client_secret`: OAuth客户端密钥
  - `username`: 用户名
  - `password`: 密码
  - `auto_save`: 是否自动保存检测到的URL（默认开启）

### 5. 核心功能实现
- **自动保存功能**：
  - 监听用户消息，自动检测URL
  - 调用Wallabag API保存文章
  - 向用户反馈保存结果（成功/失败）

- **手动保存功能**：
  - 通过指令手动保存URL
  - 支持批量URL处理

- **文章管理功能**：
  - 查看已保存文章列表
  - 删除指定文章
  - 获取文章详情

### 6. 用户交互与反馈
- **响应消息设计**：
  - 保存成功的确认消息
  - 保存失败的错误提示（包含具体错误信息）
  - 文章列表的格式化显示
  - 帮助信息和使用说明

- **消息格式**：
  - 使用富文本消息提升用户体验
  - 支持Markdown格式（如果平台支持）
  - 错误信息的友好提示

### 7. 错误处理与日志
- **错误处理机制**：
  - 网络连接错误处理
  - API认证失败处理
  - URL无效处理
  - Wallabag服务器错误处理

- **日志记录**：
  - 使用astrbot.api.logger记录操作日志
  - 记录成功保存的文章信息
  - 记录错误和异常信息

### 8. 数据持久化
- **本地缓存**：
  - 缓存access_token和refresh_token
  - 缓存已保存文章信息（避免重复保存）
  - 在插件data目录下存储数据

### 9. 测试与优化
- **功能测试**：
  - URL检测准确性测试
  - Wallabag API调用测试
  - 各种错误场景测试

- **性能优化**：
  - 异步操作优化
  - 网络请求超时处理
  - 内存使用优化

### 10. 文档与部署
- **使用文档**：
  - 编写README.md，包含安装和配置说明
  - 提供Wallabag服务器搭建指引
  - 常见问题解答

- **插件发布**：
  - 代码格式化（使用ruff）
  - 版本号管理
  - 提交到AstrBot插件市场

## 技术要点
- 使用异步编程（asyncio）提高性能
- 遵循AstrBot插件开发规范
- 完善的错误处理和用户反馈
- 灵活的配置管理
- 安全的认证信息存储

## 开发进度
- [x] 创建插件目录结构和基础文件
- [ ] 编写metadata.yaml配置文件
- [ ] 创建requirements.txt依赖文件
- [ ] 实现main.py基础插件类
- [ ] 实现Wallabag API认证模块
- [ ] 封装Wallabag API调用功能
- [ ] 实现URL检测和消息监听
- [ ] 创建配置系统_conf_schema.json
- [ ] 实现自动保存功能
- [ ] 实现手动指令功能
- [ ] 实现文章管理功能
- [ ] 完善错误处理和日志记录
- [ ] 实现数据持久化缓存
- [ ] 测试所有功能
- [ ] 编写使用文档