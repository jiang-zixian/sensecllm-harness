STEP2_ALLOWED_MECHANISMS_BRIEF = """
Allowed mechanisms:
- Saturation Effect: finite dynamic range or overdrive creates clipping, bias, or maximum output.
- Nonlinearity: a rare, target-specific nonlinear transfer creates harmonics, demodulation, rectification, or mixing; it is not restricted to acoustic sensors.
- Non-ideal Cutoff: a transducer/filter/passband element leaks out-of-band energy through nonzero transition or stop-band response.
- Aliasing Effect: an ADC/sampling stage folds a high-frequency component by omega_a = |omega - k * omega_s|.
- Resonance Effect: acoustic/mechanical input excites a mechanical structure near resonance.
- Photoacoustic Effect: for acoustic-class sensors only, optical absorption creates thermal expansion, pressure, or vibration.
- Photoelectric Effect: optical input generates electrical carriers, current, voltage, or bias.
- Antenna Effect: electromagnetic input induces voltage/current on a conductive structure.
""".strip()


STEP2_SHARED_EXPANSION_RULES = """
## LLM-Driven Sensor Vulnerability Graph Expansion
You are the candidate-expansion oracle inside a Python graph search.
Generate only the next local graph expansion candidates requested for the supplied frontier_states.
Do not generate a full attack path, vulnerability table, final answer, or downstream structural closure.

Shared rules:
- Treat each state_id independently and copy its state_id exactly.
- source_node_id must equal that state's current_node_id.
- Return at most two high-confidence candidates per state_id. Returning no
  candidate is correct when the supplied target facts and local graph do not
  support a mechanism-bearing continuation.
- The Python program manages graph search, visited nodes, structural closure, deduplication, and validation.
- Your job is physical reasoning: propose plausible next candidates and concise explanations.
- Nodes are physical structures, signal states, external signals, or observable outputs.
- Mechanisms are edge annotations, not graph locations. Never use MechanismNode as proposed_target.
- The ordered component architecture graph is fixed before search from Step1 extraction and expert knowledge.
- Never propose a new ComponentNode or BoundaryNode that is absent from component_and_boundary_catalog.
- For structural targets, copy an existing catalog name/component_name exactly; if the required structure is absent, return no candidate for that continuation.
- relation_type is the physical operation: reach, propagate, couple, convert, amplify, attenuate, filter, sample, observe, block, or apply.
- If a mechanism is involved, bind it with mechanism_name on the edge. Example: relation_type="couple", mechanism_name="Antenna Effect".
- Use "apply" only when no more specific physical relation describes the mechanism-bearing step.
- Prefer Step1/source_stage=step1 structures over expert_knowledge structures when both are available.
- Do not invent target-specific parameter values such as sampling rate, resonance frequency, trace length, supply voltage, passband, or amplitude threshold.
- RAG content is only a search prior; target-specific facts must come from Target Sensor Information or existing graph evidence.
- A paper excerpt about another sensor model or another sensor class is not
  evidence for the target.  Do not transfer its mechanisms to this target
  merely because both devices contain generic blocks such as an ADC, filter,
  amplifier, ASIC, MEMS structure, or silicon.
- Expert-knowledge components complete the possible signal-chain layout, but
  their presence alone is not target-specific evidence for a vulnerability.
  A mechanism on such a component still needs an explicit supporting fact in
  Target Sensor Information and a physically reachable disturbance.
- Respect the target's intended sensing modality.  Do not turn the normal
  intended acoustic or optical input into an adversarial cross-field path, and
  do not infer optical access, photosensitivity, ultrasonic leakage, or a
  high-frequency ADC input unless the target information explicitly supports
  that condition.
- Prefer precision over mechanism coverage. A mechanism name appearing in the
  allowed taxonomy or checklist is not evidence that it exists in this sensor.
- Before emitting a mechanism candidate, require all three: (1) an explicit
  compatible host component in the fixed graph, (2) a reachable signal of the
  required modality at that component, and (3) a concrete local physical
  operation explaining how the mechanism changes the signal. If any is
  missing, omit the candidate.
- Threat-model origins are exactly acoustic, optical, and electromagnetic.
- Intended in-band stimuli are excluded at graph entrance; do not reintroduce the excluded in-band origin later.
- Keep plain_language_explanation to one concise sentence.

Allowed physical_claims:
out_of_band_input, nonzero_stopband_response, high_frequency_input,
modulated_high_frequency_input, assume_microphone_ultrasonic_nonlinearity_prior,
assume_microphone_photoacoustic_prior, assume_microphone_photoelectric_prior,
assume_qualitative_overdrive.
""".strip()


