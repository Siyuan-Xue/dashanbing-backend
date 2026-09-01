# FastAPI Auth Demo（本地演示）

这是一个用于本地学习和验证认证流程的 FastAPI 小型示例。

## 环境准备

- Python 3.10 或更高版本
- 已安装 [uv](https://docs.astral.sh/uv/)

在项目目录执行：

```bash
uv sync
uv run fastapi dev
```

开发服务器默认地址为 <http://127.0.0.1:8000>。运行测试：

```bash
uv run pytest
```

## 接口

- `GET /`：返回演示服务状态。
- `POST /auth/register`：以 JSON 注册用户，例如
  `{"username":"alice","password":"secret"}`。成功返回用户公开信息。
- `POST /auth/token`：使用 OAuth2 密码表单登录；提交
  `application/x-www-form-urlencoded` 字段 `username` 和 `password`，成功返回 Bearer 访问令牌。
- `GET /users/me`：需要在请求头提供 `Authorization: Bearer <access_token>`，返回当前用户公开信息。
- `GET /docs`：打开 Swagger UI 交互式接口文档。

访问令牌使用 HS256 签名，有效期为 30 分钟。可通过环境变量覆盖本地密钥：

```bash
JWT_SECRET_KEY='your-local-secret' uv run fastapi dev
```

代码中的 fallback JWT secret 和自动创建数据库表仅是本地演示便利设置，并非生产环境默认值。

## 重置演示

停止服务器后，删除项目根目录的 `demo.db` 即可清空用户和重新开始：

```bash
rm demo.db
```

下次启动时会自动创建数据库表。
