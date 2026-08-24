from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .constants import STATUS_FALSE, STATUS_TRUE, STATUS_UNKNOWN
from .mechanism_taxonomy import (
    component_is_conductor,
    component_is_signal_conditioning,
    component_is_transducer,
)
from .models import GraphNode, SensorPhysicalGraph


@dataclass
class CheckResult:
    status: str
    explanation: str
    mandatory_preconditions: List[Dict[str, Any]] = field(default_factory=list)
    parameter_constraints: List[Dict[str, Any]] = field(default_factory=list)


def _precondition(claim: str, status: str, scope: str = "generic_physics") -> Dict[str, Any]:
    return {
        "claim": claim,
        "required_evidence_scope": scope,
        "current_status": status,
        "evidence_refs": [],
    }


def _is_microphone_graph(graph: SensorPhysicalGraph) -> bool:
    text = " ".join(
        [graph.sensor_model]
        + [
            f"{node.name} {node.component_name}"
            for node in graph.component_nodes()
            if node.source_stage == "step1"
        ]
    ).lower()
    return "microphone" in text or "麦克风" in text


def _is_acoustic_sensor_graph(graph: SensorPhysicalGraph) -> bool:
    text = " ".join(
        [graph.sensor_model]
        + [
            " ".join(
                [
                    node.name,
                    node.component_name,
                    " ".join(str(alias) for alias in node.attributes.get("collapsed_aliases", [])),
                ]
            )
            for node in graph.component_nodes()
            if node.source_stage == "step1"
        ]
    ).lower()
    acoustic_keywords = [
        "microphone",
        "麦克风",
        "ultrasonic sensor",
        "ultrasonic ranging",
        "ultrasound sensor",
        "sonar",
        "acoustic sensor",
        "超声波传感器",
    ]
    if any(keyword in text for keyword in acoustic_keywords):
        return True
    return any(
        node.source_stage == "step1"
        and node.component_category == "Acoustic Transducer"
        for node in graph.component_nodes()
    )


class BaseMechanismChecker:
    mechanism_name = ""

    def check(self, graph: SensorPhysicalGraph, source_node: GraphNode, target_node: GraphNode, candidate: Dict[str, Any]) -> CheckResult:
        raise NotImplementedError

    def _component_category(self, source_node: GraphNode, target_node: GraphNode) -> str:
        return target_node.component_category or source_node.component_category

    def _component_name(self, source_node: GraphNode, target_node: GraphNode) -> str:
        return target_node.component_name or target_node.name or source_node.component_name or source_node.name


class SaturationEffectChecker(BaseMechanismChecker):
    mechanism_name = "Saturation Effect"

    def check(self, graph, source_node, target_node, candidate):
        category = self._component_category(source_node, target_node)
        ok_component = component_is_transducer(category) or component_is_signal_conditioning(category)
        preconditions = [
            _precondition("Target component is a transducer or signal conditioning component.", STATUS_TRUE if ok_component else STATUS_FALSE, "target_specific"),
            _precondition("Input amplitude/charge/voltage/current may exceed dynamic range.", STATUS_UNKNOWN, "target_specific"),
            _precondition("Saturation can propagate as clipping, bias, maximum output, or distortion.", STATUS_TRUE),
        ]
        if not ok_component:
            return CheckResult(STATUS_FALSE, "Saturation requires a transducer or signal conditioning component.", preconditions)
        status = STATUS_UNKNOWN
        if candidate.get("assume_qualitative_overdrive") or target_node.component_category in {"Amplifier", "Optical Transducer"}:
            status = STATUS_TRUE
            preconditions[1]["current_status"] = STATUS_TRUE
        return CheckResult(status, "Saturation is admissible only when overdrive or dynamic-range excess is supported.", preconditions)


class NonlinearityChecker(BaseMechanismChecker):
    mechanism_name = "Nonlinearity"

    def check(self, graph, source_node, target_node, candidate):
        category = self._component_category(source_node, target_node)
        ok_component = component_is_transducer(category) or component_is_signal_conditioning(category)
        preconditions = [
            _precondition("Target component can have a specific nonlinear response.", STATUS_UNKNOWN if ok_component else STATUS_FALSE, "target_specific"),
            _precondition("Nonlinearity may generate harmonics, demodulation, or AC-to-DC effects.", STATUS_TRUE),
            _precondition("The converted signal can propagate to output.", STATUS_UNKNOWN, "target_specific"),
        ]
        if not ok_component:
            return CheckResult(STATUS_FALSE, "Nonlinearity needs a specific nonlinear component, not generic circuit handwaving.", preconditions)
        if (
            _is_microphone_graph(graph)
            and candidate.get("assume_microphone_ultrasonic_nonlinearity_prior")
            and candidate.get("modulated_high_frequency_input")
        ):
            preconditions[0]["current_status"] = STATUS_TRUE
            preconditions[2]["current_status"] = STATUS_TRUE
            return CheckResult(
                STATUS_TRUE,
                "A modulated ultrasonic microphone input may be demodulated by nonlinear MEMS/AFE transfer terms and propagate at baseband.",
                preconditions,
            )
        return CheckResult(
            STATUS_UNKNOWN,
            "Nonlinearity is rare and requires target-specific evidence; component taxonomy alone is insufficient.",
            preconditions,
        )


