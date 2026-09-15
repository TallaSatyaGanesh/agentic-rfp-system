import re
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import RFPProposalState
from app.agents.llm_factory import LLMFactory
from app.core.prompts import WRITER_AGENT_PROMPT
from app.models.schemas import (
    ProposalDraft,
    ProposalSection,
    RequirementResponse
)

logger = logging.getLogger(__name__)

# Unsupported commitment patterns on INFORMATION_REQUIRED or NON_COMPLIANT
UNSUPPORTED_COMMITMENT_PATTERNS = re.compile(
    r'\b(?:we\s+(?:guarantee|comply|certify|commit|provide|support|have\s+achieved|hold\s+(?:an?\s+)?(?:active\s+)?certification)|'
    r'(?:our\s+)?(?:company|platform|team|solution|vendor)\s+(?:is|are|holds?|has)?\s*(?:[\w-]+\s+){0,3}(?:certified|certification|compliant)|'
    r'platform\s+(?:fully\s+supports|guarantees|complies)|'
    r'is\s+(?:fully\s+)?(?:compliant|certified)|certified\s+(?:for|by|under|with)|'
    r'we\s+(?:are\s+certified|hold\s+(?:an?\s+)?[\w-]+\s+certification)|'
    r'we\s+will\s+(?:implement|deliver|ensure|support)|'
    r'company\s+(?:is\s+certified|holds\s+certification|supports|complies))\b',
    re.IGNORECASE
)

# Invented claims patterns: false customer references, years in business, pricing
INVENTED_CLAIMS_PATTERNS = re.compile(
    r'\b(?:over\s+\d+\s+years\s+of\s+experience|\d+\+\s+years\s+in\s+business|'
    r'trusted\s+by\s+(?:Fortune\s+500|leading\s+banks|global\s+enterprises)|'
    r'fixed\s+price\s+of\s+\$|discount\s+of\s+\d+%|'
    r'guaranteed\s+completion\s+in\s+\d+\s+days)\b',
    re.IGNORECASE
)


