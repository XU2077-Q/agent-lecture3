# Agent 外部通讯 · 第三讲课后任务

中山大学《软工新生研讨实践》第三讲课后任务：**把微信或飞书接入你的 AI 模型**。
本仓库两个平台都实现了，另附课件讲解与 Agent 功能说明两份 Word 文档（`docs/`）。

## 仓库结构

| 文件 | 说明 |
|---|---|
| `echo_bot.py` | 第零步：命令行复读机，最小“收→回”循环 |
| `llm.py` | 大模型调用封装（OpenAI 兼容接口，可换任意服务商）+ 人设 |
| `wechat_bot.py` | 微信 ClawBot：iLink 扫码登录 → 长轮询收消息 → 调大模型 → 回消息 |
| `feishu_bot.py` | 飞书 ClawBot：WebSocket 长连接收消息 → 调大模型 → CardKit 流式卡片回复（失败自动降级纯文本） |
| `docs/第三讲-讲解.docx` | 课件逐节讲解 + 术语解释 |
| `docs/Agent功能说明.docx` | 本 Agent 的主要功能说明 |
| `gen_docs.py` | 生成上述两份 Word 的脚本 |

## 快速开始

```bash
pip install -r requirements.txt
```

### 0. 命令行复读机

```bash
python echo_bot.py      # 输入 quit 退出
```

### 1. 配置大模型密钥

任选其一：

- 环境变量：`LLM_KEY`（可选 `LLM_BASE`、`LLM_MODEL`，默认 OpenAI `gpt-4o-mini`）
- 当前目录新建 `llm_key.txt`，粘贴密钥（已在 `.gitignore`）

换国产模型示例（DeepSeek）：

```bash
export LLM_BASE=https://api.deepseek.com/v1
export LLM_MODEL=deepseek-chat
```

### 2. 微信端

```bash
python wechat_bot.py
```

首次运行生成 `qr_wechat.png`，微信扫码并在手机上确认；登录态写入 `wx_token.txt`，之后启动直接上线。

### 3. 飞书端

1. [open.feishu.cn/app](https://open.feishu.cn/app) 创建自建应用，开启机器人能力
2. 权限：`im:message`、`im:message:send_as_bot`、`cardkit:card:write`
3. 事件订阅选“使用长连接接收事件”，添加 `im.message.receive_v1`
4. 创建版本并发布
5. App ID / App Secret 写入环境变量 `FS_APP_ID` / `FS_APP_SECRET`（或 `fs_app_id.txt` / `fs_app_secret.txt`）

```bash
python feishu_bot.py
```

## 安全须知

`llm_key.txt`、`wx_token.txt`、`fs_app_secret.txt` 等密钥文件全部在 `.gitignore` 中，
**永远不会被提交**。App Secret 就是密码，不要发给任何人、不要截图外传。
