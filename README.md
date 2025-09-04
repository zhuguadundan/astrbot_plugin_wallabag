# AstrBot Wallabag插件

一个智能的Wallabag插件，可以自动监听用户发送的URL消息并保存到Wallabag服务中。

## 功能特性

- 🔗 **自动保存URL**: 自动检测消息中的URL并保存到Wallabag
- 📝 **手动保存**: 支持通过指令手动保存指定URL
- 🔄 **智能缓存**: 避免重复保存相同的URL
- 🔐 **安全认证**: 基于OAuth2的安全认证机制
- ⚙️ **灵活配置**: 丰富的配置选项，支持自动保存开关
- 🛡️ **错误处理**: 完善的错误处理和日志记录

## 安装配置

### 1. 环境要求

- AstrBot >= 3.4.0
- Python >= 3.8
- aiohttp >= 3.8.0

### 2. 安装插件

将插件文件夹 `astrbot_plugin_wallabag` 放置到AstrBot的插件目录中，然后在WebUI的插件管理页面启用该插件。

### 3. 配置Wallabag

#### 3.1 创建OAuth客户端

1. 登录您的Wallabag实例
2. 访问开发者页面：`https://your-wallabag-domain.com/developer/client/create`
3. 填写应用信息：
   - **应用名称**: `AstrBot Wallabag Plugin`
   - **重定向URL**: 可以填写任意有效的URL（如 `http://localhost:8080`）
4. 创建客户端后，记录 **Client ID** 和 **Client Secret**

#### 3.2 插件配置

在AstrBot WebUI的插件管理页面，找到Wallabag插件并点击"管理"，然后配置以下参数：

**必需配置**：
- `wallabag_url`: 您的Wallabag服务器地址（如：`https://wallabag.example.com`）
- `client_id`: OAuth客户端ID
- `client_secret`: OAuth客户端密钥
- `username`: Wallabag用户名
- `password`: Wallabag密码

**可选配置**：
- `auto_save`: 是否自动保存URL（默认：`true`）
- `request_timeout`: 请求超时时间（默认：`30`秒）
- `cache_max_size`: 缓存最大数量（默认：`1000`）
- `debug_mode`: 调试模式（默认：`false`）

## 使用方法

### 自动保存URL

启用插件后，当您发送包含URL的消息时，插件会自动检测并保存到Wallabag：

```
用户：看看这个有趣的网站：https://example.com/article
机器人：📎 自动保存: 有趣的文章标题...
```

### 手动保存URL

使用指令手动保存指定URL：

```
/wallabag save https://example.com/article
```

### 查看帮助

```
/wallabag
```

## 指令列表

| 指令 | 功能 | 示例 |
|------|------|------|
| `/wallabag` | 显示帮助信息 | `/wallabag` |
| `/wallabag save <URL>` | 手动保存URL | `/wallabag save https://example.com` |

## 注意事项

1. **URL格式**: 只支持 `http://` 和 `https://` 开头的URL
2. **重复URL**: 插件会缓存已保存的URL，避免重复保存
3. **网络超时**: 如果保存失败，请检查网络连接和Wallabag服务状态
4. **认证失败**: 如果出现认证错误，请检查配置的用户名密码和OAuth凭证
5. **缓存文件**: 插件会在 `data/wallabag/` 目录下创建缓存文件

## 故障排除

### 常见问题

**Q: 保存URL时提示"配置不完整"**
A: 请检查插件配置是否完整填写了所有必需参数

**Q: 提示"无法获取访问令牌"**
A: 请检查Wallabag服务器地址、用户名密码和OAuth凭证是否正确

**Q: 保存失败但配置正确**
A: 请检查网络连接，Wallabag服务是否正常运行，查看调试日志获取详细错误信息

**Q: 自动保存功能不工作**
A: 请检查 `auto_save` 配置是否设置为 `true`

### 日志查看

启用 `debug_mode` 配置可以查看更详细的日志信息，帮助定位问题。

## 开发信息

- **作者**: AstrBot Developer
- **版本**: 1.0.0
- **仓库**: https://github.com/astrbot/astrbot_plugin_wallabag
- **许可证**: MIT

## 支持

如有问题或建议，请：
1. 查看AstrBot官方文档：https://astrbot.app
2. 在GitHub仓库提交Issue
3. 在社区论坛寻求帮助