def write_proposal_node(state: RFPProposalState) -> Dict[str, Any]:
    """
    Agent 5: Proposal Writer Agent
    Transforms:
    - RFP metadata (Agent 1)
    - Classified requirements (Agent 2)
    - Compliance findings & company citations (Agent 3)
    - Risks & Clarification questions (Agent 4)
    - Reviewer critique directives (if in revision cycle)

    Produces:
    - Structured ProposalDraft containing requirement-by-requirement traceable responses (RequirementResponse)
    - Evidence-grounded proposal sections
    - Consolidated full markdown
    - Strict anti-hallucination guarantees (unverified items remain INFORMATION_REQUIRED, never invented)
    """
    metadata = state.get("metadata") or {}
    compliance_matrix = state.get("compliance_matrix", [])
    risks = state.get("risks", [])
    clarifications = state.get("clarification_questions", [])
    requirements = state.get("requirements", [])
    current_version = state.get("current_version", 0) + 1
    review_reports = state.get("review_reports", [])
    latest_review = review_reports[-1] if review_reports else None

    # Build lookup maps for fast correlation
    req_map: Dict[str, Dict[str, Any]] = {
        r.get("req_code", f"REQ-{idx}"): r
        for idx, r in enumerate(requirements)
    }
    comp_map: Dict[str, Dict[str, Any]] = {
        c.get("req_code", f"REQ-{idx}"): c
        for idx, c in enumerate(compliance_matrix)
    }
    risk_map: Dict[str, Dict[str, Any]] = {}
    for r in risks:
        code = r.get("requirement_id")
        if code and code not in risk_map:
            risk_map[code] = r

    clarif_map: Dict[str, Dict[str, Any]] = {}
    for cl in clarifications:
        code = cl.get("requirement_id")
        if code and code not in clarif_map:
            clarif_map[code] = cl

    llm = LLMFactory.get_chat_model()
    draft: ProposalDraft

    if llm and requirements:
        try:
            instructions = ""
            if latest_review and latest_review.get("actionable_revision_instructions"):
                instructions = "\nREVISION DIRECTIVES FROM RED TEAM REVIEWER:\n- " + "\n- ".join(
                    latest_review["actionable_revision_instructions"]
                )

            # Build concise structured prompt context
            req_summary = []
            for r_code, r_data in list(req_map.items())[:20]:
                c_data = comp_map.get(r_code, {})
                req_summary.append({
                    "requirement_id": r_code,
                    "text": r_data.get("text"),
                    "category": r_data.get("category"),
                    "is_mandatory": r_data.get("is_mandatory"),
                    "compliance_status": c_data.get("status", "INFORMATION_REQUIRED"),
                    "evidence_snippet": c_data.get("evidence_text"),
                    "company_source_doc": c_data.get("company_source_doc"),
                    "risk": risk_map.get(r_code, {}).get("title"),
                    "clarification": clarif_map.get(r_code, {}).get("question_text")
                })

            prompt = (
                f"RFP Metadata: {metadata}\n"
                f"Requirements & Compliance Matrix ({len(req_summary)} items):\n{req_summary}\n\n"
                f"Proposal Version: {current_version}\n"
                f"{instructions}\n\n"
                f"Author a formal, evidence-grounded proposal draft. For every requirement, formulate a structured "
                f"RequirementResponse adhering strictly to the compliance status (COMPLIANT_RESPONSE, PARTIAL_RESPONSE, "
                f"EXCEPTION_RESPONSE, or INFORMATION_REQUIRED_RESPONSE). Do NOT invent missing capabilities or certifications."
            )

            structured_writer = llm.with_structured_output(ProposalDraft)
            llm_draft: ProposalDraft = structured_writer.invoke([
                SystemMessage(content=WRITER_AGENT_PROMPT),
                HumanMessage(content=prompt)
            ])

            # Apply Programmatic Safety Guard
            draft = _apply_writer_programmatic_safety_guard(
                llm_draft=llm_draft,
                req_map=req_map,
                comp_map=comp_map,
                risk_map=risk_map,
                clarif_map=clarif_map,
                metadata=metadata,
                version=current_version
            )
        except Exception as e:
            print(f"[Agent 5: Writer] LLM generation failed or unavailable ({e}). Using deterministic template writer.")
            draft = _generate_proposal_draft(
                metadata=metadata,
                compliance_matrix=compliance_matrix,
                risks=risks,
                clarifications=clarifications,
                requirements=requirements,
                version=current_version,
                latest_review=latest_review
            )
    else:
        draft = _generate_proposal_draft(
            metadata=metadata,
            compliance_matrix=compliance_matrix,
            risks=risks,
            clarifications=clarifications,
            requirements=requirements,
            version=current_version,
            latest_review=latest_review
        )

    log_entry = {
        "agent": "Proposal Writer Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": f"Authored Proposal Draft v{current_version} with {len(draft.requirement_responses)} structured requirement responses and {len(draft.sections)} sections."
    }

    return {
        "proposal_drafts": state.get("proposal_drafts", []) + [draft.model_dump()],
        "current_version": current_version,
        "active_agent": "Proposal Writer Agent",
        "workflow_status": "REVIEWING",
        "logs": state.get("logs", []) + [log_entry]
    }


def _sanitize_response_text(
    text: str,
    status: str,
    evidence_text: Optional[str],
    notes: Optional[str],
    req_code: str
) -> str:
    """
    Sanitizes LLM response text according to compliance status:
    - For INFORMATION_REQUIRED: Cannot contain affirmative commitments or claims of certification/capability.
    - For NON_COMPLIANT: Cannot promise compliance or state that the platform supports the feature.
    - For PARTIALLY_COMPLIANT: Cannot omit the documented limitation.
    """
    if status == "INFORMATION_REQUIRED":
        if UNSUPPORTED_COMMITMENT_PATTERNS.search(text) or INVENTED_CLAIMS_PATTERNS.search(text):
            return (
                f"Information Required: Verification data for {req_code} is currently unconfirmed in available "
                f"company documentation. Internal confirmation and supporting collateral must be provided by the "
                f"internal bid/compliance team prior to proposal finalization."
            )
        # If text doesn't clearly mention information required / unconfirmed, ensure it is flagged
        if not re.search(r'\b(?:information\s+required|unconfirmed|requires?\s+confirmation|to\s+be\s+confirmed|verify)\b', text, re.IGNORECASE):
            return (
                f"Information Required: Verification data for {req_code} could not be verified from available "
                f"company collateral. Internal confirmation is required prior to submission."
            )

    elif status == "NON_COMPLIANT":
        if UNSUPPORTED_COMMITMENT_PATTERNS.search(text):
            limitation = evidence_text or notes or "documented out of scope"
            return (
                f"Exception / Scope Variance: The available company documentation indicates that requirement {req_code} "
                f"is not currently supported ({limitation}). Proposal treatment requires an approved exception or alternative approach."
            )

    elif status == "PARTIALLY_COMPLIANT":
        # Check if text falsely claims full compliance
        if re.search(r'\b(?:fully\s+compliant|fully\s+supports|complete\s+compliance|100%\s+compliant)\b', text, re.IGNORECASE):
            limitation = notes or evidence_text or "documented workaround / partial scope"
            return (
                f"Partial Compliance: The proposed solution supports the identified capability, but documented limitation applies: "
                f"'{limitation}'. Client confirmation is required regarding this limitation."
            )

    return text


