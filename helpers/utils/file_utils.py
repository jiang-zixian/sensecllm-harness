# helpers/utils/file_utils.py
"""
文件写入、打印、辅助函数
"""
from pathlib import Path

def ensure_parent_exists(file_path: str):
    p = Path(file_path)
    if not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)

def write_report_header(output_path: str):
    ensure_parent_exists(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Sensor Vulnerability Report\n")

def append_report(output_path: str, content: str):
    ensure_parent_exists(output_path)
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(content)
