# 合拍 API 后端原型

此目录包含模型适配器和早期 API 基础：访客会话、一次性长期记忆同意、加密保存对话和记忆事件、记忆读取/单条删除/删除全部数据。它未接入微信登录、生产级内容审核或真实候选人匹配，尚不可面向公众上线。

## 当前选择

代码按阿里云百炼华北 2（北京）OpenAI 兼容接口预留 `qwen-flash`。这只是模型接入候选，不代表模型已配置或已经核验可用于该产品。模型供应商会处理送入 API 的聊天内容；记忆未开启时，后端不持久化该次对话，但仍会发送本次请求生成回复。长期记忆开启后，应用数据库会加密保存用户与 AI 消息和记忆事件。上线前必须明确披露并核验模型供应商的数据处理方式、处理地点、保存期限和协议。API Key 必须保留在服务器环境变量中。官方接口与定价信息见[百炼接口文档](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)和[模型价格页](https://help.aliyun.com/zh/model-studio/qwen-flash)。

## 本地准备

1. 安装 Python 3.11 或更新版本。
2. 安装依赖：`python -m pip install -r requirements.txt`。
3. 配置本地或托管 PostgreSQL 的 `DATABASE_URL`。本地临时开发可设为 `sqlite:///./hepai-local.db`。
4. 生成并设置随机 `SESSION_SECRET` 和 `DATA_ENCRYPTION_KEY`。可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成会话密钥，用 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成数据加密密钥。妥善保管数据密钥；丢失后无法解密备份。
5. 配置 `BAILIAN_BASE_URL`、`BAILIAN_API_KEY`、`BAILIAN_MODEL`、`BAILIAN_TIMEOUT_SECONDS`。Key 只放在本地/服务器环境变量中，不要提交 `.env`。
6. 本地启动：`uvicorn main:app --host 127.0.0.1 --port 8000`。开发时可将 `COOKIE_SECURE=false`；部署到 HTTPS 后必须设为 `true`。

调用示例（从 Python 服务端调用，不要在浏览器 JavaScript 或小程序代码中调用）：

```python
from bailian_client import chat_completion

answer = await chat_completion([
    {"role": "system", "content": "合拍交友画像助手的系统提示词"},
    {"role": "user", "content": "我希望认识什么样的人？"},
])
```

## 当前边界和公网启用前的工作

- `main.py` 创建的是访客会话，不是实名/微信正式账号；当前没有微信 `code2session` 登录。
- 长期同意后，访客聊天和原话会以应用层加密写入数据库；用户可查看、导出记忆、删除单条记忆或删除全部访客数据。删除单条记忆会保留原始聊天记录。相关 API 的密钥、数据库和 cookie 配置都必须在服务器端管理。
- 当前内容拦截只是少量关键词规则，无法可靠识别变形文本、语境或新型有害内容；模型提示词也不是内容审核。后端不得直接开放公网。
- 记忆检索目前是基于近期事件和文本重合的早期方案，尚未实现经过验证的长期画像总结、语义检索和人物匹配质量评估。
- `/api/chat` 接收 `topic_id`，只在顺序符合时记录初始话题；真人匹配 API 和服务端年龄验证仍需实现。前端原型可连接这些开发 API，但前端门槛不能替代服务端授权或匹配校验。
- 数据表通过 SQLAlchemy `create_all` 创建，尚未建立正式迁移、备份恢复和数据保留/清理流程。现有记忆检索只用于早期演示，不能视为经过评估的画像或匹配算法。

公网启用前还必须接入：

- 微信或其他正式账号认证、用户数据隔离和会话授权。
- 记忆授权记录、数据加密、导出/删除/撤回同意能力。
- 服务端内容审核与安全处置；模型提示词不能代替审核服务。
- PostgreSQL 持久化的消息、记忆时间线、初始交流进度和匹配偏好。
- 服务端验证 10 个核心话题完成后，才允许请求真人匹配。
- 登录、年龄保护、投诉举报、安全事件处置、时长提醒和运营审核流程。
- 中国大陆云环境、TLS、密钥管理、日志脱敏、访问控制和必要的备案/登记/安全评估。

这些控制尚未实现前，不要把此目录单独部署为面向公众的交友服务。
