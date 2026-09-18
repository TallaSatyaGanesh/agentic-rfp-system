import re
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import RFPProposalState
from app.agents.llm_factory import LLMFactory
from app.core.prompts import CLASSIFICATION_AGENT_PROMPT
from app.models.schemas import ClassificationAgentOutput, ClassifiedRequirement

# Canonical category to prefix mapping
CATEGORY_PREFIX_MAP: Dict[str, str] = {
    "Technical": "TECH",
    "Commercial": "COMM",
    "Contractual": "CONTRACT",
    "Administrative": "ADMIN",
    "Certification": "CERT",
    "Delivery": "DELIVERY",
    "Documentation": "DOC",
    "Submission": "SUBMISSION",
    "Eligibility": "ELIGIBILITY"
}

# Synonyms/legacy mappings to canonical categories
CATEGORY_SYNONYMS: Dict[str, str] = {
    "Security": "Certification",
    "Legal": "Contractual",
    "Functional": "Technical",
    "Management": "Delivery",
    "Financial": "Commercial",
    "Compliance": "Certification"
}

def classify_requirements_node(state: RFPProposalState) -> Dict[str, Any]:
    """
    Agent 2: Requirement Classification Agent
    Receives RawClause objects produced by Agent 1, categorizes them into
    the 9 canonical requirement types, determines mandatory vs optional status,
    and assigns deterministic canonical IDs (REQ-{CATEGORY}-XXX).
    """
    raw_clauses = state.get("raw_clauses", [])
    if not raw_clauses:
        return {
            "requirements": [],
            "active_agent": "Classification Agent",
            "workflow_status": "ANALYZING_COMPLIANCE",
            "logs": state.get("logs", []) + [{
                "agent": "Classification Agent",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "No raw clauses provided for classification."
            }]
        }

    # 1. Deduplicate raw clauses while preserving traceability
    deduped_clauses = _deduplicate_raw_clauses(raw_clauses)

    # 2. Classify clauses (LLM batching with deterministic fallback)
    classified_reqs = _classify_all_clauses(deduped_clauses)

    # 3. Assign deterministic, canonical requirement IDs
    final_requirements = _assign_canonical_ids(classified_reqs)

    log_entry = {
        "agent": "Classification Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": f"Classified {len(final_requirements)} formal requirements across {len(CATEGORY_PREFIX_MAP)} canonical categories."
    }

    return {
        "requirements": [r.model_dump() for r in final_requirements],
        "active_agent": "Classification Agent",
        "workflow_status": "ANALYZING_COMPLIANCE",
        "logs": state.get("logs", []) + [log_entry]
    }


def _classify_all_clauses(raw_clauses: List[Dict[str, Any]]) -> List[ClassifiedRequirement]:
    """
    Classifies all clauses. If LLM is available, processes in bounded batches.
    Falls back deterministically to rule-based classification on failure or when offline.
    """
    llm = LLMFactory.get_chat_model()
    classified_results: List[ClassifiedRequirement] = []

    if llm:
        batch_size = 10
        batches = [raw_clauses[i:i + batch_size] for i in range(0, len(raw_clauses), batch_size)]

        for batch in batches:
            batch_text = "\n\n".join([
                f"[Clause ID: {c.get('clause_id')} | Page: {c.get('source_page')} | Section: {c.get('source_section')}]\n{c.get('text')}"
                for c in batch
            ])
            try:
                structured_classifier = llm.with_structured_output(ClassificationAgentOutput)
                prompt = (
                    "Classify each of the following extracted raw clauses into one of the 9 canonical requirement categories:\n"
                    "Technical, Commercial, Contractual, Administrative, Certification, Delivery, Documentation, Submission, Eligibility.\n\n"
                    "CRITICAL RULES:\n"
                    "- Classify ONLY the supplied clauses. Do NOT invent new requirements.\n"
                    "- Preserve source_clause_id, source_page, and source_section from each clause.\n"
                    "- Distinguish mandatory (SHALL, MUST, REQUIRED) vs optional (SHOULD, MAY, PREFERABLE).\n"
                    "- Provide original_text verbatim and a crisp normalized_description.\n\n"
                    f"Clauses:\n{batch_text}"
                )
                output: ClassificationAgentOutput = structured_classifier.invoke([
                    SystemMessage(content=CLASSIFICATION_AGENT_PROMPT),
                    HumanMessage(content=prompt)
                ])

                if output and output.requirements:
                    # Validate and map LLM outputs to batch clauses
                    for req in output.requirements:
                        req.category = _normalize_category(req.category, req.text)
                        # Ensure source fields are populated
                        matching_clause = next(
                            (c for c in batch if c.get("clause_id") == req.source_clause_id),
                            None
                        )
                        if matching_clause:
                            if not req.original_text:
                                req.original_text = matching_clause.get("text")
                            req.source_page = matching_clause.get("source_page", req.source_page)
                            req.source_section = matching_clause.get("source_section", req.source_section)

                        # Enforce mandatory/optional validation against actual modal evidence from text or original_text
                        is_m, prio, m_conf, m_reas = _determine_mandatory(req.text, req.original_text)
                        if m_conf == 0.0:
                            # Ambiguous clause: never allow false high-confidence mandatory claims
                            req.is_mandatory = False
                            req.priority = "Low"
                            req.mandatory_confidence = 0.0
                            req.mandatory_reasoning = m_reas
                        else:
                            req.is_mandatory = is_m
                            req.priority = prio
                            req.mandatory_confidence = m_conf
                            req.mandatory_reasoning = m_reas

                        classified_results.append(req)
                else:
                    # Fallback for this batch
                    classified_results.extend(_fallback_classify_batch(batch))
            except Exception as e:
                print(f"[Agent 2: Classification] LLM batch classification error: {e}. Using rule-based fallback.")
                classified_results.extend(_fallback_classify_batch(batch))
    else:
        # LLM not available: deterministic rule-based classification across all clauses
        classified_results = _fallback_classify_batch(raw_clauses)

    return classified_results


