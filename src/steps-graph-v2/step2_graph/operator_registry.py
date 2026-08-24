from __future__ import annotations

from typing import Any, Dict, List

from .constants import ALLOWED_MECHANISMS
from .mechanism_checkers import CheckResult, build_mechanism_checkers
from .models import GraphNode, SensorPhysicalGraph


class PhysicalOperatorRegistry:
    def __init__(self) -> None:
        self.checkers = build_mechanism_checkers()
        self.operators = self._build_operator_metadata()

    def _build_operator_metadata(self) -> Dict[str, Dict[str, Any]]:
        return {
            "Saturation Effect": {
                "mechanism_name": "Saturation Effect",
                "allowed_input_modalities": ["acoustic", "optical", "electromagnetic", "mechanical", "electrical"],
                "allowed_component_categories": ["Acoustic Transducer", "Optical Transducer", "Force Transducer", "Signal Conditioning Circuits", "Amplifier", "Filter", "ADC"],
                "allowed_component_properties": ["finite dynamic range", "maximum charge/voltage/current"],
                "output_modalities": ["electrical", "digital"],
                "mandatory_preconditions": ["overdrive or dynamic-range excess", "output propagation"],
                "parameter_relations": ["input magnitude > component dynamic range"],
                "incompatible_conditions": ["no transducer or signal conditioning stage"],
            },
            "Nonlinearity": {
                "mechanism_name": "Nonlinearity",
                "allowed_input_modalities": ["acoustic", "mechanical", "electrical"],
                "allowed_component_categories": ["Acoustic Transducer", "Signal Conditioning Circuits", "Amplifier", "Filter", "ADC"],
                "allowed_component_properties": ["specific nonlinear transfer in an acoustic-class sensor"],
                "output_modalities": ["electrical", "digital"],
                "mandatory_preconditions": ["specific nonlinear response", "propagation to output"],
                "parameter_relations": ["harmonic, demodulated, or rectified component"],
                "incompatible_conditions": ["non-acoustic target sensor", "accepted only because circuits are usually nonlinear"],
            },
            "Non-ideal Cutoff": {
                "mechanism_name": "Non-ideal Cutoff",
                "allowed_input_modalities": ["acoustic", "optical", "mechanical", "electrical"],
                "allowed_component_categories": ["Acoustic Transducer", "Optical Transducer", "Force Transducer", "Signal Conditioning Circuits", "Amplifier", "Filter"],
                "allowed_component_properties": ["intended passband/stopband"],
                "output_modalities": ["electrical", "digital"],
                "mandatory_preconditions": ["design band exists", "input is outside intended band", "nonzero stop-band response"],
                "parameter_relations": ["input frequency outside passband but not fully rejected"],
                "incompatible_conditions": ["no passband/stopband element"],
            },
            "Aliasing Effect": {
                "mechanism_name": "Aliasing Effect",
                "allowed_input_modalities": ["electrical"],
                "allowed_component_categories": ["ADC"],
                "allowed_component_properties": ["sampling"],
                "output_modalities": ["digital"],
                "mandatory_preconditions": ["ADC/sampling stage", "input above Nyquist"],
                "parameter_relations": ["omega_a = |omega - k * omega_s|"],
                "incompatible_conditions": ["no sampling operation"],
            },
            "Resonance Effect": {
                "mechanism_name": "Resonance Effect",
                "allowed_input_modalities": ["acoustic", "mechanical"],
                "allowed_component_categories": ["Acoustic Transducer", "Force Transducer"],
                "allowed_component_properties": ["mechanically vibrating structure"],
                "output_modalities": ["mechanical", "electrical"],
                "mandatory_preconditions": ["attack frequency near structural resonance", "mechanical-to-electrical propagation"],
                "parameter_relations": ["attack frequency approximately equals resonance frequency"],
                "incompatible_conditions": ["direct electromagnetic resonance", "direct optical resonance"],
            },
            "Photoacoustic Effect": {
                "mechanism_name": "Photoacoustic Effect",
                "allowed_input_modalities": ["optical"],
                "allowed_component_categories": ["Acoustic Transducer", "Force Transducer", "Optical Transducer"],
                "allowed_component_properties": ["light absorption", "thermal expansion", "mechanical vibration"],
                "output_modalities": ["mechanical", "electrical"],
                "mandatory_preconditions": ["optical input", "absorption-induced vibration", "mechanical response"],
                "parameter_relations": ["absorbed optical energy produces pressure/vibration"],
                "incompatible_conditions": ["non-optical input", "non-acoustic target sensor"],
            },
            "Photoelectric Effect": {
                "mechanism_name": "Photoelectric Effect",
                "allowed_input_modalities": ["optical"],
                "allowed_component_categories": ["Optical Transducer", "Signal Conditioning Circuits", "Wires"],
                "allowed_component_properties": ["carrier generation material or conductive structure"],
                "output_modalities": ["electrical"],
                "mandatory_preconditions": ["optical input", "carrier generation", "electrical propagation"],
                "parameter_relations": ["photons generate current/voltage/DC bias"],
                "incompatible_conditions": ["non-optical input"],
            },
            "Antenna Effect": {
                "mechanism_name": "Antenna Effect",
                "allowed_input_modalities": ["electromagnetic"],
                "allowed_component_categories": ["Wires", "Power Supply", "Communication Interface"],
                "allowed_component_properties": ["conductor", "pin", "wire", "PCB trace", "power line", "communication cable"],
                "output_modalities": ["electrical"],
                "mandatory_preconditions": ["electromagnetic input", "conductive target", "induced voltage/current"],
                "parameter_relations": ["L approximately lambda/4 is only a symbolic relation unless target length is known"],
                "incompatible_conditions": ["non-conductive target"],
            },
        }

    def serialize_allowed_operators(self) -> List[Dict[str, Any]]:
        return [self.operators[name] for name in ALLOWED_MECHANISMS]

    def check(self, mechanism_name: str, graph: SensorPhysicalGraph, source_node: GraphNode, target_node: GraphNode, candidate: Dict[str, Any]) -> CheckResult:
        checker = self.checkers.get(mechanism_name)
        if checker is None:
            return CheckResult("FALSE", f"Mechanism is not in prompt3_1 taxonomy: {mechanism_name}")
        return checker.check(graph, source_node, target_node, candidate)
