from pathlib import Path

from helpers.configs.configs import output_report


def get_temp_dir() -> Path:
    report_path = Path(output_report)
    temp_dir = report_path.parent / "temp_data" / report_path.stem
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def temp_path(filename: str) -> Path:
    return get_temp_dir() / filename
