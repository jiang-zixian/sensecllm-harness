ALLOWED_MECHANISMS = [
    "Saturation Effect",
    "Nonlinearity",
    "Non-ideal Cutoff",
    "Aliasing Effect",
    "Resonance Effect",
    "Photoacoustic Effect",
    "Photoelectric Effect",
    "Antenna Effect",
]

NORMAL_RELATIONS = {
    "reach",
    "propagate",
    "couple",
    "convert",
    "amplify",
    "attenuate",
    "filter",
    "sample",
    "observe",
    "block",
}

SIGNAL_ORIGINS = ["acoustic", "optical", "electromagnetic"]

STATUS_TRUE = "TRUE"
STATUS_FALSE = "FALSE"
STATUS_UNKNOWN = "UNKNOWN"

ACCEPTED = "ACCEPTED_ADMISSIBLE"
UNRESOLVED = "UNRESOLVED"
REJECTED = "REJECTED"
ACTIVE = "ACTIVE"

COMPONENT_CATEGORY_ALIASES = {
    "transducer": "Transducer Module",
    "optical transducer": "Optical Transducer",
    "acoustic transducer": "Acoustic Transducer",
    "electromagnetic transducer": "Electromagnetic Transducer",
    "force transducer": "Force Transducer",
    "signal conditioning": "Signal Conditioning Circuits",
    "signal conditioning circuit": "Signal Conditioning Circuits",
    "amplifier": "Amplifier",
    "filter": "Filter",
    "adc": "ADC",
    "computing": "Computing and Communication Module",
    "dsp": "DSP",
    "communication interface": "Communication Interface",
    "auxiliary": "Auxiliary Module",
    "power supply": "Power Supply",
    "wire": "Wires",
    "wires": "Wires",
    "clock oscillator": "Clock Oscillator",
}

BOUNDARY_KEYWORDS = {
    "package",
    "bottom-port",
    "bottom port",
    "acoustic port",
    "optical window",
    "exposed pin",
    "pin",
    "pcb",
    "conductive trace",
    "trace",
    "wire",
    "communication cable",
    "shielding layer",
    "power line",
}