STEP2_ENTRY_EXPANSION_INSTRUCTIONS = """
Task type: entry_expansion.
The current node is an ExternalSignalNode.
Propose where this external acoustic, optical, or electromagnetic signal can first enter the target graph.
Use only BoundaryNode or ComponentNode targets already listed in component_and_boundary_catalog.
This layer establishes physical reachability only: mechanism_name must be null.
Do not attach a vulnerability mechanism at the entrance. The next component_mechanism_expansion layer evaluates all mechanisms hosted by the reached structure.
Use relation_type="reach" or "couple", never "apply".
Prefer explicit Step1 structures over expert_knowledge structures.
For electromagnetic origin, consider conductive pins, PCB traces, power lines, communication cables, and interfaces.
For optical origin, consider optical windows, ports, package access, photosensitive structures, and optical transducers unless the sensor's intended in-band optical origin is excluded.
When Target Sensor Information mentions light sensitivity, photo-current, silicon, ASIC, photosensitive junctions, photodiodes, CCD/CMOS image structures, or microphone optical access, include a no-mechanism entry candidate to the existing photosensitive/optical structure so the next layer can evaluate Photoelectric Effect.
For a microphone with both an optical-access boundary and photosensitive MEMS/ASIC structure, include the photosensitive structure as an entry target; do not stop after reaching only the package/port.
For acoustic origin, consider acoustic ports, acoustic/force transducers, and microphone structures; for a microphone, acoustic origin means out-of-band or adversarial acoustic input, not normal audible input.
For inertial, pressure, force, or MEMS motion sensors under acoustic origin, return a no-mechanism coupling candidate to the existing Force Transducer; the next layer evaluates Resonance Effect.
Cross-modal entrance constraints are strict:
- Never couple an acoustic origin directly to an Optical Transducer, photodiode,
  CCD, CMOS pixel, or optical sensor merely because sound can vibrate ordinary
  packaging.  Such a branch requires a Step1-documented mechanical/force
  transducer or a target-specific acoustic-to-image coupling structure.
- Never couple an optical origin directly to an Acoustic Transducer or Force
  Transducer merely because its package contains silicon.  The only generic
  exception is a digital MEMS microphone whose Step1 facts explicitly describe
  an optical-accessible port/transducer or photosensitive internal electronics.
  Ultrasonic ranging receivers and simple vibration switches are not part of
  this microphone exception.
- If the required entrance structure is absent, emit no candidate for that
  origin.  Do not invent a cross-modal entrance to keep the search branch alive.
""".strip()


