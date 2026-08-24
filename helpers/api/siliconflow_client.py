# helpers/api/siliconflow_client.py
"""
封装对 siliconflow (DeepSeek-V3) 的请求（保留原脚本的 payload / header 结构）
"""
import requests
import json

def siliconflow_chat_completion(model: str, messages: list, auth_header: str):
    url = "https://api.siliconflow.cn/v1/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": 1048,
        "stop": None,
        "temperature": 0.7,
        "top_p": 0.7,
        "top_k": 50,
        "frequency_penalty": 0.5,
        "n": 1,
        "response_format": {"type": "text"},
        "tools": [
            {
                "type": "function",
                "function": {
                    "description": "<string>",
                    "name": "<string>",
                    "parameters": {},
                    "strict": False
                }
            }
        ]
    }

    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }

    response = requests.request("POST", url, json=payload, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"siliconflow 请求失败：{response.status_code} {response.text}")
    return response.json()
