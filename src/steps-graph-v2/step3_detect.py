import json
import re
from typing import Any, List, Dict, Optional
from helpers.configs.configs import output_report, chatanywhere_auth_header
from helpers.utils.file_utils import append_report
from helpers.api.chatanywhere_client import chatanywhere_chat_completion
from helpers.configs.prompts import prompt2_1, prompt2_2, prompt2_3
from report_renderers import render_vulnerability_detection
from temp_paths import temp_path


MAX_DETECTION_RETRY = 3

STEP3_JSON_OUTPUT_INSTRUCTIONS = """
## Required JSON Output
Output strict JSON only.
Return exactly one JSON object and no extra prose:
{
  "vulnerability_items": [
    {
      "no": 1,
      "vulnerability_name": "string",
      "mechanism_name": "string",
      "source_component": "string",
      "description": "string",
      "judgment_reason": "string",
      "evidence": [
        {
          "source": "datasheet | Step2 Mechanism | Literatures | Vulnerability Cases | Expert Knowledge",
          "summary": "brief evidence content summary"
        }
      ]
    }
  ]
}

Rules:
- Review every supplied Step-2 mechanism entry and every supplied graph path before answering.
- Treat all supplied paths equally. Step 3 has no accepted/UNKNOWN distinction and
  must not omit a path because exact physical parameters have not yet been verified.
- Classify every numbered Step-2 mechanism entry. Every entry must produce at least
  one vulnerability item with the same `no`, mechanism_name, and source_component.
- Use matching detailed graph paths whenever present. If a numbered mechanism entry
  has no complete end-to-end path, classify it from its Step-2 attack origin, local
  input/output modality, component, mechanism analysis, and sensor facts; absence of
  a complete path must never cause the entry to be omitted.
- The "no" field must be the 1-based index of the corresponding Step-2 mechanism entry, not a free row number.
- One mechanism may produce multiple vulnerability items if the sensor/component context supports them.
- Keep mechanism_name and source_component aligned with the Step-2 mechanism entry.
- Every vulnerability item must have a non-empty "evidence" array grounded in the provided context.
- Each evidence item must include both "source" and "summary".
- Use only these evidence sources: datasheet, Step2 Mechanism, Literatures, Vulnerability Cases, Expert Knowledge.
- Do not output a vulnerability item if you cannot ground it in at least one evidence item.
- Do not output Markdown tables.
- Perform the modality, mechanism-correspondence, and evidence checks yourself before
  emitting the final JSON. There is no downstream verifier in the active Step-3 flow.
- HARD OUTPUT INVARIANT: every item whose mechanism_name is `Saturation Effect`
  and whose described failure is finite-range overdrive, clipping, bias, or
  saturation of an electrical output must use vulnerability_name
  `Electrical-Amplitude Out-of-Range`. Never label that item Cross-Field merely
  from the external attack origin. Check this invariant on every item immediately
  before returning JSON.
""".strip()


STEP3_FORWARD_REASONING_SYSTEM_PROMPT = """
You are the forward-reasoning vulnerability classifier in a generative sensor-security
detection pipeline. Step 2 has already searched a directed physical graph. Your task is
to infer standardized component-level vulnerability names from those paths. Do not
re-run the graph search and do not use a hard-coded lookup result; reason from each
path's external origin, local signal modalities, mechanism edge, component, physical
effect, and observable output.

## Benchmark taxonomy precedence (mandatory)
- `Saturation Effect` always maps to `Electrical-Amplitude Out-of-Range` in this
  benchmark. This mapping has no Cross-Field exception. Apply it even when the
  Saturation Effect is hosted at an optical or acoustic transducer and the remote
  attack origin is acoustic, optical, or electromagnetic.
- Cross-Field may describe a separate explicit coupling/conversion mechanism on the
  same physical path, but must not be assigned to the Saturation Effect item itself.

## Classification procedure (follow internally for every mechanism entry and path)
1. Inspect every numbered mechanism entry and every supplied path. Locate each
   mechanism edge using mechanism name and source component together, and infer its
   vulnerability class from that path when available.
   Do not prioritize or discard paths based on confidence/completeness categories:
   Step 3 intentionally receives no accepted/UNKNOWN distinction.
2. Track two different concepts without conflating them:
   - external attack origin: acoustic, optical, electromagnetic, or mechanical energy;
   - local signal at the mechanism component: the input/output modality on that edge.
3. Identify the physical failure variable. Mechanism-local failure classification
   has priority over the remote attack origin:
   - amplitude limit exceeded -> Amplitude Out-of-Range;
   - intended bandwidth/Nyquist limit exceeded, including demodulation or folding of
     an out-of-band carrier -> Frequency Out-of-Range;
   - unintended coupling or energy conversion from a non-native physical field ->
     Cross-Field.
   Cross-Field applies to the explicit coupling/conversion mechanism instance, not
   automatically to a downstream Saturation Effect instance on the same path.
4. Apply the rules below, then silently self-check modality consistency,
   mechanism-attack correspondence, path grounding, and evidence grounding.

## Naming rules and checker knowledge
- Use exactly `{Modality}-Amplitude Out-of-Range`,
  `{Modality}-Frequency Out-of-Range`, or `{Attack Modality} Cross-Field`.
- Cross-Field names use the EXTERNAL ATTACK modality. They are valid only when that
  modality differs from the sensor/transducer's native measurand modality and the path
  contains an unintended coupling/conversion mechanism. A microphone must not be
  labeled Acoustic Cross-Field merely because an acoustic signal reaches an electrical
  amplifier later in its intended chain.
- Electromagnetic Cross-Field requires unintended EM coupling such as the Antenna
  Effect at wiring, pins, traces, power paths, interfaces, or circuitry.
- Optical Cross-Field requires an optical-to-non-optical disturbance such as the
  Photoacoustic Effect or Photoelectric/Photoelectronic Effect. Treat
  `Photoelectric Effect` and `Photoelectronic Effect` as naming variants of the same
  mechanism family, while preserving the Step-2 mechanism_name in the output.
- Acoustic Cross-Field normally requires Resonance Effect in a sensor whose native
  measurand is not acoustic. Mechanical Cross-Field requires mechanically conducted
  vibration/resonance into a non-mechanical native sensing path.
- Amplitude Out-of-Range requires Saturation Effect, clipping, rail/headroom excess,
  material capacity excess, or an equivalent explicit amplitude-limit path. For an
  amplifier/filter/ADC/circuit, the local limiting quantity is normally electrical,
  so use Electrical-Amplitude Out-of-Range even when EM, optical, or acoustic energy
  originally created that electrical overdrive.
- This Saturation rule is exclusive. If a Saturation Effect entry says that a
  transducer, analog front end, signal-conditioning circuit, or other finite-range
  stage is overdriven and its electrical output clips, biases, or saturates, emit
  Electrical-Amplitude Out-of-Range only. A non-native external acoustic, optical,
  or electromagnetic origin explains how the overdrive was created; it does not by
  itself change this Saturation entry into Cross-Field. In particular, do not emit
  Acoustic Cross-Field for acoustic excitation of an optical transducer when the
  supplied mechanism instance is Saturation Effect and the stated failure is finite
  electrical-output dynamic range.
- Frequency Out-of-Range requires Nonlinearity, Non-ideal Cutoff, or Aliasing Effect
  and an explicit out-of-band/high-frequency condition. At an ADC/sampling stage,
  aliasing classifies as Electrical-Frequency Out-of-Range because the quantity that
  violates Nyquist at the ADC input is electrical; do not rename it after the remote
  external origin. This rule is exclusive: for one Aliasing Effect entry hosted by an
  ADC/sampling stage, emit Electrical-Frequency Out-of-Range only. Do not additionally
  emit Acoustic-Frequency Out-of-Range, Electromagnetic-Frequency Out-of-Range, or any
  second vulnerability merely because another path to that ADC began with a different
  external attack modality.
- Important microphone/front-end convention: if an out-of-band acoustic or ultrasonic
  carrier enters the acoustic sensing path and Non-ideal Cutoff or Nonlinearity lets it
  pass/demodulate into the measurement, classify it as Acoustic-Frequency Out-of-Range.
  This remains true when the nonlinear or filtering manifestation is described at the
  microphone analog front-end, because the violated input band belongs to the acoustic
  sensing path. Do not mislabel this case Acoustic Cross-Field.
- A multi-mechanism path may support separate vulnerabilities: for example, Antenna
  Effect at the coupling point supports Electromagnetic Cross-Field, while downstream
  Saturation or Aliasing can separately support Electrical-Amplitude or
  Electrical-Frequency Out-of-Range. Do not collapse those mechanism instances.
- Propagation through a component does not by itself create another vulnerability.
  Classify only explicit mechanism instances with a physically corresponding effect.
- Do not perform Step-4 feasibility checks (exact attack frequency, bandwidth,
  equipment, or achievable intensity) in Step 3.

## Evidence rules
- Every emitted item needs concrete evidence. Prefer `Step2 Mechanism` evidence that
  cites a path/edge and states the relevant origin -> mechanism -> output reasoning;
  add `datasheet` when a sensor fact supplies the native modality, bandwidth, sampling,
  headroom, or component structure.
- Never invent a paper, vulnerability case, numeric limit, component, or path.
- Missing exact parameters do not weaken or filter a Step-3 classification. Step 3
  classifies all mechanism paths produced for downstream reasoning; exact attack
  parameters and device-specific thresholds belong to Step 4.
- Every supplied path containing a mechanism instance must be classified. Paths with
  the same mechanism/component/vulnerability may be consolidated into one output item,
  but no distinct mechanism instance or distinct vulnerability class may be skipped.
- Every numbered mechanism entry must also be classified even when no supplied path
  contains its edge. Such an entry is a Step-2 graph-search result, not an invitation
  to invent a mechanism: use its supplied attack origin, local modalities, component,
  and detailed analysis as the reasoning evidence. Before returning JSON, verify that
  every numbered entry `no` appears in at least one output item.
- In particular, a missing exact resonance frequency does not prevent classifying acoustic
  excitation of a MEMS force/mechanical transducer through Resonance Effect as Acoustic
  Cross-Field; the exact resonant frequency belongs to later physical verification.
  Likewise, a missing exact overdrive threshold does not prevent classifying Saturation
  Effect in an electrically driven signal-conditioning stage as
  Electrical-Amplitude Out-of-Range when the graph already supplies the induced
  electrical input and propagation route.

Favor completeness across supported paths, but never manufacture a vulnerability to
force one output per mechanism. Return only the required JSON object.
""".strip()


