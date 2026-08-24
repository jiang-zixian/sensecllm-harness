from __future__ import annotations

import re


_GENERIC_QUERIES = {
    "do the task",
    "retrieve",
    "search",
    "开始检索",
    "执行任务",
}

_DOMAIN_EXPANSIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("microphone", "麦克风", "voice", "audio"), "ultrasound acoustic laser electromagnetic voice command injection transduction nonlinearity"),
    (("accelerometer", "加速度", "gyroscope", "陀螺", "imu", "mems"), "acoustic resonance electromagnetic signal injection MEMS inertial sensor spoofing"),
    (("camera", "相机", "ccd", "cmos", "image sensor"), "optical laser electromagnetic signal injection rolling shutter image sensor spoofing"),
    (("lidar", "激光雷达", "point cloud"), "laser spoofing removal attack point cloud autonomous vehicle sensor attack"),
    (("pressure", "压力", "barometer", "气压"), "piezoresistive MEMS laser acoustic electromagnetic pressure sensor spoofing"),
    (("temperature", "温度", "thermal", "thermometer"), "temperature sensor rectification electromagnetic thermal spoofing"),
    (("touch", "触摸", "touchscreen", "capacitive"), "capacitive touchscreen electromagnetic conducted ghost touch injection"),
    (("ultrasonic sensor", "超声波传感器", "sonar"), "ultrasonic sensor spoofing jamming acoustic interference autonomous vehicle"),
    (("light sensor", "光照", "photodiode", "color sensor", "颜色传感器"), "optical electromagnetic light sensor signal injection photodiode saturation"),
    (("magnetometer", "磁力计", "hall sensor"), "magnetic electromagnetic interference sensor spoofing"),
)


def build_retrieval_query(query: str, rag_input: str | None) -> str:
    parts: list[str] = []
    if rag_input and rag_input.strip():
        parts.append(rag_input.strip())
    if query and query.strip().casefold() not in _GENERIC_QUERIES:
        parts.append(query.strip())
    base = "\n".join(parts).strip() or query.strip()
    lowered = base.casefold()
    expansions = [expansion for keys, expansion in _DOMAIN_EXPANSIONS if any(key in lowered for key in keys)]
    return f"{base}\nSensor-security retrieval terms: {'; '.join(expansions)}" if expansions else base


def build_fts_query(query: str, max_terms: int = 28) -> str:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,}", query)
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "into", "using", "sensor",
        "task", "paper", "retrieval", "terms", "security", "进行", "相关", "研究", "传感器",
    }
    selected: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = token.casefold().strip("_-")
        if normalized in stop or normalized in seen:
            continue
        seen.add(normalized)
        selected.append(normalized.replace("-", " ").replace("_", " "))
        if len(selected) >= max_terms:
            break
    return " OR ".join(selected) or query
