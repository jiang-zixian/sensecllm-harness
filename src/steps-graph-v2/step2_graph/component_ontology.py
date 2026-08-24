from __future__ import annotations

from typing import Any, Dict, List


COMPONENT_ONTOLOGY: Dict[str, Dict[str, Any]] = {
    "Transducer Module": {
        "module": "Transducer Module",
        "input_modalities": ["acoustic", "optical", "electromagnetic", "mechanical"],
        "output_modalities": ["electrical"],
    },
    "Acoustic Transducer": {
        "module": "Transducer Module",
        "input_modalities": ["acoustic"],
        "output_modalities": ["electrical"],
    },
    "Optical Transducer": {
        "module": "Transducer Module",
        "input_modalities": ["optical"],
        "output_modalities": ["electrical"],
    },
    "Electromagnetic Transducer": {
        "module": "Transducer Module",
        "input_modalities": ["electromagnetic"],
        "output_modalities": ["electrical"],
    },
    "Force Transducer": {
        "module": "Transducer Module",
        "input_modalities": ["mechanical", "acoustic"],
        "output_modalities": ["electrical"],
    },
    "Signal Conditioning Circuits": {
        "module": "Signal Conditioning Circuits",
        "input_modalities": ["electrical"],
        "output_modalities": ["electrical"],
    },
    "Amplifier": {
        "module": "Signal Conditioning Circuits",
        "input_modalities": ["electrical"],
        "output_modalities": ["electrical"],
    },
    "Filter": {
        "module": "Signal Conditioning Circuits",
        "input_modalities": ["electrical"],
        "output_modalities": ["electrical"],
    },
    "ADC": {
        "module": "Signal Conditioning Circuits",
        "input_modalities": ["electrical"],
        "output_modalities": ["digital"],
    },
    "Computing and Communication Module": {
        "module": "Computing and Communication Module",
        "input_modalities": ["digital"],
        "output_modalities": ["digital"],
    },
    "DSP": {
        "module": "Computing and Communication Module",
        "input_modalities": ["digital"],
        "output_modalities": ["digital"],
    },
    "Communication Interface": {
        "module": "Computing and Communication Module",
        "input_modalities": ["digital", "electrical"],
        "output_modalities": ["digital", "electrical"],
    },
    "Auxiliary Module": {
        "module": "Auxiliary Module",
        "input_modalities": [],
        "output_modalities": [],
    },
    "Power Supply": {
        "module": "Auxiliary Module",
        "input_modalities": ["electromagnetic", "electrical"],
        "output_modalities": ["electrical"],
    },
    "Wires": {
        "module": "Auxiliary Module",
        "input_modalities": ["electromagnetic", "electrical"],
        "output_modalities": ["electrical"],
    },
    "Clock Oscillator": {
        "module": "Auxiliary Module",
        "input_modalities": ["electrical"],
        "output_modalities": ["electrical", "digital"],
    },
}


TRANSDUCER_CATEGORIES = {
    "Transducer Module",
    "Acoustic Transducer",
    "Optical Transducer",
    "Electromagnetic Transducer",
    "Force Transducer",
}

SIGNAL_CONDITIONING_CATEGORIES = {
    "Signal Conditioning Circuits",
    "Amplifier",
    "Filter",
    "ADC",
}

COMPUTING_CATEGORIES = {
    "Computing and Communication Module",
    "DSP",
    "Communication Interface",
}

AUXILIARY_CATEGORIES = {
    "Auxiliary Module",
    "Power Supply",
    "Wires",
    "Clock Oscillator",
}


def component_capabilities(category: str) -> Dict[str, Any]:
    return dict(COMPONENT_ONTOLOGY.get(category, {}))