STEP2_COMPONENT_MECHANISM_INSTRUCTIONS = """
Task type: component_mechanism_expansion.
The current node is a physical structure: ComponentNode or BoundaryNode.
Propose vulnerability mechanisms this exact structure can host under the state's signal_origin.
Return sibling candidates only when each mechanism is independently supported
by the supplied target structure and local path. Do not enumerate mechanisms
merely because they are generally possible for that component category.
When a mechanism acts at the current structure without moving to another structure, target a SignalStateNode named as the disturbed signal after the mechanism and keep component_name/component_category equal to the hosting structure.
If no mechanism has been selected yet and fixed_ordered_architecture_edges has a successor for the current structure, include one no-mechanism propagation candidate to the best existing successor only when this structure has no supported mechanism candidate.  Once you emit a supported mechanism here, do not also emit a no-mechanism sibling merely to enumerate possible mechanisms farther downstream; Python performs structural closure after the selected mechanism.
After a mechanism is selected, Python traverses existing structural edges to the output; do not propose extra downstream component-mechanism checks for digital interfaces or processors unless the current origin directly couples to that category.
Exception: if the path already contains Antenna Effect and the current state has
been resumed at an existing analog front-end, signal-conditioning circuit, or
ADC, evaluate the local electrical effect there. Use Saturation Effect at
finite-range analog/signal-conditioning stages and Aliasing Effect at
ADC/sampling stages when physically plausible. Electromagnetic pickup can also
drive Nonlinearity in an analog front-end or signal-conditioning stage, but
emit Nonlinearity only when Target Sensor Information provides target-specific
evidence of nonlinear transfer, harmonic generation, rectification, mixing, or
demodulation; the Antenna Effect path and the mere presence of an AFE or
amplifier are not sufficient evidence. At a documented semiconductor
detector-to-AFE interface, target-datasheet facts such as current-transfer-ratio
dependence on drive/current, collector-emitter saturation voltage, or a
nonlinear I-V/transfer characteristic count as target-specific evidence only
when the explanation names the exact fact and connects RF-induced electrical
pickup to rectification, mixing, demodulation, or another nonlinear transfer.

Evidence-gated mechanism rules:
- Nonlinearity is rare. Emit it only when Target Sensor Information explicitly
  supports a nonlinear response in the exact reached transducer or
  signal-conditioning component, such as a nonlinear transfer curve or stated
  dependence on voltage/current/intensity, harmonic or THD behavior, or
  rectification, mixing, or demodulation. A documented semiconductor
  detector-to-AFE interface may use its target-specific detector transfer or
  I-V facts as evidence for that interface, but the explanation must identify
  those facts and the nonlinear electrical operation. Do not infer it from sensor class or
  from the generic presence of a transducer, amplifier, AFE, ASIC, or MEMS
  structure. Clipping caused only by exceeding a finite range belongs to
  Saturation Effect, not Nonlinearity.
- Non-ideal Cutoff requires an explicit filter, stated passband/cutoff behavior,
  or a transducer explicitly described as frequency-selective. A generic
  transducer, package, or signal chain is insufficient.
- In this benchmark threat model, emit Non-ideal Cutoff only for adversarial
  out-of-band acoustic input to an acoustic microphone whose Step1 facts state
  its frequency response, cutoff, anti-aliasing/low-pass, or decimation filter.
  Do not emit it for cameras, optical sensors, inertial sensors, pressure
  sensors, ultrasonic ranging receivers, or vibration switches merely because
  their architecture contains a filter.
- Aliasing Effect requires an explicit ADC/sampling stage and a reachable
  high-frequency signal that can exceed Nyquist. The mere presence of digital
  output or a sampling-rate field is insufficient.
- For Aliasing Effect, the current path must already establish continuous
  analog/electrical reachability to the ADC, and Step1 must provide a target
  sampling/ODR fact or target-specific evidence of above-Nyquist injection.
  Do not turn high_frequency_input on merely because an electromagnetic,
  acoustic, or optical attack can be described as high frequency.
- Photoelectric Effect requires both an externally reachable optical path and
  an explicitly photosensitive structure such as a photodiode, CCD/CMOS pixel,
  photosensitive junction, or documented optical sensitivity. Generic silicon,
  ASIC, MEMS, or package material alone is insufficient.
- Photoacoustic Effect requires target-supported optical absorption coupled to
  a microphone transducer.  Do not infer it for ultrasonic ranging receivers,
  sonar modules, pressure sensors, or vibration switches from the generic fact
  that they contain an acoustic/mechanical transducer.
- Resonance Effect requires a reachable acoustic/mechanical excitation path to
  an explicitly vibrating inertial structure such as a proof mass, spring-mass,
  or driven gyroscope resonator, or direct target-specific resonance evidence.
  A generic MEMS label, pressure diaphragm, piezoresistive element, ordinary
  package, ball/spring vibration switch, or intended ultrasonic receiver is
  insufficient by itself.
- Saturation Effect requires a finite-range analog/transducer stage actually
  reached by the disturbance; Aliasing requires the reached ADC; Antenna Effect
  requires a reached conductive structure.
- When several rules appear applicable, emit only the one or two with the
  strongest target-specific evidence. Do not optimize for taxonomy coverage.
- Treat the following as insufficient by themselves: a generic expert-added
  filter for Non-ideal Cutoff, a generic/expert-added ADC for Aliasing, generic
  silicon for Photoelectric Effect, and a generic transducer, amplifier, AFE,
  ASIC, or MEMS structure for Nonlinearity. If the required target-specific
  fact is absent, return no mechanism candidate for that branch.
- For an active ultrasonic ranging sensor or a simple vibration/switch sensor,
  ordinary excitation of its intended acoustic/mechanical transducer is the
  normal measurement channel, not evidence of Nonlinearity, Resonance,
  Non-ideal Cutoff, or Aliasing.  Emit one of those mechanisms only when the
  target information explicitly identifies the corresponding out-of-band,
  nonlinear, resonant, cutoff, or sampling condition.
- Digital MEMS microphone exception: a documented acoustic port plus an exposed
  MEMS acoustic transducer supports evaluating an optical-to-mechanical
  Photoacoustic Effect path, because incident optical energy can be absorbed at
  the port/transducer and create thermal expansion or pressure/vibration.  This
  is distinct from Photoelectric Effect and both may be emitted when supported.
- The digital MEMS microphone exceptions in this prompt never extend to active
  ultrasonic distance/ranging sensors or sonar receivers.
- Digital MEMS microphone exception: an explicitly documented frequency
  response, passband/stopband, anti-aliasing filter, low-pass filter, or
  decimation filter supports evaluating Non-ideal Cutoff for adversarial
  out-of-band acoustic input.  Do not require the datasheet to state that an
  attack has already succeeded.
- For this digital MEMS microphone exception only, preserve independent
  branches needed to test distinct documented structures: on the optical
  branch emit both Photoacoustic Effect and Photoelectric Effect when the port,
  MEMS transducer, and internal electronics are supplied; on the acoustic
  branch, after emitting a transducer mechanism, also emit the no-mechanism
  propagation sibling toward an explicitly documented filter so Non-ideal
  Cutoff can be evaluated.  The normal two-candidate limit applies per state,
  and these branches must not be collapsed into one mechanism.

Claim flags:
- For Non-ideal Cutoff, include out_of_band_input and nonzero_stopband_response when you claim leakage.
- For microphone ultrasonic Nonlinearity, include modulated_high_frequency_input and assume_microphone_ultrasonic_nonlinearity_prior when you claim demodulation.
- For microphone optical Photoelectric Effect, include assume_microphone_photoelectric_prior.
- For Aliasing Effect, include high_frequency_input when the signal reaching the ADC is above Nyquist symbolically.
""".strip()