class NonIdealCutoffChecker(BaseMechanismChecker):
    mechanism_name = "Non-ideal Cutoff"

    def check(self, graph, source_node, target_node, candidate):
        category = self._component_category(source_node, target_node)
        ok_component = category in {"Filter", "Acoustic Transducer", "Optical Transducer", "Force Transducer", "Amplifier"}
        preconditions = [
            _precondition("An intended passband/stopband exists.", STATUS_TRUE if ok_component else STATUS_FALSE, "target_specific"),
            _precondition("Input lies outside the intended design band.", STATUS_UNKNOWN, "target_specific"),
            _precondition("Nonzero stop-band response can propagate further.", STATUS_UNKNOWN, "target_specific"),
        ]
        if not ok_component:
            return CheckResult(STATUS_FALSE, "Non-ideal cutoff needs a transducer/filter/passband element.", preconditions)
        if candidate.get("out_of_band_input") and candidate.get("nonzero_stopband_response"):
            preconditions[1]["current_status"] = STATUS_TRUE
            preconditions[2]["current_status"] = STATUS_TRUE
            return CheckResult(
                STATUS_TRUE,
                "The input is outside the intended band and a real transition/stop band has nonzero response.",
                preconditions,
            )
        return CheckResult(STATUS_UNKNOWN, "Band edge and stop-band response parameters are not fixed in Step2.", preconditions)


class AliasingEffectChecker(BaseMechanismChecker):
    mechanism_name = "Aliasing Effect"

    def check(self, graph, source_node, target_node, candidate):
        category = self._component_category(source_node, target_node)
        has_adc = category == "ADC" or any(node.component_category == "ADC" for node in graph.component_nodes())
        target_is_adc = category == "ADC"
        preconditions = [
            _precondition("Aliasing occurs at an ADC/sampling stage.", STATUS_TRUE if target_is_adc else STATUS_FALSE, "target_specific"),
            _precondition("Input contains a component above Nyquist.", STATUS_UNKNOWN, "target_specific"),
            _precondition("Alias relation is omega_a = |omega - k * omega_s|.", STATUS_TRUE),
        ]
        if not has_adc or not target_is_adc:
            return CheckResult(STATUS_FALSE, "Aliasing can only be placed at an ADC sampling stage.", preconditions)
        status = STATUS_TRUE if candidate.get("high_frequency_input") else STATUS_UNKNOWN
        if status == STATUS_TRUE:
            preconditions[1]["current_status"] = STATUS_TRUE
        return CheckResult(status, "Sampling can fold high-frequency input into a lower-frequency digital component.", preconditions)


class ResonanceEffectChecker(BaseMechanismChecker):
    mechanism_name = "Resonance Effect"

    def check(self, graph, source_node, target_node, candidate):
        if _is_microphone_graph(graph):
            return CheckResult(
                STATUS_FALSE,
                "Microphone-class sensors are excluded from Resonance Effect by the Step2 threat model.",
                [
                    _precondition(
                        "Target sensor is not a microphone-class sensor.",
                        STATUS_FALSE,
                        "target_specific",
                    )
                ],
            )
        input_modality = (candidate.get("input_modality") or source_node.modality or "").lower()
        category = self._component_category(source_node, target_node)
        ok_input = input_modality in {"acoustic", "mechanical"}
        ok_component = category in {"Force Transducer", "Acoustic Transducer"} or "mems" in self._component_name(source_node, target_node).lower()
        preconditions = [
            _precondition("Input is acoustic or mechanical.", STATUS_TRUE if ok_input else STATUS_FALSE),
            _precondition("Target is a mechanical structure or mechanically vibrating transducer.", STATUS_TRUE if ok_component else STATUS_FALSE, "target_specific"),
            _precondition("Attack frequency may be near structural resonance.", STATUS_UNKNOWN, "target_specific"),
            _precondition("Mechanical response can propagate to electrical output.", STATUS_UNKNOWN, "target_specific"),
        ]
        if not ok_input:
            return CheckResult(STATUS_FALSE, f"Resonance input cannot be {input_modality or 'unknown'} without an explicit mechanical conversion.", preconditions)
        if not ok_component:
            return CheckResult(STATUS_FALSE, "No mechanically resonant target component is supported by Step1.", preconditions)
        return CheckResult(STATUS_UNKNOWN, "Resonant frequency and mechanical transfer evidence are not known in Step2.", preconditions)


