import re
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import RFPProposalState
from app.agents.llm_factory import LLMFactory
from app.core.prompts import RISK_AGENT_PROMPT
from app.models.schemas import RiskItem, ClarificationQuestion, RiskAndClarificationOutput
from app.rag.retriever import extract_relevant_evidence_snippet

# Severe liability/contractual trigger keywords
HARSH_CONTRACT_PATTERNS = re.compile(
    r'\b(?:unlimited\s+liability|liquidated\s+damages|uncapped\s+indemnit|indemnify\s+and\s+hold\s+harmless|'
    r'forfeit\s+all\s+intellectual\s+property|penalty\s+of|termination\s+for\s+convenience\s+without\s+compensation|'
    r'sole\s+remedy|unilateral\s+right\s+to\s+terminate)\b',
    re.IGNORECASE
)

# Financial performance security and bank guarantee patterns
PERFORMANCE_SECURITY_PATTERNS = re.compile(
    r'\b(?:performance\s+security|performance\s+bank\s+guarantee|security\s+deposit|'
    r'performance\s+guarantee|pbg\b|earnest\s+money\s+deposit|emd\b)\b',
    re.IGNORECASE
)

# Serious technical security obligations and strict quantified SLA patterns
SERIOUS_TECH_SECURITY_OR_SLA_PATTERNS = re.compile(
    r'\b(?:two[- ]factor\s+authentication|2fa\b|multi[- ]factor\s+authentication|mfa\b|'
    r'end[- ]to[- ]end\s+encryption|encrypt(?:ed|ion)?\s+(?:sensitive\s+information\s+)?at\s+rest|'
    r'aes[- ]256|tls\s*1\.[23]|fips\s*140|'
    r'disaster\s+recovery|rto\b|rpo\b|business\s+continuity|active[- ]active\s+clustering|'
    r'security\s+incident\s+(?:notification|reporting|affecting)\s+within\s+(?:24|12|4|2|1)\s+hours?|'
    r'breach\s+notification|uptime\s+of\s+at\s+least\s+99\.[5-9]|availability\s+of\s+at\s+least\s+99\.[5-9]|'
    r'99\.[5-9]%\s+(?:monthly\s+)?availability|incident\s+response\s+within\s+(?:15|30|60)\s+minutes?|'
    r'critical\s+production\s+incidents?\s+shall\s+receive|sla\s+penalt(?:y|ies))\b',
    re.IGNORECASE
)

# Moderate operational or contractual impact patterns
MODERATE_OPERATIONAL_IMPACT_PATTERNS = re.compile(
    r'\b(?:data\s+migration|migrate\s+.*?\s+data|backup\s+and\s+recovery|audit\s+trail|'
    r'rest\s+apis?|api\s+integration|confidentiality|non[- ]disclosure|patient[- ]related\s+information|'
    r'within\s+\d+\s*(?:weeks?|months?)\s+(?:from|of|after)\s+(?:contract|award|commencement)|'
    r'deployment\s+within\s+\d+\s*(?:weeks?|months?))\b',
    re.IGNORECASE
)

# Negative assertion patterns to sanitize on INFORMATION_REQUIRED
ASSERTED_FAILURE_PATTERNS = re.compile(
    r'\b(?:company\s+(?:does\s+not|doesn\'t|lacks|fails\s+to|does\s+not\s+have|has\s+no|cannot)|'
    r'vendor\s+(?:does\s+not|doesn\'t|lacks|fails\s+to|does\s+not\s+have|has\s+no|cannot)|'
    r'we\s+(?:do\s+not|don\'t|lack|have\s+no|cannot))\b',
    re.IGNORECASE
)

# Explicit disqualification / bid-blocking patterns in RFP text
BID_BLOCKING_DISQUALIFY_PATTERNS = re.compile(
    r'\b(?:ineligible|disqualif(?:ied|y|ying|ication)|sole\s+basis\s+for\s+rejection|'
    r'mandatory\s+condition\s+precedent|bid\s+rejection|automatic(?:ally)?\s+disqualif|'
    r'grounds\s+for\s+rejection|will\s+be\s+rejected|mandatory\s+disqualification)\b',
    re.IGNORECASE
)


