from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Sequence


_UNIT_PATTERN = (
    r"GHz|MHz|kHz|KHz|Hz|baud|bps|V|mV|A|mA|uA|µA|mm|cm|m²|m2|m|"
    r"ns|us|µs|ms|s|°C|°F|degrees?|nm|lux|lx|dBA?|Pa|hPa|bar|%RH|%|"
    r"g|dps|°/s|fps|TVL|bits?"
)
_VALUE_WITH_UNIT_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<lo>[+-]?\d+(?:\.\d+)?)"
    rf"(?:\s*(?:-|to|–|—|~|～)\s*(?P<hi>[+-]?\d+(?:\.\d+)?))?"
    rf"\s*(?P<unit>{_UNIT_PATTERN})\b",
    flags=re.IGNORECASE,
)


def _sensor_text(step1_data: Any) -> str:
    if isinstance(step1_data, dict):
        sensor_info = step1_data.get("sensor_info")
        if isinstance(sensor_info, str):
            return sensor_info
        if sensor_info is not None:
            return json.dumps(sensor_info, ensure_ascii=False, indent=2)
    if isinstance(step1_data, str):
        return step1_data
    return json.dumps(step1_data, ensure_ascii=False, indent=2)


def _clean_label(line: str) -> str:
    cleaned = re.sub(r"^\s*[-*+]\s*", "", line).strip()
    cleaned = cleaned.replace("**", "").replace("__", "")
    label = cleaned.split(":", 1)[0].strip(" -")
    return label[:160] or "datasheet parameter"


def _canonical_unit(unit: str) -> str:
    lowered = unit.casefold()
    return {
        "ghz": "GHz",
        "mhz": "MHz",
        "khz": "kHz",
        "hz": "Hz",
        "ua": "uA",
        "µa": "uA",
        "us": "us",
        "µs": "us",
        "m2": "m²",
    }.get(lowered, unit)


def _role_for_line(text: str) -> str:
    lowered = text.casefold()
    rules = (
        (("cable", "wire length", "trace length", "lead length", "interconnect length"), "coupling_length"),
        (("sampling rate", "sample rate", "output data rate", "measurement rate", "odr", "nyquist"), "sampling_rate"),
        (("resonan",), "resonance_frequency"),
        (("operating frequency", "center frequency", "carrier frequency"), "operating_frequency"),
        (("clock frequency", "oscillator", "sck frequency", "ws frequency", "external clock", "clock inputs"), "clock_frequency"),
        (("bandwidth", "passband"), "bandwidth"),
        (("cutoff", "cut-off"), "cutoff_frequency"),
        (("baud", "serial communication", "data rate", "bit rate"), "communication_rate"),
        (("trigger", "pulse width", "pulse duration"), "pulse_width"),
        (("clock period", "clock rise", "clock/data", "timing limit", "hold time", "data delay", "reset time", "measurement time", "measurement duration"), "timing_parameter"),
        (("wavelength", "wave length"), "wavelength"),
        (("voltage", "vdd", "v_dd", "vbus", "v_bus", "supply"), "supply_voltage"),
        (("current",), "operating_current"),
        (("maximum range", "minimum range", "blind zone", "measurement range", "operating distance"), "measurement_range"),
        (("full scale", "fsr", "zero-rate level", "self-test output"), "measurement_amplitude_range"),
        (("esd", "latch-up", "latchup"), "electrical_limit"),
        (("shock", "vibration resistance", "vibration tolerance"), "mechanical_limit"),
        (("harmonic distortion", "thd", "spl"), "nonlinearity_limit"),
        (("temperature",), "temperature_limit"),
        (("sensitivity",), "sensitivity"),
        (("noise",), "noise_level"),
        (("angle", "field of view", "fov"), "angular_range"),
    )
    for terms, role in rules:
        if any(term in lowered for term in terms):
            return role
    return "datasheet_numeric_parameter"


