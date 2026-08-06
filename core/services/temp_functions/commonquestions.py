import re
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

from chatbot.services.chat_engine import generate_grounded_response_for_query


COMMON_QUESTIONS_INDEX_CACHE_KEY = "common-questions-warmup:keys"
COMMON_QUESTIONS_CACHE_PREFIX = "common-questions-warmup:"
COMMON_QUESTIONS_CACHE_TIMEOUT = 60 * 60 * 12
DEFAULT_COMMON_QUESTIONS_PATH = settings.BASE_DIR / "common questions.md"

QUESTION_LINE_RE = re.compile(r"^\s*\d+\.\s+(.*\S)\s*$")
HEADING_LINE_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")
INLINE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
INLINE_BOLD_RE = re.compile(r"\*\*(.*?)\*\*")
WHITESPACE_RE = re.compile(r"\s+")

FALLBACK_COMMON_QUESTIONS = [
    {
        "section": "Section 1: Systems Thinking & Causal Loop Diagrams (CLDs)",
        "step": "",
        "question": "Develop individual Causal Loop Diagrams (CLDs) using Vensim for the Structural, Sociotechnical, and Governance subsystems based on a hospital diagnostic scenario, labeling all reinforcing and balancing loops.",
    },
    {
        "section": "Section 1: Systems Thinking & Causal Loop Diagrams (CLDs)",
        "step": "",
        "question": "Synthesize the three subsystem CLDs into a single Integrated Causal Loop Diagram. Identify and explain at least two cross-subsystem feedback loops that drive diagnostic underutilization.",
    },
    {
        "section": "Section 1: Systems Thinking & Causal Loop Diagrams (CLDs)",
        "step": "",
        "question": "Analyze how feedback delays in receiving laboratory results affect clinician trust in microbial diagnostics and perpetuate reliance on empirical prescribing practices.",
    },
    {
        "section": "Section 1: Systems Thinking & Causal Loop Diagrams (CLDs)",
        "step": "",
        "question": "Evaluate the systemic impact of infrastructure failures (e.g., power outages) on LIMS downtime, staff workload, and diagnostic error rates using systems thinking principles.",
    },
    {
        "section": "Section 2: Systems Engineering Framework (Steps 1 - 4)",
        "step": "Step 1: Objectives and Context",
        "question": "Define the core operational objectives and broader socio-economic context for introducing a Diagnostic Strengthening Initiative (DSI) in a district-level public hospital.",
    },
    {
        "section": "Section 2: Systems Engineering Framework (Steps 1 - 4)",
        "step": "Step 1: Objectives and Context",
        "question": "Identify key primary and secondary stakeholders within a district hospital ecosystem and explain how their competing goals (e.g., cost containment vs. broad diagnostic coverage) create systemic friction.",
    },
    {
        "section": "Section 2: Systems Engineering Framework (Steps 1 - 4)",
        "step": "Step 2: Systems Types",
        "question": "Classify a district hospital diagnostic operations environment as a Complex Adaptive System, System of Systems (SoS), or Enterprise System. Justify your classification based on system boundaries and interactions.",
    },
    {
        "section": "Section 2: Systems Engineering Framework (Steps 1 - 4)",
        "step": "Step 2: Systems Types",
        "question": "Analyze how unexpected emergent behaviors arise when interconnecting national health policy, local treasury budgets, and hospital operations.",
    },
    {
        "section": "Section 2: Systems Engineering Framework (Steps 1 - 4)",
        "step": "Step 3: Baseline and Needs",
        "question": "Conduct a baseline assessment of a district hospital experiencing high empirical prescribing rates. Identify the primary operational gaps across resources, technology, and workflows.",
    },
    {
        "section": "Section 2: Systems Engineering Framework (Steps 1 - 4)",
        "step": "Step 3: Baseline and Needs",
        "question": "Formulate a structured Needs Analysis table that maps observed operational shortfalls (e.g., LIMS downtime, manual reporting delays) to root-cause systemic needs.",
    },
    {
        "section": "Section 2: Systems Engineering Framework (Steps 1 - 4)",
        "step": "Step 4: Concept Exploration",
        "question": "Generate three distinct technological or operational concept interventions aimed at reducing diagnostic turnaround time in low-resource settings.",
    },
    {
        "section": "Section 2: Systems Engineering Framework (Steps 1 - 4)",
        "step": "Step 4: Concept Exploration",
        "question": "Evaluate the feasibility, cost-effectiveness, and sustainability of the proposed intervention concepts, justifying the selection of the most viable option.",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 5: Architecture Development",
        "question": "Develop a comprehensive System Architecture for a hospital diagnostic ecosystem by categorizing key elements using the format below",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 5: Architecture Development",
        "question": "Explain how weaknesses in physical infrastructure propagate through processes and impact human behavior within the system architecture.",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 6: Functional Analysis and Allocation",
        "question": "Perform a functional decomposition of the diagnostic-to-treatment workflow, breaking the system down into core operational sub-functions.",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 6: Functional Analysis and Allocation",
        "question": "Allocate the decomposed functions across Human Assets, Automated Machinery, and Digital Software Systems, justifying each allocation based on efficiency and error reduction.",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 7: Developing Requirements",
        "question": "Evaluate two selected digital interventions (e.g., Electronic Prescribing & Decision Support Systems vs. Rapid Microbiology Diagnostic Tools) by completing the system requirements table.",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 7: Developing Requirements",
        "question": "Comparatively evaluate the system requirements established above and recommend the most suitable intervention for implementation in a rural district hospital experiencing intermittent connectivity.",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 8: Interfaces",
        "question": "Define and justify a minimum of six operational interfaces supporting informational and workflow continuity in a healthcare facility using the format below",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 8: Interfaces",
        "question": "Critically analyze the failure points that occur at the interface between manual paper-based reporting protocols and digital LIMS platforms.",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 9: System Integration",
        "question": "Propose a comprehensive System Integration plan for introducing a new digital health tool into an existing hospital operation, detailing design, installation, testing, and operational transition phases.",
    },
    {
        "section": "Section 3: Systems Engineering Framework (Steps 5 - 9)",
        "step": "Step 9: System Integration",
        "question": "Design an operational verification and validation matrix to ensure that the integrated solution meets both functional requirements and overarching antimicrobial effectiveness goals.",
    },
]


