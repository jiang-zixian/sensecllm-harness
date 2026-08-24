# helpers/pdf/pdf_reader.py
"""
PDF 提取模块：
- 优先使用 Kimi / OpenAI 风格的文件提取（与你原始脚本一致）
- 回退使用 PyPDF2（原脚本的注释部分）
注意：API Key / base_url 从 configuration.py 中读取。
"""
from openai import OpenAI
from pathlib import Path
import PyPDF2
import io

def extract_text_with_kimi(api_key: str, base_url: str, file_path: Path) -> str:
    """
    使用 Kimi (OpenAI-like) API 提取 PDF 文本（保留原始调用方式）。
    file_path: pathlib.Path
    返回提取的纯文本（字符串）。
    """
    client_kimi = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    file_object = client_kimi.files.create(file=file_path, purpose="file-extract")
    file_content = client_kimi.files.content(file_id=file_object.id).text
    return file_content

def extract_text_with_pypdf2(pdf_path: Path) -> str:
    """
    使用 PyPDF2 提取文本（回退方案）。
    """
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                # 某些 PDF 页可能返回 None，所以用 or ""
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"提取PDF失败: {e}")
        return None
    return text