def _fallback_classify_batch(clauses: List[Dict[str, Any]]) -> List[ClassifiedRequirement]:
    """
    Deterministic rule-based requirement classifier.
    Operates strictly from actual clause text without fabricating data.
    """
    classified: List[ClassifiedRequirement] = []

    for c in clauses:
        clause_id = c.get("clause_id", "")
        text = c.get("text", "")
        page = c.get("source_page", 1)
        section = c.get("source_section", "General")

        category, reason = _determine_category(text, section)
        is_mandatory, priority, mand_conf, mand_reason = _determine_mandatory(text, text)

        # Build crisp normalized statement
        clean_text = re.sub(r'\s+', ' ', text).strip()
        # Remove leading numbering like "2.1 High Availability & SLA:"
        norm_desc = re.sub(r'^(?:(?:\d+\.){1,3}\d*|(?:REQ|SPEC|DELIV|SEC|TECH)[-_:\s])\s*', '', clean_text)
        if len(norm_desc) > 160:
            norm_desc = norm_desc[:157] + "..."

        classified.append(
            ClassifiedRequirement(
                req_code="",  # Will be assigned canonically in _assign_canonical_ids
                category=category,
                priority=priority,
                is_mandatory=is_mandatory,
                mandatory_confidence=mand_conf,
                mandatory_reasoning=mand_reason,
                text=clean_text,
                original_text=clean_text,
                normalized_description=norm_desc,
                source_clause_id=clause_id,
                source_page=page,
                source_section=section,
                confidence=0.95 if mand_conf > 0.5 else 0.60,
                reasoning=f"{reason}; {mand_reason}"
            )
        )

    return classified


