from helpers.configs.configs import dify_chat_api_key
from helpers.api.dify_client import ask_dify
from temp_paths import temp_path

def run_step_7():
    print("\n--------------------------------第七步 打开交互式对话助手--------------------------------")
    # 组合所有历史信息作为系统提示
    s1 = temp_path("step1_output.txt").read_text(encoding="utf-8")
    s2 = temp_path("step2_output.txt").read_text(encoding="utf-8")
    s3 = temp_path("step3_output.txt").read_text(encoding="utf-8")
    s4 = temp_path("step4_output.txt").read_text(encoding="utf-8")
    s5 = temp_path("step5_output.txt").read_text(encoding="utf-8")
    
    system_prompt = f"{s1}\n{s2}\n{s3}\n{s4}\n{s5}"+"\nYou are a sensor security expert. Please use all the information above to answer the user's question in detail."
    conversation_id = None

    try:
        while True:
            user_input = input("\n🧑 你：")
            if user_input.strip().lower() in ["exit", "quit"]: break
            answer, conversation_id = ask_dify(
                question=user_input,
                api_key=dify_chat_api_key,
                sys_prompt=system_prompt,
                conv_id=conversation_id
            )
            print(f"🤖 AI: {answer}")
    except KeyboardInterrupt:
        print("\n对话已终止。")
