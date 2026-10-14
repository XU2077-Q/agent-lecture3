# -*- coding: utf-8 -*-
"""
大模型调用封装（OpenAI 兼容接口）
任何兼容 /chat/completions 的服务都能用：OpenAI、DeepSeek、通义、Kimi、火山方舟……
只要改 LLM_BASE / LLM_MODEL / 密钥即可。

密钥三选一（优先级从高到低）：
    1. 环境变量 LLM_KEY
    2. 当前目录 llm_key.txt（已在 .gitignore 中，绝不提交）
"""
import os

import requests

LLM_BASE = os.environ.get("LLM_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

# 默认人设：system 角色消息，决定机器人“是谁、怎么说话”
DEFAULT_SYSTEM = "你是一个乐于助人的中文智能助手，回答简洁友好。"


def load_key():
    key = os.environ.get("LLM_KEY")
    if key:
        return key.strip()
    with open("llm_key.txt", encoding="utf-8") as f:
        return f.read().strip()


def ask_llm(text, system=DEFAULT_SYSTEM):
    """整段问、整段答：微信端拿到完整回复后一次发出。"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})  # 人设
    messages.append({"role": "user", "content": text})
    r = requests.post(
        LLM_BASE + "/chat/completions",
        headers={"Authorization": "Bearer " + load_key()},
        json={"model": LLM_MODEL, "messages": messages},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


if __name__ == "__main__":
    # 课件里的人设例子：周杰伦粉丝
    print(ask_llm("你觉得周杰伦怎么样",
                  system="你是周杰伦的粉丝，回答都向着偶像"))
