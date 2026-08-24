# helpers/api/dify_client.py
"""
保留你原始的 ask_dify 函数实现（尽量不改动任何字段/变量名/逻辑）。
"""
import requests
import json

def ask_dify(question, api_key):
    api_url = "http://localhost/v1/chat-messages"

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    data = {
        "inputs": {},
        "query": question,
        "response_mode": "streaming",
        "conversation_id": "",
        "user": "healer_jzx"
    }

    response = requests.post(api_url, headers=headers, data=json.dumps(data), stream=True)

    if response.status_code == 200:
        print("Request successful")
        full_answer = ""
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[6:]  # 去掉 "data: " 前缀
                    try:
                        data = json.loads(json_str)
                        
                        # 🚀 改进的逻辑：尝试从 'text' 或 'answer' 字段中获取内容
                        answer_part = data.get("text") or data.get("answer")
                        
                        if answer_part:
                            full_answer += answer_part
                            # 💡 提示：如果 API 使用 'event': 'message'，则可以使用 data.get("text")
                        
                        # ⚠️ 调试：如果上述方法仍无效，请打印 data 对象来查看 API 的真实格式
                        # print("--- DEBUG RAW DATA ---")
                        # print(data)
                        # print("----------------------")

                    except json.JSONDecodeError:
                        print("Failed to parse JSON:", json_str)
        
        print("\nFull answer:", full_answer)  # 打印完整回答
        return full_answer
    else:
        print(f"Request failed: {response.status_code}")
        print(response.text)
        return None
