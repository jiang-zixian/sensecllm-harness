from pathlib import Path
from helpers.configs.configs import dify_api_key, output_report, output_report_cn
from helpers.api.dify_client import ask_dify

def run_step_6():
    print("\n--------------------------------第六步 将英文报告翻译为中文报告--------------------------------")
    with open(output_report, "r", encoding="utf-8") as f:
        english_report = f.read()
    
    translation_prompt = f"请将以下英文技术报告翻译成中文，保持专业术语和格式不变：\n\n{english_report}"
    chinese_report = ask_dify(translation_prompt, dify_api_key)[0]
    
    with open(output_report_cn, "w", encoding="utf-8") as f:
        f.write(chinese_report)
    print(f"中文报告已写入：{output_report_cn}")
    
# 运行测试
if __name__ == "__main__":
    run_step_6()