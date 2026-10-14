# -*- coding: utf-8 -*-
"""
微信 ClawBot —— 通过 iLink 官方机器人接口把微信接入大模型

消息流转总览（课件四步）：
    微信 App 发消息 → iLink 服务器暂存 → 本程序长轮询取回 → 调大模型 → 调 sendmessage 回复

十步流程（对应课件“微信 ClawBot（一）~（十）”）：
    1  命令行复读机（见 echo_bot.py）
    2  GET get_bot_qrcode 取登录二维码内容
    3  qrcode 库把内容画成 qr_wechat.png
    4  轮询 get_qrcode_status：wait → scaned → confirmed，拿到 bot_token 存 wx_token.txt
    5  组装请求头（Authorization Bearer + X-WECHAT-UIN）
    6  POST getupdates 长轮询收消息（服务器最多挂住约 35 秒，超时继续下一轮）
    7  解析消息：message_type==1 且 item_list 里 type==1 才是用户文字
    8  POST sendmessage 回消息（context_token 原样带回，才回到对应会话）
    9  串成 while True 主循环
    10 中间插入 ask_llm，复读机升级为 AI 机器人

用法：
    pip install -r requirements.txt
    python wechat_bot.py          # 首次运行生成 qr_wechat.png，用微信扫码确认
    python wechat_bot.py          # 已有 wx_token.txt 时直接上线收发
"""
import base64
import json
import random
import time
import uuid

import qrcode
import requests

from llm import ask_llm, DEFAULT_SYSTEM

BASE = "https://ilinkai.weixin.qq.com"
TOKEN_FILE = "wx_token.txt"
SYSTEM_PROMPT = DEFAULT_SYSTEM  # 人设，想换性格改这一句即可


# ---------- 第 2~4 步：扫码登录 ----------

def login():
    """取二维码 → 存图 → 等扫码确认 → 拿 bot_token。"""
    r = requests.get(BASE + "/ilink/bot/get_bot_qrcode",
                     params={"bot_type": 3}, timeout=30)
    data = r.json()
    open("qr_content.txt", "w", encoding="utf-8").write(
        json.dumps(data, ensure_ascii=False, indent=2))  # 留底方便排查
    qr_text = (data.get("qrcode_img_content") or data.get("qr_content")
               or data.get("qrcode_content") or data.get("content"))
    qrcode.make(qr_text).save("qr_wechat.png")
    print("已生成 qr_wechat.png，请用微信扫码并在手机上确认登录……")

    qr_id = data.get("qrcode") or data.get("qrcode_id") or qr_text
    while True:
        time.sleep(2)
        s = requests.get(BASE + "/ilink/bot/get_qrcode_status",
                         params={"qrcode": qr_id}, timeout=30).json()
        status = s.get("status")
        print("扫码状态:", status)  # wait → scaned → confirmed
        if status == "confirmed":
            token = s.get("bot_token") or s.get("token")
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(token)
            print("登录成功，token 已写入", TOKEN_FILE)
            return token


# ---------- 第 5 步：请求头 ----------

def get_headers(token):
    # X-WECHAT-UIN：一个数字的 base64，课件示例可固定（如 10086），这里随机生成
    uin = base64.b64encode(str(random.randint(10 ** 8, 10 ** 9)).encode()).decode()
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": "Bearer " + token,
        "X-WECHAT-UIN": uin,
    }


# ---------- 第 6 步：长轮询收消息 ----------

def get_updates(token, cursor):
    """服务器最多挂住约 35 秒；cursor 是书签，断线续传不丢消息。"""
    try:
        r = requests.post(BASE + "/ilink/bot/getupdates",
                          headers=get_headers(token),
                          json={"get_updates_buf": cursor},
                          timeout=45)
        return r.json()
    except requests.exceptions.RequestException:
        return None  # 超时/网络抖动：下一轮继续


# ---------- 第 7 步：解析消息 ----------

def parse_text(msg):
    """message_type==1 是用户消息；item_list 里 type==1 是文字（2图/3语音/4文件/5视频）。"""
    if msg.get("message_type") != 1:
        return None
    for item in msg.get("item_list", []):
        if item.get("type") == 1:
            return msg["from_user_id"], msg["context_token"], item["text_item"]["text"]
    return None


# ---------- 第 8 步：回消息 ----------

def send_text(token, uid, ctx, text):
    """context_token 必须原样带回——它决定回复落到哪个聊天窗口。"""
    requests.post(BASE + "/ilink/bot/sendmessage",
                  headers=get_headers(token),
                  json={"msg": {
                      "from_user_id": "",
                      "to_user_id": uid,
                      "client_id": "claw-" + uuid.uuid4().hex[:12],  # 全局唯一，防重
                      "message_type": 2,
                      "message_state": 2,
                      "context_token": ctx,
                      "item_list": [{"type": 1, "text_item": {"text": text}}],
                      "base_info": {"channel_version": "1.0.3"},
                  }}, timeout=30)


# ---------- 第 9+10 步：主循环，中间插大模型 ----------

def main():
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            token = f.read().strip()
    except FileNotFoundError:
        token = login()

    cursor = ""
    print("机器人已上线，开始长轮询（Ctrl+C 退出）……")
    while True:
        resp = get_updates(token, cursor)
        if not resp:
            continue
        cursor = resp.get("get_updates_buf", cursor)
        msgs = resp.get("msgs") or resp.get("msg_list") or []
        # 原始包留底：调试时直接看 last_msg.json
        with open("last_msg.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(msgs, ensure_ascii=False, indent=2))
        for msg in msgs:
            parsed = parse_text(msg)
            if not parsed:
                continue
            uid, ctx, text = parsed
            print("收到:", text)
            try:
                reply = ask_llm(text, system=SYSTEM_PROMPT)
            except Exception as e:  # 大模型挂了也不能让主循环死
                reply = "大模型出错了：" + str(e)
            print("回复:", (reply[:50] + "……") if len(reply) > 50 else reply)
            send_text(token, uid, ctx, reply)


if __name__ == "__main__":
    main()