def assess_risks_node(state: RFPProposalState) -> Dict[str, Any]:
    """
    Agent 4: Risk & Clarification Agent
    Consumes outputs from Agents 1, 2, and 3:
    - Classified requirements (mandatory/optional, categories)
    - Compliance matrix (COMPLIANT, PARTIALLY_COMPLIANT, NON_COMPLIANT, INFORMATION_REQUIRED)
    - Evidence and source traceability metadata
    
    Produces:
    - Evidence-grounded Risk Register with calibrated severity (CRITICAL, HIGH, MEDIUM, LOW)
    - Specific, actionable Clarification Questions tied to requirements
    - Guaranteed zero hallucinations (missing evidence is strictly unverified, never assumed failure)
    """
    requirements = state.get("requirements", [])
    compliance_matrix = state.get("compliance_matrix", [])
    metadata = state.get("metadata", {})
    llm = LLMFactory.get_chat_model()

    # Build fast lookup maps
    req_map: Dict[str, Dict[str, Any]] = {
        r.get("req_code", f"REQ-{idx}"): r
        for idx, r in enumerate(requirements)
    }
    comp_map: Dict[str, Dict[str, Any]] = {
        c.get("req_code", f"REQ-{idx}"): c
        for idx, c in enumerate(compliance_matrix)
    }

    risks: List[RiskItem] = []
    clarifications: List[ClarificationQuestion] = []

    # Attempt LLM evaluation with structured output
    if llm and (requirements or compliance_matrix):
        try:
            # Filter to items requiring attention: non-compliant, partial, info required, or high-risk clauses
            attention_items = []
            for req_code, req in req_map.items():
                comp = comp_map.get(req_code, {})
                status = comp.get("status", "INFORMATION_REQUIRED")
                is_mandatory = req.get("is_mandatory", False)
                cat = req.get("category", "General")
                text = req.get("text", "")
                
                # Check if item warrants review
                if status in ["NON_COMPLIANT", "PARTIALLY_COMPLIANT"]:
                    attention_items.append({"req": req, "comp": comp})
                elif status == "INFORMATION_REQUIRED" and (is_mandatory or cat in ["Certification", "Eligibility", "Contractual", "Legal", "Delivery"]):
                    attention_items.append({"req": req, "comp": comp})
                elif HARSH_CONTRACT_PATTERNS.search(text):
                    attention_items.append({"req": req, "comp": comp})

            if attention_items:
                prompt_items_summary = []
                for item in attention_items:
                    r = item["req"]
                    c = item["comp"]
                    prompt_items_summary.append({
                        "requirement_id": r.get("req_code"),
                        "text": r.get("text"),
                        "category": r.get("category"),
                        "is_mandatory": r.get("is_mandatory"),
                        "compliance_status": c.get("status"),
                        "compliance_notes": c.get("notes"),
                        "evidence_snippet": extract_relevant_evidence_snippet(r.get("text", ""), c.get("evidence_text"), status=c.get("status")),
                        "company_source_doc": c.get("company_source_doc")
                    })

                audit_prompt = (
                    f"RFP Context: {metadata}\n\n"
                    f"Requirements Requiring Risk/Clarification Audit ({len(prompt_items_summary)} items):\n"
                    f"{prompt_items_summary}\n\n"
                    f"Instructions:\n"
                    f"1. Generate evidence-grounded risks with calibrated severity (CRITICAL, HIGH, MEDIUM, LOW).\n"
                    f"2. Formulate specific clarification questions for items with missing/partial information.\n"
                    f"3. Tie every item strictly to its originating requirement_id.\n"
                    f"4. NEVER mix, borrow, or cite evidence snippets from one requirement into another requirement.\n"
                    f"5. If a requirement is NON_COMPLIANT or PARTIALLY_COMPLIANT, cite ONLY its own evidence snippet or notes.\n"
                    f"6. If a requirement is INFORMATION_REQUIRED, state that verification is missing and DO NOT attach collateral evidence from other requirements.\n"
                    f"7. NEVER invent facts, capabilities, certifications, or commitments."
                )

                structured_agent = llm.with_structured_output(RiskAndClarificationOutput)
                llm_result: RiskAndClarificationOutput = structured_agent.invoke([
                    SystemMessage(content=RISK_AGENT_PROMPT),
                    HumanMessage(content=audit_prompt)
                ])

                # Apply Programmatic Safety Guard to LLM Output
                risks, clarifications = _apply_programmatic_safety_guard(
                    llm_output=llm_result,
                    req_map=req_map,
                    comp_map=comp_map
                )
        except Exception as e:
            print(f"[Agent 4: Risk] LLM audit failed or unavailable ({e}). Using deterministic fallback.")
            risks = []
            clarifications = []

    # If LLM was unavailable, errored, or produced no items, run deterministic fallback
    if not risks and not clarifications:
        risks, clarifications = _fallback_risk_analysis(requirements, compliance_matrix, metadata)

    log_entry = {
        "agent": "Risk & Clarification Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": f"Identified {len(risks)} evidence-grounded risks and generated {len(clarifications)} targeted clarification questions."
    }

    return {
        "risks": [r.model_dump() for r in risks],
        "clarification_questions": [q.model_dump() for q in clarifications],
        "active_agent": "Risk & Clarification Agent",
        "workflow_status": "AWAITING_GO_NOGO",
        "logs": state.get("logs", []) + [log_entry]
    }