def _normalize_question_text(value: str) -> str:
    cleaned = INLINE_IMAGE_RE.sub(" ", value or "")
    cleaned = INLINE_BOLD_RE.sub(r"\1", cleaned)
    cleaned = WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip(" :-")


def extract_common_questions(markdown_text: str) -> list[dict]:
    questions = []
    current_parts = []
    current_section = ""
    current_step = ""
    current_context = {"section": "", "step": ""}
    heading_parts = []

    def flush_current() -> None:
        nonlocal current_parts, current_context
        if not current_parts:
            return
        question_text = _normalize_question_text(" ".join(current_parts))
        if question_text:
            questions.append(
                {
                    "question": question_text,
                    "section": current_context["section"],
                    "step": current_context["step"],
                }
            )
        current_parts = []
        current_context = {"section": current_section, "step": current_step}

    def flush_heading() -> None:
        nonlocal heading_parts, current_section, current_step
        if not heading_parts:
            return
        heading = _normalize_question_text(" ".join(heading_parts))
        heading_parts = []
        lowered = heading.lower()
        if lowered.startswith("section"):
            current_section = heading
            current_step = ""
        elif lowered.startswith("step"):
            current_step = heading

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_current()
            flush_heading()
            continue

        if not current_parts and (heading_parts or line.startswith("**")):
            heading_parts.append(line)
            if line.endswith("**"):
                flush_heading()
            continue

        question_match = QUESTION_LINE_RE.match(raw_line)
        if question_match:
            flush_current()
            flush_heading()
            current_context = {"section": current_section, "step": current_step}
            current_parts = [question_match.group(1)]
            continue

        if current_parts:
            current_parts.append(line)

    flush_current()
    flush_heading()
    return questions


def load_common_questions(path: str | Path | None = None) -> list[dict]:
    source_path = Path(path or DEFAULT_COMMON_QUESTIONS_PATH)
    markdown_text = source_path.read_text(encoding="utf-8")
    questions = extract_common_questions(markdown_text)
    if questions:
        return questions
    if source_path == DEFAULT_COMMON_QUESTIONS_PATH:
        return [dict(item) for item in FALLBACK_COMMON_QUESTIONS]
    return []


def warm_common_question_cache(*, path: str | Path | None = None, course=None, limit: int | None = None) -> list[dict]:
    questions = load_common_questions(path=path)
    if limit is not None:
        questions = questions[:limit]

    warmed_entries = []
    cache_keys = []
    for entry in questions:
        question = entry["question"]
        cache_key = COMMON_QUESTIONS_CACHE_PREFIX + sha256(question.strip().lower().encode("utf-8")).hexdigest()
        payload = generate_grounded_response_for_query(question, course=course)
        cached_entry = {
            **entry,
            "cache_key": cache_key,
            "payload": payload,
        }
        cache.set(cache_key, cached_entry, timeout=COMMON_QUESTIONS_CACHE_TIMEOUT)
        cache_keys.append(cache_key)
        warmed_entries.append(
            {
                "question": question,
                "cache_key": cache_key,
                "grounded": payload.get("metadata", {}).get("grounded", False),
                "source_count": len(payload.get("metadata", {}).get("sources", [])),
                "external_suggestion_count": len(payload.get("metadata", {}).get("external_suggestions", [])),
            }
        )

    cache.set(COMMON_QUESTIONS_INDEX_CACHE_KEY, cache_keys, timeout=COMMON_QUESTIONS_CACHE_TIMEOUT)
    return warmed_entries