# Proposal framing vocabulary (grammatical and structuring words allowed in paraphrasing)
PROPOSAL_FRAMING_TERMS = {
    "we", "our", "ours", "us", "the", "a", "an", "this", "that", "these", "those",
    "all", "each", "every", "any", "some", "such", "both", "either",
    "in", "on", "at", "to", "for", "with", "by", "from", "as", "into", "through",
    "during", "including", "regarding", "and", "or", "but", "while", "where",
    "about", "against", "between", "under", "above", "over", "within", "across",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "will", "shall", "can", "could", "would", "should", "must", "may",
    "provide", "provides", "provided", "providing", "provision",
    "support", "supports", "supported", "supporting",
    "deliver", "delivers", "delivered", "delivering", "delivery",
    "offer", "offers", "offered", "offering",
    "include", "includes", "included", "including",
    "ensure", "ensures", "ensured", "ensuring",
    "satisfy", "satisfies", "satisfied", "satisfying",
    "meet", "meets", "met", "meeting",
    "align", "aligns", "aligned", "aligning", "alignment",
    "comply", "complies", "complied", "complying", "compliance",
    "implement", "implements", "implemented", "implementing", "implementation",
    "solution", "solutions",
    "platform", "platforms",
    "system", "systems",
    "service", "services",
    "architecture", "architectures", "architectural",
    "capability", "capabilities",
    "feature", "features",
    "functionality", "functionalities",
    "requirement", "requirements",
    "specification", "specifications",
    "proposal", "proposals",
    "response", "responses",
    "organization", "company", "vendor", "bidder",
    "client", "customer", "authority",
    "based", "verified", "documented", "documentation", "collateral", "evidence",
    "specifically", "directly", "fully", "completely", "standard", "core",
    "available", "active", "current", "currently",
    "confirm", "confirms", "confirmed", "confirmation",
    "require", "requires", "required",
    "state", "states", "stated", "statement",
    "note", "notes", "noted",
    "scope", "approach", "framework",
    "tender", "project", "operational", "technical", "formal", "process"
}

# Critical technical capability concepts that cannot be introduced without evidence
CRITICAL_CAPABILITY_TERMS = {
    "disaster", "recovery", "replication", "failover", "geo-redundant", "multi-region",
    "cross-region", "quantum", "blockchain", "real-time", "microservices", "kubernetes",
    "biometric", "mainframe", "zero-trust", "pci-dss", "hipaa", "fedramp", "iso", "soc"
}


def _extract_substantive_tokens(text: str) -> Set[str]:
    """
    Extracts substantive words (filtering punctuation and proposal framing terms).
    """
    raw_tokens = re.findall(r'[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)?', text.lower())
    substantive = set()
    for tok in raw_tokens:
        tok_clean = tok.strip("-")
        if not tok_clean:
            continue
        if tok_clean.isdigit():
            substantive.add(tok_clean)
            continue
        if len(tok_clean) < 3:
            continue
        if tok_clean in PROPOSAL_FRAMING_TERMS:
            continue
        substantive.add(tok_clean)
    return substantive


def _is_token_grounded(token: str, evidence_text: str, req_text: str) -> bool:
    """
    Checks if a substantive token or metric from the proposal response
    is semantically grounded in the evidence text or the requirement prompt.
    Uses light stemming to allow natural grammatical paraphrasing.
    """
    combined_grounding = f"{evidence_text} {req_text}".lower()
    
    # Direct substring check
    if token in combined_grounding:
        return True
    
    # Hyphenated check (e.g., cross-region -> cross region)
    if "-" in token:
        parts = token.split("-")
        if all(p in combined_grounding for p in parts if len(p) >= 3):
            return True

    # Light stemming checks
    if token.endswith("ies") and (token[:-3] + "y") in combined_grounding:
        return True
    if token.endswith("es") and token[:-2] in combined_grounding:
        return True
    if token.endswith("s") and token[:-1] in combined_grounding:
        return True
    if token.endswith("ing") and token[:-3] in combined_grounding:
        return True
    if token.endswith("ed") and token[:-2] in combined_grounding:
        return True

    # Prefix stem matching for technical derivations (e.g. encrypt -> encryption, backup -> backups)
    if len(token) >= 5:
        stem = token[:5]
        if stem in combined_grounding:
            return True

    return False


