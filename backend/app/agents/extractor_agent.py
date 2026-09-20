import re
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import RFPProposalState
from app.agents.llm_factory import LLMFactory
from app.core.prompts import EXTRACTION_AGENT_PROMPT
from app.models.schemas import ExtractionAgentOutput, RFPMetadata, RawClause, ExtractedBlock
from app.services.document_parser import DocumentParserService

# Guardrail: Legacy fictional placeholders that must NEVER appear in real or fallback metadata
PROHIBITED_FICTIONAL_STRINGS = [
    "Enterprise Cloud & Digital Transformation RFP",
    "Global Logistics & Transportation Authority",
    "October 31, 2026 at 5:00 PM EST",
    "Enterprise-wide hybrid cloud deployment and SLA-governed support"
]

class ExtractedClauseBatch(BaseModel):
    clauses: List[RawClause] = Field(
        default_factory=list,
        description="Candidate requirement clauses extracted verbatim from the document text"
    )

def extract_rfp_node(state: RFPProposalState) -> Dict[str, Any]:
    """
    Agent 1: RFP Document Extraction Agent
    Extracts structural hierarchy, RFP metadata, and candidate requirement clauses
    across the ENTIRE parsed RFP document while preserving page and section traceability.
    """
    file_path = state["file_path"]
    rfp_id = state["rfp_id"]

    # 1. Parse document into layout-annotated blocks across ALL pages
    blocks = DocumentParserService.parse_document(file_path)
    if not blocks:
        empty_meta = RFPMetadata(
            title="INFORMATION REQUIRED",
            issuer="INFORMATION REQUIRED",
            submission_deadline=None,
            budget_or_scope=None,
            evaluation_criteria=[],
            summary="INFORMATION REQUIRED"
        )
        return {
            "metadata": empty_meta.model_dump(),
            "raw_clauses": [],
            "active_agent": "Extraction Agent",
            "workflow_status": "CLASSIFYING",
            "logs": state.get("logs", []) + [{
                "agent": "Extraction Agent",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "Parsed 0 blocks from document. Metadata marked INFORMATION REQUIRED."
            }]
        }

    # 2. Extract Metadata (from introductory content and criteria sections)
    metadata = _extract_metadata(blocks)

    # 3. Extract Candidate Clauses across the ENTIRE document (Full-Document Strategy)
    raw_clauses, stats = _extract_all_clauses(blocks)

    # 4. Final safety sanity check: ensure no prohibited fictional strings exist
    metadata = _sanitize_metadata(metadata)

    log_entry = {
        "agent": "Extraction Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": f"Extracted metadata and identified {len(raw_clauses)} candidate clauses (Evaluated {stats['candidates_evaluated_before_validation']} candidates -> Filtered {stats['candidates_filtered_by_semantic_validation']} non-requirements -> Accepted {stats['candidates_accepted_after_validation']} requirements) across {len(blocks)} blocks covering all pages."
    }

    return {
        "metadata": metadata.model_dump(),
        "raw_clauses": [c.model_dump() for c in raw_clauses],
        "active_agent": "Extraction Agent",
        "workflow_status": "CLASSIFYING",
        "logs": state.get("logs", []) + [log_entry]
    }


def _extract_metadata(blocks: List[ExtractedBlock]) -> RFPMetadata:
    """
    Extracts metadata from actual document blocks.
    Uses LLM with structured output when available, falling back strictly to
    rule-based extraction from the actual text (no fictional defaults).
    """
    # Select introductory blocks (pages 1-3 or first 20 blocks)
    intro_blocks = [b for b in blocks if b.page_number <= 3]
    if not intro_blocks:
        intro_blocks = blocks[:20]

    # Also include any blocks across the entire document mentioning evaluation or criteria
    criteria_blocks = [
        b for b in blocks 
        if b not in intro_blocks and any(k in (b.section_title + " " + b.text).lower() for k in ["evaluation", "criteria", "scoring", "award criteria"])
    ]

    meta_context_blocks = intro_blocks + criteria_blocks
    context_text = "\n\n".join([f"[{b.section_title} - Page {b.page_number}]\n{b.text}" for b in meta_context_blocks])[:6000]

    llm = LLMFactory.get_chat_model()
    if llm:
        try:
            structured_meta_llm = llm.with_structured_output(RFPMetadata)
            prompt = (
                "Analyze the following RFP document segments and extract the official metadata.\n"
                "CRITICAL RULES:\n"
                "- Extract ONLY information explicitly stated in the text.\n"
                "- If title or issuer is not found, set it to 'INFORMATION REQUIRED'.\n"
                "- If submission deadline or budget/scope is not mentioned, set it to null.\n"
                "- If evaluation criteria are not stated, return an empty list [].\n"
                "- If summary cannot be derived, set it to 'INFORMATION REQUIRED'.\n"
                "- NEVER invent or assume fictional RFP titles, organizations, dates, or criteria.\n\n"
                f"Document Segments:\n{context_text}"
            )
            result: RFPMetadata = structured_meta_llm.invoke([
                SystemMessage(content=EXTRACTION_AGENT_PROMPT),
                HumanMessage(content=prompt)
            ])
            # Validate LLM result against empty/hallucinated values
            if result and result.title and result.title != "INFORMATION REQUIRED":
                return _sanitize_metadata(result)
        except Exception as e:
            print(f"[Agent 1: Extraction] LLM metadata extraction error, using rule-based extractor: {e}")

    # Fallback to rule-based extraction strictly derived from document text
    return _fallback_metadata(blocks, context_text)


def _fallback_metadata(blocks: List[ExtractedBlock], context_text: str) -> RFPMetadata:
    """
    Extracts metadata strictly from the actual parsed text of the document.
    Never invents or hardcodes fictional defaults.
    """
    full_text = context_text if context_text else "\n\n".join([b.text for b in blocks[:25]])

    # 1. Title Extraction
    title = None
    title_match = re.search(
        r'(?im)^\s*(?:TITLE|PROJECT(?:\s+TITLE)?|RFP\s+TITLE|NAME\s+OF\s+(?:PROJECT|TENDER)|SOLICITATION\s+NAME)[\s:\-–—]+([^\n\r]+)',
        full_text
    )
    if title_match:
        title = title_match.group(1).strip().strip('"\'')
    else:
        # Check for explicit REQUEST FOR PROPOSAL / RFP / TENDER lines with titles
        rfp_line_match = re.search(
            r'(?im)^\s*(?:REQUEST\s+FOR\s+PROPOSALS?|RFP|TENDER|INVITATION\s+TO\s+BID|SOLICITATION)[\s:\-–—]+([^\n\r]+)',
            full_text
        )
        if rfp_line_match:
            candidate = rfp_line_match.group(1).strip().strip('"\'()')
            if len(candidate) > 4 and not candidate.isupper() and "document ref" not in candidate.lower():
                title = candidate

    if not title:
        # Check early heading blocks on page 1
        for b in blocks:
            if b.page_number == 1 and b.block_type == "heading":
                candidate = b.text.strip().strip('# \t\r\n"\'')
                lower_cand = candidate.lower()
                if (
                    len(candidate) >= 8 and len(candidate) <= 120
                    and not lower_cand.startswith("section")
                    and not lower_cand.startswith("page")
                    and not lower_cand.startswith("document ref")
                    and "table of contents" not in lower_cand
                ):
                    title = candidate
                    break

    if not title:
        title = "INFORMATION REQUIRED"

    # 2. Issuer Extraction
    issuer = None
    issuer_match = re.search(
        r'(?im)^\s*(?:ISSUED\s+BY|CLIENT|ORGANIZATION|AGENCY|AUTHORITY|PROCURING\s+ENTITY|PROCURING\s+AGENCY|BUYER|ISSUING\s+ORGANIZATION)[\s:\-–—]+([^\n\r]+)',
        full_text
    )
    if issuer_match:
        issuer = issuer_match.group(1).strip().strip('"\'.,')
    else:
        # Check natural language invitation sentences
        agency_pattern = re.search(
            r'(?i)The\s+([A-Z][A-Za-z0-9\s&,\.\-–—]+?(?:Authority|Agency|Department|Ministry|Corporation|Commission|Board|District|Administration|Council|Foundation|Institute|Services|LLC|Inc|Ltd))\s+(?:invites|requests|issues|is\s+seeking|solicits|hereby\s+issues)',
            full_text
        )
        if agency_pattern:
            issuer = agency_pattern.group(1).strip().strip('"\'.,')

    if not issuer:
        issuer = "INFORMATION REQUIRED"

    # 3. Submission Deadline Extraction
    deadline = None
    deadline_match = re.search(
        r'(?im)^\s*(?:DUE\s+DATE|SUBMISSION\s+DEADLINE|CLOSING\s+DATE|PROPOSALS?\s+DUE|DEADLINE\s+FOR\s+SUBMISSION|RESPONSE\s+DEADLINE)[\s:\-–—]+([^\n\r]+)',
        full_text
    )
    if deadline_match:
        deadline = deadline_match.group(1).strip().strip('"\'.,')
    else:
        dl_phrase_match = re.search(
            r'(?im)(?:due\s+on\s+or\s+before|submitted\s+no\s+later\s+than|closing\s+time\s+and\s+date\s+is)[\s:\-–—]+([^\n\r\.]+)',
            full_text
        )
        if dl_phrase_match:
            deadline = dl_phrase_match.group(1).strip().strip('"\'.,')

    # 4. Budget or Scope Extraction
    budget = None
    budget_match = re.search(
        r'(?im)^\s*(?:ESTIMATED\s+BUDGET|BUDGET|NOT\s+TO\s+EXCEED|CONTRACT\s+VALUE|MAXIMUM\s+VALUE|ENGAGEMENT\s+SCOPE|SCOPE\s+OF\s+WORK)[\s:\-–—]+([^\n\r]+)',
        full_text
    )
    if budget_match:
        budget = budget_match.group(1).strip().strip('"\'.,')
    else:
        curr_match = re.search(
            r'(?i)(?:budget|contract\s+value|estimated\s+value)[\s:\-–—]*(?:is|of)?\s*([\$£€]\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|k|thousand))?)',
            full_text
        )
        if curr_match:
            budget = curr_match.group(1).strip()

    # 5. Evaluation Criteria Extraction
    evaluation_criteria = []
    # Find criteria sections
    criteria_sections = [
        b for b in blocks 
        if any(k in (b.section_title + " " + b.text).lower() for k in ["evaluation criteria", "selection criteria", "award criteria", "scoring criteria", "evaluation"])
    ]
    for cb in criteria_sections:
        lines = cb.text.split("\n")
        for line in lines:
            line_str = line.strip()
            # Match numbered or bulleted criteria with weight/percent e.g. "1. Technical Architecture (30%)"
            crit_match = re.search(r'(?i)^\s*(?:\d+[\.\)]\s*|[-*•]\s*)?([^\n\r]+?\(\s*\d+%\s*\)|[^\n\r]+?\b\d+\s*(?:%|percent|points\b)[^\n\r]*)', line_str)
            if crit_match:
                cleaned_crit = crit_match.group(0).strip().strip('-*• \t')
                if cleaned_crit and cleaned_crit not in evaluation_criteria:
                    evaluation_criteria.append(cleaned_crit)

    # 6. Summary Extraction
    summary = None
    # Search for introductory summary blocks
    intro_summary_blocks = [
        b for b in blocks 
        if any(k in b.section_title.lower() for k in ["executive summary", "introduction", "background", "objective", "purpose", "section 1"])
        and len(b.text.split()) >= 10
    ]
    if intro_summary_blocks:
        first_block_text = intro_summary_blocks[0].text.strip()
        # Remove any section header line if repeated
        lines = [l.strip() for l in first_block_text.split("\n") if l.strip() and not l.strip().lower().startswith("section")]
        if lines:
            summary = " ".join(lines[:3])[:350].strip()

    if not summary:
        # Try taking first substantive paragraph from page 1
        for b in blocks:
            if b.page_number == 1 and len(b.text.split()) >= 15:
                lower = b.text.lower()
                if not lower.startswith("request for proposal") and not lower.startswith("title:") and not lower.startswith("issued by:"):
                    summary = b.text.strip()[:350].strip()
                    break

    if not summary:
        summary = "INFORMATION REQUIRED"

    return RFPMetadata(
        title=title,
        issuer=issuer,
        submission_deadline=deadline,
        budget_or_scope=budget,
        evaluation_criteria=evaluation_criteria,
        summary=summary
    )