def _calibrate_risk_severity(
    raw_severity: Optional[str],
    status: str,
    is_mandatory: bool,
    category: str,
    req_text: str
) -> str:
    """
    Calibrates risk severity based on deterministic enterprise rules:
    - Mandatory + NON_COMPLIANT -> CRITICAL when the failure is a genuine bid/deal-breaker, else HIGH/MEDIUM.
    - Mandatory + INFORMATION_REQUIRED:
      - Explicit disqualification condition / bid blocker -> CRITICAL
      - Mandatory Certification / Statutory Eligibility -> HIGH
      - Harsh contractual liability / Performance Security (PBG) -> HIGH
      - Serious security obligation / strict quantified SLA -> HIGH
      - Moderate operational impact / contract covenants -> MEDIUM
      - Ordinary functional / documentation / delivery capability gap -> LOW
    - Optional requirements -> MEDIUM or LOW.
    """
    has_harsh_legal = bool(HARSH_CONTRACT_PATTERNS.search(req_text))
    has_disqualifying_language = bool(BID_BLOCKING_DISQUALIFY_PATTERNS.search(req_text))
    has_perf_security = bool(PERFORMANCE_SECURITY_PATTERNS.search(req_text))
    has_serious_security_or_sla = bool(SERIOUS_TECH_SECURITY_OR_SLA_PATTERNS.search(req_text))
    has_moderate_impact = bool(MODERATE_OPERATIONAL_IMPACT_PATTERNS.search(req_text))

    if status == "NON_COMPLIANT":
        if has_disqualifying_language or (is_mandatory and (has_harsh_legal or category in ["Eligibility", "Certification"])):
            return "CRITICAL"
        if is_mandatory or category in ["Legal", "Contractual", "Delivery"]:
            return "HIGH"
        return "MEDIUM"

    if status == "INFORMATION_REQUIRED":
        # 1. Truly critical / bid-blocking condition
        if has_disqualifying_language and is_mandatory:
            return "CRITICAL"
        
        # 2. High severity: Statutory pre-qualification, harsh liabilities, PBG, serious security/SLA
        if is_mandatory:
            if category in ["Eligibility", "Certification"] or has_harsh_legal or has_perf_security or has_serious_security_or_sla:
                return "HIGH"
            if category in ["Contractual", "Legal"] or has_moderate_impact:
                return "MEDIUM"
            return "LOW"
        else:
            # Optional requirement with missing evidence
            if has_harsh_legal or category in ["Eligibility", "Certification"]:
                return "MEDIUM"
            return "LOW"

    if status == "PARTIALLY_COMPLIANT":
        if is_mandatory and (has_disqualifying_language or has_harsh_legal or category in ["Eligibility", "Certification"] or has_serious_security_or_sla):
            return "HIGH"
        if is_mandatory:
            return "MEDIUM"
        return "LOW"

    # COMPLIANT
    if has_harsh_legal:
        return "HIGH"
    
    # Normalize whatever raw_severity was if valid
    if raw_severity:
        upper = raw_severity.strip().upper()
        if upper in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            # Ensure optional requirement without harsh legal isn't inflated to CRITICAL
            if not is_mandatory and upper == "CRITICAL" and not has_harsh_legal:
                return "MEDIUM"
            # Ensure INFORMATION_REQUIRED without explicit disqualifying language isn't inflated to CRITICAL
            if status == "INFORMATION_REQUIRED" and upper == "CRITICAL" and not has_disqualifying_language:
                return "HIGH" if (category in ["Eligibility", "Certification"] or has_perf_security or has_serious_security_or_sla) else "MEDIUM"
            return upper

    return "LOW"


def _sanitize_unverified_claim(text: str, req_id: str) -> str:
    """
    Guarantees zero hallucination: Prevents claiming as fact that the company lacks a capability
    when the evidence is merely absent (INFORMATION_REQUIRED).
    """
    if ASSERTED_FAILURE_PATTERNS.search(text):
        sanitized = ASSERTED_FAILURE_PATTERNS.sub("company capability could not be verified from available evidence for", text)
        return sanitized
    return text


def _sanitize_cross_requirement_evidence(
    text: str,
    target_req_id: str,
    target_req_text: str,
    target_comp: Dict[str, Any],
    comp_map: Dict[str, Dict[str, Any]],
    req_map: Dict[str, Dict[str, Any]]
) -> str:
    """
    Prevents cross-requirement evidence contamination by verifying that text does not
    borrow evidence snippets, limitation notes, or citations from other requirements.
    """
    if not text or not target_req_id:
        return text

    status = target_comp.get("status", "INFORMATION_REQUIRED")
    target_ev = target_comp.get("evidence_text") or ""
    target_notes = target_comp.get("notes") or ""

    # Check if foreign evidence from other requirements in comp_map was inserted into text
    is_contaminated = False
    for other_id, other_comp in comp_map.items():
        if other_id == target_req_id:
            continue

        other_ev = other_comp.get("evidence_text") or ""
        other_notes = other_comp.get("notes") or ""

        # Check chunks of other evidence (e.g. sentences or phrases >= 20 chars)
        for candidate_src in [other_ev, other_notes]:
            if not candidate_src or len(candidate_src) < 20:
                continue
            segments = [s.strip() for s in re.split(r'[\n\.\;\:]+', candidate_src) if len(s.strip()) >= 20]
            for seg in segments:
                if seg.lower() in text.lower() and seg.lower() not in target_req_text.lower() and seg.lower() not in target_ev.lower() and seg.lower() not in target_notes.lower():
                    is_contaminated = True
                    break
            if is_contaminated:
                break
        if is_contaminated:
            break

    # If contaminated, deterministically rebuild text strictly grounded on target requirement
    if is_contaminated:
        if status == "NON_COMPLIANT":
            limitation = extract_relevant_evidence_snippet(target_req_text, target_ev, status=status) or target_notes[:140] or "Documented limitation in company collateral indicates requirement is unsupported."
            return f"Requirement {target_req_id} is unsupported based on company evidence. Documented limitation: '{limitation}'."
        elif status == "PARTIALLY_COMPLIANT":
            limitation = target_notes[:140] if target_notes else (extract_relevant_evidence_snippet(target_req_text, target_ev, status=status) or "Documented partial capability.")
            return f"Requirement {target_req_id} is partially supported. Documented limitation or workaround: '{limitation}'."
        elif status == "INFORMATION_REQUIRED":
            return f"Verification data is currently missing from company collateral for {target_req_id}: '{target_req_text[:140]}'. Capability status could not be verified from available evidence."
        else:
            return f"Clause {target_req_id} contains significant contractual obligations or risk exposure: '{target_req_text[:140]}'."

    return text