def infer_component_priors(sensor_text: str) -> List[Dict[str, str]]:
    """Infer minimum sensor-chain components from sensor class, not model name."""
    text = (sensor_text or "").lower()
    priors: List[Dict[str, str]] = []

    def add(name: str, category: str, reason: str) -> None:
        if not any(item["category"] == category for item in priors):
            priors.append({"name": name, "category": category, "reason": reason})

    is_microphone = any(k in text for k in ["microphone", "麦克风"])
    is_ultrasonic = any(
        k in text
        for k in [
            "ultrasonic sensor",
            "ultrasound sensor",
            "ultrasonic ranging",
            "ultrasonic transducer",
            "ultrasonic transmitter",
            "ultrasonic receiver",
            "sonar",
            "超声波传感器",
            "超声测距",
        ]
    )
    is_inertial = any(
        k in text
        for k in [
            "accelerometer",
            "gyroscope",
            "motiontracking",
            "proof mass",
            "vibratory mems",
            "coriolis",
            "加速度",
            "陀螺",
        ]
    )
    is_pressure_or_force = any(k in text for k in ["pressure sensor", "barometric", "force sensor", "diaphragm"])
    is_environmental_electrical = any(
        k in text
        for k in [
            "temperature sensor",
            "humidity sensor",
            "温度传感器",
            "湿度传感器",
            "温湿度",
            "cmosens",
            "humidity sensor opening",
            "capacitive humidity",
        ]
    )
    is_contact_or_vibration = any(
        k in text
        for k in [
            "vibration sensor switch",
            "spring type trigger",
            "conductive contact",
            "conductive pick",
            "contact switch",
            "震动传感器",
        ]
    )
    is_optical = any(
        k in text
        for k in [
            "optical sensor",
            "image sensor",
            "photodiode",
            "phototransistor",
            "infrared sensor",
            "infrared temperature",
            "color sensor",
            "light sensor",
            "ccd",
            "cmos image sensor",
            "cmos array",
            "cmos camera",
            "光照",
            "红外",
            "颜色传感器",
        ]
    )
    has_digital_interface = any(
        k in text
        for k in [
            "digital output",
            "digital-output",
            "i2c",
            "i²c",
            "i2s",
            "i²s",
            "spi",
            "uart",
            "digital interface",
            "communication interface",
        ]
    )
    has_explicit_adc = any(k in text for k in [" adc", "adcs", "analog-to-digital", "analogue-to-digital"])
    is_electronic_sensor = any(
        [
            is_microphone,
            is_ultrasonic,
            is_inertial,
            is_pressure_or_force,
            is_environmental_electrical,
            is_contact_or_vibration,
            is_optical,
            has_digital_interface,
            "sensor" in text,
        ]
    )

    if is_microphone or is_ultrasonic:
        add(
            "inferred acoustic transducer",
            "Acoustic Transducer",
            "Acoustic sensing requires an acoustic-to-electrical transducer.",
        )
    if is_inertial or is_pressure_or_force or is_contact_or_vibration:
        add(
            "inferred force/mechanical transducer",
            "Force Transducer",
            "Mechanical, inertial, pressure, or contact sensing requires a mechanical-to-electrical transducer.",
        )
    if is_optical:
        add(
            "inferred optical transducer",
            "Optical Transducer",
            "Optical sensing requires a photosensitive optical-to-electrical transducer.",
        )

    has_transducer = any(
        [
            is_microphone,
            is_ultrasonic,
            is_inertial,
            is_pressure_or_force,
            is_contact_or_vibration,
            is_optical,
        ]
    )
    has_sensing_frontend = has_transducer or is_environmental_electrical
    if has_transducer:
        add(
            "inferred analog front-end",
            "Amplifier",
            "A sensor transducer requires finite-range signal conditioning before output or conversion.",
        )
        add(
            "inferred signal filter",
            "Filter",
            "A physical sensor signal chain normally limits noise and out-of-band content.",
        )
    if is_environmental_electrical:
        add(
            "inferred signal conditioning circuits",
            "Signal Conditioning Circuits",
            "Digital temperature/humidity sensors require finite-range sensing and signal-conditioning circuitry before conversion.",
        )
    if has_explicit_adc or (has_sensing_frontend and has_digital_interface):
        add(
            "inferred ADC",
            "ADC",
            "A digital physical sensor requires sampling/conversion between its analog transducer chain and digital output.",
        )
    if has_digital_interface:
        add(
            "inferred digital processing",
            "DSP",
            "A digital sensor requires digital processing/control between conversion and communication.",
        )
        add(
            "inferred communication interface",
            "Communication Interface",
            "The documented digital output implies a communication interface.",
        )
    if is_electronic_sensor:
        add(
            "inferred conductive interconnects",
            "Wires",
            "An electronic sensor necessarily contains conductive pins, traces, leads, or power interconnects.",
        )
        add(
            "inferred power supply path",
            "Power Supply",
            "An active electronic sensor requires a conductive power path.",
        )
    return priors
