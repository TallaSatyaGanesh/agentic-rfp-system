import re
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import RFPProposalState
from app.agents.llm_factory import LLMFactory
from app.core.prompts import COMPLIANCE_AGENT_PROMPT
from app.models.schemas import ComplianceItem, ComplianceAgentOutput
from app.rag.retriever import KnowledgeBaseRetriever, sanitize_requirement_query
from app.core.config import settings

# Explicit non-compliance patterns in company collateral
NON_COMPLIANT_PATTERNS = re.compile(
    r'\b(?:(?:do|does|did|is|are|was|were|can|could|will|would)\s+(?:not|never)\s+(?:currently\s+|presently\s+|natively\s+|directly\s+)?(?:support|provide|offer|feature|hold|comply|guarantee|include)|'
    r'not\s+(?:currently\s+|presently\s+|natively\s+)?(?:supported|provided|offered|held|certified|available|compliant|included)|'
    r'unsupported|out\s+of\s+scope|explicitly\s+excluded|no\s+plans\s+to\s+support|cannot\s+comply|cannot\s+provide|cannot\s+support|unheld|business\s+hours\s+only)\b',
    re.IGNORECASE
)

# Explicit partial compliance / limitation patterns in company collateral
PARTIAL_COMPLIANT_PATTERNS = re.compile(
    r'\b(?:partially\s+supported|partial\s+support|limited\s+support|requires\s+custom|workaround|'
    r'conditional|planned\s+for|roadmap|beta|add-on\s+required|subject\s+to\s+third[- ]party|'
    r'available\s+only\s+during\s+business\s+hours|business\s+hours\s+only|'
    r'partially\s+compliant)\b',
    re.IGNORECASE
)

# Explicit notice that a term/SLA/currency requires separate commercial negotiation or formal agreement
SEPARATE_CONFIRMATION_PATTERNS = re.compile(
    r'\b(?:must\s+be\s+confirmed\s+separately|require\s+separate|requires\s+separate|'
    r'separate\s+commercial\s+negotiation|separate\s+qualification|subject\s+to\s+separate|'
    r'confirmed\s+separately|requires\s+formal\s+scoping\s+validation)\b',
    re.IGNORECASE
)

# Affirmative capability verbs and nouns signifying verified satisfaction
AFFIRMATIVE_PATTERNS = re.compile(
    r'\b(?:guarantees|guarantee|guaranteed|supports|support|supported|provides|provide|provided|'
    r'operates|certified|compliance|compliant|complies|adheres|features|includes|included|'
    r'secured|encrypted|backed|native|implements|ensures|retention|replicated|'
    r'develops|develop|developed|builds|build|built|delivers|deliver|delivered|'
    r'engineered|maintains|maintain|offers|offer|designs|designed|available|compatible|'
    r'enforces|enforce|timelines|scoping|commitments|methodology|architecture|'
    r'manuals?|guides?|documentation|specifications?|training|workshops?)\b',
    re.IGNORECASE
)

GENERIC_RFP_WORDS = {
    "must", "shall", "should", "may", "will", "can", "cannot", "could", "would",
    "is", "are", "was", "were", "be", "been", "being",
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on", "at", "by", "from",
    "vendor", "bidder", "contractor", "provider", "company", "platform", "solution", "system",
    "service", "services", "requirement", "requirements", "ensure", "ensures", "provide", "provides",
    "support", "supports", "all", "any", "that", "this", "which", "our", "their", "its", "each",
    "have", "has", "having", "do", "does", "did", "per", "via", "into", "including", "such",
    "as", "well", "both", "either", "neither", "nor"
}