def _validate_claim_evidence_grounding(
    response_text: str,
    status: str,
    evidence_text: Optional[str],
    notes: Optional[str],
    req_text: str,
    citations: List[Dict[str, Any]],
    company_source_doc: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Validates that factual claims in the response are grounded in the Agent 3 evidence.
    Returns (is_valid: bool, reason: str).
    """
    resp_lower = response_text.lower()
    ev_full = f"{evidence_text or ''} {notes or ''} {company_source_doc or ''}"
    for c in citations:
        ev_full += f" {c.get('snippet', '')} {c.get('document_title', '')}"
    ev_lower = ev_full.lower()
    req_lower = (req_text or "").lower()

    # --- 1. INFORMATION_REQUIRED VALIDATION ---
    if status == "INFORMATION_REQUIRED":
        # Must NOT make affirmative claims that company supports, provides, has achieved, or is certified
        if UNSUPPORTED_COMMITMENT_PATTERNS.search(response_text) or INVENTED_CLAIMS_PATTERNS.search(response_text):
            return False, "INFORMATION_REQUIRED response contains affirmative capability or certification commitment"
        
        # Must contain indication of unconfirmed status / internal verification needed
        has_info_marker = bool(re.search(
            r'\b(?:information\s+required|unconfirmed|requires?\s+(?:internal\s+)?confirmation|'
            r'pending\s+(?:verification|confirmation)|to\s+be\s+confirmed|confirmation\s+is\s+required)\b',
            response_text,
            re.IGNORECASE
        ))
        if not has_info_marker:
            return False, "INFORMATION_REQUIRED response lacks required unconfirmed/verification-needed statement"

        return True, "INFORMATION_REQUIRED response properly preserves uncertainty"

    # --- 2. NON_COMPLIANT VALIDATION ---
    if status == "NON_COMPLIANT":
        # Must NOT promise compliance, implementation, or support
        if re.search(r'\b(?:we\s+(?:will\s+implement|support|can\s+provide)|fully\s+compliant|meets\s+the\s+requirement)\b', response_text, re.IGNORECASE):
            return False, "NON_COMPLIANT response improperly claims support or promises implementation"
        
        # Must acknowledge limitation, exception, variance, or out-of-scope status
        has_exception_marker = bool(re.search(
            r'\b(?:exception|out\s+of\s+scope|variance|unsupported|not\s+(?:currently\s+)?supported|limitation)\b',
            response_text,
            re.IGNORECASE
        ))
        if not has_exception_marker:
            return False, "NON_COMPLIANT response fails to state exception or unsupported status"

        return True, "NON_COMPLIANT response properly states exception"

    # --- 3. PARTIALLY_COMPLIANT VALIDATION ---
    if status == "PARTIALLY_COMPLIANT":
        # Must NOT claim full compliance
        if re.search(r'\b(?:fully\s+compliant|complete\s+(?:24/7|support|compliance)|100%\s+compliant)\b', response_text, re.IGNORECASE):
            return False, "PARTIALLY_COMPLIANT response improperly claims complete or full compliance"
        
        # Must preserve limitation language from evidence / notes if present
        if re.search(r'\b(?:business\s+hours|office\s+hours|standard\s+hours)\b', ev_lower):
            if not re.search(r'\b(?:business\s+hours|office\s+hours|standard\s+hours)\b', resp_lower):
                return False, "PARTIALLY_COMPLIANT response omits documented business hours limitation"

        has_partial_marker = bool(re.search(
            r'\b(?:partial|partially|limitation|workaround|conditional|restricted|specific\s+hours)\b',
            response_text,
            re.IGNORECASE
        ))
        if not has_partial_marker:
            return False, "PARTIALLY_COMPLIANT response fails to indicate partial support or workaround"

        return True, "PARTIALLY_COMPLIANT response preserves partial scope and limitation"

    # --- 4. COMPLIANT VALIDATION ---
    if status == "COMPLIANT":
        # If no evidence was provided, cannot be valid COMPLIANT response
        if not ev_lower.strip():
            return False, "COMPLIANT response lacks underlying evidence"

        # Check for ungrounded SLA / metric claims (e.g. 24/7, 15 minutes, 99.999%) - MUST be in company evidence
        sla_matches = re.findall(r'\b(?:24/7|24x7|\d+(?:\.\d+)?%|\d+\s*(?:minutes?|hours?|days?))\b', response_text, re.IGNORECASE)
        for sla in sla_matches:
            sla_clean = sla.lower()
            if sla_clean not in ev_lower:
                return False, f"Response introduces ungrounded SLA or metric claim: '{sla}' not found in company evidence"

        # Extract substantive capability tokens
        substantive_tokens = _extract_substantive_tokens(response_text)
        if not substantive_tokens:
            return True, "No substantive terms to validate"

        # Check for critical capability terms - MUST be in company evidence
        for tok in substantive_tokens:
            if tok in CRITICAL_CAPABILITY_TERMS:
                if not _is_token_grounded(tok, ev_lower, ""):
                    return False, f"Response introduces ungrounded critical technical capability: '{tok}' not found in company evidence"

        ungrounded_tokens = []
        for tok in substantive_tokens:
            if not _is_token_grounded(tok, ev_lower, req_lower):
                ungrounded_tokens.append(tok)

        # If more than 35% of substantive tokens are completely absent from evidence and requirement:
        ungrounded_ratio = len(ungrounded_tokens) / len(substantive_tokens)
        if ungrounded_ratio > 0.35 and len(ungrounded_tokens) >= 2:
            return False, f"Response contains ungrounded claims: {', '.join(ungrounded_tokens[:3])}"

        return True, "COMPLIANT response is semantically grounded in evidence"

    return True, "Status validated"


def _build_safe_requirement_response(
    req: Dict[str, Any],
    comp: Dict[str, Any],
    risk: Optional[Dict[str, Any]],
    clarif: Optional[Dict[str, Any]]
) -> RequirementResponse:
    """
    Builds a deterministic, evidence-grounded RequirementResponse for a single requirement.
    """
    req_code = req.get("req_code", "REQ-GEN")
    req_text = req.get("text", "")
    category = req.get("category", "General")
    is_mandatory = req.get("is_mandatory", False)
    status = comp.get("status", "INFORMATION_REQUIRED")
    evidence_text = comp.get("evidence_text")
    notes = comp.get("notes", "")
    source_doc = comp.get("company_source_doc")
    source_page = req.get("source_page")
    source_section = req.get("source_section")
    citations = comp.get("citations", [])

    risk_summary = None
    if risk:
        risk_summary = f"[{risk.get('severity', 'HIGH')} Risk]: {risk.get('title') or risk.get('description', '')[:100]}"

    clarif_note = None
    if clarif:
        clarif_note = clarif.get("question_text") or clarif.get("question")

    if status == "COMPLIANT":
        resp_type = "COMPLIANT_RESPONSE"
        summary_ev = evidence_text if evidence_text else (notes if notes else "Confirmed in company collateral.")
        response_text = (
            f"The proposed solution fully supports this requirement based on verified company documentation. "
            f"Specifically: {summary_ev} "
            f"[Company: {source_doc or 'Verified Collateral'}]"
        )
    elif status == "PARTIALLY_COMPLIANT":
        resp_type = "PARTIAL_RESPONSE"
        limitation = notes if notes else (evidence_text if evidence_text else "documented workaround")
        response_text = (
            f"Partial Compliance: The proposed solution supports the identifiable capability within standard scope. "
            f"Documented limitation / workaround: '{limitation}'. "
            f"Confirmation is requested regarding client acceptance of this technical approach."
        )
    elif status == "NON_COMPLIANT":
        resp_type = "EXCEPTION_RESPONSE"
        limitation = evidence_text if evidence_text else (notes if notes else "Out of scope")
        response_text = (
            f"Exception / Scope Variance: The available company documentation indicates that requirement {req_code} "
            f"is not currently supported ({limitation}). Proposal treatment requires an approved exception or alternative technical approach."
        )
    else:  # INFORMATION_REQUIRED
        resp_type = "INFORMATION_REQUIRED_RESPONSE"
        response_text = (
            f"Information Required: Verification data for {req_code} is currently unconfirmed in available company documentation. "
            f"Internal confirmation and supporting collateral (e.g. valid certificate or architecture specification) must be provided "
            f"by the internal bid/compliance team prior to final submission."
        )

    return RequirementResponse(
        requirement_id=req_code,
        requirement_text=req_text,
        category=category,
        is_mandatory=is_mandatory,
        compliance_status=status,
        response_type=resp_type,
        response=response_text,
        company_doc_id=comp.get("company_doc_id"),
        chunk_id=comp.get("chunk_id"),
        source_page=source_page,
        source_section=source_section,
        evidence_snippet=evidence_text,
        citations=citations,
        assumptions=[],
        clarification_required=clarif_note,
        risk_summary=risk_summary
    )


def _apply_writer_programmatic_safety_guard(
    llm_draft: ProposalDraft,
    req_map: Dict[str, Dict[str, Any]],
    comp_map: Dict[str, Dict[str, Any]],
    risk_map: Dict[str, Dict[str, Any]],
    clarif_map: Dict[str, Dict[str, Any]],
    metadata: Dict[str, Any],
    version: int
) -> ProposalDraft:
    """
    Enforces programmatic safety checks on the proposal draft:
    1. Requirement ID Whitelist: Rejects responses for hallucinated/orphan requirement IDs.
    2. Compliance Status Immutability: Enforces exact status from Agent 3; prevents conversion to COMPLIANT.
    3. Response Type Enforcement: Forces COMPLIANT_RESPONSE, PARTIAL_RESPONSE, EXCEPTION_RESPONSE, INFORMATION_REQUIRED_RESPONSE.
    4. Unsupported Commitment Scrubbing: Sanitizes affirmative claims on unverified or unsupported items.
    5. Source Provenance Injection: Injects genuine company citations, doc IDs, and RFP page/sections.
    6. Completeness Guarantee: If LLM omitted any requirement, generates safe deterministic response for it.
    """
    valid_req_ids = set(req_map.keys())
    validated_responses: List[RequirementResponse] = []
    seen_req_ids: Set[str] = set()

    for resp in llm_draft.requirement_responses:
        req_id = resp.requirement_id
        # Reject hallucinated requirement ID
        if req_id not in valid_req_ids:
            matches = [vid for vid in valid_req_ids if vid in str(req_id)]
            if matches:
                req_id = matches[0]
            else:
                continue  # Discard orphan requirement response

        if req_id in seen_req_ids:
            continue
        seen_req_ids.add(req_id)

        req = req_map[req_id]
        comp = comp_map.get(req_id, {})
        risk = risk_map.get(req_id)
        clarif = clarif_map.get(req_id)

        # IMMUTABLE COMPLIANCE STATUS: Never allow LLM to change status from Agent 3
        true_status = comp.get("status", "INFORMATION_REQUIRED")
        
        # Enforce response_type matching compliance status
        if true_status == "COMPLIANT":
            expected_type = "COMPLIANT_RESPONSE"
        elif true_status == "PARTIALLY_COMPLIANT":
            expected_type = "PARTIAL_RESPONSE"
        elif true_status == "NON_COMPLIANT":
            expected_type = "EXCEPTION_RESPONSE"
        else:
            expected_type = "INFORMATION_REQUIRED_RESPONSE"

        # Sanitize response text
        sanitized_text = _sanitize_response_text(
            text=resp.response,
            status=true_status,
            evidence_text=comp.get("evidence_text"),
            notes=comp.get("notes"),
            req_code=req_id
        )

        # Factual claim evidence grounding check
        is_grounded, grounding_reason = _validate_claim_evidence_grounding(
            response_text=sanitized_text,
            status=true_status,
            evidence_text=comp.get("evidence_text"),
            notes=comp.get("notes"),
            req_text=req.get("text", resp.requirement_text or ""),
            citations=comp.get("citations", []),
            company_source_doc=comp.get("company_source_doc")
        )
        assumptions = resp.assumptions or []
        if not is_grounded:
            logger.warning(
                f"[WriterSafety] Response for {req_id} failed factual claim grounding check: {grounding_reason}. "
                f"Replacing with deterministic evidence-grounded response."
            )
            safe_resp = _build_safe_requirement_response(req, comp, risk, clarif)
            sanitized_text = safe_resp.response
            assumptions = []

        risk_summary = resp.risk_summary or (f"[{risk.get('severity', 'HIGH')} Risk]: {risk.get('title')}" if risk else None)
        clarif_required = resp.clarification_required or (clarif.get("question_text") or clarif.get("question") if clarif else None)

        validated_responses.append(
            RequirementResponse(
                requirement_id=req_id,
                requirement_text=req.get("text", resp.requirement_text),
                category=req.get("category", resp.category),
                is_mandatory=req.get("is_mandatory", resp.is_mandatory),
                compliance_status=true_status,
                response_type=expected_type,
                response=sanitized_text,
                company_doc_id=comp.get("company_doc_id"),
                chunk_id=comp.get("chunk_id"),
                source_page=req.get("source_page"),
                source_section=req.get("source_section"),
                evidence_snippet=comp.get("evidence_text"),
                citations=comp.get("citations", []),
                assumptions=assumptions,
                clarification_required=clarif_required,
                risk_summary=risk_summary
            )
        )

    # Check for missing requirements (ensure 100% coverage)
    for req_id, req in req_map.items():
        if req_id not in seen_req_ids:
            comp = comp_map.get(req_id, {})
            risk = risk_map.get(req_id)
            clarif = clarif_map.get(req_id)
            safe_resp = _build_safe_requirement_response(req, comp, risk, clarif)
            validated_responses.append(safe_resp)
            seen_req_ids.add(req_id)

    # Sort responses by requirement_id for deterministic order
    validated_responses.sort(key=lambda r: r.requirement_id)

    # Reconstruct sections and full_markdown
    sections, full_markdown = _build_sections_and_markdown(
        metadata=metadata,
        version=version,
        requirement_responses=validated_responses,
        comp_map=comp_map,
        risks=list(risk_map.values()),
        clarifications=list(clarif_map.values())
    )

    return ProposalDraft(
        version=version,
        title=llm_draft.title or f"Proposal Response: {metadata.get('title', 'Enterprise Tender')} (v{version})",
        executive_summary=llm_draft.executive_summary or (sections[0].content_markdown if sections else ""),
        sections=sections,
        full_markdown=full_markdown,
        requirement_responses=validated_responses
    )


def _build_sections_and_markdown(
    metadata: Dict[str, Any],
    version: int,
    requirement_responses: List[RequirementResponse],
    comp_map: Dict[str, Dict[str, Any]],
    risks: List[Dict[str, Any]],
    clarifications: List[Dict[str, Any]]
) -> Tuple[List[ProposalSection], str]:
    """
    Builds the 5 formal proposal sections and the complete full_markdown.
    """
    title = metadata.get("title", "Enterprise RFP Proposal Response")
    issuer = metadata.get("issuer", "Valued Client")

    # 1. Executive Summary
    sec1_md = (
        f"### Executive Summary & Value Proposition\n"
        f"Our organization is pleased to submit this formal proposal in response to **{title}** issued by **{issuer}**.\n\n"
        f"Our response is grounded directly in verified corporate capabilities, technical specifications, and architectural documentation. "
        f"We provide a comprehensive, transparent compliance mapping against all tender requirements.\n\n"
        f"**Key Tenets of Our Response:**\n"
        f"- **Rigorous Evidence Grounding:** All affirmative claims are corroborated with documented corporate collateral.\n"
        f"- **Transparent Scope Boundaries:** Any partial support, custom integration requirements, or scope exceptions are explicitly disclosed.\n"
        f"- **Traceable Verification:** Outstanding information items are formally cataloged with internal verification action items prior to contract finalization.\n"
    )

    # 2. Requirement-by-Requirement Technical & Compliance Responses
    sec2_md = "### Requirement-by-Requirement Technical & Compliance Responses\n\n"
    for r in requirement_responses:
        p_str = f"p. {r.source_page}" if r.source_page else "General"
        s_str = f"§ {r.source_section}" if r.source_section else "Scope"
        sec2_md += f"#### [{r.requirement_id}] {r.category} ({r.compliance_status})\n"
        sec2_md += f"> **RFP Specification [{p_str}, {s_str}]:** \"{r.requirement_text}\"\n\n"
        sec2_md += f"- **Compliance Verdict:** `{r.compliance_status}`\n"
        sec2_md += f"- **Response Classification:** `{r.response_type}`\n"
        sec2_md += f"- **Proposal Statement:** {r.response}\n"

        if r.compliance_status == "INFORMATION_REQUIRED":
            alert_text = r.clarification_required or "Internal confirmation and collateral documentation required from capability owner."
            sec2_md += f"\n> **[INFORMATION REQUIRED]**: For {r.requirement_id}, verification collateral is pending. {alert_text}\n"

        if r.citations:
            cit_snippets = "; ".join([c.get("document_title", c.get("company_doc_id", "Collateral")) for c in r.citations[:2]])
            sec2_md += f"\n*Verified Source Provenance:* `[Company: {cit_snippets}]`\n"
        elif r.company_doc_id:
            sec2_md += f"\n*Verified Source Provenance:* `[Company Doc ID: {r.company_doc_id}]`\n"

        if r.risk_summary:
            sec2_md += f"- **Risk Assessment:** {r.risk_summary}\n"

        sec2_md += "\n---\n\n"

    # 3. Compliance Matrix & Exception Register
    sec3_md = (
        "### Requirement Compliance Matrix & Exception Register\n\n"
        "| Requirement ID | Category | Mandatory | Compliance Verdict | Response Classification |\n"
        "|---|---|---|---|---|\n"
    )
    for r in requirement_responses:
        mand = "Yes" if r.is_mandatory else "No"
        sec3_md += f"| {r.requirement_id} | {r.category} | {mand} | **{r.compliance_status}** | {r.response_type} |\n"

    exceptions = [r for r in requirement_responses if r.compliance_status in ["NON_COMPLIANT", "PARTIALLY_COMPLIANT"]]
    if exceptions:
        sec3_md += "\n\n#### Documented Exceptions and Scope Variances\n"
        for ex in exceptions:
            sec3_md += f"- **[{ex.requirement_id}] {ex.compliance_status}:** {ex.response}\n"

    # 4. Information Required & Action Items
    info_items = [r for r in requirement_responses if r.compliance_status == "INFORMATION_REQUIRED"]
    sec4_md = "### Information Required & Internal Verification Register\n\n"
    if info_items:
        sec4_md += "The following requirements require verification collateral or internal SME confirmation before final contract award:\n\n"
        for item in info_items:
            sec4_md += (
                f"> **[INFORMATION REQUIRED]**: **{item.requirement_id}** ({item.category})\n"
                f"> - *Clause:* \"{item.requirement_text}\"\n"
                f"> - *Required Action:* {item.clarification_required or 'Attach verified certificate or engineering proof.'}\n\n"
            )
    else:
        sec4_md += "All tender requirements have been verified against available company collateral.\n"

    # 5. Risk Mitigation & Clarification Strategy
    sec5_md = "### Risk Mitigation & Clarification Strategy\n\n"
    if risks:
        sec5_md += "#### Key Tender Risks Identified\n"
        for rk in risks[:5]:
            sec5_md += f"- **[{rk.get('severity', 'MEDIUM')} Severity - {rk.get('category', 'General')}]:** {rk.get('title') or rk.get('description', '')[:120]}\n  *Mitigation:* {rk.get('mitigation_strategy', 'Consult legal and technical leads.')}\n"

    if clarifications:
        sec5_md += "\n#### Outstanding Clarification Requests\n"
        for cl in clarifications[:5]:
            q_text = cl.get("question_text") or cl.get("question") or ""
            sec5_md += f"- **[{cl.get('clarification_type', 'CLARIFICATION')} - {cl.get('target_owner', 'Bid Team')}]:** {q_text}\n"

    sections = [
        ProposalSection(section_title="1. Executive Summary & Value Proposition", content_markdown=sec1_md),
        ProposalSection(section_title="2. Requirement-by-Requirement Technical & Compliance Responses", content_markdown=sec2_md),
        ProposalSection(section_title="3. Requirement Compliance Matrix & Exception Register", content_markdown=sec3_md),
        ProposalSection(section_title="4. Information Required & Internal Verification Register", content_markdown=sec4_md),
        ProposalSection(section_title="5. Risk Mitigation & Clarification Strategy", content_markdown=sec5_md)
    ]

    revision_header = f"> *Proposal Draft Version {version} - Revision Incorporating Red Team Critique*\n\n" if version > 1 else ""
    full_markdown = revision_header + "\n\n---\n\n".join([f"## {s.section_title}\n\n{s.content_markdown}" for s in sections])

    return sections, full_markdown


def _generate_proposal_draft(
    metadata: Dict[str, Any],
    compliance_matrix: List[Dict[str, Any]],
    risks: List[Dict[str, Any]],
    clarifications: List[Dict[str, Any]],
    requirements: List[Dict[str, Any]],
    version: int,
    latest_review: Optional[Dict[str, Any]] = None
) -> ProposalDraft:
    """
    Deterministic rule-based proposal writer fallback.
    Generates 100% evidence-grounded RequirementResponse objects and proposal sections
    with zero external hallucinations.
    """
    comp_map = {c.get("req_code", f"REQ-{i}"): c for i, c in enumerate(compliance_matrix)}
    risk_map = {r.get("requirement_id"): r for r in risks if r.get("requirement_id")}
    clarif_map = {cl.get("requirement_id"): cl for cl in clarifications if cl.get("requirement_id")}

    requirement_responses: List[RequirementResponse] = []
    for idx, req in enumerate(requirements):
        req_code = req.get("req_code", f"REQ-{idx}")
        comp = comp_map.get(req_code, {})
        risk = risk_map.get(req_code)
        clarif = clarif_map.get(req_code)

        resp = _build_safe_requirement_response(
            req=req,
            comp=comp,
            risk=risk,
            clarif=clarif
        )
        requirement_responses.append(resp)

    # Sort responses by requirement_id
    requirement_responses.sort(key=lambda r: r.requirement_id)

    sections, full_markdown = _build_sections_and_markdown(
        metadata=metadata,
        version=version,
        requirement_responses=requirement_responses,
        comp_map=comp_map,
        risks=risks,
        clarifications=clarifications
    )

    title = metadata.get("title", "Enterprise RFP Proposal Response")
    return ProposalDraft(
        version=version,
        title=f"Proposal Response: {title} (v{version})",
        executive_summary=sections[0].content_markdown,
        sections=sections,
        full_markdown=full_markdown,
        requirement_responses=requirement_responses
    )
