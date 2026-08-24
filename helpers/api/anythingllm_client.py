# helpers/api/anythingllm_client.py
"""
保留你原始的 ask_anythingllm 函数实现（尽量不改动任何字段/变量名/逻辑）。
"""
import requests
import json

def ask_anythingllm(question, workspace_name, api_key):
    url = f"http://localhost:3001/api/v1/workspace/{workspace_name}/chat"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "accept": "text/event-stream"
    }
    data = {
        "message": question,
        "mode": "chat",
        'max_tokens': 1024,
        "stream": True
    }

    output = ""  # 初始化变量用于存储文字输出

    with requests.post(url, headers=headers, json=data, stream=True) as response:
        if response.status_code == 200:
            for chunk in response.iter_lines():
                if chunk:
                    decoded_chunk = chunk.decode("utf-8")
                    try:
                        json_data = json.loads(decoded_chunk)
                        if "textResponse" in json_data:
                            output += json_data["textResponse"]  # 提取文字部分并拼接
                    except json.JSONDecodeError:
                        pass  # 忽略非JSON格式的数据
    return output