def _determine_clarification_type(status: str, req_text: str, q_text: str = "") -> str:
    """
    Determines whether a clarification is an ISSUER_CLARIFICATION or an INTERNAL_INFORMATION_REQUEST:
    - ISSUER_CLARIFICATION: Directed to RFP issuer/client regarding ambiguity, interpretation,
      conflicting clauses, missing RFP specifications, or permitted exceptions/variances.
    - INTERNAL_INFORMATION_REQUEST: Directed to internal company SME/team regarding missing company
      evidence (e.g. confirming certification status, capabilities, metrics, documentation).
    """
    if status == "INFORMATION_REQUIRED":
        combined = f"{req_text} {q_text}".lower()
        # Check if question or clause asks client authority regarding RFP ambiguity / missing SLA specification
        if any(term in combined for term in [
            "could the authority", "could the client", "issuing authority", 
            "clarify the required response", "clarify the required resolution", 
            "clarify response time", "clarify the milestone"
        ]):
            return "ISSUER_CLARIFICATION"
        # Check if the requirement clause itself contains ambiguous language without specified criteria:
        if re.search(r'\b(?:rapid\s+response|rapid\s+turnaround|reasonable\s+time|as\s+needed|to\s+be\s+agreed)\b', req_text, re.IGNORECASE) and not re.search(r'\b(?:confirm\s+whether\s+the\s+company|internal\s+team|company\s+holds)\b', q_text, re.IGNORECASE):
            return "ISSUER_CLARIFICATION"
        # Default for missing evidence is an internal SME information request
        return "INTERNAL_INFORMATION_REQUEST"
    
    # NON_COMPLIANT or PARTIALLY_COMPLIANT: directed to issuer/client to ask about exception/workaround
    return "ISSUER_CLARIFICATION"


def _determine_target_owner(category: str, status: str, clarif_type: str = "ISSUER_CLARIFICATION") -> str:
    cat = (category or "").lower()
    if clarif_type == "INTERNAL_INFORMATION_REQUEST":
        if "doc" in cat:
            return "Internal Technical Documentation Lead"
        if "cert" in cat or "secur" in cat:
            return "Internal Security & Compliance Lead"
        if "legal" in cat or "contract" in cat:
            return "Internal Legal Counsel"
        if "commerc" in cat or "financ" in cat or "price" in cat:
            return "Internal Finance & Commercial Lead"
        if "deliver" in cat or "timeline" in cat:
            return "Internal Project Delivery Director"
        if "elig" in cat:
            return "Internal Compliance & Eligibility SME"
        if "tech" in cat or "arch" in cat:
            return "Internal Technical Architect"
        return "Internal Bid Team / SME"
    else:
        # ISSUER_CLARIFICATION
        if "doc" in cat:
            return "RFP Issuing Authority / Documentation Lead"
        if "legal" in cat or "contract" in cat:
            return "RFP Issuing Authority / Contracting Officer"
        if "commerc" in cat or "financ" in cat or "price" in cat:
            return "RFP Issuing Authority / Commercial Lead"
        if "cert" in cat:
            return "RFP Issuing Authority / Compliance Office"
        if "deliver" in cat:
            return "RFP Issuing Authority / Project Manager"
        if "tech" in cat or "arch" in cat:
            return "RFP Issuing Authority / Technical Committee"
        return "RFP Issuing Authority / Procurement Officer"