def _component_categories(text: str, role: str) -> List[str]:
    lowered = text.casefold()
    categories: List[str] = []

    def add(category: str) -> None:
        if category not in categories:
            categories.append(category)

    if role == "coupling_length" or re.search(
        r"\b(?:cables?|wires?|traces?|leads?|pins?)\b", lowered
    ):
        add("Wires")
    if role == "sampling_rate" or any(word in lowered for word in ("adc", "sampling", "sample rate", "nyquist", "odr")):
        add("ADC")
    if role in {"communication_rate", "timing_parameter"} or any(word in lowered for word in ("serial", "baud", "uart", "i2c", "i²c", "i2s", "spi", "interface", "trigger", "echo", "sck", "scl", "clk")):
        add("Communication Interface")
    if role == "clock_frequency":
        add("Clock Oscillator")
        if any(word in lowered for word in ("sck", "scl", "ws", "i2s", "i²s", "external clock")):
            add("Communication Interface")
    if role in {"supply_voltage", "operating_current"} or any(word in lowered for word in ("voltage", "current", "power", "vdd", "supply")):
        add("Power Supply")
    if role in {"bandwidth", "cutoff_frequency"} or "filter" in lowered:
        add("Filter")
    if any(word in lowered for word in ("gain", "amplifier", "sensitivity", "noise")):
        add("Amplifier")
    if any(word in lowered for word in ("acoustic", "ultrasonic", "sound", "microphone", "beam angle")) or (
        role in {"operating_frequency", "resonance_frequency"} and "optical" not in lowered
    ):
        add("Acoustic Transducer")
    if role == "wavelength" or any(word in lowered for word in ("optical", "light", "lux", "photodiode", "color")):
        add("Optical Transducer")
    if role in {"measurement_amplitude_range", "mechanical_limit"} or any(word in lowered for word in ("acceleration", "gyroscope", "vibration", "pressure", "force", "proof mass")):
        add("Force Transducer")
    if role in {"electrical_limit"}:
        add("Wires")
        add("Signal Conditioning Circuits")
    if role == "nonlinearity_limit":
        add("Acoustic Transducer")
        add("Amplifier")
    return categories


def _modalities(text: str, role: str, categories: Sequence[str]) -> List[str]:
    lowered = text.casefold()
    modalities: List[str] = []

    def add(modality: str) -> None:
        if modality not in modalities:
            modalities.append(modality)

    if "Acoustic Transducer" in categories or any(word in lowered for word in ("acoustic", "ultrasonic", "sound")):
        add("acoustic")
    if "Optical Transducer" in categories or any(word in lowered for word in ("optical", "light", "lux", "wavelength")):
        add("optical")
    if "Force Transducer" in categories or any(word in lowered for word in ("mechanical", "vibration", "force", "pressure")):
        add("mechanical")
    if role in {"coupling_length", "clock_frequency", "timing_parameter", "electrical_limit"} or any(
        category in categories
        for category in ("Wires", "ADC", "Communication Interface", "Power Supply", "Amplifier", "Filter")
    ):
        add("electromagnetic")
    if role in {"mechanical_limit", "measurement_amplitude_range"}:
        add("mechanical")
    return modalities


def extract_sensor_parameters(step1_data: Any) -> List[Dict[str, Any]]:
    """Extract a lossless, line-grounded catalog of Step1 numeric parameters.

    This deliberately preserves the original line and raw values. It does not try
    to decide an attack range; it only creates explicit parameter provenance that
    later graph paths can carry forward.
    """
    parameters: List[Dict[str, Any]] = []
    seen = set()
    for line_no, line in enumerate(_sensor_text(step1_data).splitlines(), start=1):
        matches = list(_VALUE_WITH_UNIT_RE.finditer(line))
        if not matches:
            continue
        raw_text = line.strip()
        if not raw_text:
            continue
        values = []
        for match in matches:
            lo = float(match.group("lo"))
            hi_raw = match.group("hi")
            value: Dict[str, Any] = {
                "raw": match.group(0).strip(),
                "unit": _canonical_unit(match.group("unit")),
            }
            if hi_raw is None:
                value["value"] = lo
            else:
                value["range"] = [min(lo, float(hi_raw)), max(lo, float(hi_raw))]
            values.append(value)
        dedupe_key = (raw_text.casefold(), tuple(value["raw"].casefold() for value in values))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        role = _role_for_line(raw_text)
        categories = _component_categories(raw_text, role)
        parameters.append(
            {
                "parameter_id": f"sensor_param_{len(parameters) + 1:03d}",
                "name": _clean_label(raw_text),
                "parameter_role": role,
                "raw_text": raw_text,
                "values": values,
                "component_categories": categories,
                "relevant_modalities": _modalities(raw_text, role, categories),
                "source": "step1_output.json",
                "source_locator": f"sensor_info:line_{line_no}",
            }
        )
    return parameters


def parameters_for_path(
    catalog: Iterable[Dict[str, Any]],
    component_categories: Iterable[str],
    external_modality: str,
) -> List[Dict[str, Any]]:
    categories = {str(value) for value in component_categories if str(value)}
    modality = str(external_modality or "").casefold()
    selected: List[Dict[str, Any]] = []
    for parameter in catalog:
        parameter_categories = set(parameter.get("component_categories") or [])
        parameter_modalities = {
            str(value).casefold() for value in parameter.get("relevant_modalities") or []
        }
        if categories & parameter_categories or (modality and modality in parameter_modalities):
            selected.append(parameter)
    return selected
