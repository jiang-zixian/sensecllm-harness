from __future__ import annotations

from typing import Any, Dict, Set

from .models import SensorPhysicalGraph


EXPECTED_MODALITY_KEYWORDS = {
    "acoustic": {
        "acoustic microphone",
        "microphone",
        "acoustic sensor",
        "ultrasonic sensor",
        "ultrasound sensor",
        "hydrophone",
        "麦克风",
        "超声波传感器",
    },
    "optical": {
        "optical sensor",
        "ambient light sensor",
        "light sensor",
        "color sensor",
        "image sensor",
        "camera",
        "infrared temperature sensor",
        "reflective optical sensor",
        "photodetector",
        "颜色传感器",
        "光照传感器",
        "相机",
        "红外温度传感器",
        "红外距离传感器",
    },
    "mechanical": {
        "mechanical signal",
        "motion sensor",
        "accelerometer",
        "gyroscope",
        "pressure sensor",
        "barometric pressure",
        "vibration sensor",
        "force sensor",
        "加速度计",
        "陀螺仪",
        "压力传感器",
        "震动传感器",
    },
    "electromagnetic": {
        "magnetic sensor",
        "magnetometer",
        "hall sensor",
        "electromagnetic sensor",
        "磁传感器",
        "霍尔传感器",
    },
}


ULTRASONIC_RECEIVER_KEYWORDS = {
    "ultrasonic distance sensor",
    "ultrasonic ranging sensor",
    "ultrasonic range sensor",
    "ultrasonic sensor",
    "ultrasound distance sensor",
    "ultrasound ranging sensor",
    "ultrasound sensor",
    "sonar sensor",
    "超声波距离传感器",
    "超声波测距传感器",
    "超声波传感器",
}


def is_ultrasonic_receiving_sensor(graph: SensorPhysicalGraph) -> bool:
    """Return whether acoustic/ultrasonic energy is the intended received input.

    This deliberately does not match microphones: adversarial out-of-band
    acoustic input remains a valid D1 origin for microphone analysis.  Active
    ultrasonic ranging receivers instead consume ultrasound as their normal
    measurand, so an acoustic D1 attack origin would duplicate the intended
    channel rather than represent a cross-field entrance.
    """
    text_parts = [str(graph.sensor_model or "")]
    for node in graph.component_nodes() + graph.boundary_nodes():
        if node.source_stage != "step1":
            continue
        text_parts.extend(
            [
                str(node.name or ""),
                str(node.component_name or ""),
                " ".join(str(value or "") for value in node.attributes.values()),
            ]
        )
    text = " ".join(text_parts).casefold()
    return any(keyword in text for keyword in ULTRASONIC_RECEIVER_KEYWORDS) or (
        any(keyword in text for keyword in ("ultrasonic", "ultrasound", "超声波"))
        and any(keyword in text for keyword in ("receiver", "receive", "ranging", "distance", "echo", "接收", "测距"))
    )


def infer_expected_input_modalities(graph: SensorPhysicalGraph) -> Set[str]:
    """Infer intended sensing modalities from the sensor-class description."""
    text = (graph.sensor_model or "").lower()
    expected = {
        modality
        for modality, keywords in EXPECTED_MODALITY_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }
    if expected:
        return expected

    explicit_transducers = {
        node.component_category
        for node in graph.component_nodes()
        if node.source_stage == "step1"
        and node.component_category
        in {
            "Acoustic Transducer",
            "Optical Transducer",
            "Electromagnetic Transducer",
            "Force Transducer",
        }
    }
    category_modalities = {
        "Acoustic Transducer": "acoustic",
        "Optical Transducer": "optical",
        "Electromagnetic Transducer": "electromagnetic",
        "Force Transducer": "mechanical",
    }
    if len(explicit_transducers) == 1:
        return {category_modalities[next(iter(explicit_transducers))]}
    return set()


class Step2AttackScopePolicy:
    """Apply threat-model exclusions once, at the unified signal origins."""

    def __init__(self, graph: SensorPhysicalGraph) -> None:
        self.graph = graph
        self.expected_modalities = infer_expected_input_modalities(graph)
        self.ultrasonic_receiving_sensor = is_ultrasonic_receiving_sensor(graph)

    def skip_origin(self, signal_origin: str) -> bool:
        if signal_origin == "mechanical":
            return True
        if signal_origin == "acoustic" and self.ultrasonic_receiving_sensor:
            return True
        # Optical stimuli against an optical sensor are in-band even when a
        # laser causes photoelectric conversion or optical saturation.
        return signal_origin == "optical" and signal_origin in self.expected_modalities

    def annotate_origin_nodes(self) -> None:
        for modality in {"acoustic", "optical", "electromagnetic"}:
            node = self.graph.nodes.get(f"external_{modality}")
            if node is None:
                continue
            node.attributes["unified_attack_origin"] = True
            node.attributes["in_band_expected_input_excluded"] = (
                modality in self.expected_modalities
            )
            if modality == "acoustic" and modality in self.expected_modalities:
                if self.ultrasonic_receiving_sensor:
                    node.attributes["scope_note"] = (
                        "The acoustic D1 origin is not searched because received "
                        "ultrasound is this ranging sensor's intended input."
                    )
                else:
                    node.attributes["scope_note"] = (
                        "The unified acoustic attack origin excludes the sensor's "
                        "intended in-band sound, such as audible sound for a microphone."
                    )
            elif modality == "optical" and modality in self.expected_modalities:
                node.attributes["scope_note"] = (
                    "The optical origin is not searched because light is the "
                    "sensor's intended input."
                )

    def metadata(self) -> Dict[str, Any]:
        excluded_origins = ["mechanical"]
        if self.ultrasonic_receiving_sensor:
            excluded_origins.append("acoustic")
        allowed_origins = ["acoustic", "optical", "electromagnetic"]
        if self.ultrasonic_receiving_sensor:
            allowed_origins.remove("acoustic")
        return {
            "allowed_attack_origins": allowed_origins,
            "excluded_attack_origins": excluded_origins,
            "expected_input_modalities": sorted(self.expected_modalities),
            "ultrasonic_receiving_sensor": self.ultrasonic_receiving_sensor,
            "unified_origins": True,
            "in_band_expected_input_excluded_at_origin": True,
            "policy": (
                "Use one origin per modality and exclude intended in-band stimuli at "
                "the graph entrance; do not split origins into cross-field and out-of-range."
            ),
        }