def _extract_chat_content(response_data: dict) -> str:
    try:
        message = response_data["choices"][0]["message"]
    except Exception as e:
        raise RuntimeError(f"ChatAnywhere 返回格式异常: {e}; response={response_data}")
    for key in ("content", "reasoning_content", "reasoning", "refusal"):
        value = message.get(key) if isinstance(message, dict) else None
        if isinstance(value, str) and value.strip():
            return value
    raise RuntimeError(f"ChatAnywhere 返回不包含文本: response={response_data}")


def _normalize_text(text: str) -> str:
    """
    Normalize text for fuzzy matching.
    - lowercase
    - normalize full-width/common punctuation
    - normalize key phrases (cross-field / out-of-range)
    - drop non-alnum chars
    """
    t = str(text or "").strip().lower()
    t = (
        t.replace("｜", "|")
        .replace("¦", "|")
        .replace("—", "-")
        .replace("–", "-")
        .replace("−", "-")
        .replace("（", "(")
        .replace("）", ")")
    )
    t = t.replace("out of range", "out-of-range")
    t = t.replace("cross field", "cross-field")
    return re.sub(r"[^a-z0-9]+", "", t)


def _extract_sensor_type(rag_input: str) -> str:
    """
    Extract and classify sensor type from rag_input.
    Returns one of: Acoustic, Mechanical, Optical, Electromagnetic
    """
    text_lower = rag_input.lower()

    if any(keyword in text_lower for keyword in ["acoustic"]):
        return "Acoustic"
    if any(keyword in text_lower for keyword in ["mechanical", "force", "motion", "pressure", "barometer", "barometric"]):
        return "Mechanical"
    if any(keyword in text_lower for keyword in ["optical"]):
        return "Optical"
    if any(keyword in text_lower for keyword in ["electromagnetic"]):
        return "Electromagnetic"
    # Default fallback
    return "Unknown"