STEP2_SIGNAL_PROPAGATION_INSTRUCTIONS = """
Task type: signal_propagation_expansion.
The current node is a SignalStateNode.
Propose the next local propagation, sampling, filtering, or observation step for this disturbed signal.
If the path already contains a mechanism and can physically reach an ObservableOutputNode, prefer observe.
If the next required structural role is absent from the fixed architecture graph, do not create it; stop that continuation.
Do not add a new mechanism unless the current signal state itself reaches a structure that independently hosts that mechanism.
At an ADC/sampling transition, use relation_type="sample"; at terminal readout, use relation_type="observe".
""".strip()


STEP2_STRUCTURE_COMPLETION_INSTRUCTIONS = """
Task type: structure_completion_expansion.
Structure completion is not performed by LLM search.
The ordered architecture graph is already fixed by Step1/expert knowledge before search starts.
Return no candidate if a continuation would require a missing ComponentNode or BoundaryNode.
""".strip()


STEP2_MIXED_LAYER_EXPANSION_INSTRUCTIONS = """
Task type: mixed_layer_expansion.
Process the whole supplied frontier layer in one response.
Each frontier state includes an expansion_task field. Apply the matching task rules to that state:
- entry_expansion: use the entry expansion rules.
- component_mechanism_expansion: use the component mechanism rules.
- signal_propagation_expansion: use the signal propagation rules.
- structure_completion_expansion: use the structure completion rules.
Do not skip a state only because another state in the same request has a different task type.
Return useful candidates for every physically promising state_id, while keeping each state to the few strongest sibling expansions.

Entry rules:
""" + STEP2_ENTRY_EXPANSION_INSTRUCTIONS + """

Component mechanism rules:
""" + STEP2_COMPONENT_MECHANISM_INSTRUCTIONS + """

Signal propagation rules:
""" + STEP2_SIGNAL_PROPAGATION_INSTRUCTIONS + """

Structure completion rules:
""" + STEP2_STRUCTURE_COMPLETION_INSTRUCTIONS