class PhotoacousticEffectChecker(BaseMechanismChecker):
    mechanism_name = "Photoacoustic Effect"

    def check(self, graph, source_node, target_node, candidate):
        input_modality = (candidate.get("input_modality") or source_node.modality or "").lower()
        inferred_microphone_prior = bool(candidate.get("assume_microphone_photoacoustic_prior"))
        if not _is_acoustic_sensor_graph(graph):
            return CheckResult(
                STATUS_FALSE,
                "Photoacoustic Effect is restricted to acoustic-class sensors in this Step2 mechanism model.",
                [
                    _precondition("Input is optical.", STATUS_TRUE if input_modality == "optical" else STATUS_FALSE),
                    _precondition("Target sensor is acoustic-class.", STATUS_FALSE, "target_specific"),
                ],
            )
        preconditions = [
            _precondition("Input is optical.", STATUS_TRUE if input_modality == "optical" else STATUS_FALSE),
            _precondition("Light absorption can create thermal expansion or mechanical vibration.", STATUS_TRUE),
            _precondition("A target component can respond to resulting mechanical vibration.", STATUS_TRUE if inferred_microphone_prior else STATUS_UNKNOWN, "target_specific"),
            _precondition("Mechanical response can form electrical output.", STATUS_TRUE if inferred_microphone_prior else STATUS_UNKNOWN, "target_specific"),
        ]
        if input_modality != "optical":
            return CheckResult(STATUS_FALSE, "Photoacoustic effect requires optical input.", preconditions)
        if inferred_microphone_prior:
            return CheckResult(STATUS_TRUE, "Microphone optical-access prior admits a photoacoustic path unless optical shielding is explicit.", preconditions)
        return CheckResult(STATUS_UNKNOWN, "Photoacoustic conversion is possible in physics but target-specific absorption/mechanics are unknown.", preconditions)


class PhotoelectricEffectChecker(BaseMechanismChecker):
    mechanism_name = "Photoelectric Effect"

    def check(self, graph, source_node, target_node, candidate):
        input_modality = (candidate.get("input_modality") or source_node.modality or "").lower()
        category = self._component_category(source_node, target_node)
        component_name = self._component_name(source_node, target_node).lower()
        inferred_microphone_prior = bool(candidate.get("assume_microphone_photoelectric_prior"))
        photo_target = (
            inferred_microphone_prior
            or category == "Optical Transducer"
            or any(k in component_name for k in ["photodiode", "ccd", "cmos", "photosensitive", "junction"])
        )
        preconditions = [
            _precondition("Input is optical.", STATUS_TRUE if input_modality == "optical" else STATUS_FALSE),
            _precondition("Target material/structure can generate carriers.", STATUS_TRUE if photo_target else STATUS_UNKNOWN, "target_specific"),
            _precondition("Generated current, voltage, or DC bias enters downstream circuitry.", STATUS_TRUE if inferred_microphone_prior else STATUS_UNKNOWN, "target_specific"),
        ]
        if input_modality != "optical":
            return CheckResult(STATUS_FALSE, "Photoelectric effect requires optical input.", preconditions)
        status = STATUS_TRUE if photo_target else STATUS_UNKNOWN
        return CheckResult(status, "Optical input may generate electrical charge/current in a photo-sensitive target.", preconditions)


class AntennaEffectChecker(BaseMechanismChecker):
    mechanism_name = "Antenna Effect"

    def check(self, graph, source_node, target_node, candidate):
        input_modality = (candidate.get("input_modality") or source_node.modality or "").lower()
        category = self._component_category(source_node, target_node)
        name = self._component_name(source_node, target_node)
        conductor = component_is_conductor(category, name)
        preconditions = [
            _precondition("Input is electromagnetic.", STATUS_TRUE if input_modality == "electromagnetic" else STATUS_FALSE),
            _precondition("Target structure is conductive, such as pin, wire, PCB trace, power line, or cable.", STATUS_TRUE if conductor else STATUS_FALSE, "target_specific"),
            _precondition("A conductive structure can develop induced voltage/current under electromagnetic excitation.", STATUS_TRUE),
        ]
        if input_modality != "electromagnetic":
            return CheckResult(STATUS_FALSE, "Antenna effect requires electromagnetic input.", preconditions)
        if not conductor:
            return CheckResult(STATUS_FALSE, "Antenna effect requires a conductive target structure.", preconditions)
        status = STATUS_TRUE if target_node.evidence_status == STATUS_TRUE else STATUS_UNKNOWN
        return CheckResult(status, "Conductive structures can pick up electromagnetic energy as induced electrical interference.", preconditions)


CHECKER_CLASSES = [
    SaturationEffectChecker,
    NonlinearityChecker,
    NonIdealCutoffChecker,
    AliasingEffectChecker,
    ResonanceEffectChecker,
    PhotoacousticEffectChecker,
    PhotoelectricEffectChecker,
    AntennaEffectChecker,
]


def build_mechanism_checkers() -> Dict[str, BaseMechanismChecker]:
    return {cls.mechanism_name: cls() for cls in CHECKER_CLASSES}