def _extract_all_clauses(blocks: List[ExtractedBlock]) -> tuple[List[RawClause], Dict[str, int]]:
    """
    Extracts candidate clauses across the ENTIRE document (all pages).
    Processes blocks in batches to keep within context limits if LLM is active,
    and runs a comprehensive rule-based extractor to guarantee complete,
    traceable coverage without any hallucinations.
    Returns (formatted_clauses, stats_dict).
    """
    raw_clauses: List[RawClause] = []
    seen_signatures: Set[str] = set()
    total_evaluated = 0
    total_filtered = 0

    llm = LLMFactory.get_chat_model()
    batches = _create_block_batches(blocks, max_blocks_per_batch=10, max_chars_per_batch=3500)

    # 1. LLM Batch Extraction (if available)
    if llm:
        for batch in batches:
            batch_text = "\n\n".join([
                f"[Block {idx + 1} | Page {b.page_number} | Section: {b.section_title}]\n{b.text}"
                for idx, b in enumerate(batch)
            ])
            try:
                structured_batch_llm = llm.with_structured_output(ExtractedClauseBatch)
                prompt = (
                    "You are an expert RFP requirement clause extractor. Extract all candidate requirement clauses "
                    "verbatim from the following document blocks. For each clause:\n"
                    "- Extract exact verbatim text (never summarize, alter, or fabricate requirements).\n"
                    "- Set source_page to the exact Page number indicated in the block header.\n"
                    "- Set source_section to the exact Section indicated in the block header.\n\n"
                    f"Document Blocks:\n{batch_text}"
                )
                batch_result: ExtractedClauseBatch = structured_batch_llm.invoke([
                    SystemMessage(content=EXTRACTION_AGENT_PROMPT),
                    HumanMessage(content=prompt)
                ])
                if batch_result and batch_result.clauses:
                    for c in batch_result.clauses:
                        total_evaluated += 1
                        if _is_non_requirement_heading_or_criterion(c.text):
                            total_filtered += 1
                            continue
                        norm_sig = _normalize_clause_sig(c.text)
                        if norm_sig and norm_sig not in seen_signatures:
                            # Validate source_page and source_section
                            if not c.source_page or c.source_page <= 0:
                                c.source_page = batch[0].page_number
                            if not c.source_section or c.source_section == "General":
                                c.source_section = batch[0].section_title
                            seen_signatures.add(norm_sig)
                            raw_clauses.append(c)
            except Exception as e:
                print(f"[Agent 1: Extraction] LLM clause batch error: {e}")

    # 2. Rule-Based Clause Extraction across ALL blocks
    # Guarantees full-document coverage, even when LLM is offline or skips blocks
    rule_clauses, rule_eval_count, rule_filter_count = _extract_clauses_rule_based(blocks)
    total_evaluated += rule_eval_count
    total_filtered += rule_filter_count

    for rc in rule_clauses:
        norm_sig = _normalize_clause_sig(rc.text)
        if norm_sig and norm_sig not in seen_signatures:
            seen_signatures.add(norm_sig)
            raw_clauses.append(rc)

    # 3. Canonical numbering and final formatting
    formatted_clauses: List[RawClause] = []
    for idx, c in enumerate(raw_clauses, start=1):
        formatted_clauses.append(
            RawClause(
                clause_id=f"CLAUSE-{idx:03d}",
                text=c.text.strip(),
                source_page=max(1, c.source_page),
                source_section=c.source_section.strip() if c.source_section else "General"
            )
        )

    stats = {
        "candidates_evaluated_before_validation": total_evaluated,
        "candidates_filtered_by_semantic_validation": total_filtered,
        "candidates_accepted_after_validation": len(formatted_clauses)
    }

    print(f"[Agent 1: Extraction] Semantic Validation Summary: Evaluated {total_evaluated} candidates -> Filtered {total_filtered} non-requirements -> Accepted {len(formatted_clauses)} genuine requirement clauses.")

    return formatted_clauses, stats


def _classify_section_tier(section_title: str) -> str:
    """
    Classifies a section title into structural hierarchy tiers across commercial,
    government, defense, and international procurement standards:
    - CONTEXT_PURPOSE: Purpose, Introduction, Executive Summary, Background, Objective, Overview, Preamble, NIT, EOI
    - CONTEXT_EVALUATION: Evaluation Criteria, Selection Criteria, Scoring Matrix, Award Criteria, Methodology, Marks Allocation
    - CONTEXT_TIMELINE: Timeline, Schedule of Events, Key Dates, Milestones, Procurement Calendar
    - CONTEXT_INSTRUCTIONS: Vendor Instructions, Submission Guidelines, Proposal Format, ITB, ITT, Portal Walkthroughs, EMD/BG
    - FORMAL_REQUIREMENTS: Requirements, System Requirements, Specifications, Functional/Non-Functional Specs, Compliance Matrix, Terms & Conditions (GTC/STC), SLA, Server Details
    - SCOPE_OF_WORK: Scope of Work (SOW), Performance Work Statement (PWS), Statement of Objectives (SOO), Terms of Reference (TOR), Deliverables
    - GENERAL: Default/unspecified
    """
    sec = section_title.strip().lower()

    # 1. Purpose / Introduction / Executive Summary / Overview / Background / Preamble / Invitation
    if re.search(r'\b(?:purpose|introduction|executive\s+summary|background|objective|procurement\s+objective|about\s+(?:the\s+)?(?:project|rfp|solicitation|company)|overview|intent|preamble|invitation\s+to\s+tender|notice\s+inviting\s+tender|nit|expression\s+of\s+interest|eoi|invitation\s+to\s+bid)\b', sec):
        if not re.search(r'\b(?:requirements?|specifications?|deliverables?|scope\s+of\s+work|statement\s+of\s+work)\b', sec):
            return "CONTEXT_PURPOSE"

    # 2. Evaluation / Scoring Criteria / Assessment Methodology / Marks / QCBS
    if re.search(r'\b(?:evaluation|scoring|selection\s+criteria|award\s+criteria|rating\s+criteria|assessment\s+criteria|evaluation\s+methodology|marks\b|marking\s+scheme|weightage|qcbs|more\s+than\s+\d+.*marks)\b', sec):
        return "CONTEXT_EVALUATION"

    # 3. Timeline / Schedule of Events / Key Dates / Milestones / Procurement Calendar
    if re.search(r'\b(?:timeline|key\s+dates|milestones|procurement\s+timeline|due\s+dates?|procurement\s+schedule|bid\s+calendar|schedule\s+of\s+events|important\s+dates|project\s+timeline)\b', sec):
        if not re.search(r'\b(?:commercial|pricing|rates|fees|requirements?|specifications?|deliverables?)\b', sec):
            return "CONTEXT_TIMELINE"

    # 4. Instructions / Submission Guidelines / Format / Packaging / Vendor Response / Registration Walkthrough / EMD / BG / Proforma
    if re.search(r'\b(?:submission\s+instructions|vendor\s+response|vendor\s+instructions|proposal\s+instructions|format\s+of\s+proposal|submission\s+guidelines|instructions\s+to\s+bidders|instructions\s+to\s+proposers|instructions\s+to\s+tenderers|itb|itt|response\s+format|proposal\s+submission|proposal\s+packaging|proposal\s+preparation|general\s+instructions|registration\s+process|applicant\s+registration|user\s+registration|portal\s+registration|registration\s+procedure|online\s+payment\s+of\s+emd|payment\s+of\s+emd|bank\s+guarant[ee]{2}|bank\s+gurantee|earnest\s+money|emd\b|bid\s+security|exemption\s+certificate|declaration\s+in\s+lieu|proforma|annexure\s+ii|annexure\s+iii)\b', sec):
        return "CONTEXT_INSTRUCTIONS"

    # 5. Formal Requirements / Specifications / Technical / Compliance / Terms / Hardware Details
    if re.search(r'\b(?:requirements?|specifications?|technical\s+specifications?|compliance\s+matrix|mandatory\s+requirements?|system\s+requirements?|functional\s+requirements?|non-functional\s+requirements?|security\s+requirements?|technical\s+architecture|statement\s+of\s+requirements|schedule\s+of\s+requirements|technical\s+schedule|commercial\s+terms|legal\s+terms|contractual\s+terms|general\s+terms|special\s+terms|gtc|stc|service\s+level|sla|server\s+details|hardware\s+details)\b', sec):
        return "FORMAL_REQUIREMENTS"

    # 6. Scope of Work / Deliverables / Obligations / Performance Work Statement
    if re.search(r'\b(?:scope\s+of\s+work|scope\s+of\s+services|scope|services\s+required|vendor\s+obligations|technical\s+approach|statement\s+of\s+work|sow|performance\s+work\s+statement|pws|statement\s+of\s+objectives|soo|terms\s+of\s+reference|tor|deliverables?|work\s+breakdown|tasks\s+and\s+deliverables)\b', sec):
        return "SCOPE_OF_WORK"

    return "GENERAL"