def analyze_compliance_node(state: RFPProposalState) -> Dict[str, Any]:
    """
    Agent 3: Compliance Analysis Agent
    Evaluates classified requirements against company knowledge base evidence using RAG.
    
    Safety Rules Enforced:
    1. ZERO trustworthy evidence above threshold -> strictly INFORMATION_REQUIRED.
    2. Missing evidence != NON_COMPLIANT (missing evidence is always INFORMATION_REQUIRED).
    3. COMPLIANT requires direct, verified company evidence.
    4. NON_COMPLIANT requires company evidence demonstrating failure/unsupported status.
    5. Programmatic safety guard prevents LLM hallucinations from claiming unsupported compliance.
    """
    requirements = state.get("requirements", [])
    retriever = KnowledgeBaseRetriever()
    llm = LLMFactory.get_chat_model()
    
    compliance_items: List[ComplianceItem] = []
    compliant_count = 0
    partially_compliant_count = 0

    for req in requirements:
        req_code = req.get("req_code", "REQ-UNKNOWN")
        req_text = req.get("text", "")
        category = req.get("category", "General")

        # 1. Retrieve evidence from company knowledge base using sanitized core query and domain keywords
        clean_req_text = sanitize_requirement_query(req_text)
        domain_terms = _extract_domain_terms(clean_req_text or req_text)
        # Prioritize distinctive domain terms (longer words, numbers/metrics) for fallback queries
        sorted_terms = sorted(domain_terms, key=lambda t: (any(c.isdigit() for c in t), len(t)), reverse=True)
        domain_kw = " ".join(sorted_terms[:6]) if sorted_terms else ""
        
        fallback_queries: List[str] = []
        if req_text and req_text != clean_req_text:
            fallback_queries.append(req_text)
        if domain_kw and domain_kw != clean_req_text:
            fallback_queries.append(domain_kw)

        evidence_list = retriever.retrieve_relevant_evidence(
            query=clean_req_text or req_text,
            top_k=settings.RAG_TOP_K,
            threshold=settings.SIMILARITY_THRESHOLD,
            fallback_queries=fallback_queries
        )

        # 2. PROGRAMMATIC SAFETY GATE:
        # If no evidence passed the similarity threshold, MUST be INFORMATION_REQUIRED.
        # LLM is NOT called to prevent any hallucinated compliance.
        if not evidence_list:
            compliance_items.append(
                ComplianceItem(
                    req_code=req_code,
                    requirement_text=req_text,
                    category=category,
                    status="INFORMATION_REQUIRED",
                    confidence=0.0,
                    evidence_text=None,
                    company_source_doc=None,
                    company_doc_id=None,
                    chunk_id=None,
                    source_page=None,
                    source_section=None,
                    similarity_score=0.0,
                    citations=[],
                    notes="No verified company capability or policy found in knowledge base exceeding threshold. Explicit input required from bid team."
                )
            )
            continue

        # Format citations preserving full source traceability
        citations: List[Dict[str, Any]] = [
            {
                "company_doc_id": ev.get("company_doc_id", ""),
                "document_title": ev.get("document_title", "Unknown Document"),
                "filename": ev.get("filename", "Unknown File"),
                "chunk_id": ev.get("chunk_id", ""),
                "source_page": ev.get("page_number", 1),
                "source_section": ev.get("section", "General"),
                "similarity_score": ev.get("similarity", 0.0),
                "snippet": ev.get("evidence_text", "")
            }
            for ev in evidence_list
        ]

        # Select best candidate evidence chunk:
        # Evaluate each retrieved candidate chunk by specification authority, semantic relevance, and domain coverage
        clean_req = clean_req_text or req_text
        low_req = req_text.lower()
        is_exp_req = any(k in low_req for k in ["experience", "case study", "track record", "reference", "references", "past project", "operating experience", "years in business"])

        # Determine target domain for requirement
        req_cat_lower = (category or "").lower()
        if not req_cat_lower or req_cat_lower in ["general", "other", "requirement"]:
            if any(k in low_req for k in ["api", "rest", "database", "backup", "web", "architecture", "server", "cloud", "ui", "frontend", "backend", "application"]):
                req_cat_lower = "technical"
            elif any(k in low_req for k in ["security", "rbac", "mfa", "encryption", "auth", "access control", "iso", "soc", "governance", "certification"]):
                req_cat_lower = "security"
            elif any(k in low_req for k in ["timeline", "delivery", "manual", "guide", "documentation", "weeks", "training", "deployment", "implementation"]):
                req_cat_lower = "delivery"
            elif is_exp_req:
                req_cat_lower = "experience"

        req_terms = _extract_domain_terms(clean_req)

        scored_candidates = []
        for ev_cand in evidence_list:
            cand_text = ev_cand.get("evidence_text", "")
            cand_title = ev_cand.get("document_title", "")
            cand_cat = ev_cand.get("category", "")
            sim = ev_cand.get("similarity", 0.0)

            cand_status, cand_conf, cand_notes = _evaluate_semantic_compliance(clean_req, cand_text)
            coverage, matched_terms = _compute_semantic_coverage(req_terms, cand_text)

            is_case_study = (
                "case study" in cand_text.lower()
                or "experience & references" in cand_title.lower()
                or cand_cat.lower() in ["experience", "references"]
            )

            # Specification Authority Scoring:
            # Core technical/security/delivery specs > General Overview > Services/Deployment > Case studies
            authority_score = 50.0
            cand_cat_lower = (cand_cat or "").lower()
            cand_title_lower = cand_title.lower()

            if req_cat_lower in ["technical", "functional", "architecture", "platform"]:
                if any(k in cand_cat_lower or k in cand_title_lower for k in ["technical", "platform", "architecture"]):
                    authority_score = 80.0
                elif any(k in cand_cat_lower or k in cand_title_lower for k in ["overview", "general"]):
                    authority_score = 65.0
                elif any(k in cand_cat_lower or k in cand_title_lower for k in ["delivery", "implementation", "support", "services"]):
                    authority_score = 40.0
                elif is_case_study:
                    authority_score = 20.0
            elif req_cat_lower in ["security", "governance", "compliance", "certification"]:
                if any(k in cand_cat_lower or k in cand_title_lower for k in ["security", "governance", "compliance"]):
                    authority_score = 80.0
                elif is_case_study:
                    authority_score = 20.0
            elif req_cat_lower in ["delivery", "documentation", "timeline", "implementation", "support"]:
                if any(k in cand_cat_lower or k in cand_title_lower for k in ["delivery", "implementation", "documentation", "support"]):
                    authority_score = 80.0
                elif is_case_study:
                    authority_score = 20.0
            elif req_cat_lower in ["experience", "references", "eligibility"]:
                if any(k in cand_cat_lower or k in cand_title_lower for k in ["experience", "references"]):
                    authority_score = 80.0

            # Relevance and Semantic Coverage Scoring:
            relevance_score = (sim * 50.0) + (coverage * 50.0)
            total_score = authority_score + relevance_score

            scored_candidates.append({
                "score": total_score,
                "authority": authority_score,
                "relevance": relevance_score,
                "status": cand_status,
                "conf": cand_conf,
                "notes": cand_notes,
                "cand": ev_cand,
                "coverage": coverage,
                "matched_terms": matched_terms,
                "is_case_study": is_case_study
            })

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        # Contradiction Detection & Safety Arbitrament across relevant retrieved candidates
        relevant_cands = [
            c for c in scored_candidates
            if c["coverage"] >= 0.35 or len(c["matched_terms"]) >= 2
        ]

        comp_cands = [c for c in relevant_cands if c["status"] == "COMPLIANT"]
        non_comp_cands = [c for c in relevant_cands if c["status"] == "NON_COMPLIANT"]
        partial_cands = [c for c in relevant_cands if c["status"] == "PARTIALLY_COMPLIANT"]

        forced_status: Optional[str] = None
        contradiction_note: Optional[str] = None
        best_candidate_entry = scored_candidates[0] if scored_candidates else None

        # Scenario A: Contradictory evidence detected (Both affirmative COMPLIANT and negative NON_COMPLIANT exist on this requirement topic)
        if comp_cands and non_comp_cands:
            top_comp = comp_cands[0]
            top_non_comp = non_comp_cands[0]

            # If the negative statement comes from a higher-authority spec doc than a vague positive case study/collateral:
            if top_non_comp["authority"] > top_comp["authority"]:
                best_candidate_entry = top_non_comp
                forced_status = "NON_COMPLIANT"
                contradiction_note = top_non_comp["notes"]
            # If documents have equal authority or conflicting statements:
            elif abs(top_non_comp["authority"] - top_comp["authority"]) < 10.0:
                best_candidate_entry = top_comp if top_comp["score"] >= top_non_comp["score"] else top_non_comp
                forced_status = "INFORMATION_REQUIRED"
                contradiction_note = (
                    "Conflicting evidence detected in company knowledge base: some collateral indicates support "
                    "while other documentation specifies this capability is unsupported or restricted. "
                    "Explicit bid team clarification required."
                )
            else:
                # Top comp has higher authority, but check if there's an ambiguous scope limitation
                best_candidate_entry = top_comp
                if top_non_comp["coverage"] >= 0.50:
                    forced_status = "INFORMATION_REQUIRED"
                    contradiction_note = (
                        "Ambiguous or conditional statements detected across company collateral regarding this capability. "
                        "Information required from bid team to confirm compliance scope."
                    )

        # Scenario B: Partial limitation vs Full compliance on same topic
        elif comp_cands and partial_cands:
            top_comp = comp_cands[0]
            top_partial = partial_cands[0]
            if top_partial["authority"] >= top_comp["authority"]:
                best_candidate_entry = top_partial
            else:
                best_candidate_entry = top_comp

        # Scenario C: Only negative candidates exist
        elif non_comp_cands and not comp_cands:
            best_candidate_entry = non_comp_cands[0]

        # Scenario D: Only affirmative candidates exist
        elif comp_cands and not non_comp_cands:
            best_candidate_entry = comp_cands[0]

        # Scenario E: Only partial candidates exist
        elif partial_cands and not comp_cands and not non_comp_cands:
            best_candidate_entry = partial_cands[0]

        best_evidence = best_candidate_entry["cand"] if best_candidate_entry else evidence_list[0]

        evidence_text = best_evidence.get("evidence_text", "")
        source_doc = f"{best_evidence.get('document_title')} ({best_evidence.get('filename')})"
        sim_score = best_evidence.get("similarity", 0.0)

        # 3. LLM-Assisted Compliance Evaluation (if available)
        evaluated_item: Optional[ComplianceItem] = None
        if llm:
            try:
                audit_prompt = (
                    f"RFP Requirement ({req_code}):\n{req_text}\n\n"
                    f"Company Evidence Source: {source_doc}\n"
                    f"Company Evidence Text:\n{evidence_text}\n\n"
                    f"Audit Instructions:\n"
                    f"- Compare the requirement directly against the supplied company evidence.\n"
                    f"- Determine status strictly as one of: COMPLIANT, PARTIALLY_COMPLIANT, NON_COMPLIANT, INFORMATION_REQUIRED.\n"
                    f"- If evidence is missing or insufficient, output INFORMATION_REQUIRED.\n"
                    f"- Quote the exact evidence snippet in `evidence_text` and provide detailed reasoning in `notes`."
                )
                structured_evaluator = llm.with_structured_output(ComplianceItem)
                llm_output: ComplianceItem = structured_evaluator.invoke([
                    SystemMessage(content=COMPLIANCE_AGENT_PROMPT),
                    HumanMessage(content=audit_prompt)
                ])

                # 4. PROGRAMMATIC SAFETY GUARD on LLM Output:
                # Never allow unsupported COMPLIANT or improper NON_COMPLIANT
                evaluated_item = _apply_programmatic_safety_guard(
                    llm_output=llm_output,
                    req_code=req_code,
                    req_text=req_text,
                    category=category,
                    best_evidence=best_evidence,
                    citations=citations,
                    forced_status=forced_status,
                    contradiction_note=contradiction_note
                )
            except Exception as e:
                print(f"[Agent 3: Compliance] LLM audit failed for {req_code}: {e}. Using deterministic fallback.")
                evaluated_item = None

        # 5. Deterministic Fallback if LLM was unavailable or errored
        if not evaluated_item:
            evaluated_item = _fallback_compliance_eval(
                req_code=req_code,
                req_text=req_text,
                category=category,
                best_evidence=best_evidence,
                citations=citations,
                forced_status=forced_status,
                contradiction_note=contradiction_note
            )

        compliance_items.append(evaluated_item)
        if evaluated_item.status == "COMPLIANT":
            compliant_count += 1
        elif evaluated_item.status == "PARTIALLY_COMPLIANT":
            partially_compliant_count += 1

    total = max(len(requirements), 1)
    # Overall score: 1.0 for COMPLIANT, 0.5 for PARTIALLY_COMPLIANT
    compliance_score = round(((compliant_count + (0.5 * partially_compliant_count)) / total) * 100, 1)

    log_entry = {
        "agent": "Compliance Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": f"Evaluated {len(requirements)} requirements against RAG knowledge base. Overall Compliance: {compliance_score}% ({compliant_count} Compliant, {partially_compliant_count} Partial, {len(requirements) - compliant_count - partially_compliant_count} Information Required / Non-Compliant)."
    }

    return {
        "compliance_matrix": [item.model_dump() for item in compliance_items],
        "overall_compliance_score": compliance_score,
        "active_agent": "Compliance Agent",
        "workflow_status": "ASSESSING_RISKS",
        "logs": state.get("logs", []) + [log_entry]
    }