def _determine_category(text: str, section: str) -> tuple[str, str]:
    """
    Determines category based on targeted keyword patterns and section context.
    Returns (category_name, rationale).
    """
    text_lower = text.lower()
    sec_lower = section.lower()
    combined = f"{sec_lower} {text_lower}"

    # 1. Certification
    if re.search(r'\b(?:iso\s*\d+|soc\s*2|soc2|hipaa|pci[- ]dss|fedramp|fips|gdpr|csa\s*star|certif(?:ication|ied|y)|accredit(?:ation|ed)|attestation|cpa\s+audit|type\s+ii|type\s+2)\b', combined):
        return "Certification", "Clause references mandatory compliance, security standard, or industry certification audit"

    # 2. Submission
    if re.search(r'\b(?:bid\s+submission|submit\s+proposals?|proposals?\s+due|tender\s+box|submission\s+deadline|sealed\s+envelope|portal\s+upload|hard\s+copies|electronic\s+submission|submission\s+instructions|format\s+of\s+proposal|shall\s+submit|must\s+submit|invites\s+proposals)\b', combined):
        return "Submission", "Clause specifies tender submission procedure, deadline, or delivery format"

    # 3. Commercial
    if re.search(r'\b(?:pricing|cost|fee|fees|commercial\s+terms|payment\s+schedule|invoic(?:e|ing)|payment\s+terms|milestone\s+payment|budget|discount|hourly\s+rate|fixed\s+price|rates?\s+card|expenses|currency|financial\s+proposal|financial\s+quote)\b', combined):
        return "Commercial", "Clause establishes pricing model, commercial fees, invoicing terms, or payment schedule"

    # 4. Delivery
    if re.search(r'\b(?:timeline|milestone|schedule|weeks?\s+of\s+contract|concluded\s+within|completed\s+within|delivery\s+date|go[- ]live|deployment\s+schedule|implementation\s+timeline|lead\s+time|shipment|freight|handover|completion\s+date|phase\s+\d+|rollout)\b', combined):
        return "Delivery", "Clause defines implementation timeline, rollout schedule, delivery milestone, or freight handover"

    # 5. Contractual
    if re.search(r'\b(?:liability|unlimited\s+liability|indemnif|penalty|penalties|sla|service\s+level|uptime\s+guarantee|warranty|warranties|intellectual\s+property|ip\s+rights|governing\s+law|jurisdiction|breach|liquidated\s+damages|termination\s+for\s+convenience|terms\s+and\s+conditions)\b', combined):
        return "Contractual", "Clause governs legal liability, contractual commitments, warranties, SLA penalties, or indemnification"

    # 6. Documentation
    if re.search(r'\b(?:documentation|user\s+manual|architecture\s+diagram|training\s+materials?|runbook|api\s+docs|documented\s+restful|as-built|system\s+guide|specification\s+document|audit\s+trail\s+log|operations\s+manual)\b', combined):
        return "Documentation", "Clause mandates delivery of technical architecture, user manuals, training materials, or API runbooks"

    # 7. Eligibility
    if re.search(r'\b(?:eligibility|eligible|minimum\s+(?:\d+|five|ten)\s+years|prior\s+experience|past\s+performance|annual\s+turnover|track\s+record|case\s+studies|qualification\s+criteria|authorized\s+partner|licensed\s+to\s+operate|conflict\s+of\s+interest|corporate\s+standing)\b', combined):
        return "Eligibility", "Clause specifies vendor pre-qualification criteria, past performance case studies, or corporate standing"

    # 8. Administrative
    if re.search(r'\b(?:administrative|authorized\s+signatory|point\s+of\s+contact|company\s+registration|duns|ein|tin|tax\s+clearance|executive\s+contact|primary\s+liaison|notice\s+address|organizational\s+chart|administrative\s+form|power\s+of\s+attorney)\b', combined):
        return "Administrative", "Clause defines administrative vendor details, points of contact, or registration paperwork"

    # 9. Technical (Default)
    return "Technical", "Clause specifies architectural, technical infrastructure, software functionality, or performance criteria"


def _determine_mandatory(text: str, original_text: Optional[str] = None) -> tuple[bool, str, float, str]:
    """
    Evaluates mandatory vs optional status based on explicit modal evidence from text and original_text.
    Returns (is_mandatory, priority, mandatory_confidence, mandatory_reasoning).
    """
    combined_text = f"{text} {original_text or ''}".lower()

    mandatory_pattern = re.compile(
        r'\b(?:shall|must|mandatory|required|will\s+be\s+required|is\s+required\s+to|are\s+required\s+to|agrees\s+to|covenants|undertakes|cannot|strict\s+requirement)\b',
        re.IGNORECASE
    )
    optional_pattern = re.compile(
        r'\b(?:should|may|optional|preferable|preferred|desirable|nice\s+to\s+have|encouraged|recommended)\b',
        re.IGNORECASE
    )

    mandatory_match = mandatory_pattern.search(combined_text)
    optional_match = optional_pattern.search(combined_text)

    if mandatory_match and not optional_match:
        word = mandatory_match.group(0).upper()
        return True, "High", 1.0, f"Explicit mandatory evidence: Contains binding imperative '{word}'"
    elif optional_match and not mandatory_match:
        word = optional_match.group(0).upper()
        return False, "Low", 1.0, f"Explicit optional evidence: Contains advisory modal '{word}'"
    elif mandatory_match and optional_match:
        m_word = mandatory_match.group(0).upper()
        o_word = optional_match.group(0).upper()
        return True, "High", 0.85, f"Explicit mandatory evidence: Primary imperative '{m_word}' with subordinate advisory '{o_word}'"
    else:
        # Ambiguous / no-modal: DO NOT claim it is mandatory
        return False, "Low", 0.0, "Inferred/ambiguous status: Clause contains no explicit modal imperatives (SHALL, MUST, REQUIRED) or explicit advisory terms (SHOULD, MAY). Status cannot be determined with certainty from text alone."


def _normalize_category(category_name: str, text: str) -> str:
    """Normalizes category name to one of the 9 canonical types."""
    cat = category_name.strip().title() if category_name else "Technical"

    if cat in CATEGORY_PREFIX_MAP:
        return cat

    if cat in CATEGORY_SYNONYMS:
        syn = CATEGORY_SYNONYMS[cat]
        # Contextual adjustment: if "Security" has encryption/firewall without certs, map to Technical
        if cat == "Security" and not re.search(r'\b(?:iso|soc|hipaa|certif|audit|attestation)\b', text.lower()):
            return "Technical"
        return syn

    # Default fallback
    return "Technical"


