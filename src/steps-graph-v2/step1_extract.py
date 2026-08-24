from pathlib import Path
import json
import re
try:
    import fitz
except Exception:
    fitz = None

from helpers.configs.configs import chatanywhere_auth_header, input_file, output_report
from helpers.api.chatanywhere_client import chatanywhere_chat_completion
from helpers.utils.file_utils import write_report_header, append_report
from helpers.configs.prompts import prompt1_1
from report_renderers import render_sensor_info
from temp_paths import temp_path


def extract_json_text(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start:end + 1]
    return t


def parse_json_with_fallback(text: str):
    raw = extract_json_text(text)
    candidates = [raw]

    # 1) 去除不可见控制字符（保留 \n\r\t）
    c1 = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw)
    # 2) 去除常见尾逗号
    c2 = re.sub(r",\s*([}\]])", r"\1", c1)
    candidates.extend([c1, c2])

    last_err = None
    for c in candidates:
        try:
            return json.loads(c)
        except Exception as e:
            last_err = e
        try:
            # strict=False 可容忍字符串中的控制字符
            return json.loads(c, strict=False)
        except Exception as e:
            last_err = e

    raise RuntimeError(f"JSON 解析失败，最后错误: {last_err}")


def repair_json_with_llm(malformed_text: str) -> dict:
    repair_messages = [
        {"role": "system", "content": "You repair malformed JSON. Return strict JSON only, no markdown."},
        {"role": "user", "content": malformed_text},
    ]
    resp = chatanywhere_chat_completion(
        model="gpt-5.4-mini",
        messages=repair_messages,
        auth_header=chatanywhere_auth_header,
        temperature=0.0,
    )
    fixed = resp["choices"][0]["message"]["content"]
    return parse_json_with_fallback(fixed)


def extract_text_tables_with_pymupdf(pdf_path: Path) -> str:
    if fitz is None:
        raise RuntimeError("未安装 PyMuPDF（fitz），无法解析 PDF。")
    parts = []
    with fitz.open(pdf_path) as doc:
        for page_no, page in enumerate(doc, start=1):
            text = (page.get_text("text") or "").strip()
            if text:
                parts.append(f"\n## Page {page_no} Text\n{text}")

            # Try table extraction (available in newer PyMuPDF versions).
            try:
                tf = page.find_tables()
                tables = tf.tables if tf else []
                if tables:
                    parts.append(f"\n## Page {page_no} Tables")
                for idx, tb in enumerate(tables, start=1):
                    parts.append(f"\n### Table {idx}")
                    for row in tb.extract():
                        cells = ["" if c is None else str(c).strip() for c in row]
                        parts.append("| " + " | ".join(cells) + " |")
            except Exception:
                # Keep compatibility with older PyMuPDF versions.
                pass

    return "\n".join(parts).strip()


def run_step_1(model_for_analyze="glm-5"):
    print("---------------------------------------第一步 从产品规划书中提取传感器信息---------------------------------------")
    src_path = Path(input_file)
    if not src_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {src_path}")

    suffix = src_path.suffix.lower()
    if suffix == ".pdf":
        print("检测到 PDF 输入，使用 PyMuPDF 提取文字和表格...")
        file_content = extract_text_tables_with_pymupdf(src_path)
        if not file_content:
            raise RuntimeError("PyMuPDF 未提取到有效内容。")
        temp_path("step1_raw_pdf_text.txt").write_text(file_content, encoding="utf-8")
    elif suffix in {".md", ".markdown"}:
        print("检测到 Markdown 输入，直接读取文件内容并交给大模型提取...")
        file_content = src_path.read_text(encoding="utf-8")
        if not file_content.strip():
            raise RuntimeError("Markdown 文件为空，无法提取。")
        temp_path("step1_raw_md_text.txt").write_text(file_content, encoding="utf-8")
    else:
        raise ValueError(f"不支持的输入格式: {suffix}，当前仅支持 .pdf/.md/.markdown")

    # 清空并初始化报告
    open(output_report, "w").close()
    write_report_header(output_report)

    messages1 = [
        {"role": "system", "content": file_content},
        {"role": "user", "content": prompt1_1},
    ]

    response_data = chatanywhere_chat_completion(
        model=model_for_analyze,  # 可替换为其他支持的模型名称
        messages=messages1,
        auth_header=chatanywhere_auth_header,
    )
    output = response_data["choices"][0]["message"]["content"]

    temp_path("step1_output.txt").write_text(output, encoding="utf-8")

    # 尝试从模型输出中提取 JSON（带容错）
    cleaned = output.strip()
    temp_path("step1_output_raw_llm.txt").write_text(cleaned, encoding="utf-8")
    try:
        data = parse_json_with_fallback(cleaned)
    except Exception as e:
        print(f"[Step1] 首次 JSON 解析失败，尝试 LLM 修复: {e}")
        data = repair_json_with_llm(cleaned)

    # 写入 JSON 文件
    output_json_path = temp_path("step1_output.json")
    output_json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rag_input = data["rag_input"]
    sensor_info = data["sensor_info"]

    sensor_info_str = (
        sensor_info
        if isinstance(sensor_info, str)
        else json.dumps(sensor_info, ensure_ascii=False, indent=2)
    )
    temp_path("step1_output.txt").write_text(sensor_info_str, encoding="utf-8")
    append_report(output_report, "\n" + render_sensor_info(data) + "\n")
    return rag_input, sensor_info

# 运行测试
if __name__ == "__main__":
    run_step_1()