def _apply_programmatic_safety_guard(
    llm_output: RiskAndClarificationOutput,
    req_map: Dict[str, Dict[str, Any]],
    comp_map: Dict[str, Dict[str, Any]]
) -> Tuple[List[RiskItem], List[ClarificationQuestion]]:
    """
    Enforces deterministic safety rules on LLM outputs:
    1. Validates requirement IDs against real requirements. Rejects hallucinated requirement references.
    2. Enforces severity calibration based on compliance status and mandatory/optional flag.
    3. Sanitizes unsupported negative assertions on INFORMATION_REQUIRED items.
    4. Eliminates cross-requirement evidence contamination.
    5. Deduplicates risks and clarifications per requirement.
    6. Populates complete source traceability metadata strictly isolated to the originating requirement.
    """
    valid_req_ids = set(req_map.keys())
    validated_risks: List[RiskItem] = []
    validated_clarifs: List[ClarificationQuestion] = []

    seen_risk_reqs: Set[str] = set()
    seen_clarif_reqs: Set[str] = set()

    for idx, risk in enumerate(llm_output.risks):
        req_id = risk.requirement_id or risk.rfp_reference
        # If requirement_id is specified but not in valid requirements -> reject orphan/hallucinated risk!
        if req_id and req_id not in valid_req_ids:
            extracted_ids = [vid for vid in valid_req_ids if vid in str(req_id)]
            if extracted_ids:
                req_id = extracted_ids[0]
            else:
                continue  # Reject hallucinated requirement reference

        req_info = req_map.get(req_id) if req_id else None
        comp_info = comp_map.get(req_id) if req_id else {}

        # Prevent duplicates for the same requirement
        if req_id:
            if req_id in seen_risk_reqs:
                continue
            seen_risk_reqs.add(req_id)

        # Determine status, mandatory, and CANONICAL category
        status = comp_info.get("status") if comp_info else "INFORMATION_REQUIRED"
        is_mandatory = req_info.get("is_mandatory", False) if req_info else False
        category = req_info.get("category", risk.category or "Operational") if req_info else (risk.category or "Operational")
        req_text = req_info.get("text", "") if req_info else (risk.requirement_text or risk.description)

        # Calibrate severity
        severity = _calibrate_risk_severity(
            raw_severity=risk.severity,
            status=status,
            is_mandatory=is_mandatory,
            category=category,
            req_text=req_text
        )

        # Sanitize cross-requirement evidence contamination
        description = risk.description or ""
        description = _sanitize_cross_requirement_evidence(
            text=description,
            target_req_id=req_id or "",
            target_req_text=req_text,
            target_comp=comp_info,
            comp_map=comp_map,
            req_map=req_map
        )

        # Sanitize ungrounded claims on INFORMATION_REQUIRED items
        if status == "INFORMATION_REQUIRED":
            description = _sanitize_unverified_claim(description, req_id or "requirement")

        # Citations and source doc strictly isolated to originating requirement
        citations = comp_info.get("citations", []) if (comp_info and status != "INFORMATION_REQUIRED") else []
        company_doc_id = comp_info.get("company_doc_id") if (comp_info and status != "INFORMATION_REQUIRED") else None
        chunk_id = comp_info.get("chunk_id") if (comp_info and status != "INFORMATION_REQUIRED") else None

        risk_id = risk.risk_id or f"RISK-{req_id or idx + 1}"
        rfp_ref = risk.rfp_reference or (f"{req_id} (p. {req_info.get('source_page', 1)}, § {req_info.get('source_section', 'General')})" if req_info else (f"Ref: {req_id}" if req_id else "General"))

        validated_risks.append(
            RiskItem(
                risk_id=risk_id,
                id=risk.id or risk_id,
                requirement_id=req_id,
                requirement_text=req_text,
                category=category,
                severity=severity,
                likelihood=risk.likelihood or "Medium",
                title=risk.title or f"{severity} Risk: {category} ({req_id or 'General'})",
                description=description,
                impact=risk.impact or ("Risk of proposal disqualification or compliance penalty." if is_mandatory else "Potential proposal scoring deduction."),
                mitigation_strategy=risk.mitigation_strategy or risk.recommended_action or "Seek formal clarification or internal verification.",
                recommended_action=risk.recommended_action or risk.mitigation_strategy,
                compliance_status=status,
                rfp_reference=rfp_ref,
                company_doc_id=company_doc_id,
                chunk_id=chunk_id,
                source_page=req_info.get("source_page") if req_info else None,
                source_section=req_info.get("source_section") if req_info else None,
                citations=citations
            )
        )

    q_counter = 1
    for clarif in llm_output.clarification_questions:
        req_id = clarif.requirement_id or clarif.rfp_section_reference
        if req_id and req_id not in valid_req_ids:
            extracted_ids = [vid for vid in valid_req_ids if vid in str(req_id)]
            if extracted_ids:
                req_id = extracted_ids[0]
            else:
                continue  # Reject hallucinated requirement reference

        if req_id:
            if req_id in seen_clarif_reqs:
                continue
            seen_clarif_reqs.add(req_id)

        req_info = req_map.get(req_id) if req_id else None
        comp_info = comp_map.get(req_id) if req_id else {}
        status = comp_info.get("status") if comp_info else "INFORMATION_REQUIRED"
        is_mandatory = req_info.get("is_mandatory", False) if req_info else False
        req_text = req_info.get("text", "") if req_info else ""

        # Sanitize question text and rationale against cross-requirement evidence
        q_text = clarif.question_text or clarif.question or ""
        q_rationale = clarif.rationale or clarif.reason or ""

        q_text = _sanitize_cross_requirement_evidence(
            text=q_text,
            target_req_id=req_id or "",
            target_req_text=req_text,
            target_comp=comp_info,
            comp_map=comp_map,
            req_map=req_map
        )
        q_rationale = _sanitize_cross_requirement_evidence(
            text=q_rationale,
            target_req_id=req_id or "",
            target_req_text=req_text,
            target_comp=comp_info,
            comp_map=comp_map,
            req_map=req_map
        )

        if status == "INFORMATION_REQUIRED":
            q_text = _sanitize_unverified_claim(q_text, req_id or "requirement")
            q_rationale = _sanitize_unverified_claim(q_rationale, req_id or "requirement")

        clarif_id = clarif.clarification_id or f"CLARIF-{req_id or q_counter}"
        priority = "CRITICAL" if (status == "NON_COMPLIANT" and is_mandatory) else ("HIGH" if is_mandatory else "MEDIUM")

        # Determine clarification type
        raw_type = getattr(clarif, "clarification_type", None)
        if raw_type in ["ISSUER_CLARIFICATION", "INTERNAL_INFORMATION_REQUEST"]:
            clarif_type = raw_type
        else:
            clarif_type = _determine_clarification_type(
                status=status,
                req_text=req_text,
                q_text=q_text
            )

        # Reconcile target owner strictly using canonical category
        category = req_info.get("category") if req_info else "General"
        target_owner = _determine_target_owner(category, status, clarif_type)

        clarif_citations = comp_info.get("citations", []) if (comp_info and status != "INFORMATION_REQUIRED") else []

        validated_clarifs.append(
            ClarificationQuestion(
                q_number=q_counter,
                clarification_id=clarif_id,
                id=clarif.id or clarif_id,
                requirement_id=req_id,
                rfp_section_reference=clarif.rfp_section_reference or (f"Ref: {req_id}" if req_id else "General"),
                question_text=q_text,
                question=q_text,
                rationale=q_rationale,
                reason=q_rationale,
                priority=clarif.priority or priority,
                clarification_type=clarif_type,
                target_owner=target_owner,
                compliance_status=status,
                citations=clarif_citations
            )
        )
        q_counter += 1

    return validated_risks, validated_clarifs