def _clean_clause_text(text: str) -> str:
    """
    Cleans running page headers/footers, bullet artifacts, and excess whitespace.
    e.g. '24 | P a g e with required...' -> 'with required...'
         '15 | P a g e will be H-1.' -> 'will be H-1.'
    """
    cleaned = text.strip()
    # Strip leading PDF running page headers e.g. "24 | P a g e", "15 | Page", "Page 24 of 50"
    cleaned = re.sub(r'^\s*\d+\s*\|\s*P\s*a\s*g\s*e\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b\d+\s*\|\s*P\s*a\s*g\s*e\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*Page\s+\d+(?:\s+of\s+\d+)?\s*[-|:]?\s*', '', cleaned, flags=re.IGNORECASE)
    # Strip leading bullet/unicode artifacts (strictly symbols, never ASCII letters like 'o')
    cleaned = re.sub(r'^(?:[\u2022\u25cf\u25cb\u25ef\u25e6\u2219\u2043\u25aa\u25ab\uf0b7\uf0a7•*\-–—]\s*)+', '', cleaned)
    cleaned = re.sub(r'^\s*[oO]\s{2,}(?=[A-Z0-9])', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _is_non_requirement_heading_or_criterion(text: str) -> bool:
    """
    Returns True if the text represents:
    - Section / chapter / subsection headers
    - Buyer / client / authority internal actions, nominations, payment disbursements, disclaimers, or rights
    - Strategic objectives, marketing context, or background preambles without concrete vendor obligations
    - Template drafting placeholders (e.g. <Define the new modules...>, <Mention the additional...>)
    - Proforma agreements, non-judicial stamp paper drafting templates (e.g. WHEREAS We, ...)
    - Form artifacts (Date, Place, Name, Signature of Authorized Signatory)
    - Incomplete bullet fragments, dangling colons/prepositions, and SLA preamble headers
    - Evaluation / scoring criteria, committee actions, marks formulas, QCBS calculations
    - End-user / society / departmental manual workflow walkthroughs (preserving underlying system capabilities)
    - Tender fee, EMD deposit, and Bank Guarantee transaction instructions
    - Proposal response meta-instructions
    - Table column headers or metadata key-value lines
    
    Top-priority override: Explicit IDs (e.g. REQ-TECH-001:) are always preserved.
    """
    clean_text = _clean_clause_text(text)
    if not clean_text or len(clean_text) < 15:
        return True

    # Top-priority override: explicit requirement IDs present in text
    if re.search(r'\bREQ-[A-Z0-9]+-\d{3,4}\b', clean_text, re.IGNORECASE):
        return False

    # Check for binding obligation modals
    has_obligation_modal = bool(re.search(
        r'\b(?:shall|must|is\s+required\s+to|are\s+required\s+to|must\s+provide|shall\s+agree|must\s+hold|must\s+support|shall\s+reside|will\s+deliver|will\s+provide|agrees?\s+to|covenants|undertakes|is\s+mandatory|mandatory\s+requirement)\b',
        clean_text,
        re.IGNORECASE
    ))

    # Check for explicit vendor/contractor subject obligations
    has_vendor_actor = bool(re.search(
        r'\b(?:vendor|bidder|contractor|system\s+integrator|si\b|service\s+provider|company|platform|system|application|solution|portal)\s+(?:shall|must|is\s+required\s+to|are\s+required\s+to|will|needs\s+to|should|agrees\s+to|is\s+responsible\s+for|guarantees?|undertakes?|provides?)\b',
        clean_text,
        re.IGNORECASE
    ))

    # 1. Section / Chapter / Part / Appendix Title Headers
    if re.match(r'^(?:SECTION|CHAPTER|APPENDIX|PART|ANNEXURE|SCHEDULE|\d+\.)\s+[A-Za-z0-9\s&,\.\-–—:/()]+$', clean_text, re.IGNORECASE) and not has_obligation_modal:
        return True

    # 2. Subsection Title Headings without verbs/modals (e.g., "1. Technical Specifications", "5.1 Commercial Terms", "A.1 Database Engine")
    if re.match(r'^(?:[A-Z]\.|\d+(?:\.\d+)*\.?)\s+[A-Z][A-Za-z0-9\s&,\.\-–—:/()]+$', clean_text) and not has_obligation_modal:
        return True

    # 3. Buyer / Client / Authority Responsibilities, Disclaimers & Internal Actions
    # Distinguish buyer-side duties/rights/nominations/reviews/disclaimers from vendor obligations
    buyer_subjects = (
        r'(?:(?:the\s+)?(?:duly\s+constituted\s+)?(?:rcs(?:\s*[-_ /]\s*<[a-z0-9_]+>|\s*<[a-z0-9_]+>|\s+office|\s+[a-z0-9_]+)?|'
        r'buyer|client|department|authority|state(?:\s+government)?|pao|procuring\s+entity|tender\s+inviting\s+authority|'
        r'employer|purchaser|committee|evaluation\s+committee|procurement\s+committee|tender\s+scrutiny\s+committee|competent\s+authority)'
        r'(?:\s*[/\\-]\s*(?:committee|department|authority|buyer|client|rcs))*)'
    )
    if re.search(
        rf'\b{buyer_subjects}\s+(?:shall|will|must|may|reserves?\s+the\s+right\s+to|has\s+the\s+right\s+to|is\s+responsible\s+for|(?:also\s+)?nominates?|(?:will|shall)\s+(?:also\s+)?nominate|(?:will|shall)\s+take\s+up|takes?\s+up|makes?\s+payments?|(?:will|shall)\s+make\s+payments?|will\s+not\s+make\s+any\s+payments?|releases?\s+payments?|provides?\s+signoff|(?:will|shall)\s+have\s+the\s+right|must\s+include\s+the\s+requirements|wants\s+to\s+develop|designates?|(?:will|shall)\s+designate|provides?\s+office\s+space|(?:will|shall)\s+provide\s+office\s+space|reviews?|(?:will|shall)\s+review|evaluates?|(?:will|shall)\s+evaluate|opens?|(?:will|shall)\s+open|determines?|(?:will|shall)\s+determine|allocates?|(?:will|shall)\s+allocate|examines?|(?:will|shall)\s+examine|scrutinizes?|(?:will|shall)\s+scrutinize|notif(?:y|ies)|(?:will|shall)\s+notify|refunds?|(?:will|shall)\s+refund|awards?|(?:will|shall)\s+award|intimates?|(?:will|shall)\s+intimate|disclaims?|accepts?\s+no\s+liability)\b',
        clean_text,
        re.IGNORECASE
    ) and not has_vendor_actor:
        return True

    # Buyer reservation rights & outright bid rejection by client
    if (
        re.search(r'\b(?:reserves?\s+the\s+right\s+to\s+accept\s+or\s+reject\s+any\s+proposal|annul\s+the\s+bidding\s+process)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:the\s+)?(?:incomplete\s+)?(?:bids?|proposals?)\s+will\s+be\s+rejected\s+outright\b', clean_text, re.IGNORECASE)
    ) and not has_vendor_actor:
        return True

    # Buyer payment commitments, disclaimers, non-representation and non-liability clauses
    if (
        re.search(r'\b(?:does\s+not\s+make\s+any\s+representation\s+or\s+warranty|makes?\s+no\s+(?:representation\s+or\s+)?warranty|accepts?\s+no\s+liability\s*(?:for\s+any\s+loss|or\s+responsibility)?|is\s+not\s+an\s+offer\s+by|disclaims?\s+(?:all|any)\s+(?:warranties|liability|responsibility)|shall\s+not\s+be\s+liable\s+for\s+(?:any\s+)?(?:loss|damage)|disclaim\s+all\s+liability)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:neither\s+the\s+(?:client|buyer|authority|rcs|department)\s+nor\s+(?:its|their)\s+employees)\b', clean_text, re.IGNORECASE)
        or re.search(r'\bno\s+binding\s+legal\s+relationship\s+will\s+exist\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:security\s+deposit\s+(?:amount\s+)?will\s+be\s+refunded|refunded\s+to\s+the\s+contractor\s+without\s+interest)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:cost\s+incurred\s+(?:on\s+actual\s+basis\s+)?will\s+be\s+paid\s+&\s+procured\s+by|will\s+be\s+paid\s+&\s+procured\s+by|cost(?:[^\n\r.]+?)?(?:will|shall)\s+be\s+borne\s+by\s+(?:the\s+)?(?:buyer|client|authority|department|rcs))\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:loss\s+or\s+damage\s+arises\s+in\s+connection\s+with\s+any\s+negligence|misrepresentation\s+on\s+the\s+part\s+of)\b', clean_text, re.IGNORECASE)
    ) and not has_vendor_actor:
        return True

    # Recipient / Prospective Bidder Independent Due Diligence & Deemed Acceptance Advisories
    if (
        re.search(r'\b(?:recipients?|interested\s+part(?:y|ies)|prospective\s+bidders?|applicants?)\s+(?:must|should|is\s+advised\s+to|are\s+advised\s+to|shall)\s+(?:conduct|verify|satisfy|make)\s+(?:its|their)\s+own\s+(?:independent\s+)?(?:investigation|assessment|inquiries|analysis|due\s+diligence)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:recipients?|prospective\s+bidders?)\s+should\s+verify\s+the\s+accuracy,\s*reliability\s+and\s+completeness\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:recipient|bidder)\s+(?:will|shall),?\s+(?:by\s+responding\s+to[^\n\r,]+,?\s+)?be\s+deemed\s+to\s+have\s+accepted\s+the\s+terms\b', clean_text, re.IGNORECASE)
    ) and not has_vendor_actor:
        return True

    # Committee preliminary examination & responsiveness scrutiny procedures
    if (
        re.search(r'\b(?:preliminary\s+examination|scrutiny|examination)\s+of\s+bids?\s+(?:will|shall)\s+be\s+(?:conducted|undertaken|carried\s+out)\b', clean_text, re.IGNORECASE)
        or re.search(r'\bdetermine\s+(?:the\s+)?(?:substantial\s+)?responsiveness\s+of\s+(?:each\s+)?bid\b', clean_text, re.IGNORECASE)
        or re.search(r'\bif\s+a\s+bid\s+is\s+not\s+substantially\s+responsive\b', clean_text, re.IGNORECASE)
    ) and not has_vendor_actor:
        return True

    # Passive buyer actions (e.g. "will be reviewed by the RCS", "will be evaluated by the client", "will be rejected by committee", "shall be released by authority")
    if re.search(
        rf'\b(?:will|shall|is\s+to)\s+be\s+(?:reviewed|monitored|evaluated|decided|approved|settled|released|disbursed|paid|conducted|examined|scrutinized|rejected|refunded|notified|opened)\s+by\s+(?:the\s+)?{buyer_subjects}\b',
        clean_text,
        re.IGNORECASE
    ) and not has_vendor_actor:
        return True

    # Buyer settlement of final bill & PBG / security deposit release
    if (
        re.search(r'\b(?:(?:final\s+)?(?:bill|payment|invoices?)\s+(?:and\s+)?(?:shall|will)\s+be\s+settled|(?:pbg|performance\s+bank\s+guarantee|security\s+deposit)\s+(?:shall|will)\s+be\s+released\s+by\s+[^\n\r.]+?)\b', clean_text, re.IGNORECASE)
    ) and not has_vendor_actor:
        return True

    # Award / Contract Formation Notification
    if (
        re.search(r'\bnotification\s+of\s+award\s+will\s+constitute\s+the\s+formation\s+of\s+(?:the\s+)?contract\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:will|shall)\s+notify\s+the\s+successful\s+bidder\s+(?:in\s+writing\s+)?(?:by\s+registered\s+letter|by\s+email|that\s+its\s+bid\s+has\s+been\s+accepted)\b', clean_text, re.IGNORECASE)
    ) and not has_vendor_actor:
        return True

    # Tender reading guidelines & Disqualification meta-conditions
    if (
        re.search(r'\b(?:the\s+)?bidder\s+is\s+expected\s+to\s+examine\s+all\s+instructions\b', clean_text, re.IGNORECASE)
        or re.search(r'\bfailure\s+to\s+furnish\s+all\s+information\s+required\s+by\s+the\s+bidding\s+document\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:will\s+be\s+at\s+the\s+bidder[’\']s\s+risk|may\s+result\s+in\s+the\s+rejection\s+of\s+its\s+bid)\b', clean_text, re.IGNORECASE)
        or re.search(r'\bany\s+form\s+of\s+(?:canvassing|lobbying|influence|query\s+regarding\s+short\s*listing)\b', clean_text, re.IGNORECASE)
    ):
        return True

    # 4. Strategic Objectives, Marketing Context, Background Preambles & Pure List Lead-Ins
    # Safeguard 1: Structural lead-ins are excluded ONLY when they contain no concrete requirements or SLA/delivery metrics
    has_substantive_metrics = bool(re.search(
        r'\b(?:\d+%\s*uptime|\d+\s*(?:days?|hours?|months?|weeks?|years?|crores?|lakhs?|inr|usd|cmmi|iso)|24\s*x\s*7|api|sso|2fa|rbac|backup|encryption|audit\s+trail|helpdesk|warranty|mtbf|mttr|downtime|penalty)\b',
        clean_text,
        re.IGNORECASE
    ))

    is_pure_structural_leadin = bool(
        re.search(r'^(?:following\s+are\s+(?:the\s+)?(?:deliverables|services|requirements|modules|responsibilities|milestones)|the\s+service\s+provider\s+is\s+expected\s+to\s+provide\s+[^\n\r.]+?\s+as\s+follows|the\s+deliverables\s+(?:and\s+payment\s+milestones\s+)?are\s+as\s+below|as\s+per\s+the\s+details\s+given\s+below)[:\s.]*$', clean_text, re.IGNORECASE)
        or (
            re.search(r'\b(?:is\s+expected\s+to\s+provide\s+[^\n\r.]+?\s+as\s+follows|deliverables\s+which\s+will\s+be\s+responsibilities\s+of\s+successful\s+vendor|milestones\s+are\s+as\s+below|services?\s+as\s+follows)[:\s.]*$', clean_text, re.IGNORECASE)
            and not has_substantive_metrics
        )
    )
    if is_pure_structural_leadin:
        return True

    if (
        re.search(r'\b(?:following\s+)?(?:strategic\s+)?objectives?\s+(?:will\s+be\s+achieved|are\s+as\s+follows|of\s+the\s+project)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:strategic\s+objectives?\s+will\s+be\s+achieved)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:the\s+above\s+solution\s+is\s+designed\s+with\s+flexibility)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:the\s+vision\s+of\s+this\s+program\s+is|project\s+aims\s+at\s+establishing|over\s+the\s+years,\s+the\s+department)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:scope\s+of\s+engagement\s+encompasses|scope\s+of\s+work\s+(?:includes|encompasses)|following\s+high[- ]level\s+areas)[:\s]*$', clean_text, re.IGNORECASE)
        or (
            re.search(r'\bthe\s+purpose\s+of\s+this\s+(?:service\s+level\s+[a-z/]+|sla|document|section|agreement|schedule|annexure|rfp)\b[^\n\r.]+?\bis\s+to\s+(?:clearly\s+)?define\b', clean_text, re.IGNORECASE)
            and not has_substantive_metrics
        )
        or re.search(r'^(?:first|second|next)\s+(?:[a-z]+|\d+)\s+months?\s+period\s+will\s+come\s+under\s+d-?\d+', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:needs\s+to\s+be\s+done\s+through|including)[:\s]*$', clean_text, re.IGNORECASE)
    ):
        return True

    # 5. Template Placeholders, Drafting Guides & Proforma Agreements
    if (
        re.search(r'<[a-zA-Z0-9_\s\-–—/]+(?:need\s+to|give\s+the\s+details|details\s+of|insert|fill|specify|mention|define|state-specific)[^>]*>', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:for\s+other\s+procurement\s+methods\s*[-–—:]\s*)?(?:the\s+)?(?:respective\s+)?(?:states?|departments?|buyers?|agencies?|authorities?)\s+need\s+to\s+(?:define|give|specify|fill|insert|mention)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:procedure\s+&\s+submission\s+of\s+bid\s+(?:through|by)\s+.*?\s+or\s+by\s+any\s+other\s+state-specific|or\s+procedure\s+&\s+submission\s+of\s+bid)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:bid\s+shall\s+be\s+submitted\s+the\s+bid\s+on\s+<[^>]+>|bid\s+shall\s+be\s+submitted\s+the\s+bid\s+on\s+gem)\b', clean_text, re.IGNORECASE)
        or re.search(r'<(?:define|insert|specify|enter|fill|describe|placeholder|select|mention)\b[^>]*>', clean_text, re.IGNORECASE)
        or re.search(r'\[(?:please\s+)?(?:attach|define|insert|specify|enter|fill|select|provide|mention)\b[^\]]*\]', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:please\s+attach\s+(?:certified\s+copy|copy\s+of))\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:define\s+the\s+new\s+modules|define/change\s+the\s+procedure|define\s+the\s+requirements?\s+here)\b', clean_text, re.IGNORECASE)
        or re.search(r'\(?(?:Sample\s+Format|Proforma|Draft\s+Agreement|Standard\s+Format|Template\s+Format)\s*[-–—:]\s*(?:To\s+be\s+executed|To\s+be\s+submitted|On\s+non-judicial|On\s+stamp\s+paper)', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:To\s+be\s+executed\s+on\s+(?:a\s+)?non-judicial\s+stamped?\s+paper)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:WHEREAS\s+We\b|hereinafter\s+referred\s+to\s+as\s+the\s+COMPANY\b|NOW\s+THEREFORE,\s+in\s+consideration\s+of\s+the\s+foregoing\b)', clean_text, re.IGNORECASE)
    ):
        return True

    # 6. Form & Signature Artifacts
    if (
        re.search(r'^(?:Date|Place|Name|Signature)\s+(?:of\s+)?(?:the\s+)?(?:Authorized\s+Signatory|Bidder|Vendor|Representative|Seal|Designation|Tenderer)[\s…\._]*$', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:Signature\s+of\s+(?:the\s+)?(?:Authorized\s+Signatory|Bidder|Tenderer|Vendor)(?:\s+with\s+(?:Seal|Stamp))?)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:Name\s+of\s+(?:the\s+)?Authorized\s+Signatory|Date\s+Signature\s+of\s+Authorized|Place\s+Name\s+of\s+the\s+Authorized)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:Place\s*:\s*[A-Za-z\s]+\s+Date\s*:\s*[\d\.\-\/]+)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:Sl\.?\s*No\.?\s+Parameter\s+Minimum\s+Specification)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:Name\s+of\s+(?:the\s+)?Authorized\s+Signatory\s*:\s*Designation\s*:)\b', clean_text, re.IGNORECASE)
        or re.search(r'^\s*Authorized\s+Signatory\s*\[In\s+the\s+capacity\s+of', clean_text, re.IGNORECASE)
        or re.match(r'^\s*(?:Date|Place|Signature|Name)\s*[:–—\.]+\s*(?:_{3,}|\.{3,}|\(?[A-Za-z\s]+\)?[\s…\._]*)$', clean_text, re.IGNORECASE)
    ):
        return True

    # 7. Dangling Fragments, Incomplete Clauses & SLA Preambles
    if (
        re.search(r'\b(?:the\s+purpose\s+of\s+this\s+(?:service\s+level\s+requirements?/?agreement|sla|document|section)\s+is\s+to)\s*$', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:functionality\s+will\s+be\s+provided\s+to\s+view\s+(?:this\s+)?changes\s*/\s*audit\s+trail\s+based\s+on\s+various\s+conditions\s+like)\s*$', clean_text, re.IGNORECASE)
        or re.search(r'^(?:role\s+in\s+monitoring\s+the\s+sla\s+compliance\s+by\s+the|and\s+their\s+operation\s+efficient|and\s+its\s+designated\s+agency|management\.)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:contained\s+in\s+this|in\s+connection\s+therewith|based\s+on\s+various\s+conditions\s+like|as\s+follows\s+Sr\.?)\s*$', clean_text, re.IGNORECASE)
        or re.match(r'^(?:with\s+required\s+information\s+and\s+documents|n\s+the\s+rfp\s+document)\b', clean_text, re.IGNORECASE)
        or re.search(r'^(?:be\s+responsible\s+for\s+delivery\s+of\s+services\s+and\s+act\s+as\s+a\s+primary\s+interface)\b', clean_text, re.IGNORECASE)
        or len(clean_text.split()) < 4
    ):
        return True

    # Check if text describes a technical SLA or commercial rate/penalty (so it is not confused with evaluation scoring)
    is_sla_or_commercial_rate = bool(re.search(
        r'\b(?:uptime|availability|failover|accuracy|throughput|latency|penalty|liquidated\s+damages|discount|retention|interest|tax|gst|vat|rate|billing|subscription\s+fee|monthly\s+fee|annual\s+fee)\b',
        clean_text,
        re.IGNORECASE
    ))

    # 8. Evaluation / Scoring Preamble, QCBS Formulas, Marks Allocation & Selection Outcomes
    if not is_sla_or_commercial_rate:
        if (
            re.search(r'\b(?:evaluated\s+based\s+on|evaluation(?:\s+&\s+scoring)?\s+criteria|scoring\s+(?:matrix|criteria)|weighting|award\s+criteria)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:proposals?|bids?|bidders?)\s+(?:will|shall|are\s+to)\s+be\s+(?:evaluated|scored|ranked|marked|opened|shortlisted|assessed|judged|allocated\s+marks|allotted\s+marks|weighed|weighted)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:proposals?|bids?|bidders?)\s+(?:[^\n\r.]+?)?\b(?:will|shall)\s+be\s+given\s+a\s+(?:financial|technical)?\s*score\s+of\s+\d+\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:proposals?|bids?|bidders?)\s+(?:[^\n\r.]+?)?\bshall\s+be\s+given\s+a\s+score\s+of\s+\d+\b', clean_text, re.IGNORECASE)
            or re.search(r'\bproposals?\s+(?:with\s+(?:the\s+)?highest\s+technical\s+marks?\s*(?:\([^\)]*\))?\s*shall\s+be\s+given\s+a\s+score\s+of)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:technical|financial|quality|cost|combined)\s+(?:marks?|scores?|weights?|points?)\s+(?:shall|will|as\s+allotted)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:highest|lowest)\s+(?:technical|financial|combined)?\s*(?:marks?|scores?|points?)\s+(?:shall|will)\s+be\s+(?:given|ranked|awarded|allotted|allocated)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:ranked\s+(?:as\s+)?[HhLl]-?\d+|securing\s+the\s+highest\s+combined\s+(?:marks|score)|highest\s+(?:total\s+)?combined\s+score|evaluated\s+bid\s+score|calculated\s+for\s+each\s+responsive\s+bid\s+using\s+the\s+following\s+formula|qcbs\s*(?:\(\s*\d+:\d+\s*\)|\d+:\d+)?\s*(?:methodology|formula)?|quality\s+and\s+cost\s+based\s+selection)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:weighing|weighting)\s+the\s+quality\s+and\s+cost\s+scores\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:the\s+)?(?:bidders?|proposals?)\s+shall\s+be\s+ranked\s+in\s+terms\s+of\s+(?:the\s+)?total\s+score\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:financial|technical|commercial)\s+proposals?\s+(?:[^\n\r.]+?)?\b(?:will|shall)\s+be\s+opened\s+and\s+evaluated\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:in\s+the\s+case\s+of\s+a\s+single\s+(?:technically\s+)?qualified\s+bidder|financial\s+proposal\s+of\s+that\s+bidder\s+only\s+will\s+be\s+evaluated)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:proposals?|bidders?)\s+scoring\s+(?:above|below|more\s+than|at\s+least|less\s+than)?\s*\d+%', clean_text, re.IGNORECASE)
            or re.search(r'\bdeviations?\s+from\s+or\s+objections?\s+or\s+reservations?\s+to\s+critical\s+provisions\b', clean_text, re.IGNORECASE)
            or re.search(r'\bwill\s+be\s+deemed\s+to\s+be\s+a\s+material\s+deviation\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:proposals?\s+not\s+complying\s+with\s+(?:the\s+)?prescribed\s+[‘\'"]?eligibility\s+criteria[’\'"]?\s+and\s+not\s+submitted\s+along\s+with\s+duly\s+filled\s+up\s+annexures\s+are\s+liable\s+to\s+be\s+rejected)\b', clean_text, re.IGNORECASE)
            or re.search(r'\(\s*\d+%\s*\)', clean_text)
            or re.search(r'\b\d+\s*marks\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:only\s+)?(?:one|single)\s+bidder\s+(?:will|shall)\s+be\s+selected\b', clean_text, re.IGNORECASE)
            or re.search(r'^\s*(?:will\s+be\s+)?(?:ranked\s+)?[HhLl]-?\d+\.?\s*$', clean_text, re.IGNORECASE)
        ):
            return True

    # 9. End-User / Society / Departmental Officer Portal & Process Walkthroughs
    if not has_vendor_actor:
        if (
            re.search(
                r'\b(?:user|applicant|citizen|society|cooperative\s+soci[a-z]+|society\s+representative|end-?user|customer|operator|physician|nurse|doctor|officer|official|concerning\s+officer|department\s+official|dealing\s+hand)\s+'
                r'(?:will|shall|can|may|must|should|is\s+required\s+to|will\s+be\s+able\s+to|can\s+be\s+able\s+to|is\s+able\s+to)?\s*'
                r'(?:register|registered|register\s+himself|login|logins?|logs?\s+in|log\s+in|clicks?|click|fills?|fill|selects?|select|attaches?|attach|uploads?|upload|downloads?|download|views?|view|enters?|enter|revises?|revise|changes?|change|receives?|receive|submits?|submit|accept|issue\s+the\s+order|conduct\s+an\s+annual)\b',
                clean_text,
                re.IGNORECASE
            )
            or re.search(r'\b(?:user\s+will\s+be\s+registered|registration\s+form\s+will\s+(?:be\s+)?forward(?:ed)?\s+to\s+department|user\s+id\s+and\s+password\s+will\s+be\s+generated\s+and\s+shared|if\s+both\s+passwords?\s+match,\s*password\s+will\s+be\s+changed)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:if\s+the\s+society\s+wants\s+to\s+raise\s+a\s+request|society\s+will\s+fill\s+the\s+request|election\s+request\s+will\s+be\s+submitted|concerning\s+officer\s+will\s+accept\s+and\s+issue|concerning\s+officer\s+will\s+be\s+able\s+to\s+view)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:clicks?|click)\s+(?:on\s+)?(?:the\s+)?(?:edit|submit|save|next|previous|continue|download|upload|search|button|link|icon|tab|print)\b', clean_text, re.IGNORECASE)
            or re.search(r'^(?:select|click|choose|enter|type|open)\s+(?:the\s+)?(?:appropriate\s+)?[a-z\s]+(?:from\s+the\s+dropdown|from\s+the\s+list|button|screen|menu)\s+and\s+(?:click|press|select)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:fills?|fill)\s+(?:the\s+)?(?:responses?|fields?|form|application|basic\s+details|vital\s+signs)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:enters?|enter)\s+(?:user\s*id|username|password|otp|captcha|registered\s+email)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:changes?|change)\s+(?:his|her|their)?\s*password\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:if\s+user\s+forgets\s+his\s+password,\s+he\s+will\s+enter\s+his\s+registered\s+email\s+id)\b', clean_text, re.IGNORECASE)
            or re.search(r'\bthe\s+process\s+(?:for|of)\s+(?:filing\s+annual\s+returns|raising\s+an\s+appeal|user\s+registration)\b', clean_text, re.IGNORECASE)
            or re.search(r'\bcooperative\s+soci[a-z]+\s+must\s+(?:also\s+)?conduct\s+an\s+annual\s+general\s+meeting\b', clean_text, re.IGNORECASE)
            or re.search(r'\ball\s+states/uts\s+rcs\s+are\s+required\s+to\s+write\s+in\s+detail\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:the\s+)?system\s+will\s+display\s+relevant\s+fields\s+in\s+the\s+form\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:it\s+will\s+also\s+)?request\s+the\s+user\s+to\s+upload\s+relevant\s+annexures\s+&\s+documents\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:system|portal)\s+opens?\s+(?:the\s+)?(?:registration|login|dashboard|page|screen|window|form)\b', clean_text, re.IGNORECASE)
        ):
            return True

    # 9.5 Vague UI Form Display & Generic Touchpoint Narrative without actionable specifications
    if (
        re.search(r'^(?:the\s+)?(?:system|portal|application|form)\s+will\s+display\s+relevant\s+fields\s+in\s+the\s+form\.?\s*$', clean_text, re.IGNORECASE)
        or re.search(r'^\s*(?:The\s+)?(?:User\s+Touchpoints\s+)?(?:Web\s+Portal|Portal|Application|System)\s+will\s+(?:allow\s+users\s+to\s+(?:manage\s+and\s+)?access|provide\s+access\s+to)\s+(?:any|all)\s+information\.?\s*$', clean_text, re.IGNORECASE)
        or re.search(r'^\s*There\s+(?:will\s+be|are)\s+(?:various|different|multiple)?\s*(?:external\s+)?(?:services|systems|gateways|servers|platforms|sources)\s+(?:like|such\s+as)\b[^\n\r]*$', clean_text, re.IGNORECASE)
    ):
        return True

    # 10. Tender Deposits, EMD, and Bank Guarantee Logistics
    if (
        re.search(r'\b(?:online\s+payment\s+of\s+emd|payment\s+of\s+emd|earnest\s+money\s+deposit|bid\s+security\s+deposit|tender\s+fee|cost\s+of\s+tender)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:payment\s+(?:of\s+emd\s+)?by\s+(?:cheque|cash|tdr|fdr|dd|demand\s+draft|rtgs|neft)\s+(?:will|shall|is)\b)', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:bank\s+guarant[ee]{2}|bank\s+gurantee|bg)\s+(?:favoring|in\s+favou?r\s+of|shall\s+be\s+valid|should\s+be\s+valid|is\s+extendable|needs?\s+to\s+be\s+sent\s+by\s+post|of\s+equivalent\s+amount)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:bid-?security\s+declaration|exempt(?:ed|ion)?\s+(?:from\s+)?(?:emd|earnest\s+money|bg|bid\s+security)|exemption\s+certificate|without\s+emd|rejected\s+without\s+emd)\b', clean_text, re.IGNORECASE)
    ):
        return True

    # 11. Form Templates, Spreadsheet Sequences, and Drafting Placeholders
    if (
        re.match(r'^\s*(?:\d+\s+){3,}\d*\s*(?:TOTAL|COST|INR|USD|Please\s+add/delete)?', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:please\s+add\s*/\s*delete\s+rows|add/delete\s+rows\s+if\s+required)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:total\s+cost\s+\([a-z0-9]\)\s+inr|total\s+cost\s+\([a-z0-9]\)\s+in\s+words|cost\s+in\s+words:\s*_{3,})\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:proforma\s+technical\s+proposal|proforma\s+financial\s+proposal)\b', clean_text, re.IGNORECASE)
    ):
        return True

    # 12. Document Titles & Cover Preamble (e.g., "REQUEST FOR PROPOSAL (RFP)", "System Specification & Commercial Requirements Document")
    if (
        re.search(r'\b(?:REQUEST\s+FOR\s+PROPOSAL|SOLICITATION\s+DOCUMENT|TENDER\s+DOCUMENT|INVITATION\s+TO\s+BID)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:System\s+Specification|Requirements\s+Document|Commercial\s+Requirements\s+Document|Specification\s+Document|Scope\s+of\s+Work|Vendor\s+Commitments)\b', clean_text, re.IGNORECASE)
    ) and not has_obligation_modal:
        return True

    # 13. Table Column Headers
    if (
        re.search(r'\b(?:Req\s*ID|Requirement\s*ID|Item\s*#|Clause\s*#|Ref\s*#|Sl\.?\s*No\.?)\b', clean_text, re.IGNORECASE)
        and re.search(r'\b(?:Category|Specification|Description|Mandatory|Priority|Status|Compliance|Deliverable|Feature)\b', clean_text, re.IGNORECASE)
    ) and not has_obligation_modal:
        return True

    # 14. Vendor Response Instructions & Proposal Answering Meta-Guidelines
    if (
        re.search(r'\bterms\s+and\s+conditions\s+(?:\(general\s+conditions\)\s+)?of\s+the\s+bidder\s+will\s+not\s+be\s+considered\b', clean_text, re.IGNORECASE)
        or re.search(r'\bproposals?\s+received\s+after\s+the\s+due\s+date\s+(?:&\s*time|\band\s+time)?\s+will\s+not\s+be\s+considered\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:the\s+)?offers?\s+containing\s+erasures\s+or\s+alterations\s+will\s+not\s+be\s+considered\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:the\s+)?bidder\s+shall\s+prepare\s+the\s+bid\s+based\s+on\s+details\s+provided\s+in\s+the\s+rfp\s+documents?\.?\s*$', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:technical\s+details|technical\s+information|details|responses?)\s+must\s+be\s+filled\s+in\b', clean_text, re.IGNORECASE)
        or re.search(r'\bcorrect\s+technical\s+information\s+about\s+the\s+product[^\n\r.]+?must\s+be\s+filled\s+in\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:state\s+(?:their|its)?\s*compliance|indicate\s+(?:their|its)?\s*compliance|confirm\s+(?:their|its)?\s*compliance)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:unsupported\s+claims|cannot\s+be\s+(?:fully\s+)?confirmed|identify\s+the\s+limitation)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:respond\s+to\s+(?:each|this|every)\s+requirement|address\s+(?:each|all)\s+requirements?\s+in\s+(?:the|their|its)\s+proposal)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:format\s+(?:their|its|the)\s+response|complete\s+(?:the|this)\s+compliance\s+(?:matrix|table))\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:proposals?|bidders?|vendors?|contractors?)\s+(?:shall|must|should|are\s+required\s+to)\s+(?:clearly\s+)?(?:state|explain|describe|detail|indicate)\s+(?:how|their|its|whether|compliance)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:proposals?|bidders?|vendors?)\s+(?:must|shall|should)\s+not\s+make\s+(?:any\s+)?(?:unsupported|false|unverified)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:bidders?|vendors?)\s+(?:must|shall)\s+submit\s+(?:technical\s+and\s+commercial\s+proposals|in\s+separate\s+sealed\s+envelopes|via\s+the\s+procurement\s+portal)\b', clean_text, re.IGNORECASE)
    ):
        return True

    # 15. Metadata Key-Value Header lines without requirements
    if re.match(r'^(?:DOCUMENT\s+REF|ISSUED\s+BY|DUE\s+DATE|SUBMISSION\s+DEADLINE|CLIENT|PROJECT\s+TITLE|TITLE|AUTHORITY)[\s:\-–—]+[^\n\r]+$', clean_text, re.IGNORECASE) and not has_obligation_modal:
        return True

    # 16. Pre-Bid Conference Logistics & Notice Dissemination
    if not has_vendor_actor:
        if (
            re.search(r'\b(?:pre-bid\s+(?:conference|meeting)|clarification\s+meeting)\s+(?:shall|will)\s+be\s+(?:scheduled|held|conducted|virtual|notified)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:in\s+case\s+of\s+(?:any\s+)?change\s+in\s+(?:the\s+)?schedule\s+of\s+(?:the\s+)?pre-bid|changed\s+schedule\s+shall\s+be\s+notified\s+(?:of\s+)?through\s+email)\b', clean_text, re.IGNORECASE)
            or re.search(r'\bqueries\s+(?:received|submitted)\s+after\s+(?:the\s+)?due\s+date\s+(?:for\s+pre-bid|will\s+not\s+be\s+entertained)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:queries\s+must\s+be\s+submitted\s+in\s+microsoft\s+excel\s+format|clarification\s+to\s+be\s+sought\s+name\s+of\s+bidder|common\s+set\s+of\s+conditions/deviations|during\s+the\s+pre-bid\s+conferences?,\s+the\s+bidders\s+will\s+be\s+free\s+to\s+seek\s+clarifications)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:not\s+finding\s+place\s+in\s+c\.?s\.?d\.?|deemed\s+to\s+have\s+been\s+rejected\s+by\s+(?:the\s+)?[^\n\r.]+?)\b', clean_text, re.IGNORECASE)
            or re.search(r'\b(?:queries|clarifications)\s+must\s+reach\s+(?:the\s+)?[^\n\r.]+?\s+before\s*[\'\"‘“\[]?\s*(?:the\s+)?last\s+date\s+for\s+submission\s+of\s+(?:written\s+)?queries\b', clean_text, re.IGNORECASE)
        ):
            return True

    return False