def _is_separator_row(cells: List[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells)


def _parse_markdown_table_rows(text: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or _is_separator_row(cells):
            continue
        rows.append(cells)
    return rows


def _extract_item_numbers(text: str) -> List[int]:
    """
    Extract serial numbers from table/list style content.
    Used for mechanism item-count conservation checks.
    """
    nums: List[int] = []

    # 1) Markdown table first column
    for cells in _parse_markdown_table_rows(text):
        if not cells:
            continue
        first = str(cells[0]).strip()
        m = re.fullmatch(r"(\d+)\s*[\.\)]?", first)
        if m:
            nums.append(int(m.group(1)))

    # 2) Numbered list lines: "1. xxx" / "1) xxx" / "- 1. xxx"
    for line in (text or "").splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?(\d+)\s*[\.\)]\s+", line)
        if m:
            nums.append(int(m.group(1)))

    return sorted(set(nums))


def _count_table_data_rows(text: str) -> int:
    rows = _parse_markdown_table_rows(text)
    if not rows:
        return 0
    count = 0
    for cells in rows:
        if not cells:
            continue
        first = str(cells[0]).strip().lower()
        joined = " ".join(str(c) for c in cells).lower()
        if first in {"no", "no.", "#"}:
            continue
        if "mechanism" in joined and ("source component" in joined or "description" in joined):
            continue
        count += 1
    return count


def _estimate_mechanism_item_count(text: str) -> int:
    """
    Estimate mechanism item count from text.
    Priority:
    1) Explicit serial numbers extracted from report/compressed result
    2) Arrow-style mechanism lines ("name -> component -> desc")
    3) Markdown table data rows
    """
    nums = _extract_item_numbers(text)
    if nums:
        return len(nums)

    arrow_lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if "->" not in stripped:
            continue
        if "mechanism summary" in stripped.lower():
            continue
        arrow_lines.append(stripped)
    if arrow_lines:
        return len(arrow_lines)

    return _count_table_data_rows(text)


def _parse_vulnerability_items(step3_text: str) -> List[Dict[str, str]]:
    rows = _parse_markdown_table_rows(step3_text)
    items: List[Dict[str, str]] = []
    for cells in rows:
        if not cells:
            continue
        first = cells[0].lower()
        if first in {"no.", "no", "------", ":---:"}:
            continue
        if len(cells) >= 6:
            items.append(
                {
                    "no": cells[0],
                    "vulnerability_name": cells[1],
                    "mechanism_name": cells[2],
                    "source_component": cells[3],
                    "description": cells[4],
                    "judgment_reason": cells[5],
                }
            )
            continue
        if len(cells) >= 5:
            mechanism_name = cells[2]
            source_component = ""
            split_parts = re.split(r"\s*[|｜¦]\s*", mechanism_name, maxsplit=1)
            if len(split_parts) == 2:
                mechanism_name, source_component = [x.strip() for x in split_parts]
            items.append(
                {
                    "no": cells[0],
                    "vulnerability_name": cells[1],
                    "mechanism_name": mechanism_name,
                    "source_component": source_component,
                    "description": cells[3],
                    "judgment_reason": cells[4],
                }
            )
    return items


def _strip_json_fence(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _extract_json_text(text: str) -> str:
    stripped = _strip_json_fence(text)
    if not stripped:
        raise ValueError("empty model response")
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass

    starts = [idx for idx in (stripped.find("{"), stripped.find("[")) if idx != -1]
    if not starts:
        raise ValueError("no JSON object or array found")
    start = min(starts)
    end = max(stripped.rfind("}"), stripped.rfind("]"))
    if end < start:
        raise ValueError("incomplete JSON payload")
    candidate = stripped[start : end + 1]
    json.loads(candidate)
    return candidate


def _parse_json_response(text: str) -> Any:
    return json.loads(_extract_json_text(text))


def _first_present(item: Dict[str, Any], keys: tuple) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _normalize_evidence(evidence: Any) -> List[Dict[str, str]]:
    if evidence is None:
        return []
    if isinstance(evidence, str):
        evidence = evidence.strip()
        return [{"source": "unspecified", "summary": evidence}] if evidence else []
    if isinstance(evidence, dict):
        evidence = [evidence]
    if not isinstance(evidence, list):
        return []

    normalized: List[Dict[str, str]] = []
    for entry in evidence:
        if isinstance(entry, str):
            summary = entry.strip()
            if not summary:
                continue
            if ":" in summary or "：" in summary:
                sep = ":" if ":" in summary else "："
                source, content = summary.split(sep, 1)
                normalized.append({"source": source.strip(), "summary": content.strip()})
            else:
                normalized.append({"source": "unspecified", "summary": summary})
            continue
        if not isinstance(entry, dict):
            continue
        source = _first_present(entry, ("source", "Source", "来源", "source_type", "type"))
        summary = _first_present(entry, ("summary", "Summary", "简要内容概括", "content", "evidence", "内容"))
        if source or summary:
            normalized.append({"source": source or "unspecified", "summary": summary})
    return normalized


def _canonical_evidence_source(source: Any) -> str:
    normalized = " ".join(str(source or "").strip().lower().replace("_", " ").split())
    if normalized in {"datasheet", "data sheet", "sensor info", "sensor information", "step1"}:
        return "datasheet"
    if normalized in {"step2 mechanism", "step 2 mechanism", "mechanism", "mechanism analysis", "step2"}:
        return "Step2 Mechanism"
    if normalized in {"literatures", "literature", "paper", "papers", "publication", "publications"}:
        return "Literatures"
    if normalized in {
        "vulnerability cases",
        "vulnerability case",
        "failure cases",
        "failure case",
        "historical cases",
        "historical case",
        "case",
        "cases",
    }:
        return "Vulnerability Cases"
    if normalized in {
        "expert knowledge",
        "expert",
        "taxonomy",
        "mechanism taxonomy",
        "prompt taxonomy",
        "attack knowledge",
        "mechanism knowledge",
        "domain knowledge",
    }:
        return "Expert Knowledge"
    return ""


def _grounded_evidence(evidence: Any) -> List[Dict[str, str]]:
    grounded: List[Dict[str, str]] = []
    for entry in _normalize_evidence(evidence):
        source = _canonical_evidence_source(entry.get("source"))
        summary = str(entry.get("summary") or "").strip()
        if source and summary:
            grounded.append({"source": source, "summary": summary})
    return grounded


def _normalize_vulnerability_item(item: Dict[str, Any], fallback_no: int) -> Dict[str, str]:
    mechanism_name = _first_present(
        item,
        (
            "mechanism_name",
            "Mechanism Name",
            "mechanism",
            "Mechanism",
            "corresponding_mechanism",
            "Mechanism Name ｜Source Component",
            "Mechanism Name | Source Component",
        ),
    )
    source_component = _first_present(
        item,
        (
            "source_component",
            "Source Component",
            "component",
            "Component",
            "specific_sensor_component",
            "Specific Sensor Component",
        ),
    )
    split_parts = re.split(r"\s*[|｜¦]\s*", mechanism_name, maxsplit=1)
    if len(split_parts) == 2 and not source_component:
        mechanism_name, source_component = [x.strip() for x in split_parts]

    evidence = _grounded_evidence(item.get("evidence") or item.get("Evidence") or item.get("证据"))
    return {
        "no": _first_present(item, ("no", "No.", "No", "index", "#")) or str(fallback_no),
        "vulnerability_name": _first_present(
            item,
            (
                "vulnerability_name",
                "Vulnerability Name",
                "vulnerability",
                "Vulnerability",
                "vulnerability_subtype",
                "Vulnerability Subtype",
            ),
        ),
        "mechanism_name": mechanism_name,
        "source_component": source_component,
        "description": _first_present(
            item,
            ("description", "Description", "vulnerability_description", "Vulnerability Description"),
        ),
        "judgment_reason": _first_present(
            item,
            (
                "judgment_reason",
                "Judgment Reason",
                "reason",
                "Reason",
                "basis",
                "Basis",
                "rationale",
                "Rationale",
            ),
        ),
        "evidence": evidence,
    }


def _coerce_vulnerability_items(payload: Any) -> List[Dict[str, str]]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = []
        for key in (
            "vulnerability_items",
            "vulnerabilities",
            "vulnerability_detections",
            "Vulnerability Detection",
            "items",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                raw_items = value
                break
        if not raw_items:
            raise ValueError("vulnerability JSON does not contain a vulnerability_items array")
    else:
        raise ValueError("vulnerability JSON must be an object or list")

    normalized_items = []
    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            continue
        normalized = _normalize_vulnerability_item(raw_item, fallback_no=index)
        if normalized["vulnerability_name"] and normalized["mechanism_name"]:
            normalized_items.append(normalized)
    return normalized_items


def _parse_vulnerability_json_items(raw_text: str) -> List[Dict[str, str]]:
    return _coerce_vulnerability_items(_parse_json_response(raw_text))


def _deduplicate_vulnerability_items(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set = set()
    deduped_items: List[Dict[str, str]] = []
    for item in items:
        key = (
            _normalize_text(item.get("vulnerability_name", "")),
            _normalize_text(item.get("mechanism_name", "")),
            _normalize_text(item.get("source_component", "")),
        )
        if key in seen:
            print(
                "[Step3] Dedup removed: "
                f"{item.get('vulnerability_name')} + {item.get('mechanism_name')} + {item.get('source_component')}"
            )
            continue
        seen.add(key)
        deduped_items.append(item)
    if len(deduped_items) < len(items):
        print(f"[Step3] After dedup: {len(items)} -> {len(deduped_items)}")
    return deduped_items


def _item_no(item: Dict[str, Any]) -> str:
    return str(item.get("no") or "").strip()


def _passed_items_from_slots(item_slots: List[Optional[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return [item for item in item_slots if isinstance(item, dict)]


def _ensure_slot_count(item_slots: List[Optional[Dict[str, Any]]], count: int) -> None:
    while len(item_slots) < count:
        item_slots.append(None)


def _slot_index_for_result(result: Dict[str, Any], fallback_zero_index: int) -> int:
    try:
        slot_index = int(result.get("slot_index"))
        if slot_index >= 0:
            return slot_index
    except (TypeError, ValueError):
        pass
    try:
        item_index = int(result.get("item_index"))
        if item_index > 0:
            return item_index - 1
    except (TypeError, ValueError):
        pass
    item = result.get("item", {}) if isinstance(result, dict) else {}
    if isinstance(item, dict):
        try:
            no = int(_item_no(item))
            if no > 0:
                return no - 1
        except (TypeError, ValueError):
            pass
    return fallback_zero_index


def _failed_result_no(result: Dict[str, Any]) -> str:
    slot_no = str(result.get("slot_no") or "").strip() if isinstance(result, dict) else ""
    if slot_no:
        return slot_no
    item = result.get("item", {}) if isinstance(result, dict) else {}
    if isinstance(item, dict):
        no = _item_no(item)
        if no:
            return no
    try:
        return str(int(result.get("item_index")))
    except (AttributeError, TypeError, ValueError):
        return ""


def _normalize_revision_item_numbers(
    revision_items: List[Dict[str, str]],
    failed_results: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    failed_numbers = [_failed_result_no(result) for result in failed_results]
    failed_numbers = [no for no in failed_numbers if no]
    failed_number_set = set(failed_numbers)
    normalized: List[Dict[str, str]] = []

    for index, item in enumerate(revision_items):
        revised = dict(item)
        current_no = _item_no(revised)
        if current_no not in failed_number_set and index < len(failed_numbers):
            revised["no"] = failed_numbers[index]
        normalized.append(revised)
    return normalized


def _initial_items_and_slots(items: List[Dict[str, str]]) -> tuple:
    normalized: List[Dict[str, str]] = []
    slots: List[int] = []
    for zero_index, item in enumerate(items):
        numbered = dict(item)
        try:
            slot_index = int(_item_no(numbered)) - 1
        except (TypeError, ValueError):
            slot_index = zero_index
        if slot_index < 0:
            slot_index = zero_index
        numbered["no"] = str(slot_index + 1)
        normalized.append(numbered)
        slots.append(slot_index)
    return normalized, slots


def _attach_slot_indexes(
    failed_results: List[Dict[str, Any]],
    candidate_slots: List[int],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for index, result in enumerate(failed_results):
        item_index = 0
        try:
            item_index = int(result.get("item_index"))
        except (TypeError, ValueError):
            item_index = index + 1
        if 0 < item_index <= len(candidate_slots):
            slot_index = candidate_slots[item_index - 1]
        elif index < len(candidate_slots):
            slot_index = candidate_slots[index]
        else:
            slot_index = index
        enriched_result = dict(result)
        enriched_result["slot_index"] = slot_index
        enriched_result["slot_no"] = str(slot_index + 1)
        enriched.append(enriched_result)
    return enriched


def _regenerate_markdown_table(items: List[Dict[str, str]]) -> str:
    """Regenerate a markdown table from the forward-reasoned vulnerability items."""
    return render_vulnerability_detection(items)


def _project_mechanism_candidate(candidate: Any, fallback_no: int) -> Dict[str, Any]:
    if not isinstance(candidate, dict):
        return {}
    return {
        "no": fallback_no,
        "mechanism_name": candidate.get("mechanism_name", ""),
        "source_component": candidate.get("source_component", ""),
        "edge_id": candidate.get("edge_id", ""),
        "attack_origin": candidate.get("attack_origin", ""),
        "input_modality": candidate.get("input_modality", ""),
        "output_modality": candidate.get("output_modality", ""),
        "plain_language_analysis": candidate.get("plain_language_analysis", ""),
        "mandatory_preconditions": _project_preconditions(
            candidate.get("mandatory_preconditions", [])
        ),
        "parameter_constraints": candidate.get("parameter_constraints", []),
        "relevant_parameter_refs": candidate.get("relevant_parameter_refs", []),
    }


def _project_preconditions(preconditions: Any) -> List[Dict[str, Any]]:
    """Keep physical claims while removing Step-2 confidence/status labels."""
    if not isinstance(preconditions, list):
        return []
    projected: List[Dict[str, Any]] = []
    for condition in preconditions:
        if not isinstance(condition, dict):
            continue
        projected.append(
            {
                "claim": condition.get("claim", ""),
                "required_evidence_scope": condition.get("required_evidence_scope", ""),
                "evidence_refs": condition.get("evidence_refs", []),
            }
        )
    return projected


def _project_graph_path(path: Any) -> Dict[str, Any]:
    if not isinstance(path, dict):
        return {}
    nodes = []
    for node in path.get("nodes", []):
        if not isinstance(node, dict):
            continue
        nodes.append(
            {
                "node_id": node.get("node_id", ""),
                "node_type": node.get("node_type", ""),
                "name": node.get("name", ""),
                "modality": node.get("modality", ""),
                "component_category": node.get("component_category", ""),
                "component_name": node.get("component_name", ""),
                "parameter_refs": (node.get("attributes") or {}).get("parameter_refs", []),
            }
        )

    edges = []
    for edge in path.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edges.append(
            {
                "edge_id": edge.get("edge_id", ""),
                "source_node_id": edge.get("source_node_id", ""),
                "target_node_id": edge.get("target_node_id", ""),
                "relation_type": edge.get("relation_type", ""),
                "mechanism_name": edge.get("mechanism_name"),
                "attack_origin": edge.get("attack_origin", ""),
                "input_modality": edge.get("input_modality", ""),
                "output_modality": edge.get("output_modality", ""),
                "mandatory_preconditions": _project_preconditions(
                    edge.get("mandatory_preconditions", [])
                ),
                "parameter_constraints": edge.get("parameter_constraints", []),
                "explanation": edge.get("explanation", ""),
            }
        )

    return {
        "path_id": path.get("path_id", ""),
        "external_signal": path.get("external_signal", {}),
        "nodes": nodes,
        "edges": edges,
        "mechanism_instances": path.get("mechanism_instances", []),
        "observable_output": path.get("observable_output", ""),
        "mandatory_preconditions": _project_preconditions(
            path.get("mandatory_preconditions", [])
        ),
        "relevant_parameter_refs": path.get("relevant_parameter_refs", []),
    }


def _project_numbered_mechanism_entries(mechanism_analysis: str) -> str:
    """Remove confidence metadata while preserving Step-2 numbering and content."""
    try:
        payload = json.loads(mechanism_analysis)
    except json.JSONDecodeError:
        return mechanism_analysis
    if not isinstance(payload, dict) or not isinstance(payload.get("mechanisms"), list):
        return mechanism_analysis

    projected = []
    for index, item in enumerate(payload["mechanisms"], start=1):
        if not isinstance(item, dict):
            continue
        external_signal = item.get("External Signal")
        projected.append(
            {
                "no": item.get("no") or index,
                "external_signal": external_signal if isinstance(external_signal, dict) else {},
                "mechanism_name": item.get("Mechanism Name") or item.get("mechanism_name", ""),
                "source_component": item.get("Source Component") or item.get("source_component", ""),
                "detailed_analysis": item.get("Detailed Description and Analysis")
                or item.get("mechanism", ""),
            }
        )
    return json.dumps({"mechanisms": projected}, ensure_ascii=False, indent=2)


def _build_graph_reasoning_context(
    rag_input: str,
    sensor_type: str,
    sensor_info: str,
    mechanism_analysis: str,
    mechanism_paths_payload: Optional[Dict[str, Any]],
) -> str:
    """Build a loss-minimized Step-3 context; no vulnerability mapping occurs here."""
    sections = [
        "=== Step 1 Sensor Identity ===\n"
        + json.dumps(
            {"rag_input": rag_input, "sensor_type": sensor_type},
            ensure_ascii=False,
            indent=2,
        ),
        "=== Step 1 Datasheet-Derived Sensor Facts ===\n" + str(sensor_info),
        "=== Step 2 Numbered Mechanism Entries (the output `no` must reference these entries) ===\n"
        + _project_numbered_mechanism_entries(mechanism_analysis),
    ]

    if isinstance(mechanism_paths_payload, dict):
        candidates = [
            _project_mechanism_candidate(candidate, index)
            for index, candidate in enumerate(
                mechanism_paths_payload.get("mechanism_candidates", []),
                start=1,
            )
        ]
        all_reasoning_paths = [
            _project_graph_path(path)
            for path in (
                list(mechanism_paths_payload.get("accepted_paths", []))
                + list(mechanism_paths_payload.get("unresolved_paths", []))
            )
        ]
        graph_context = {
            "attack_scope": mechanism_paths_payload.get("attack_scope", {}),
            "signal_coverage": mechanism_paths_payload.get("signal_coverage", {}),
            "mechanism_candidates": [item for item in candidates if item],
            "paths": [item for item in all_reasoning_paths if item],
            "sensor_parameter_catalog": mechanism_paths_payload.get(
                "sensor_parameter_catalog", []
            ),
        }
        sections.append(
            "=== Step 2 Directed-Graph Paths (all paths are equal classification inputs; status labels removed) ===\n"
            # Keep the complete projected path content while avoiding indentation
            # overhead in what is already the largest prompt section.
            + json.dumps(graph_context, ensure_ascii=False, separators=(",", ":"))
        )
    else:
        sections.append(
            "=== Step 2 Directed-Graph Search Results ===\n"
            "Dedicated graph-path payload unavailable; reason from the numbered Step-2 entries above."
        )

    return "\n\n".join(sections)


def _lineage_mechanism_matches(left: Any, right: Any) -> bool:
    aliases = {
        "photoelectroniceffect": "photoelectriceffect",
        "aliasing": "aliasingeffect",
        "antenna": "antennaeffect",
        "nonidealcutoffeffect": "nonidealcutoff",
        "nonlinearityeffect": "nonlinearity",
    }
    a = aliases.get(_normalize_text(str(left or "")), _normalize_text(str(left or "")))
    b = aliases.get(_normalize_text(str(right or "")), _normalize_text(str(right or "")))
    return bool(a and b and a == b)


def _lineage_component_matches(left: Any, right: Any) -> bool:
    a = _normalize_text(str(left or ""))
    b = _normalize_text(str(right or ""))
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    alias_groups = (
        {"afe", "analogfrontend", "analogfrontendamplifier", "amplifier"},
        {"adc", "samplingstage", "adcsamplingstage", "analogtodigitalconverter"},
        {"wire", "wires", "interconnect", "interconnects", "conductiveinterconnects", "pcbtraces"},
        {"filter", "signalfilter", "lowpassfilter", "antialiasingfilter"},
        {"transducer", "acoustictransducer", "microphone", "memsmicrophone"},
        {"communicationinterface", "digitalinterface", "serialinterface", "i2s"},
        {"powersupply", "powersupplypath", "powerlines"},
    )
    return any(a in group and b in group for group in alias_groups)


def _merge_lineage_parameters(records: List[Dict[str, Any]]) -> tuple[List[str], List[Dict[str, Any]]]:
    refs: List[str] = []
    parameters: List[Dict[str, Any]] = []
    seen_parameters = set()
    for record in records:
        for ref in record.get("relevant_parameter_refs", []) or []:
            ref_text = str(ref)
            if ref_text and ref_text not in refs:
                refs.append(ref_text)
        for parameter in record.get("relevant_sensor_parameters", []) or []:
            if not isinstance(parameter, dict):
                continue
            key = str(parameter.get("parameter_id") or parameter.get("raw_text") or "")
            if key and key not in seen_parameters:
                seen_parameters.add(key)
                parameters.append(parameter)
    return refs, parameters


def _enrich_vulnerability_parameter_lineage(
    items: List[Dict[str, Any]],
    mechanism_paths_payload: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Deterministically carry matching Step1 parameter provenance into Step3."""
    if not isinstance(mechanism_paths_payload, dict):
        return items
    paths = [
        path
        for path in (
            list(mechanism_paths_payload.get("accepted_paths", []))
            + list(mechanism_paths_payload.get("unresolved_paths", []))
        )
        if isinstance(path, dict)
    ]
    candidates = [
        candidate
        for candidate in mechanism_paths_payload.get("mechanism_candidates", []) or []
        if isinstance(candidate, dict)
    ]
    enriched: List[Dict[str, Any]] = []
    for item in items:
        mechanism = item.get("mechanism_name")
        component = item.get("source_component")
        matching_paths = []
        for path in paths:
            instances = path.get("mechanism_instances", []) or []
            if any(
                isinstance(instance, dict)
                and _lineage_mechanism_matches(mechanism, instance.get("mechanism_name"))
                and _lineage_component_matches(component, instance.get("source_component"))
                for instance in instances
            ):
                matching_paths.append(path)
        matching_candidates = [
            candidate
            for candidate in candidates
            if _lineage_mechanism_matches(mechanism, candidate.get("mechanism_name"))
            and _lineage_component_matches(component, candidate.get("source_component"))
        ]
        records = matching_paths or matching_candidates
        refs, parameters = _merge_lineage_parameters(records)
        copied = dict(item)
        copied["supporting_path_ids"] = [
            str(path.get("path_id")) for path in matching_paths if path.get("path_id")
        ]
        copied["relevant_parameter_refs"] = refs
        copied["relevant_sensor_parameters"] = parameters
        enriched.append(copied)
    return enriched


def compress_history_for_detect(sensor_info: str, mechanism_analysis: str) -> str:
    """
    Compress long history before vulnerability detection.
    Focus: sensor info + mechanism names/descriptions that matter for detection.
    """
    raw_history = (
        "=== Sensor Information ===\n"
        + sensor_info
        + "\n\n=== Mechanism Analysis ===\n"
        + mechanism_analysis
    )
    sensor_compression_prompt = """
You are a context compressor for sensor-security vulnerability detection.
Compress only SENSOR INFORMATION into a concise memo.

Requirements:
1) Keep only facts that help vulnerability classification.
2) Preserve numeric constraints (ranges, limits, units, operating conditions).
3) Remove narrative and generic statements.
4) Output in English, <= 150 words.
5) Output format:
   - Detection-Relevant Sensor Facts:
   - Classification Hints:
""".strip()

    mechanism_compression_prompt = """
You are a context compressor for sensor-security vulnerability detection.
Compress only MECHANISM ANALYSIS into a concise memo.

Requirements:
1) Keep mechanism entries as complete as possible; do NOT drop valid mechanism items.
2) Keep one line per mechanism in this format:
   mechanism name -> source component -> short description
3) Preserve numeric constraints (ranges, limits, units) supporting classification.
4) Remove redundant narrative and duplicates only.
5) Output in English, <= 220 words.
6) Output format:
   - Mechanism Summary (name -> source component ->description):
   - Classification Hints:
""".strip()

    mechanism_retry_prompt = """
You are a context compressor for sensor-security vulnerability detection.
Re-compress MECHANISM ANALYSIS with strict item-count conservation.

Hard constraints:
1) Do not drop valid mechanism entries.
2) Keep at least the same number of mechanism items as in input.
3) Output one mechanism per line, and prefix each line with serial number:
   1. mechanism name -> source component -> short description
4) Keep key numeric constraints (ranges, limits, units).
5) Remove only true duplicates and generic narrative.
6) Output in English.
7) Output format:
   - Mechanism Summary (numbered):
   - Classification Hints:
""".strip()

    sensor_compact = ""
    mechanism_compact = ""

    try:
        sensor_response = chatanywhere_chat_completion(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": sensor_compression_prompt},
                {"role": "user", "content": sensor_info},
            ],
            auth_header=chatanywhere_auth_header,
            temperature=0.1,
        )
        sensor_compact = _extract_chat_content(sensor_response).strip()
    except Exception as e:
        print(f"[Step3] Sensor Information 浓缩失败，回退原始片段: {e}")
        sensor_compact = (
            "- Detection-Relevant Sensor Facts:\n"
            + sensor_info.strip()
            + "\n- Classification Hints:\n"
            + "(fallback: use original sensor information)"
        )

    try:
        mechanism_response = chatanywhere_chat_completion(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": mechanism_compression_prompt},
                {"role": "user", "content": mechanism_analysis},
            ],
            auth_header=chatanywhere_auth_header,
            temperature=0.1,
        )
        mechanism_compact = _extract_chat_content(mechanism_response).strip()
    except Exception as e:
        print(f"[Step3] Mechanism Analysis 浓缩失败，回退原始片段: {e}")
        mechanism_compact = (
            "- Mechanism Summary (name -> source component ->description):\n"
            + mechanism_analysis.strip()
            + "\n- Classification Hints:\n"
            + "(fallback: use original mechanism analysis)"
        )

    # Mechanism item-count conservation check:
    # if compressed count < original count, retry one stricter compression;
    # if still smaller, fallback to original mechanism analysis.
    orig_nums = _extract_item_numbers(mechanism_analysis)
    compact_nums = _extract_item_numbers(mechanism_compact)
    orig_count = len(orig_nums) if orig_nums else _estimate_mechanism_item_count(mechanism_analysis)
    compact_count = len(compact_nums) if compact_nums else _estimate_mechanism_item_count(mechanism_compact)
    print(
        f"[Step3] Mechanism count check: original={orig_count} "
        f"(nums={orig_nums}), compressed={compact_count} (nums={compact_nums})"
    )

    if orig_count > 0 and compact_count < orig_count:
        print(
            "[Step3] Mechanism 条目数量守恒检查未通过，触发重压缩: "
            f"original={orig_count}, compressed={compact_count}"
        )
        try:
            retry_user = (
                f"Original mechanism item count reference: {orig_count}\n\n"
                + mechanism_analysis
            )
            retry_response = chatanywhere_chat_completion(
                model="gpt-5.4-mini",
                messages=[
                    {"role": "system", "content": mechanism_retry_prompt},
                    {"role": "user", "content": retry_user},
                ],
                auth_header=chatanywhere_auth_header,
                temperature=0.1,
            )
            retry_compact = _extract_chat_content(retry_response).strip()
            retry_nums = _extract_item_numbers(retry_compact)
            retry_count = len(retry_nums) if retry_nums else _estimate_mechanism_item_count(retry_compact)
            print(
                f"[Step3] Mechanism retry count: {retry_count} "
                f"(nums={retry_nums}), target>={orig_count}"
            )
            if retry_count >= orig_count:
                mechanism_compact = retry_compact
            else:
                print("[Step3] 重压缩后数量仍不足，回退原始 Mechanism Analysis")
                mechanism_compact = (
                    "- Mechanism Summary (name -> source component ->description):\n"
                    + mechanism_analysis.strip()
                    + "\n- Classification Hints:\n"
                    + "(fallback: keep all original mechanism entries)"
                )
        except Exception as e:
            print(f"[Step3] Mechanism 重压缩失败，回退原始片段: {e}")
            mechanism_compact = (
                "- Mechanism Summary (name -> source component ->description):\n"
                + mechanism_analysis.strip()
                + "\n- Classification Hints:\n"
                + "(fallback: retry failed, use original mechanism analysis)"
            )

    compact_context = (
        "=== Compressed Sensor Information ===\n"
        + sensor_compact
        + "\n\n=== Compressed Mechanism Analysis ===\n"
        + mechanism_compact
    )

    # If both sections unexpectedly collapse to empty, fallback to full raw history.
    if not sensor_compact.strip() and not mechanism_compact.strip():
        print("[Step3] 历史信息浓缩结果为空，回退原始上下文")
        return raw_history
    return compact_context


def _build_step3_user_prompt(compact_context: str, retry_feedback: str = "") -> str:
    prompt = (
        "Infer the supported vulnerability names from the supplied Step-2 directed-graph "
        "results. First perform the full path-level classification and checker self-audit "
        "internally; then return only the final JSON.\n\n"
        + compact_context
        + "\n\n"
        + STEP3_JSON_OUTPUT_INSTRUCTIONS
    )
    if retry_feedback:
        prompt += (
            "\n\n## Previous response format failure\n"
            + retry_feedback
            + "\nRegenerate the complete answer as strict JSON; do not merely patch a fragment."
        )
    return prompt


def _call_vulnerability_detector(
    model_for_detect: str,
    compact_context: str,
    retry_feedback: str = "",
) -> str:
    print(
        f"[Step3] Calling vulnerability detector model={model_for_detect}, "
        f"context_chars={len(compact_context)}",
        flush=True,
    )
    response_data = chatanywhere_chat_completion(
        model=model_for_detect,
        messages=[
            {"role": "system", "content": STEP3_FORWARD_REASONING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_step3_user_prompt(
                    compact_context=compact_context,
                    retry_feedback=retry_feedback,
                ),
            },
        ],
        auth_header=chatanywhere_auth_header,
        temperature=0.1,
        timeout=900 if model_for_detect == "minimax-m3" else 180,
    )
    content = _extract_chat_content(response_data)
    print(f"[Step3] Vulnerability detector response received, chars={len(content)}", flush=True)
    return content


def _build_failed_item_revision_prompt(
    compact_context: str,
    passed_items: List[Dict[str, Any]],
    failed_results: List[Dict[str, Any]],
    verifier_reflection: str,
) -> str:
    return (
        prompt2_1
        + "\nCondensed historical context (for detection):\n"
        + compact_context
        + "\n"
        + prompt2_2
        + "\n\n## Locked Passed Items\n"
        + "These items already passed the verifier. Do not regenerate, rewrite, remove, or duplicate them:\n"
        + json.dumps({"passed_items": passed_items}, ensure_ascii=False, indent=2)
        + "\n\n## Failed Items To Revise\n"
        + "Revise every failed item below. Return exactly one replacement for each failed item. "
        + "Do not omit failed items and do not add new items. "
        + "For every replacement, use the failed item's slot_no as the returned no exactly; "
        + "the pipeline will replace that array slot directly.\n"
        + json.dumps({"failed_items": failed_results}, ensure_ascii=False, indent=2)
        + "\n\n## Verifier Reflection\n"
        + verifier_reflection
        + "\n\nReturn strict JSON only in this schema:\n"
        + "{\n"
        + '  "vulnerability_items": [\n'
        + "    {\n"
        + '      "no": 1,\n'
        + '      "vulnerability_name": "string",\n'
        + '      "mechanism_name": "string",\n'
        + '      "source_component": "string",\n'
        + '      "description": "string",\n'
        + '      "judgment_reason": "string",\n'
        + '      "evidence": [\n'
        + '        {"source": "datasheet | Step2 Mechanism | Literatures | Vulnerability Cases | Expert Knowledge", "summary": "brief evidence content summary"}\n'
        + "      ]\n"
        + "    }\n"
        + "  ]\n"
        + "}\n"
        + "The returned vulnerability_items must contain replacements for failed items only, with slot_no copied into no. "
        + "Every replacement must include at least one grounded evidence item."
    )


def _call_failed_item_reviser(
    model_for_detect: str,
    compact_context: str,
    passed_items: List[Dict[str, Any]],
    failed_results: List[Dict[str, Any]],
    verifier_reflection: str,
) -> str:
    print(
        f"[Step3] Calling failed-item reviser model={model_for_detect}, "
        f"failed_items={len(failed_results)}",
        flush=True,
    )
    response_data = chatanywhere_chat_completion(
        model=model_for_detect,
        messages=[
            {
                "role": "system",
                "content": (
                    prompt2_3
                    + "\n\nYou are revising failed vulnerability-mechanism pairs only. "
                    + "Keep verifier-passed items locked and return replacements for failed items only. "
                    + "Every replacement must include grounded evidence."
                ),
            },
            {
                "role": "user",
                "content": _build_failed_item_revision_prompt(
                    compact_context=compact_context,
                    passed_items=passed_items,
                    failed_results=failed_results,
                    verifier_reflection=verifier_reflection,
                ),
            },
        ],
        auth_header=chatanywhere_auth_header,
        temperature=0.1,
    )
    content = _extract_chat_content(response_data)
    print(f"[Step3] Failed-item reviser response received, chars={len(content)}", flush=True)
    return content


def _load_step2_payload(raw_text: str) -> Dict[str, Any]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return {"mechanisms": [], "raw_mechanism_analysis": raw_text}
    if isinstance(payload, dict):
        return payload
    return {"mechanisms": payload if isinstance(payload, list) else [], "raw_mechanism_analysis": raw_text}


def _mechanism_key(mechanism_name: Any, source_component: Any) -> tuple:
    return (_normalize_text(mechanism_name), _normalize_text(source_component))


def _mechanism_body(raw_mechanism: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(raw_mechanism.get("Mechanism"), dict):
        body = dict(raw_mechanism["Mechanism"])
    else:
        body = dict(raw_mechanism)
    body.pop("no", None)
    body.pop("vulnerabilities", None)
    return body


def _mechanism_name_and_component(mechanism: Dict[str, Any]) -> tuple:
    body = _mechanism_body(mechanism)
    name = body.get("Mechanism Name") or body.get("mechanism_name") or body.get("Mechanism")
    component = body.get("Source Component") or body.get("source_component") or body.get("Component")
    return name, component


def _slim_vulnerability_item(item: Dict[str, str]) -> Dict[str, str]:
    return {
        "vulnerability_name": item.get("vulnerability_name", ""),
        "description": item.get("description", ""),
        "judgment_reason": item.get("judgment_reason", ""),
        "evidence": item.get("evidence", []),
    }


def _deduplicate_slim_vulnerabilities(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    by_name: Dict[str, Dict[str, str]] = {}
    order: List[str] = []
    for item in items:
        key = _normalize_text(item.get("vulnerability_name", ""))
        if not key:
            key = f"unnamed-{len(order) + 1}"
        if key not in by_name:
            order.append(key)
        by_name[key] = item
    return [by_name[key] for key in order]


def _merge_vulnerabilities_into_step2_payload(
    step2_payload: Dict[str, Any],
    vulnerability_items: List[Dict[str, str]],
    verification_report: Dict[str, Any],
) -> Dict[str, Any]:
    merged_payload = json.loads(json.dumps(step2_payload, ensure_ascii=False))
    mechanisms = merged_payload.get("mechanisms")
    if not isinstance(mechanisms, list):
        mechanisms = []
        merged_payload["mechanisms"] = mechanisms

    structured_mechanisms: List[Dict[str, Any]] = []
    for index, mechanism in enumerate(mechanisms, start=1):
        if not isinstance(mechanism, dict):
            continue
        mechanism_no = str(mechanism.get("no") or index)
        body = _mechanism_body(mechanism)
        structured = {
            "no": mechanism_no,
            "Mechanism": body,
            "vulnerabilities": [],
        }
        structured_mechanisms.append(structured)
    merged_payload["mechanisms"] = structured_mechanisms

    unmatched_items: List[Dict[str, str]] = []
    for item in vulnerability_items:
        try:
            mechanism_index = int(_item_no(item)) - 1
        except (TypeError, ValueError):
            mechanism_index = -1
        if not 0 <= mechanism_index < len(structured_mechanisms):
            unmatched_items.append(item)
            continue
        target = structured_mechanisms[mechanism_index]
        target.setdefault("vulnerabilities", []).append(_slim_vulnerability_item(item))

    for mechanism in structured_mechanisms:
        mechanism["vulnerabilities"] = _deduplicate_slim_vulnerabilities(
            mechanism.get("vulnerabilities", [])
        )

    merged_payload.pop("vulnerability_detection", None)
    return merged_payload


def _generate_forward_vulnerability_items(
    model_for_detect: str,
    reasoning_context: str,
) -> tuple:
    """Generate with forward reasoning only; retry solely for unusable JSON output."""
    attempts: List[Dict[str, Any]] = []
    retry_feedback = ""

    for attempt_index in range(1, MAX_DETECTION_RETRY + 1):
        raw_answer = ""
        try:
            raw_answer = _call_vulnerability_detector(
                model_for_detect=model_for_detect,
                compact_context=reasoning_context,
                retry_feedback=retry_feedback,
            )
            items = _deduplicate_vulnerability_items(
                _parse_vulnerability_json_items(raw_answer)
            )
            if not items:
                raise ValueError("forward reasoner returned no usable vulnerability items")
        except Exception as exc:
            attempts.append(
                {
                    "attempt": attempt_index,
                    "generation_or_parse_error": str(exc),
                    "raw_output": raw_answer,
                    "verifier_invoked": False,
                }
            )
            retry_feedback = f"The previous output could not be parsed: {exc}"
            if attempt_index >= MAX_DETECTION_RETRY:
                raise RuntimeError(
                    f"Step3 forward reasoning failed after {MAX_DETECTION_RETRY} attempts: {exc}"
                ) from exc
            continue

        attempts.append(
            {
                "attempt": attempt_index,
                "raw_output": raw_answer,
                "vulnerability_items": items,
                "verifier_invoked": False,
            }
        )
        temp_path(f"step3_attempt_{attempt_index}_raw_llm.txt").write_text(
            raw_answer,
            encoding="utf-8",
        )
        temp_path(f"step3_attempt_{attempt_index}_items.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return items, attempts

    raise RuntimeError("Step3 forward reasoning exited without a result")


def _generate_verified_vulnerability_items(
    model_for_detect: str,
    model_for_verifier: str,
    sensor_type: str,
    sensor_info: str,
    mechanism_analysis: str,
    compact_context: str,
) -> tuple:
    verifier = DomainConstraintVerifierAgent(model_for_verify=model_for_verifier)
    attempts: List[Dict[str, Any]] = []
    item_slots: List[Optional[Dict[str, Any]]] = []
    failed_results: List[Dict[str, Any]] = []
    verifier_reflection = ""
    verification_report: Dict[str, Any] = {}

    for attempt_index in range(1, MAX_DETECTION_RETRY + 1):
        try:
            omitted_failed_results: List[Dict[str, Any]] = []
            passed_items = _passed_items_from_slots(item_slots)
            if attempt_index == 1 or not failed_results:
                if attempt_index > 1 and item_slots:
                    print(
                        "[Step3] Previous attempt failed before verifier produced failed_items; "
                        "regenerating full candidate list instead of revising empty failures.",
                        flush=True,
                    )
                    item_slots = []
                raw_answer = _call_vulnerability_detector(
                    model_for_detect=model_for_detect,
                    compact_context=compact_context,
                )
                candidate_items, candidate_slots = _initial_items_and_slots(
                    _deduplicate_vulnerability_items(_parse_vulnerability_json_items(raw_answer))
                )
                _ensure_slot_count(item_slots, (max(candidate_slots) + 1) if candidate_slots else len(candidate_items))
                locked_passed_before = []
            else:
                raw_answer = _call_failed_item_reviser(
                    model_for_detect=model_for_detect,
                    compact_context=compact_context,
                    passed_items=passed_items,
                    failed_results=failed_results,
                    verifier_reflection=verifier_reflection,
                )
                candidate_items = _normalize_revision_item_numbers(
                    _parse_vulnerability_json_items(raw_answer),
                    failed_results,
                )
                candidate_items = _deduplicate_vulnerability_items(candidate_items)
                failed_slots = [_slot_index_for_result(result, index) for index, result in enumerate(failed_results)]
                if len(candidate_items) > len(failed_slots):
                    print(
                        "[Step3] Revision returned extra items; truncating to failed item count: "
                        f"{len(candidate_items)} -> {len(failed_slots)}"
                    )
                    candidate_items = candidate_items[: len(failed_slots)]
                if len(candidate_items) < len(failed_slots):
                    print(
                        "[Step3] Revision returned too few items; keeping missing failed items pending: "
                        f"{len(candidate_items)} / {len(failed_slots)}"
                    )
                    omitted_failed_results = failed_results[len(candidate_items) :]
                candidate_slots = failed_slots[: len(candidate_items)]
                _ensure_slot_count(item_slots, (max(candidate_slots) + 1) if candidate_slots else len(item_slots))
                locked_passed_before = _passed_items_from_slots(item_slots)

            print(
                f"[Step3] Calling domain verifier model={model_for_verifier}, "
                f"candidate_items={len(candidate_items)}",
                flush=True,
            )
            verification_report = verifier.verify_step3(
                sensor_type=sensor_type,
                sensor_info=sensor_info,
                mechanism_analysis=mechanism_analysis,
                vulnerability_items=candidate_items,
            )
            print("[Step3] Domain verifier response received", flush=True)
        except Exception as e:
            attempts.append(
                {
                    "attempt": attempt_index,
                    "parse_generation_or_verifier_error": str(e),
                    "raw_output": locals().get("raw_answer", ""),
                    "locked_passed_items": _passed_items_from_slots(item_slots),
                }
            )
            verifier_reflection = (
                "The previous attempt failed before verification could complete. "
                f"Error: {e}. Return strict JSON in the required schema."
            )
            if not failed_results:
                item_slots = []
            if attempt_index >= MAX_DETECTION_RETRY:
                raise RuntimeError(f"Step3 JSON generation/verifier failed after {MAX_DETECTION_RETRY} attempts: {e}") from e
            continue

        attempts.append(
            {
                "attempt": attempt_index,
                "raw_output": raw_answer,
                "candidate_items": candidate_items,
                "locked_passed_items_before_attempt": locked_passed_before,
                "verification_report": verification_report,
            }
        )
        temp_path(f"step3_attempt_{attempt_index}_raw_llm.txt").write_text(raw_answer, encoding="utf-8")
        temp_path(f"step3_attempt_{attempt_index}_items.json").write_text(
            json.dumps(candidate_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path(f"step3_attempt_{attempt_index}_verifier_report.json").write_text(
            json.dumps(verification_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        summary = verification_report.get("summary", {})
        print(
            "[Step3] LLM verifier attempt "
            f"{attempt_index}: checked_this_round={summary.get('total')}, "
            f"passed_this_round={summary.get('passed')}, failed_this_round={summary.get('failed')}"
        )
        for result in verification_report.get("results", []):
            if not result.get("passed"):
                continue
            try:
                item_index = int(result.get("item_index"))
            except (TypeError, ValueError):
                continue
            if not 0 < item_index <= len(candidate_slots):
                continue
            slot_index = candidate_slots[item_index - 1]
            _ensure_slot_count(item_slots, slot_index + 1)
            item = result.get("item")
            if isinstance(item, dict):
                item_slots[slot_index] = item
        passed_items = _passed_items_from_slots(item_slots)
        failed_results = _attach_slot_indexes(
            verification_report.get("failed_items", []),
            candidate_slots,
        ) + omitted_failed_results
        verifier_reflection = verification_report.get("reflection_prompt", "")
        if omitted_failed_results:
            verifier_reflection = (
                verifier_reflection
                + "\nMissing replacements: the previous revision returned fewer items than the pending failed-item count. "
                + "Return one replacement for every remaining failed item."
            ).strip()
        print(
            "[Step3] Locked passed items: "
            f"{len(passed_items)}; failed items pending revision: {len(failed_results)}"
        )

        if not failed_results:
            final_report = dict(verification_report)
            final_report["summary"] = {
                "total": len(passed_items),
                "passed": len(passed_items),
                "failed": 0,
            }
            final_report["passed_items"] = passed_items
            final_report["failed_items"] = []
            final_report["cumulative_passed_items"] = passed_items
            return passed_items, final_report, attempts

    passed_items = _passed_items_from_slots(item_slots)
    final_report = dict(verification_report)
    final_report["summary"] = {
        "total": len(passed_items) + len(failed_results),
        "passed": len(passed_items),
        "failed": len(failed_results),
    }
    final_report["passed_items"] = passed_items
    final_report["failed_items"] = failed_results
    final_report["cumulative_passed_items"] = passed_items
    return passed_items, final_report, attempts


def run_step_3(
    model_for_detect: str = "gpt-5.4-mini",
    model_for_verifier: str = "gpt-5.4-mini",
    use_verifier: bool = False,
) -> str:
    if use_verifier:
        raise ValueError("steps-graph-v2 forbids verifier execution; use_verifier must remain False")
    mode_name = "forward reasoning only" if not use_verifier else "forward reasoning + verifier"
    print(f"\n---------------------------------第三步 检测可能的脆弱性（{mode_name}）----------------------------------")
    step1_data = json.loads(temp_path("step1_output.json").read_text(encoding="utf-8"))
    rag_input = step1_data["rag_input"]
    sensor_info = step1_data["sensor_info"]
    mechanism_analysis = temp_path("step2_output.txt").read_text(encoding="utf-8")

    # Extract sensor type from step1 output
    sensor_type = _extract_sensor_type(rag_input)
    print(f"[Step3] Detected sensor type: {sensor_type}")

    mechanism_paths_payload: Optional[Dict[str, Any]] = None
    mechanism_paths_file = temp_path("step2_mechanism_paths.json")
    if mechanism_paths_file.exists():
        try:
            loaded_paths = json.loads(mechanism_paths_file.read_text(encoding="utf-8"))
            if isinstance(loaded_paths, dict):
                mechanism_paths_payload = loaded_paths
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[Step3] Could not load detailed Step2 graph paths; using legacy output: {exc}")

    reasoning_context = _build_graph_reasoning_context(
        rag_input=rag_input,
        sensor_type=sensor_type,
        sensor_info=sensor_info,
        mechanism_analysis=mechanism_analysis,
        mechanism_paths_payload=mechanism_paths_payload,
    )
    temp_path("step3_compact_context.txt").write_text(reasoning_context, encoding="utf-8")
    temp_path("step3_forward_reasoning_context.txt").write_text(reasoning_context, encoding="utf-8")
    print(
        "[Step3] Detailed graph context: "
        f"available={mechanism_paths_payload is not None}, chars={len(reasoning_context)}"
    )

    if use_verifier:
        # Retained for possible future re-enablement. The default/main flow does not
        # instantiate or call DomainConstraintVerifierAgent.
        vulnerability_items, verification_report, attempts = _generate_verified_vulnerability_items(
            model_for_detect=model_for_detect,
            model_for_verifier=model_for_verifier,
            sensor_type=sensor_type,
            sensor_info=sensor_info,
            mechanism_analysis=mechanism_analysis,
            compact_context=reasoning_context,
        )
    else:
        vulnerability_items, attempts = _generate_forward_vulnerability_items(
            model_for_detect=model_for_detect,
            reasoning_context=reasoning_context,
        )
        verification_report = {
            "agent": "DomainConstraintVerifierAgent",
            "enabled": False,
            "invoked": False,
            "mode": "forward_reasoning_only",
            "summary": {
                "total": len(vulnerability_items),
                "passed": len(vulnerability_items),
                "failed": 0,
            },
            "note": (
                "The verifier is intentionally disabled. Modality consistency, "
                "mechanism correspondence, and evidence grounding are performed "
                "inside the forward-reasoning prompt."
            ),
        }

    vulnerability_items = _enrich_vulnerability_parameter_lineage(
        vulnerability_items,
        mechanism_paths_payload,
    )

    print(
        "[Step3] Forward-reasoned vulnerabilities: "
        f"{len(vulnerability_items)}; verifier_invoked={use_verifier}"
    )

    # Save forward-reasoned items as JSON for step4.
    temp_path("step3_vulnerability_items.json").write_text(
        json.dumps(vulnerability_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path("step3_generation_attempts.json").write_text(
        json.dumps(attempts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path("step3_domain_verifier_report.json").write_text(
        json.dumps(verification_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    step2_payload = _load_step2_payload(mechanism_analysis)
    merged_payload = _merge_vulnerabilities_into_step2_payload(
        step2_payload=step2_payload,
        vulnerability_items=vulnerability_items,
        verification_report=verification_report,
    )
    temp_path("step2_output.json").write_text(
        json.dumps(merged_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path("step3_step2_merged_output.json").write_text(
        json.dumps(merged_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Regenerate markdown table with forward-reasoned items.
    filtered_markdown = _regenerate_markdown_table(vulnerability_items)

    temp_path("step3_output.txt").write_text(filtered_markdown, encoding="utf-8")
    append_report(output_report, "\n" + filtered_markdown + "\n")
    return filtered_markdown

# 运行测试
if __name__ == "__main__":
    run_step_3()
