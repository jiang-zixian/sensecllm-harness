from __future__ import annotations

from typing import Any, Iterable, List

from .constants import ALLOWED_MECHANISMS, COMPONENT_CATEGORY_ALIASES


def canonical_mechanism(name: Any) -> str:
    text = str(name or "").strip()
    for mechanism in ALLOWED_MECHANISMS:
        if text.lower() == mechanism.lower():
            return mechanism
    return ""


def is_allowed_mechanism(name: Any) -> bool:
    return bool(canonical_mechanism(name))


def canonical_component_category(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in COMPONENT_CATEGORY_ALIASES:
        return COMPONENT_CATEGORY_ALIASES[lowered]
    for key, canonical in COMPONENT_CATEGORY_ALIASES.items():
        if key in lowered:
            return canonical
    return text


def classify_component_name(name: Any) -> str:
    text = str(name or "").lower()
    if any(k in text for k in ["ccd", "photodiode", "photo diode", "rgb", "clear diode", "light sensor"]):
        return "Optical Transducer"
    if any(k in text for k in ["cmos image sensor", "cmos array", "cmos camera"]):
        return "Optical Transducer"
    if any(k in text for k in ["microphone", "mic", "mems sensor", "mems microphone", "ultrasonic transducer", "acoustic transducer"]):
        return "Acoustic Transducer"
    if any(k in text for k in ["mems", "proof mass", "accelerometer", "gyroscope", "gyro", "pressure", "force"]):
        return "Force Transducer"
    if any(k in text for k in ["analog front-end", "afe", "front end", "signal conditioning", "analog gain", "pga", "amplifier", "amp"]):
        return "Amplifier"
    if "filter" in text:
        return "Filter"
    if any(k in text for k in ["adc", "analog-to-digital", "a/d converter"]):
        return "ADC"
    if any(k in text for k in ["dsp", "digital processing", "digital processor", "microcontroller", "mcu"]):
        return "DSP"
    if any(k in text for k in ["i2c", "i²c", "i2s", "i²s", "spi", "uart", "interface", "sda", "scl", "sck", "sd", "ws"]):
        return "Communication Interface"
    if any(k in text for k in ["power", "vdd", "supply"]):
        return "Power Supply"
    if any(k in text for k in ["pin", "pcb", "trace", "wire", "cable", "lead", "conductive"]):
        return "Wires"
    if "clock" in text or "oscillator" in text:
        return "Clock Oscillator"
    return ""


def component_is_transducer(category: str) -> bool:
    return category in {
        "Acoustic Transducer",
        "Optical Transducer",
        "Electromagnetic Transducer",
        "Force Transducer",
        "Transducer Module",
    }


def component_is_signal_conditioning(category: str) -> bool:
    return category in {"Signal Conditioning Circuits", "Amplifier", "Filter", "ADC"}


def component_is_conductor(category: str, name: str = "") -> bool:
    lowered = (name or "").lower()
    return category in {"Wires", "Power Supply", "Communication Interface"} or any(
        k in lowered for k in ["pin", "wire", "trace", "pcb", "cable", "line", "lead", "conductive"]
    )


def unique_nonempty(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        text = str(item or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
