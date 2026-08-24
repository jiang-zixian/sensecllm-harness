"""
封装对 ChatAnywhere (OpenAI 兼容接口) 的请求
"""
import requests
import json
import os

from sensecllm.observability.usage import record_model_usage

def chatanywhere_chat_completion(
    model: str,
    messages: list,
    auth_header: str,
    temperature: float = 0.7,
    timeout: int = 180,
    max_tokens: int | None = None,
):
    """
    调用 ChatAnywhere 接口进行对话补全
    :param model: 模型名称 (例如 "gpt-3.5-turbo" 或 "gpt-4o")
    :param messages: 消息列表 [{"role": "user", "content": "..."}]
    :param auth_header: 完整的 Authorization header (例如 "Bearer sk-xxx")
    :param temperature: 采样温度
    :param timeout: 请求超时时间（秒），避免批处理在单个 API 调用上无限等待
    """
    url = "https://api.chatanywhere.tech/v1/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }

    try:
        response = requests.request("POST", url, json=payload, headers=headers, timeout=timeout)
        
        # 检查 HTTP 状态码
        if response.status_code != 200:
            raise RuntimeError(f"ChatAnywhere 请求失败：{response.status_code} {response.text}")
            
        response_data = response.json()
        record_model_usage(
            os.getenv("SENSECLLM_USAGE_FILE"),
            provider="chatanywhere",
            model=model,
            usage=response_data.get("usage"),
        )
        return response_data
        
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"网络请求异常: {e}")