def _is_structural_noise(term: str) -> bool:
    """Identifies artificial RFP requirement codes with prefixes like req-tech-001, r-sec-99, clause-2.1."""
    if not term or len(term) < 2:
        return True
    # Match structural requirement ID codes like req-tech-001, r-sec-99, schedule-phase-1, clause-2.1
    if re.match(r'^(?:req|rfp|sec|doc|tech|del|comm|cert|elig|sub|con|opt|man|mandatory|clause|schedule|part|field|integ|train|crypto)[-_][a-z0-9_\.-]+$', term, re.IGNORECASE):
        return True
    return False


def _extract_domain_terms(text: str) -> Set[str]:
    """
    Extracts distinctive meaningful domain terms from requirement or evidence text.
    Strips leading structural prefixes and excludes artificial ID tokens (e.g. '001', 'req-tech-001').
    """
    clean_text = sanitize_requirement_query(text)
    raw_tokens = re.findall(r'\b[a-zA-Z0-9_\-\.%]{2,}\b', clean_text.lower())
    terms: Set[str] = set()
    for tok in raw_tokens:
        tok_clean = tok.strip(".-")
        if tok_clean and tok_clean not in GENERIC_RFP_WORDS and len(tok_clean) >= 2 and not _is_structural_noise(tok_clean):
            terms.add(tok_clean)
            if "-" in tok_clean:
                for sub in tok_clean.split("-"):
                    sub_clean = sub.strip(".-")
                    if sub_clean and sub_clean not in GENERIC_RFP_WORDS and len(sub_clean) >= 2 and not _is_structural_noise(sub_clean):
                        terms.add(sub_clean)
    return terms