def _is_heading_or_structural_block(block: ExtractedBlock) -> bool:
    """
    Identifies if a block is a section heading, document title, or table header.
    Structural blocks must never be stitched into body paragraphs or other blocks.
    """
    if block.block_type in ("heading", "title", "table_header", "table"):
        return True

    text = block.text.strip()
    if not text:
        return True

    # Matches numbered section titles e.g. "1. Purpose", "2. Scope of Work", "Section 3: Technical Specs", "Chapter 4"
    if re.match(r'^(?:(?:\d{1,2}\.){1,3}\d{0,2}\s+[A-Z]|(?:Section|Chapter|Annexure|Appendix|Schedule|Part|Module)\s+(?:\d+|[A-ZIVX]+)[\s:\-–—])', text, re.IGNORECASE):
        return True

    # Matches standard document headers/titles
    if re.match(r'^(?:REQUEST\s+FOR\s+PROPOSAL|SOLICITATION\s+DOCUMENT|TENDER\s+DOCUMENT|INVITATION\s+TO\s+BID|TABLE\s+OF\s+CONTENTS|SCOPE\s+OF\s+WORK|COMMERCIAL\s+PROPOSAL|TECHNICAL\s+PROPOSAL)(?:\s*[\-–—:\(].*)?$', text, re.IGNORECASE):
        return True

    # Matches table header line e.g. "Req ID Category Requirement Specification Mandatory" or "Sl. No. Parameter Minimum Specification"
    if (
        re.search(r'\b(?:Req\s*ID|Requirement\s*ID|Item\s*#|Clause\s*#|Ref\s*#|Sl\.?\s*No\.?)\b', text, re.IGNORECASE)
        and re.search(r'\b(?:Category|Specification|Description|Mandatory|Priority|Status|Compliance|Deliverable|Feature)\b', text, re.IGNORECASE)
    ):
        return True

    # Short header line without trailing punctuation (< 80 chars, single line, no modal verbs like shall/must/will/requires)
    if len(text) < 80 and '\n' not in text and not text.endswith(('.', '!', '?', ';', ':', ',"', '."', '?"', '!"', '.)', '!)')):
        if not re.search(r'\b(?:shall|must|will|should|is\s+required|are\s+required|agrees?\s+to)\b', text, re.IGNORECASE):
            return True

    return False


