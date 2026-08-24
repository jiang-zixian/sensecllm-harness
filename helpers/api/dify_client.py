import requests
import json
import sys
import time

def ask_dify(
    question: str,
    api_key: str,
    RAGinput: str = None,
    conv_id: str = None,
    user: str = "healer_jzx",
    api_url: str = "http://localhost/v1/chat-messages",
    max_retry: int = 3,
    silent: bool = False,  # ← 新增
    inputs_extra: dict = None,
):
    """
    ✅ 统一版 Dify 调用（增强版，兼容 streaming，无 timeout 参数）
       - 若响应为空自动重试
       - sys_prompt 正确传入 inputs["result"]
       - 支持 conversation_id
       - 避免 iter_lines(timeout=30) 报错
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    retry = 0
    full_answer = None
    new_conversation_id = conv_id

    while retry < max_retry:

        request_inputs = {"RAGinput": RAGinput}
        if inputs_extra:
            request_inputs.update(inputs_extra)
        payload = {
            "inputs": request_inputs,   # ✅ sys_prompt 注入到 dify 变量 result
            "query": question,
            "response_mode": "streaming",
            "user": user
        }

        if conv_id:
            payload["conversation_id"] = conv_id

        print(f"\n🚀 Dify 请求中... 第 {retry+1}/{max_retry} 次尝试")
        response = requests.post(api_url, headers=headers, data=json.dumps(payload), stream=True)

        if response.status_code != 200:
            print(f"❌ 请求失败: {response.status_code}")
            print(response.text)
            retry += 1
            time.sleep(1)
            continue

        print("✅ Request successful\n")

        full_answer = ""
        start_time = time.time()

        # ✅ 不使用 timeout 参数，避免报错
        for line in response.iter_lines():

            # 简单防卡死超时 (60秒)
            if time.time() - start_time > 60:
                print("\n⏳ 超时，无更多输出")
                break

            if not line:
                continue

            decoded = line.decode("utf-8")
            if not decoded.startswith("data: "):
                continue

            try:
                data = json.loads(decoded[6:])

                chunk = data.get("answer") or data.get("text")
                if chunk:
                    if not silent:
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
                    full_answer += chunk

                if "conversation_id" in data:
                    new_conversation_id = data["conversation_id"]

                if data.get("event") == "message_end":
                    break

            except json.JSONDecodeError:
                print("\n⚠ JSON 解析失败:", decoded)

        print("\n" + "-" * 50)

        # ✅ 如果返回空则自动重试
        if not full_answer.strip():
            print("⚠️ Dify 返回为空，准备重试...")
            retry += 1
            time.sleep(1)
            continue

        return full_answer, new_conversation_id

    # 🔴 多次重试仍失败
    print("❌ 多次重试仍未获取到内容！")
    return None, new_conversation_id


def ask_dify_verify(
    question: str,
    api_key: str,
    RAGinput: str = None,
    sensor_info: str = None,
    vul: str = None,
    mec: str = None,
    conv_id: str = None,
    user: str = "healer_jzx",
    api_url: str = "http://localhost/v1/chat-messages",
    max_retry: int = 3,
    silent: bool = False,  # ← 新增
):
    """
    ✅ 统一版 Dify 调用（增强版，兼容 streaming，无 timeout 参数）
       - 若响应为空自动重试
       - sys_prompt 正确传入 inputs["result"]
       - 支持 conversation_id
       - 避免 iter_lines(timeout=30) 报错
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    retry = 0
    full_answer = None
    new_conversation_id = conv_id

    while retry < max_retry:

        payload = {
            "inputs": {"RAGinput": RAGinput, "vulnerability": vul, "mechanism": mec, "sensor_info": sensor_info},  
            "query": question,
            "response_mode": "streaming",
            "user": user
        }

        if conv_id:
            payload["conversation_id"] = conv_id

        print(f"\n🚀 Dify 请求中... 第 {retry+1}/{max_retry} 次尝试")
        response = requests.post(api_url, headers=headers, data=json.dumps(payload), stream=True)

        if response.status_code != 200:
            print(f"❌ 请求失败: {response.status_code}")
            print(response.text)
            retry += 1
            time.sleep(1)
            continue

        print("✅ Request successful\n")

        full_answer = ""
        start_time = time.time()

        # ✅ 不使用 timeout 参数，避免报错
        for line in response.iter_lines():

            # 简单防卡死超时 (60秒)
            if time.time() - start_time > 60:
                print("\n⏳ 超时，无更多输出")
                break

            if not line:
                continue

            decoded = line.decode("utf-8")
            if not decoded.startswith("data: "):
                continue

            try:
                data = json.loads(decoded[6:])

                chunk = data.get("answer") or data.get("text")
                if chunk:
                    if not silent:
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
                    full_answer += chunk

                if "conversation_id" in data:
                    new_conversation_id = data["conversation_id"]

                if data.get("event") == "message_end":
                    break

            except json.JSONDecodeError:
                print("\n⚠ JSON 解析失败:", decoded)

        print("\n" + "-" * 50)

        # ✅ 如果返回空则自动重试
        if not full_answer.strip():
            print("⚠️ Dify 返回为空，准备重试...")
            retry += 1
            time.sleep(1)
            continue

        return full_answer, new_conversation_id

    # 🔴 多次重试仍失败
    print("❌ 多次重试仍未获取到内容！")
    return None, new_conversation_id