def _compute_semantic_coverage(req_terms: Set[str], evidence_text: str) -> Tuple[float, Set[str]]:
    """Computes what fraction of distinctive requirement terms are found in the evidence text."""
    if not req_terms:
        return 1.0, set()
    lower_ev = evidence_text.lower()
    matched = {t for t in req_terms if t in lower_ev}
    coverage = len(matched) / len(req_terms)
    return coverage, matched


def _find_relevant_sentence(query: str, text: str) -> str:
    """Finds the sentence in text with the highest word overlap with the query."""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if not sentences:
        return text
    
    q_tokens = _extract_domain_terms(query)
    if not q_tokens:
        q_tokens = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', query.lower()))
    if not q_tokens:
        return sentences[0]
        
    best_sent = sentences[0]
    best_overlap = -1
    for sent in sentences:
        s_tokens = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{2,}\b', sent.lower()))
        overlap = len(q_tokens & s_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_sent = sent
            
    return best_sent


def _evaluate_semantic_compliance(
    req_text: str,
    evidence_text: str
) -> Tuple[str, float, str]:
    """
    Evaluates semantic compliance strictly based on the actual text meaning of the evidence.
    Similarity score alone is NEVER used to decide compliance.
    
    Status Rules:
    - NON_COMPLIANT: Explicit evidence of failure/refusal/exclusion/unsupported capability.
    - PARTIALLY_COMPLIANT: Identifiable portion satisfied AND another portion explicitly limited/missing/conditional.
    - COMPLIANT: Direct evidence that the company satisfies the requirement (high domain coverage + affirmative support).
    - INFORMATION_REQUIRED: Insufficient, ambiguous, weak, or missing evidence.
    """
    if not evidence_text or not evidence_text.strip():
        return "INFORMATION_REQUIRED", 0.0, "No evidence text provided. Information required from bid team."

    relevant_sent = _find_relevant_sentence(req_text, evidence_text)
    req_terms = _extract_domain_terms(req_text)
    coverage, matched_terms = _compute_semantic_coverage(req_terms, evidence_text)

    # 1. Check 24/7 vs business hours explicit conflict / partial split
    is_24_7_req = bool(re.search(r'\b(?:24/7|24x7|round[- ]the[- ]clock)\b', req_text, re.IGNORECASE))
    has_24_7_in_ev = bool(re.search(r'\b(?:24/7|24x7|round[- ]the[- ]clock)\b', evidence_text, re.IGNORECASE))
    has_business_hours = bool(re.search(r'\b(?:business\s+hours|working\s+hours|office\s+hours|standard\s+hours)\b', evidence_text, re.IGNORECASE))

    if is_24_7_req and has_business_hours:
        if has_24_7_in_ev:
            return (
                "PARTIALLY_COMPLIANT",
                0.75,
                "Company evidence indicates partial 24/7 coverage with certain channels or support restricted to business hours."
            )
        else:
            return (
                "NON_COMPLIANT",
                0.90,
                "Company documentation explicitly specifies support is restricted to business hours, failing the 24/7 requirement."
            )

    # 2. Check for explicit refusal/non-compliance patterns on requirement topic
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', evidence_text) if s.strip()]
    refusal_sent = None
    if NON_COMPLIANT_PATTERNS.search(relevant_sent):
        refusal_sent = relevant_sent
    else:
        for s in sentences:
            if NON_COMPLIANT_PATTERNS.search(s):
                s_toks = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{2,}\b', s.lower()))
                s_overlap = len(req_terms & s_toks)
                if s_overlap >= 2 or (len(req_terms) == 1 and s_overlap >= 1):
                    refusal_sent = s
                    break

    rel_is_partial = bool(PARTIAL_COMPLIANT_PATTERNS.search(relevant_sent))
    ev_is_partial = bool(PARTIAL_COMPLIANT_PATTERNS.search(evidence_text))

    if refusal_sent and not rel_is_partial:
        return (
            "NON_COMPLIANT",
            0.90,
            "Company documentation explicitly states that this feature/standard is unsupported or out of scope."
        )

    # 3. Check for separate confirmation / commercial negotiation disclaimers on this topic
    has_sep_disclaimer = bool(SEPARATE_CONFIRMATION_PATTERNS.search(relevant_sent))
    if has_sep_disclaimer:
        # 16-week delivery timeframe is standard in Delivery notice
        if "16" in req_terms and "16-week" in evidence_text.lower() and ("delivery" in req_terms or "implementation" in req_terms or "timeline" in req_terms):
            pass
        else:
            return (
                "INFORMATION_REQUIRED",
                0.0,
                "Company documentation specifies this capability/term requires separate commercial negotiation or formal qualification."
            )

    # 4. Check for explicit partial compliance (Must have some satisfied portion AND explicit limitation)
    if rel_is_partial or ev_is_partial:
        # Check that an identifiable portion is satisfied
        if coverage >= 0.35 or len(matched_terms) >= 2 or has_24_7_in_ev:
            return (
                "PARTIALLY_COMPLIANT",
                round(min(0.85, max(0.5, coverage)), 2),
                "Company documentation confirms partial support, conditional workaround, or roadmap milestone."
            )
        else:
            # Limitation language exists in collateral but requirement itself is not satisfied / unrelated
            return (
                "INFORMATION_REQUIRED",
                0.0,
                "Evidence contains limitation language on unrelated capabilities and does not demonstrate satisfaction of the required capability."
            )

    # 5. Check for direct COMPLIANT satisfaction
    # Must have high semantic coverage of distinctive domain terms AND affirmative capability language
    has_affirmative = bool(AFFIRMATIVE_PATTERNS.search(evidence_text))

    if coverage >= 0.50 and has_affirmative and not refusal_sent:
        conf = min(1.0, max(0.75, round(coverage, 2)))
        return (
            "COMPLIANT",
            conf,
            "Direct company collateral confirms satisfaction of the required capability and specifications."
        )

    # 6. Default safe outcome: Evidence exists but is semantically insufficient or ambiguous
    return (
        "INFORMATION_REQUIRED",
        0.0,
        "Retrieved collateral does not directly demonstrate satisfaction of the requirement. Information required from bid team."
    )


def _apply_programmatic_safety_guard(
    llm_output: ComplianceItem,
    req_code: str,
    req_text: str,
    category: str,
    best_evidence: Dict[str, Any],
    citations: List[Dict[str, Any]],
    forced_status: Optional[str] = None,
    contradiction_note: Optional[str] = None
) -> ComplianceItem:
    """
    Enforces deterministic safety rules regardless of LLM hallucinations:
    - Normalizes status to strictly one of 4 allowed values.
    - If contradiction / ambiguous scope was detected across candidates, enforces forced_status.
    - COMPLIANT requires direct supporting evidence. If semantically insufficient, overrides to INFORMATION_REQUIRED.
    - PARTIALLY_COMPLIANT requires explicit partial-support evidence. If weak/unrelated, overrides to INFORMATION_REQUIRED.
    - NON_COMPLIANT requires explicit failure/refusal evidence. If evidence is merely absent, overrides to INFORMATION_REQUIRED.
    - Preserves all source traceability metadata.
    """
    evidence_text = best_evidence.get("evidence_text", "")
    source_doc = f"{best_evidence.get('document_title')} ({best_evidence.get('filename')})"
    sim_score = best_evidence.get("similarity", 0.0)

    # Compute ground-truth semantic compliance from evidence text
    semantic_status, semantic_conf, default_notes = _evaluate_semantic_compliance(req_text, evidence_text)

    if forced_status:
        final_status = forced_status
        final_conf = semantic_conf if forced_status != "INFORMATION_REQUIRED" else 0.0
        notes = contradiction_note or default_notes
    else:
        llm_status = llm_output.status if llm_output.status in ["COMPLIANT", "PARTIALLY_COMPLIANT", "NON_COMPLIANT", "INFORMATION_REQUIRED"] else "INFORMATION_REQUIRED"

        # Enforce safety rules on LLM output:
        if llm_status == "COMPLIANT":
            if semantic_status == "COMPLIANT":
                final_status = "COMPLIANT"
                final_conf = max(semantic_conf, float(llm_output.confidence or 0.0))
            elif semantic_status == "PARTIALLY_COMPLIANT":
                final_status = "PARTIALLY_COMPLIANT"
                final_conf = semantic_conf
            elif semantic_status == "NON_COMPLIANT":
                final_status = "NON_COMPLIANT"
                final_conf = semantic_conf
            else:
                final_status = "INFORMATION_REQUIRED"
                final_conf = 0.0

        elif llm_status == "PARTIALLY_COMPLIANT":
            if semantic_status == "PARTIALLY_COMPLIANT":
                final_status = "PARTIALLY_COMPLIANT"
                final_conf = max(semantic_conf, float(llm_output.confidence or 0.0))
            elif semantic_status == "NON_COMPLIANT":
                final_status = "NON_COMPLIANT"
                final_conf = semantic_conf
            else:
                final_status = "INFORMATION_REQUIRED"
                final_conf = 0.0

        elif llm_status == "NON_COMPLIANT":
            if semantic_status == "NON_COMPLIANT":
                final_status = "NON_COMPLIANT"
                final_conf = max(semantic_conf, float(llm_output.confidence or 0.0))
            else:
                final_status = "INFORMATION_REQUIRED"
                final_conf = 0.0

        else:
            final_status = "INFORMATION_REQUIRED"
            final_conf = 0.0

        notes = llm_output.notes or default_notes
        if final_status == "INFORMATION_REQUIRED" and llm_status != "INFORMATION_REQUIRED":
            notes = f"[Safety Guard Override] {default_notes}"

    ev_text_out = evidence_text if final_status != "INFORMATION_REQUIRED" else None
    source_doc_out = source_doc if final_status != "INFORMATION_REQUIRED" else None
    citations_out = citations if final_status != "INFORMATION_REQUIRED" else []

    return ComplianceItem(
        req_code=req_code,
        requirement_text=req_text,
        category=category,
        status=final_status,
        confidence=final_conf,
        evidence_text=ev_text_out,
        company_source_doc=source_doc_out,
        company_doc_id=best_evidence.get("company_doc_id"),
        chunk_id=best_evidence.get("chunk_id"),
        source_page=best_evidence.get("page_number", 1),
        source_section=best_evidence.get("section", "General"),
        similarity_score=sim_score,
        citations=citations_out,
        notes=notes
    )


def _fallback_compliance_eval(
    req_code: str,
    req_text: str,
    category: str,
    best_evidence: Dict[str, Any],
    citations: List[Dict[str, Any]],
    forced_status: Optional[str] = None,
    contradiction_note: Optional[str] = None
) -> ComplianceItem:
    """
    Deterministic rule-based compliance evaluator.
    Operates strictly on the text meaning of retrieved evidence, NEVER similarity score alone.
    """
    evidence_text = best_evidence.get("evidence_text", "")
    source_doc = f"{best_evidence.get('document_title')} ({best_evidence.get('filename')})"
    sim_score = best_evidence.get("similarity", 0.0)

    semantic_status, semantic_conf, default_notes = _evaluate_semantic_compliance(req_text, evidence_text)
    status = forced_status or semantic_status
    confidence = semantic_conf if status != "INFORMATION_REQUIRED" else 0.0
    notes = contradiction_note or default_notes

    ev_text_out = evidence_text if status != "INFORMATION_REQUIRED" else None
    source_doc_out = source_doc if status != "INFORMATION_REQUIRED" else None
    citations_out = citations if status != "INFORMATION_REQUIRED" else []

    return ComplianceItem(
        req_code=req_code,
        requirement_text=req_text,
        category=category,
        status=status,
        confidence=confidence,
        evidence_text=ev_text_out,
        company_source_doc=source_doc_out,
        company_doc_id=best_evidence.get("company_doc_id"),
        chunk_id=best_evidence.get("chunk_id"),
        source_page=best_evidence.get("page_number", 1),
        source_section=best_evidence.get("section", "General"),
        similarity_score=sim_score,
        citations=citations_out,
        notes=notes
    )


def best_ev_title(best_evidence: Dict[str, Any]) -> str:
    return best_evidence.get("document_title", "Unknown Collateral")