def _stitch_blocks(blocks: List[ExtractedBlock]) -> List[ExtractedBlock]:
    """
    Safeguard 2: Stitches sequential blocks when a clause was split across block/page boundaries.
    Reconstructs wrapped sentences BEFORE final semantic filtering and classification.
    """
    if not blocks:
        return []

    stitched: List[ExtractedBlock] = []
    
    header_pattern = re.compile(r'^\s*(?:\d+\s*\|\s*P\s*a\s*g\s*e|P\s*a\s*g\s*e\s*\|\s*\d+)\s*', re.IGNORECASE)
    bullet_start_pattern = re.compile(
        r'^\s*(?:[•\-\*\uf0b7–—\u25cb\u25ef\u25e6\u2022\u2219\u2043]|\([0-9a-zA-Z]\)|(?:\d{1,2}\.){1,3}\d{1,2}|\d{1,2}[\.\)]|[a-zA-Z][\.\)]|[oO]\s{2,}(?=[A-Z0-9])|(?:REQ|SECTION|CHAPTER|ANNEXURE|APPENDIX|PART|SCHEDULE|MODULE)\b)\s+',
        re.IGNORECASE
    )
    
    sentence_end_chars = ('.', '!', '?', ';', ':', '."', '?”', '!”', ';"', '.)', '!)')
    dangling_trailing_regex = re.compile(
        r'\b(?:of|to|with|and|or|in|for|as|by|the|a|an|from|at|under|into|per|such\s+as|including|between|against|without|on|about|is|are|shall|must|will|should|be|have|has|their|its|which|that|who|whom|whose|within|during|before|after|over|with\s+["“][^"”]*)\s*$',
        re.IGNORECASE
    )

    i = 0
    while i < len(blocks):
        curr = blocks[i]
        curr_text = curr.text.strip()
        curr_text = header_pattern.sub('', curr_text).strip()

        if _is_heading_or_structural_block(curr):
            stitched.append(curr)
            i += 1
            continue

        while i + 1 < len(blocks):
            next_b = blocks[i + 1]
            if _is_heading_or_structural_block(next_b):
                break

            next_text = next_b.text.strip()
            next_text_cleaned = header_pattern.sub('', next_text).strip()
            
            if not next_text_cleaned:
                i += 1
                continue

            next_is_new_item = bool(bullet_start_pattern.match(next_text_cleaned))
            if next_is_new_item:
                break

            curr_ends_sentence = curr_text.endswith(sentence_end_chars)
            ends_in_dangling = bool(dangling_trailing_regex.search(curr_text))

            first_char = next_text_cleaned[0] if next_text_cleaned else ''
            next_starts_continuation = first_char.islower() or first_char in (',', '.', ';', ':', ')', ']', '}', '"', '”', '’')

            # Supplementary delivery/support mode sentence e.g. "Training will be conducted on VC." following a training requirement
            is_short_supplementary = (
                len(next_text_cleaned.split()) <= 7
                and bool(re.match(r'^(?:training|testing|support|meetings?|sessions?)\s+(?:will|shall)\s+be\s+(?:conducted|provided|held|done)\b', next_text_cleaned, re.IGNORECASE))
                and bool(re.search(r'\b(?:training|testing|support|meetings?)\b', curr_text, re.IGNORECASE))
            )

            should_stitch = False
            if ends_in_dangling:
                should_stitch = True
            elif not curr_ends_sentence and next_starts_continuation:
                should_stitch = True
            elif is_short_supplementary:
                should_stitch = True

            if should_stitch:
                lines = next_text_cleaned.split('\n')
                first_line = lines[0].strip()
                rest_lines = lines[1:]
                
                curr_text = curr_text + " " + first_line
                
                if rest_lines:
                    blocks[i + 1] = ExtractedBlock(
                        text="\n".join(rest_lines),
                        page_number=next_b.page_number,
                        section_title=next_b.section_title,
                        block_type=next_b.block_type
                    )
                    break
                else:
                    i += 1
            else:
                break

        stitched.append(
            ExtractedBlock(
                text=curr_text,
                page_number=curr.page_number,
                section_title=curr.section_title,
                block_type=curr.block_type
            )
        )
        i += 1

    return stitched