PREFIX_TO_CATEGORY_MAP: Dict[str, str] = {
    "TECH": "Technical",
    "COMM": "Commercial",
    "CONTRACT": "Contractual",
    "CON": "Contractual",
    "ADMIN": "Administrative",
    "CERT": "Certification",
    "DELIVERY": "Delivery",
    "DEL": "Delivery",
    "DOC": "Documentation",
    "SUBMISSION": "Submission",
    "SUB": "Submission",
    "ELIGIBILITY": "Eligibility",
    "ELIG": "Eligibility"
}


def _assign_canonical_ids(requirements: List[ClassifiedRequirement]) -> List[ClassifiedRequirement]:
    """
    Assigns deterministic, unique, sequential IDs to requirements.
    Uses a 2-pass approach:
    1. Pass 1: Preserve explicit requirement IDs present in candidate text (e.g. REQ-TECH-001, REQ-COMM-001)
       and reconcile canonical category matching explicit ID prefix.
    2. Pass 2: For unnumbered requirements, generate category-prefixed sequential IDs (REQ-{PREFIX}-{idx:03d})
       without displacing explicit IDs.
    """
    EXPLICIT_ID_REGEX = re.compile(r'\b(REQ-[A-Z0-9]+-\d{3,4})\b', re.IGNORECASE)
    seen_codes: Set[str] = set()
    used_indices_per_cat: Dict[str, Set[int]] = {cat: set() for cat in CATEGORY_PREFIX_MAP}
    
    assigned_explicit: Set[int] = set()

    # PASS 1: Assign explicit IDs & reconcile canonical categories
    for idx, req in enumerate(requirements):
        explicit_match = None
        for candidate in [req.req_code, req.original_text, req.text, req.source_clause_id]:
            if candidate:
                m = EXPLICIT_ID_REGEX.search(str(candidate))
                if m:
                    candidate_code = m.group(1).upper()
                    if candidate_code not in seen_codes:
                        explicit_match = candidate_code
                        break
        if explicit_match:
            req.req_code = explicit_match
            seen_codes.add(explicit_match)
            assigned_explicit.add(idx)

            # Reconcile category based on explicit prefix if present
            prefix_match = re.search(r'^REQ-([A-Z0-9]+)-', explicit_match, re.IGNORECASE)
            if prefix_match:
                prefix = prefix_match.group(1).upper()
                if prefix in PREFIX_TO_CATEGORY_MAP:
                    req.category = PREFIX_TO_CATEGORY_MAP[prefix]

            num_match = re.search(r'-(\d{3,4})$', explicit_match)
            if num_match:
                cat = req.category if req.category in CATEGORY_PREFIX_MAP else "Technical"
                used_indices_per_cat[cat].add(int(num_match.group(1)))

    # PASS 2: Assign synthetic IDs to unnumbered requirements
    cat_counters: Dict[str, int] = {cat: 1 for cat in CATEGORY_PREFIX_MAP}
    for idx, req in enumerate(requirements):
        if idx in assigned_explicit:
            continue
        cat = req.category if req.category in CATEGORY_PREFIX_MAP else "Technical"
        prefix = CATEGORY_PREFIX_MAP[cat]
        num_idx = cat_counters[cat]
        
        code = f"REQ-{prefix}-{num_idx:03d}"
        while code in seen_codes or num_idx in used_indices_per_cat[cat]:
            num_idx += 1
            code = f"REQ-{prefix}-{num_idx:03d}"
            
        cat_counters[cat] = num_idx + 1
        used_indices_per_cat[cat].add(num_idx)
        req.req_code = code
        seen_codes.add(code)

    return requirements


def _deduplicate_raw_clauses(raw_clauses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detects and filters obvious duplicate clauses.
    If exact duplicate text appears within the same section and page, preserves the first instance.
    If the same requirement is cited across different sections, preserves both to maintain traceability.
    """
    seen_keys: Set[str] = set()
    deduped: List[Dict[str, Any]] = []

    for c in raw_clauses:
        text_clean = re.sub(r'\s+', ' ', c.get("text", "").strip().lower())
        page = c.get("source_page", 1)
        section = c.get("source_section", "General").strip().lower()

        # Deduplication signature includes text prefix, page, and section
        sig = f"{page}_{section}_{text_clean[:120]}"
        if sig not in seen_keys:
            seen_keys.add(sig)
            deduped.append(c)

    return deduped