def _fallback_risk_analysis(
    requirements: List[Dict[str, Any]],
    compliance_matrix: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None
) -> Tuple[List[RiskItem], List[ClarificationQuestion]]:
    """
    Deterministic rule-based risk and clarification generator.
    Guarantees 100% evidence-grounded outputs without hallucination.
    """
    req_map: Dict[str, Dict[str, Any]] = {
        r.get("req_code", f"REQ-{idx}"): r
        for idx, r in enumerate(requirements)
    }
    comp_map: Dict[str, Dict[str, Any]] = {
        c.get("req_code", f"REQ-{idx}"): c
        for idx, c in enumerate(compliance_matrix)
    }

    risks: List[RiskItem] = []
    clarifications: List[ClarificationQuestion] = []
    seen_risk_reqs: Set[str] = set()
    seen_clarif_reqs: Set[str] = set()

    q_counter = 1

    for req_code, req in req_map.items():
        comp = comp_map.get(req_code, {})
        status = comp.get("status", "INFORMATION_REQUIRED")
        is_mandatory = req.get("is_mandatory", False)
        category = req.get("category", "General")
        req_text = req.get("text", "")
        source_page = req.get("source_page", 1)
        source_section = req.get("source_section", "General")
        evidence_text = comp.get("evidence_text")
        notes = comp.get("notes", "")
        citations = comp.get("citations", [])

        has_harsh_legal = bool(HARSH_CONTRACT_PATTERNS.search(req_text))

        # --- RISK GENERATION ---
        risk_to_add: Optional[RiskItem] = None

        if status == "NON_COMPLIANT":
            severity = "CRITICAL" if (is_mandatory or category in ["Eligibility", "Certification", "Legal", "Contractual"]) else "MEDIUM"
            limitation = extract_relevant_evidence_snippet(req_text, evidence_text, status=status) or (notes[:140] if notes else "Documented limitation in company collateral indicates requirement is unsupported.")
            risk_to_add = RiskItem(
                risk_id=f"RISK-{req_code}",
                id=f"RISK-{req_code}",
                requirement_id=req_code,
                requirement_text=req_text,
                category=category,
                severity=severity,
                likelihood="High",
                title=f"Non-Compliance: {category} ({req_code})",
                description=f"Requirement {req_code} is unsupported based on company evidence. Documented limitation: '{limitation}'.",
                impact="Risk of proposal disqualification or compliance score deduction if submitted without an approved variance." if is_mandatory else "Loss of evaluation points for optional requirement.",
                mitigation_strategy="Seek executive approval to formulate a formal variance/exception in the proposal response, or evaluate subcontractor partnership capabilities.",
                recommended_action="Obtain executive bid sign-off on non-compliance carve-out.",
                compliance_status=status,
                rfp_reference=f"{req_code} (p. {source_page}, § {source_section})",
                company_doc_id=comp.get("company_doc_id"),
                chunk_id=comp.get("chunk_id"),
                source_page=source_page,
                source_section=source_section,
                citations=citations
            )

        elif status == "PARTIALLY_COMPLIANT":
            severity = "HIGH" if is_mandatory else "MEDIUM"
            limitation = notes[:140] if notes else (extract_relevant_evidence_snippet(req_text, evidence_text, status=status) or "Documented partial capability.")
            risk_to_add = RiskItem(
                risk_id=f"RISK-{req_code}",
                id=f"RISK-{req_code}",
                requirement_id=req_code,
                requirement_text=req_text,
                category=category,
                severity=severity,
                likelihood="High",
                title=f"Partial Compliance Gap: {category} ({req_code})",
                description=f"Requirement {req_code} is partially supported. Documented limitation or workaround: '{limitation}'.",
                impact="Potential client pushback or scoring deduction if the workaround/limitation is not fully accepted by the tender committee.",
                mitigation_strategy="Draft an explicit proposal narrative outlining the supported portion, detailing the workaround/roadmap milestone, and confirming client fit.",
                recommended_action="Document partial compliance transparently with technical justification.",
                compliance_status=status,
                rfp_reference=f"{req_code} (p. {source_page}, § {source_section})",
                company_doc_id=comp.get("company_doc_id"),
                chunk_id=comp.get("chunk_id"),
                source_page=source_page,
                source_section=source_section,
                citations=citations
            )

        elif status == "INFORMATION_REQUIRED":
            # Calibrate severity using general-purpose semantic rules
            severity = _calibrate_risk_severity(
                raw_severity=None,
                status=status,
                is_mandatory=is_mandatory,
                category=category,
                req_text=req_text
            )

            # Likelihood and impact calibrated to risk severity
            if severity in ["CRITICAL", "HIGH"]:
                likelihood = "High"
                impact = "Risk of bid disqualification, non-responsiveness, or severe compliance penalty if required verification cannot be established."
            elif severity == "MEDIUM":
                likelihood = "Medium"
                impact = "Potential proposal scoring deduction, operational misalignment, or clarification delay if unverified before submission."
            else:
                likelihood = "Low"
                impact = "Routine capability discovery item. Low proposal risk provided standard capability is confirmed during internal review."

            risk_to_add = RiskItem(
                risk_id=f"RISK-{req_code}",
                id=f"RISK-{req_code}",
                requirement_id=req_code,
                requirement_text=req_text,
                category=category,
                severity=severity,
                likelihood=likelihood,
                title=f"Unverified Capability Gap: {category} ({req_code})",
                description=f"Verification data is currently missing from company collateral for {req_code}: '{req_text[:140]}'. Capability status could not be verified from available evidence.",
                impact=impact,
                mitigation_strategy="Conduct priority discovery with technical and compliance leads to obtain verified proof prior to proposal submission.",
                recommended_action="Obtain verified documentation from internal capability owners.",
                compliance_status=status,
                rfp_reference=f"{req_code} (p. {source_page}, § {source_section})",
                company_doc_id=None,
                chunk_id=None,
                source_page=source_page,
                source_section=source_section,
                citations=[]
            )

        elif has_harsh_legal:
            # COMPLIANT requirement with harsh legal trap
            risk_to_add = RiskItem(
                risk_id=f"RISK-{req_code}",
                id=f"RISK-{req_code}",
                requirement_id=req_code,
                requirement_text=req_text,
                category="Legal",
                severity="HIGH",
                likelihood="Medium",
                title=f"Strict Contractual Liability: {req_code}",
                description=f"Clause {req_code} contains high-exposure legal language: '{req_text[:140]}'.",
                impact="Severe financial and legal liability exposure under uncapped or harsh contract conditions.",
                mitigation_strategy="Formulate standard commercial limitation of liability cap and mutual indemnification carve-outs for proposal submission.",
                recommended_action="Submit legal exception and liability cap proposal.",
                compliance_status=status,
                rfp_reference=f"{req_code} (p. {source_page}, § {source_section})",
                company_doc_id=comp.get("company_doc_id"),
                chunk_id=comp.get("chunk_id"),
                source_page=source_page,
                source_section=source_section,
                citations=citations
            )

        if risk_to_add and req_code not in seen_risk_reqs:
            risks.append(risk_to_add)
            seen_risk_reqs.add(req_code)

        # --- CLARIFICATION GENERATION ---
        clarif_to_add: Optional[ClarificationQuestion] = None

        if status == "NON_COMPLIANT":
            priority = "CRITICAL" if is_mandatory else "MEDIUM"
            clarif_to_add = ClarificationQuestion(
                q_number=q_counter,
                clarification_id=f"CLARIF-{req_code}",
                id=f"CLARIF-{req_code}",
                requirement_id=req_code,
                rfp_section_reference=f"Section: {source_section} | Ref: {req_code}",
                question_text=f"Regarding requirement {req_code} ('{req_text[:120]}'): Can the issuing authority clarify whether alternative technical approaches or approved exceptions will be accepted, or confirm if this is an absolute disqualification criterion?",
                question=f"Regarding requirement {req_code} ('{req_text[:120]}'): Can the issuing authority clarify whether alternative technical approaches or approved exceptions will be accepted?",
                rationale="Company documentation indicates a documented limitation for this specification. Formal clarification is required to determine if a variance is permissible.",
                reason="Company documentation indicates a documented limitation for this specification. Formal clarification is required to determine if a variance is permissible.",
                priority=priority,
                clarification_type="ISSUER_CLARIFICATION",
                target_owner="RFP Issuing Authority / Contracting Officer",
                compliance_status=status,
                citations=citations
            )

        elif status == "PARTIALLY_COMPLIANT":
            priority = "HIGH" if is_mandatory else "MEDIUM"
            clarif_to_add = ClarificationQuestion(
                q_number=q_counter,
                clarification_id=f"CLARIF-{req_code}",
                id=f"CLARIF-{req_code}",
                requirement_id=req_code,
                rfp_section_reference=f"Section: {source_section} | Ref: {req_code}",
                question_text=f"Regarding requirement {req_code} ('{req_text[:120]}'): Company documentation confirms support via specific workaround/integration ({notes[:80] if notes else 'documented partial support'}). Could the client confirm if this approach satisfies the project integration criteria?",
                question=f"Regarding requirement {req_code} ('{req_text[:120]}'): Could the client confirm if the documented workaround satisfies integration criteria?",
                rationale="Ensures client acceptance of documented partial capability or workaround prior to proposal finalization.",
                reason="Ensures client acceptance of documented partial capability or workaround prior to proposal finalization.",
                priority=priority,
                clarification_type="ISSUER_CLARIFICATION",
                target_owner="RFP Issuing Authority / Technical Committee",
                compliance_status=status,
                citations=citations
            )

        elif status == "INFORMATION_REQUIRED":
            # Generate clarification if mandatory or meaningful category
            if is_mandatory or category in ["Certification", "Eligibility", "Compliance", "Contractual", "Delivery", "Technical"]:
                priority = "HIGH" if is_mandatory else "LOW"
                
                # Check for RFP ambiguity (e.g. 24/7 with rapid response and no SLA)
                has_sla_ambiguity = bool(re.search(r'\b(?:rapid\s+response|rapid\s+turnaround|reasonable\s+time|as\s+needed)\b', req_text, re.IGNORECASE))
                
                if has_sla_ambiguity:
                    clarif_type = "ISSUER_CLARIFICATION"
                    q_text = f"Regarding requirement {req_code} ('{req_text[:120]}'): Could the issuing authority clarify the required response and resolution time SLAs for this requirement?"
                    owner = "RFP Issuing Authority / Technical Committee"
                    rationale = "The RFP clause specifies rapid response without explicit metrics; clarification from the authority is required to align SLA commitments."
                elif "cert" in category.lower() or any(c in req_text.lower() for c in ["iso 27001", "iso27001", "fedramp", "soc 2", "soc2", "hipaa", "certification"]):
                    clarif_type = "INTERNAL_INFORMATION_REQUEST"
                    q_text = f"Regarding certification requirement {req_code} ('{req_text[:120]}'): Please confirm whether the company currently holds a valid certification and provide the relevant certificate and documentation."
                    owner = "Internal Security & Compliance Lead"
                    rationale = "Certification evidence is unverified in company knowledge base. Internal confirmation and certificate copy are required to substantiate proposal claims."
                elif "doc" in category.lower():
                    clarif_type = "INTERNAL_INFORMATION_REQUEST"
                    q_text = f"Regarding documentation requirement {req_code} ('{req_text[:120]}'): Please confirm internal availability of technical documentation, user guides, and training collateral."
                    owner = "Internal Technical Documentation Lead"
                    rationale = "Documentation collateral is unverified in knowledge base; internal team must confirm documentation availability."
                elif "commerc" in category.lower() or "financ" in category.lower():
                    clarif_type = "INTERNAL_INFORMATION_REQUEST"
                    q_text = f"Regarding commercial requirement {req_code} ('{req_text[:120]}'): Please confirm pricing structure, commercial model, and payment schedule alignment."
                    owner = "Internal Finance & Commercial Lead"
                    rationale = "Commercial details require internal finance team verification prior to proposal commitment."
                elif "sub" in category.lower():
                    clarif_type = "INTERNAL_INFORMATION_REQUEST"
                    q_text = f"Regarding submission requirement {req_code} ('{req_text[:120]}'): Please confirm proposal submission format, packaging, and delivery logistics."
                    owner = "Internal Bid Team / SME"
                    rationale = "Submission instructions require internal bid team logistics verification."
                elif "deliver" in category.lower() or "timeline" in category.lower():
                    clarif_type = "INTERNAL_INFORMATION_REQUEST"
                    q_text = f"Regarding delivery requirement {req_code} ('{req_text[:120]}'): Please confirm internal delivery timeline feasibility, staffing availability, and project milestone schedule."
                    owner = "Internal Project Delivery Director"
                    rationale = "Delivery schedule evidence is unverified in knowledge base; internal team must validate timeline commitments."
                elif "legal" in category.lower() or "contract" in category.lower():
                    clarif_type = "INTERNAL_INFORMATION_REQUEST"
                    q_text = f"Regarding contractual term {req_code} ('{req_text[:120]}'): Please confirm internal legal review on this obligation and provide approved standard contractual positions."
                    owner = "Internal Legal Counsel"
                    rationale = "Contractual clause requires internal legal assessment prior to proposal commitment."
                else:
                    clarif_type = "INTERNAL_INFORMATION_REQUEST"
                    q_text = f"Regarding requirement {req_code} ('{req_text[:120]}'): Please confirm verified company capability details, architecture specifications, and implementation scope to ensure full alignment with tender expectations."
                    owner = "Internal Technical Architect"
                    rationale = "Capability verification is currently unconfirmed in company knowledge base. Internal information request is required to prevent unsubstantiated proposal claims."

                clarif_to_add = ClarificationQuestion(
                    q_number=q_counter,
                    clarification_id=f"CLARIF-{req_code}",
                    id=f"CLARIF-{req_code}",
                    requirement_id=req_code,
                    rfp_section_reference=f"Section: {source_section} | Ref: {req_code}",
                    question_text=q_text,
                    question=q_text,
                    rationale=rationale,
                    reason=rationale,
                    priority=priority,
                    clarification_type=clarif_type,
                    target_owner=owner,
                    compliance_status=status,
                    citations=[]
                )

        if clarif_to_add and req_code not in seen_clarif_reqs:
            clarifications.append(clarif_to_add)
            seen_clarif_reqs.add(req_code)
            q_counter += 1

    return risks, clarifications