def _extract_clauses_rule_based(blocks: List[ExtractedBlock]) -> tuple[List[RawClause], int, int]:
    """
    Comprehensive rule-based clause extraction operating across the ENTIRE document.
    Never invents text; preserves source page and section for every clause.
    Returns (clauses, evaluated_count, filtered_count).
    """
    # Safeguard 2: Reconstruct wrapped/fragmented blocks across page boundaries first
    blocks = _stitch_blocks(blocks)

    clauses: List[RawClause] = []
    evaluated_count = 0
    filtered_count = 0
    
    # Imperatives & obligation modal verbs
    imperative_pattern = re.compile(
        r'\b(?:shall|must|required|mandatory|will|should|agrees?\s+to|is\s+required\s+to|are\s+required\s+to|is\s+expected\s+to|are\s+expected\s+to|needs?\s+to|responsible\s+for|covenants|undertakes|liability|penalty|sla|warrant(?:s|y)?|guarantee(?:s)?)\b',
        re.IGNORECASE
    )

    # Numbered clause headers e.g. "2.1 High Availability:", "REQ-01:", "3.2.1"
    numbered_clause_pattern = re.compile(
        r'^\s*(?:(?:\d{1,2}\.){1,3}\d{1,2}|\d{1,2}[\.\)]|[A-Z]\.\s+(?=[A-Z])|(?:REQ|RFP|SPEC|DELIV|SEC|TECH|FUNC|LEGAL|SLA)[-_:\s])',
        re.IGNORECASE
    )

    bullet_start_pattern = re.compile(
        r'^\s*(?:[•\-\*\uf0b7–—\u25cb\u25ef\u25e6\u2022\u2219\u2043]|\([0-9a-zA-Z]\)|\d{1,2}(?:\.\d{1,2}){0,3}[\.\)]|[a-zA-Z][\.\)]|[oO]\s+)\s*'
    )

    for b in blocks:
        text = b.text.strip()
        if not text or len(text) < 20:
            continue

        # Skip document title/metadata-only blocks
        lower_text = text.lower()
        if (
            lower_text.startswith("request for proposal")
            or lower_text.startswith("document ref:")
            or lower_text.startswith("issued by:")
            or lower_text.startswith("due date:")
            or lower_text.startswith("table of contents")
        ):
            continue

        tier = _classify_section_tier(b.section_title)
        has_explicit_id_in_block = bool(re.search(r'\bREQ-[A-Z0-9]+-\d{3,4}\b', text, re.IGNORECASE))

        # Context-aware section filtering:
        # Purely contextual sections (Purpose, Evaluation, Timeline, Submission Instructions) are skipped unless explicit REQ ID is present
        if tier in ["CONTEXT_PURPOSE", "CONTEXT_EVALUATION", "CONTEXT_TIMELINE", "CONTEXT_INSTRUCTIONS"] and not has_explicit_id_in_block:
            continue

        is_formal_req_section = (tier == "FORMAL_REQUIREMENTS")

        # Normalize unicode and font bullet characters
        norm_text = text.replace('\uf0b7', '\n• ').replace('', '\n• ').replace('\r\n', '\n')

        # Split block into individual numbered items or bullet points if present
        lines = [l.strip() for l in norm_text.split("\n") if l.strip()]
        
        # Check if block contains distinct numbered or bulleted items
        item_chunks: List[str] = []
        current_chunk: List[str] = []

        for line in lines:
            is_item_start = bool(
                numbered_clause_pattern.match(line)
                or bullet_start_pattern.match(line)
            )
            if is_item_start and current_chunk:
                item_chunks.append(" ".join(current_chunk))
                current_chunk = [re.sub(r'^\s*(?:[•\-\*\uf0b7–—\u25cb\u25ef\u25e6\u2022\u2219\u2043]|\([0-9a-zA-Z]\)|\d{1,2}(?:\.\d{1,2}){0,3}[\.\)]|[a-zA-Z][\.\)]|[oO]\s+)\s*', '', line)]
            else:
                current_chunk.append(line)
        if current_chunk:
            item_chunks.append(" ".join(current_chunk))

        # Intra-block supplementary sentence merging:
        # Merges short delivery/support channel/schedule bullets into the preceding parent bullet in the same topic
        merged_chunks: List[str] = []
        for chunk in item_chunks:
            c_clean = chunk.strip().strip('-*•o \t')
            if not c_clean:
                continue
            is_supplementary_chunk = (
                bool(merged_chunks)
                and len(c_clean.split()) <= 7
                and bool(re.match(r'^(?:training|testing|support|meetings?|sessions?)\s+(?:will|shall)\s+be\s+(?:conducted|provided|held|done|scheduled)\b', c_clean, re.IGNORECASE))
                and bool(re.search(r'\b(?:training|testing|support|meetings?|sessions?)\b', merged_chunks[-1], re.IGNORECASE))
            )
            if is_supplementary_chunk:
                merged_chunks[-1] = merged_chunks[-1].rstrip('.') + ". " + c_clean
            else:
                merged_chunks.append(chunk)

        for chunk in merged_chunks:
            chunk_clean = chunk.strip().strip('-*•o \t')
            if len(chunk_clean.split()) < 4 or len(chunk_clean) < 20:
                continue

            # Sub-split inline sub-bullets or multiple modal sentences within unnumbered prose
            sub_chunks = [chunk_clean]
            has_inline_subbullets = bool(re.search(r'\s+[oO]\s+(?=[A-Z])', chunk_clean))
            modal_count = len(re.findall(r'\b(?:shall|must|required|mandatory|will|should|is\s+required\s+to|are\s+required\s+to|is\s+expected\s+to)\b', chunk_clean, re.IGNORECASE))

            if has_inline_subbullets:
                split_bullets = [s.strip() for s in re.split(r'\s+[oO]\s+(?=[A-Z])', chunk_clean) if s.strip()]
                if len(split_bullets) >= 2:
                    sub_chunks = split_bullets
            elif modal_count >= 2 and not numbered_clause_pattern.match(chunk_clean):
                raw_sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])', chunk_clean) if s.strip()]
                if len(raw_sents) >= 2:
                    stitched_sents: List[str] = []
                    for sent in raw_sents:
                        is_short_supp = (
                            bool(stitched_sents)
                            and len(sent.split()) <= 7
                            and bool(re.match(r'^(?:training|testing|support|meetings?|sessions?)\s+(?:will|shall)\s+be\s+(?:conducted|provided|held|done|scheduled)\b', sent, re.IGNORECASE))
                            and bool(re.search(r'\b(?:training|testing|support|meetings?|sessions?)\b', stitched_sents[-1], re.IGNORECASE))
                        )
                        if is_short_supp:
                            stitched_sents[-1] = stitched_sents[-1].rstrip('.') + ". " + sent
                        else:
                            stitched_sents.append(sent)
                    sub_chunks = stitched_sents

            for sub_c in sub_chunks:
                clean_clause = _clean_clause_text(sub_c.strip().strip('-*•o \t'))
                if len(clean_clause.split()) < 4 or len(clean_clause) < 15:
                    continue

                evaluated_count += 1
                if _is_non_requirement_heading_or_criterion(clean_clause):
                    filtered_count += 1
                    continue

                # General-purpose qualifying conditions:
                # 1. Contains explicit requirement ID (e.g. REQ-TECH-001)
                # 2. Contains RFC 2119 obligation modals / imperatives (shall, must, is required to, will provide, agrees to)
                # 3. Explicitly numbered clause in specifications/deliverables (e.g. 2.1 ...)
                # 4. Or is in a formal requirement/scope section and contains substantive specification text
                has_explicit_id = bool(re.search(r'\bREQ-[A-Z0-9]+-\d{3,4}\b', clean_clause, re.IGNORECASE))
                has_imperatives = bool(imperative_pattern.search(clean_clause))
                has_numbering = bool(numbered_clause_pattern.match(clean_clause))

                if has_explicit_id or has_imperatives or has_numbering or (is_formal_req_section and len(clean_clause.split()) >= 6):
                    clauses.append(
                        RawClause(
                            clause_id="",  # Will be assigned canonical sequential ID during deduplication
                            text=clean_clause,
                            source_page=b.page_number,
                            source_section=b.section_title
                        )
                    )

    return clauses, evaluated_count, filtered_count


