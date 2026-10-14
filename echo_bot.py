# -*- coding: utf-8 -*-
"""
第零步：命令行复读机
先把“收消息 → 回消息”这个最小循环跑通，再谈接网络、接大模型。
运行：python echo_bot.py
输入 quit 退出。
"""

while True:
    text = input("你: ")
    if text == "quit":
        break
    print("机器人: " + text)
