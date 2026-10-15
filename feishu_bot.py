# -*- coding: utf-8 -*-
"""
飞书 ClawBot —— 自建应用 + WebSocket 长连接 + 流式消息卡片

与微信端的差异（课件对比表）：
    身份：自建应用（App ID / App Secret）而非扫码绑定
    收消息：WebSocket 长连接推送，而非主动长轮询——不用填公网地址
    回复载体：可修改的消息卡片（支持 Markdown），而非纯文字
    逐字显示：支持（CardKit 流式更新），微信不支持

开前准备（open.feishu.cn/app）：
    1. 创建自建应用，开启“机器人”能力
    2. 权限管理开通：im:message、im:message:send_as_bot、cardkit:card:write
    3. 事件订阅选“使用长连接接收事件”，添加事件 im.message.receive_v1
    4. 创建版本并发布（改配置后须重新发布）
    5. App ID / App Secret 写入环境变量 FS_APP_ID / FS_APP_SECRET，
       或当前目录 fs_app_id.txt / fs_app_secret.txt（Secret 就是密码，绝不外发）

运行：
    pip install -r requirements.txt
    python feishu_bot.py
"""
import json
import os
import sys
import time

# Windows 终端默认 GBK，打印 emoji 会 UnicodeEncodeError；改成容错输出
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import lark_oapi as lark
import requests
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from llm import ask_llm, DEFAULT_SYSTEM

SYSTEM_PROMPT = DEFAULT_SYSTEM

OPEN_BASE = "https://open.feishu.cn/open-apis"


def _load(name, env):
    v = os.environ.get(env)
    if v:
        return v.strip()
    with open(name, encoding="utf-8") as f:
        return f.read().strip()


APP_ID = _load("fs_app_id.txt", "FS_APP_ID")
APP_SECRET = _load("fs_app_secret.txt", "FS_APP_SECRET")


def tenant_token():
    """tenant_access_token 约 2 小时有效，每次发消息前现取即可。"""
    r = requests.post(OPEN_BASE + "/auth/v3/tenant_access_token/internal",
                      json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=30)
    return r.json()["tenant_access_token"]


# ---------- 回复载体一：纯文本（兜底） ----------

def send_plain(chat_id, text):
    token = tenant_token()
    requests.post(OPEN_BASE + "/im/v1/messages?receive_id_type=chat_id",
                  headers={"Authorization": "Bearer " + token},
                  json={"receive_id": chat_id, "msg_type": "text",
                        "content": json.dumps({"text": text})}, timeout=30)


# ---------- 回复载体二：流式消息卡片（CardKit 四步） ----------

def send_stream_card(chat_id, full_text):
    """
    四步流式输出：
      1. 建卡片实体并开启 streaming_mode
      2. 把卡片作为 interactive 消息发到会话
      3. 每隔约 0.3 秒全量替换一次 markdown 内容（sequence 严格递增，太密会被限流）
      4. 关闭流式模式，卡片定格
    任何一步失败抛异常，由调用方降级成纯文本。
    """
    token = tenant_token()
    headers = {"Authorization": "Bearer " + token}

    card = {"schema": "2.0",
            "config": {"streaming_mode": True},
            "body": {"elements": [
                {"tag": "markdown", "element_id": "md", "content": ""}]}}
    r = requests.post(OPEN_BASE + "/cardkit/v1/cards", headers=headers,
                      json={"type": "card_json", "data": json.dumps(card)},
                      timeout=30)
    card_id = r.json()["data"]["card_id"]

    r = requests.post(OPEN_BASE + "/im/v1/messages?receive_id_type=chat_id",
                      headers=headers,
                      json={"receive_id": chat_id, "msg_type": "interactive",
                            "content": json.dumps(
                                {"type": "card", "data": {"card_id": card_id}})},
                      timeout=30)
    if r.json().get("code") != 0:
        raise RuntimeError("发卡片消息失败: " + r.text)

    seq = 0
    step = max(1, len(full_text) // 40)  # 约 40 帧刷完
    for i in range(step, len(full_text) + step, step):
        seq += 1
        piece = full_text[:i]
        requests.put(OPEN_BASE + f"/cardkit/v1/cards/{card_id}"
                     f"/elements/md/content",
                     headers=headers,
                     json={"content": piece, "sequence": seq}, timeout=30)
        time.sleep(0.3)
        if i >= len(full_text):
            break

    seq += 1
    requests.post(OPEN_BASE + f"/cardkit/v1/cards/{card_id}/settings",
                  headers=headers,
                  json={"settings": json.dumps(
                            {"config": {"streaming_mode": False}}),
                        "sequence": seq}, timeout=30)


# ---------- 收消息：WebSocket 长连接事件 ----------

def on_msg(data: P2ImMessageReceiveV1):
    msg = data.event.message
    sender = data.event.sender
    if sender.sender_type == "app":      # 机器人自己发的消息——不处理，防自回环死循环
        return
    if msg.message_type != "text":
        send_plain(msg.chat_id, "目前只看得懂文字消息哦")
        return
    text = json.loads(msg.content).get("text", "").strip()
    if not text:
        return
    print("收到:", text)
    try:
        reply = ask_llm(text, system=SYSTEM_PROMPT)
    except Exception as e:
        reply = "大模型出错了：" + str(e)
    try:
        send_stream_card(msg.chat_id, reply)   # 首选：流式卡片，逐字显示
    except Exception as e:
        print("卡片失败，降级纯文本:", e)
        send_plain(msg.chat_id, reply)         # 兜底：纯文本


def main():
    handler = (lark.EventDispatcherHandler.builder("", "")
               .register_p2_im_message_receive_v1(on_msg)
               .build())
    print("飞书机器人已上线，长连接接收事件中（Ctrl+C 退出）……")
    lark.ws.Client(APP_ID, APP_SECRET,
                   event_handler=handler,
                   log_level=lark.LogLevel.INFO).start()


if __name__ == "__main__":
    main()