def _create_block_batches(
    blocks: List[ExtractedBlock],
    max_blocks_per_batch: int = 10,
    max_chars_per_batch: int = 3500
) -> List[List[ExtractedBlock]]:
    """Partitions blocks into size-bounded batches to prevent LLM context overflow."""
    batches: List[List[ExtractedBlock]] = []
    current_batch: List[ExtractedBlock] = []
    current_chars = 0

    for b in blocks:
        b_len = len(b.text)
        if current_batch and (len(current_batch) >= max_blocks_per_batch or (current_chars + b_len) > max_chars_per_batch):
            batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append(b)
        current_chars += b_len

    if current_batch:
        batches.append(current_batch)

    return batches


def _normalize_clause_sig(text: str) -> str:
    """Computes a robust semantic signature for deduplication."""
    # Strip leading common determiners / list markers e.g. "The", "A", "An", "All", "1.", "•", "o"
    clean = re.sub(r'^\s*(?:[•\-\*\uf0b7–—\u25cb\u25ef\u25e6\u2022\u2219\u2043]|\([0-9a-zA-Z]\)|\d{1,2}(?:\.\d{1,2}){0,3}[\.\)]|[a-zA-Z][\.\)]|[oO]\s+|\b(?:the|a|an|all)\b)\s*', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'[^a-z0-9]', '', clean.lower())
    return cleaned[:250]


def _sanitize_metadata(meta: RFPMetadata) -> RFPMetadata:
    """
    Strict safety check: replaces any legacy prohibited fictional placeholder
    with explicit 'INFORMATION REQUIRED' or None.
    """
    for prohibited in PROHIBITED_FICTIONAL_STRINGS:
        if prohibited.lower() in meta.title.lower():
            meta.title = "INFORMATION REQUIRED"
        if prohibited.lower() in meta.issuer.lower():
            meta.issuer = "INFORMATION REQUIRED"
        if meta.submission_deadline and prohibited.lower() in meta.submission_deadline.lower():
            meta.submission_deadline = None
        if meta.budget_or_scope and prohibited.lower() in meta.budget_or_scope.lower():
            meta.budget_or_scope = None

    if not meta.title or not meta.title.strip():
        meta.title = "INFORMATION REQUIRED"
    if not meta.issuer or not meta.issuer.strip():
        meta.issuer = "INFORMATION REQUIRED"
    if not meta.summary or not meta.summary.strip():
        meta.summary = "INFORMATION REQUIRED"

    return meta