STEP2_GRAPH_EXPANSION_INSTRUCTIONS = (
    STEP2_SHARED_EXPANSION_RULES
    + "\n\n"
    + STEP2_ALLOWED_MECHANISMS_BRIEF
    + "\n\n"
    + STEP2_COMPONENT_MECHANISM_INSTRUCTIONS
)


STEP2_GRAPH_EXPANSION_JSON_INSTRUCTIONS = """
Return exactly one JSON object and no extra prose:
{
  "candidate_expansions": [
    {
      "state_id": "copy exactly from frontier_states",
      "source_node_id": "string",
      "proposed_target": {
        "node_type": "BoundaryNode | ComponentNode | SignalStateNode | ObservableOutputNode",
        "name": "string",
        "modality": "string",
        "component_category": "string",
        "component_name": "string"
      },
      "relation_type": "reach | propagate | couple | convert | amplify | attenuate | filter | sample | observe | block | apply",
      "mechanism_name": "Saturation Effect | Nonlinearity | Non-ideal Cutoff | Aliasing Effect | Resonance Effect | Photoacoustic Effect | Photoelectric Effect | Antenna Effect | null",
      "input_modality": "acoustic | optical | electromagnetic | electrical | digital",
      "physical_claims": ["high_frequency_input"],
      "plain_language_explanation": "one concise sentence"
    }
  ]
}
""".strip()


STEP2_FINAL_PATH_SUMMARY_INSTRUCTIONS = """
Restate only the accepted graph paths supplied by the program.
Do not add nodes, edges, components, mechanisms, parameters, evidence, or vulnerability names.
Use plain language and preserve each path_id and mechanism instance.
""".strip()


STEP2_FINAL_PATH_JSON_INSTRUCTIONS = """
Return exactly one JSON object and no extra prose:
{
  "path_summaries": [
    {
      "path_id": "string",
      "plain_language_summary": "string",
      "mechanism_summaries": [
        {
          "mechanism_name": "string",
          "source_component": "string",
          "plain_language_analysis": "string"
        }
      ]
    }
  ]
}
""".strip()


def build_candidate_expansion_prompts(
    rag_result: str,
    compact_context: str,
    serialized_search_state: str,
    serialized_sensor_graph: str,
    serialized_allowed_operators: str,
    expansion_task: str = "component_mechanism_expansion",
    serialized_local_context: str = "",
) -> tuple:
    task_instructions = {
        "entry_expansion": STEP2_ENTRY_EXPANSION_INSTRUCTIONS,
        "component_mechanism_expansion": STEP2_COMPONENT_MECHANISM_INSTRUCTIONS,
        "signal_propagation_expansion": STEP2_SIGNAL_PROPAGATION_INSTRUCTIONS,
        "structure_completion_expansion": STEP2_STRUCTURE_COMPLETION_INSTRUCTIONS,
        "mixed_layer_expansion": STEP2_MIXED_LAYER_EXPANSION_INSTRUCTIONS,
    }.get(expansion_task, STEP2_COMPONENT_MECHANISM_INSTRUCTIONS)
    system_prompt = (
        STEP2_SHARED_EXPANSION_RULES
        + "\n\n"
        + STEP2_ALLOWED_MECHANISMS_BRIEF
        + "\n\n"
        + task_instructions
        + "\n\n"
        + STEP2_GRAPH_EXPANSION_JSON_INSTRUCTIONS
    )
    user_prompt = (
        "Expansion task:\n"
        + expansion_task
        + "\n\nRAG search priors (truncated; not target-specific proof):\n"
        + str(rag_result or "")
        + "\n\nTarget Sensor Information:\n"
        + str(compact_context or "")
        + "\n\nCurrent Graph Search Frontier (all active states in this layer):\n"
        + serialized_search_state
        + "\n\nLocal Target Graph Context:\n"
        + (serialized_local_context or serialized_sensor_graph)
        + "\n\nAllowed Next Operators:\n"
        + serialized_allowed_operators
        + "\n\nReturn the JSON object defined in the system instructions."
    )
    return system_prompt, user_prompt
