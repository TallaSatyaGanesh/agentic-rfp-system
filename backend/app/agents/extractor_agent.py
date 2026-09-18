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
    raw_clauses = _extract_all_clauses(blocks)

    # 4. Final safety sanity check: ensure no prohibited fictional strings exist
    metadata = _sanitize_metadata(metadata)

    log_entry = {
        "agent": "Extraction Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": f"Extracted metadata and identified {len(raw_clauses)} candidate clauses across {len(blocks)} blocks covering all pages."
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


def _extract_all_clauses(blocks: List[ExtractedBlock]) -> List[RawClause]:
    """
    Extracts candidate clauses across the ENTIRE document (all pages).
    Processes blocks in batches to keep within context limits if LLM is active,
    and runs a comprehensive rule-based extractor to guarantee complete,
    traceable coverage without any hallucinations.
    """
    raw_clauses: List[RawClause] = []
    seen_signatures: Set[str] = set()

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
                        if _is_non_requirement_heading_or_criterion(c.text):
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
    rule_clauses = _extract_clauses_rule_based(blocks)
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

    return formatted_clauses


def _classify_section_tier(section_title: str) -> str:
    """
    Classifies a section title into structural hierarchy tiers:
    - CONTEXT_PURPOSE: Purpose, Introduction, Executive Summary, Background, Objective
    - CONTEXT_EVALUATION: Evaluation Criteria, Selection Criteria, Scoring
    - CONTEXT_TIMELINE: Timeline, Schedule, Key Dates, Milestones
    - CONTEXT_INSTRUCTIONS: Vendor Instructions, Submission Guidelines, Proposal Format
    - FORMAL_REQUIREMENTS: Requirements, System Requirements, Specifications, Compliance Matrix, Terms
    - SCOPE_OF_WORK: Scope of Work, Scope, Services Required, Vendor Obligations, Technical Approach
    - GENERAL: Default/unspecified
    """
    sec = section_title.strip().lower()

    # 1. Purpose / Introduction / Executive Summary / Overview
    if re.search(r'\b(?:purpose|introduction|executive\s+summary|background|objective|procurement\s+objective|about\s+the\s+project|overview)\b', sec):
        if not re.search(r'\b(?:requirement|specification)\b', sec):
            return "CONTEXT_PURPOSE"

    # 2. Evaluation / Scoring Criteria
    if re.search(r'\b(?:evaluation|scoring|selection\s+criteria|award\s+criteria|rating\s+criteria)\b', sec):
        return "CONTEXT_EVALUATION"

    # 3. Timeline / Schedule / Key Dates / Milestones
    if re.search(r'\b(?:timeline|schedule|key\s+dates|milestones|procurement\s+timeline|due\s+dates?)\b', sec):
        return "CONTEXT_TIMELINE"

    # 4. Instructions / Submission Guidelines / Format / Packaging / Vendor Response
    if re.search(r'\b(?:submission\s+instructions|vendor\s+response|vendor\s+instructions|proposal\s+instructions|format\s+of\s+proposal|submission\s+guidelines|instructions\s+to\s+bidders|response\s+format|proposal\s+submission)\b', sec):
        return "CONTEXT_INSTRUCTIONS"

    # 5. Formal Requirements / Specifications / Technical / Compliance
    if re.search(r'\b(?:requirements?|specifications?|technical\s+specifications?|compliance\s+matrix|mandatory\s+requirements?|system\s+requirements?|functional\s+requirements?|security\s+requirements?|commercial\s+terms|legal\s+terms|contractual\s+terms)\b', sec):
        return "FORMAL_REQUIREMENTS"

    # 6. Scope of Work / Deliverables / Obligations
    if re.search(r'\b(?:scope\s+of\s+work|scope|services\s+required|vendor\s+obligations|technical\s+approach|statement\s+of\s+work|sow|deliverables?)\b', sec):
        return "SCOPE_OF_WORK"

    return "GENERAL"


def _is_non_requirement_heading_or_criterion(text: str) -> bool:
    """
    Returns True if the text represents a section header, subsection title,
    evaluation/scoring criterion, or introductory preamble line that MUST NOT
    be extracted as a requirement clause or assigned a REQ-* ID.
    
    Top-priority override: Explicit IDs (e.g. REQ-TECH-001:) are always preserved.
    """
    clean_text = text.strip()
    if not clean_text:
        return True

    # Top-priority override: explicit requirement IDs present in text
    if re.search(r'\bREQ-[A-Z0-9]+-\d{3,4}\b', clean_text, re.IGNORECASE):
        return False

    # Check for binding obligation modals
    has_obligation_modal = bool(re.search(
        r'\b(?:shall|must|is\s+required\s+to|are\s+required\s+to|must\s+provide|shall\s+agree|must\s+hold|must\s+support|shall\s+reside)\b',
        clean_text,
        re.IGNORECASE
    ))

    # 1. Section / Chapter Title Headers (e.g., "SECTION 2: TECHNICAL & INFRASTRUCTURE REQUIREMENTS", "Section A: Platform Functional Expectations", "1. Purpose", "2. Scope of Work", "3. Requirements")
    if re.match(r'^(?:SECTION|CHAPTER|APPENDIX|PART|\d+\.)\s+[A-Za-z0-9\s&,\.\-–—:]+$', clean_text, re.IGNORECASE) and not has_obligation_modal:
        return True

    # 2. Subsection Title Headings (e.g., "1. Technical Specifications", "5.1 Commercial Terms")
    if re.match(r'^\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z0-9\s&,\.\-–—]+$', clean_text) and not has_obligation_modal:
        return True

    # 3. Evaluation / Scoring Preamble & Weightings (e.g., "Proposals will be evaluated based on:", "Security & Compliance Verification (25%)", "Technical Architecture (30%)")
    if (
        re.search(r'\b(?:evaluated\s+based\s+on|evaluation(?:\s+&\s+scoring)?\s+criteria|scoring\s+(?:matrix|criteria)|weighting|award\s+criteria)\b', clean_text, re.IGNORECASE)
        or re.search(r'\(\s*\d+%\s*\)', clean_text)
        or re.search(r'\b\d+\s*(?:%|percent|points)\b', clean_text, re.IGNORECASE)
    ) and not has_obligation_modal:
        return True

    # 4. Document Titles & Subtitles (e.g., "System Specification & Commercial Requirements Document", "REQUEST FOR PROPOSAL (RFP)", "Scope of Work & Vendor Commitments")
    if (
        re.search(r'\b(?:REQUEST\s+FOR\s+PROPOSAL|SOLICITATION\s+DOCUMENT|TENDER\s+DOCUMENT)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:System\s+Specification|Requirements\s+Document|Commercial\s+Requirements\s+Document|Specification\s+Document|Scope\s+of\s+Work|Vendor\s+Commitments)\b', clean_text, re.IGNORECASE)
    ) and not has_obligation_modal:
        return True

    # 5. Table Column Headers (e.g., "Req ID Category Requirement Specification Mandatory", "ID Description Priority Mandatory")
    if (
        re.search(r'\b(?:Req\s*ID|Requirement\s*ID|Item\s*#|Clause\s*#)\b', clean_text, re.IGNORECASE)
        and re.search(r'\b(?:Category|Specification|Description|Mandatory|Priority|Status)\b', clean_text, re.IGNORECASE)
    ) and not has_obligation_modal:
        return True

    # 6. Vendor Response Instructions & Proposal Answering Meta-Guidelines
    # (e.g. "Vendors should clearly state their compliance with each requirement", "Vendors must not make unsupported claims", "Where a requirement cannot be fully confirmed, the vendor should identify the limitation...")
    if (
        re.search(r'\b(?:state\s+(?:their|its)?\s*compliance|indicate\s+(?:their|its)?\s*compliance|confirm\s+(?:their|its)?\s*compliance)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:unsupported\s+claims|cannot\s+be\s+(?:fully\s+)?confirmed|identify\s+the\s+limitation)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:respond\s+to\s+(?:each|this|every)\s+requirement|address\s+(?:each|all)\s+requirements?\s+in\s+(?:the|their|its)\s+proposal)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:format\s+(?:their|its|the)\s+response|complete\s+(?:the|this)\s+compliance\s+(?:matrix|table))\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:proposals?|bidders?|vendors?|contractors?)\s+(?:shall|must|should|are\s+required\s+to)\s+(?:clearly\s+)?(?:state|explain|describe|detail|indicate)\s+(?:how|their|its|whether|compliance)\b', clean_text, re.IGNORECASE)
        or re.search(r'\b(?:proposals?|bidders?|vendors?)\s+(?:must|shall|should)\s+not\s+make\s+(?:any\s+)?(?:unsupported|false|unverified)\b', clean_text, re.IGNORECASE)
    ):
        return True

    return False


def _extract_clauses_rule_based(blocks: List[ExtractedBlock]) -> List[RawClause]:
    """
    Comprehensive rule-based clause extraction operating across the ENTIRE document.
    Never invents text; preserves source page and section for every clause.
    """
    clauses: List[RawClause] = []
    
    # Imperatives & obligation modal verbs
    imperative_pattern = re.compile(
        r'\b(?:shall|must|required|mandatory|will|should|agrees?\s+to|is\s+required\s+to|are\s+required\s+to|is\s+expected\s+to|are\s+expected\s+to|needs?\s+to|responsible\s+for|covenants|undertakes|liability|penalty|sla|warrant(?:s|y)?|guarantee(?:s)?)\b',
        re.IGNORECASE
    )

    # Numbered clause headers e.g. "2.1 High Availability:", "REQ-01:", "3.2.1"
    numbered_clause_pattern = re.compile(
        r'^\s*(?:(?:\d+\.){1,3}\d*\s+(?=[A-Z])|(?:\d+\))\s+|[A-Z]\.\s+(?=[A-Z])|(?:REQ|RFP|SPEC|DELIV|SEC|TECH|FUNC|LEGAL|SLA)[-_:\s])',
        re.IGNORECASE
    )

    # Check if document contains a dedicated FORMAL_REQUIREMENTS tier section or explicit requirement IDs
    has_formal_requirements_tier = any(
        _classify_section_tier(b.section_title) == "FORMAL_REQUIREMENTS"
        or bool(re.search(r'\bREQ-[A-Z0-9]+-\d{3,4}\b', b.text, re.IGNORECASE))
        for b in blocks
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
            or lower_text == "section 1: executive summary & procurement objective"
        ):
            continue

        tier = _classify_section_tier(b.section_title)
        has_explicit_id_in_block = bool(re.search(r'\bREQ-[A-Z0-9]+-\d{3,4}\b', text, re.IGNORECASE))

        # Context-aware section filtering:
        # 1. Purely contextual sections (Purpose, Evaluation, Timeline, Submission Instructions) are skipped
        if tier in ["CONTEXT_PURPOSE", "CONTEXT_EVALUATION", "CONTEXT_TIMELINE", "CONTEXT_INSTRUCTIONS"] and not has_explicit_id_in_block:
            continue

        # 2. When a dedicated formal Requirements table/section exists, high-level Scope of Work summary overview blocks are skipped
        if has_formal_requirements_tier and tier == "SCOPE_OF_WORK" and not has_explicit_id_in_block:
            continue

        is_req_section = (tier == "FORMAL_REQUIREMENTS") or (not has_formal_requirements_tier and tier in ["SCOPE_OF_WORK", "GENERAL"])

        # Split block into individual numbered items or bullet points if present
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        
        # Check if block contains distinct numbered or bulleted items
        item_chunks: List[str] = []
        current_chunk: List[str] = []

        for line in lines:
            is_item_start = (
                numbered_clause_pattern.match(line)
                or line.startswith("•")
                or line.startswith("- ")
                or line.startswith("* ")
            )
            if is_item_start and current_chunk:
                item_chunks.append(" ".join(current_chunk))
                current_chunk = [line]
            else:
                current_chunk.append(line)
        if current_chunk:
            item_chunks.append(" ".join(current_chunk))

        for chunk in item_chunks:
            chunk_clean = chunk.strip().strip('-*• \t')
            if len(chunk_clean.split()) < 4 or len(chunk_clean) < 20:
                continue

            # Sub-split paragraph into individual sentences if multiple distinct obligation modals exist in unnumbered prose
            sub_chunks = [chunk_clean]
            modal_count = len(re.findall(r'\b(?:shall|must|required|mandatory|will|should|is\s+required\s+to|are\s+required\s+to|is\s+expected\s+to)\b', chunk_clean, re.IGNORECASE))
            if modal_count >= 2 and not numbered_clause_pattern.match(chunk_clean):
                split_sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])', chunk_clean) if s.strip()]
                if len(split_sents) >= 2:
                    sub_chunks = split_sents

            for sub_c in sub_chunks:
                if len(sub_c.split()) < 4 or len(sub_c) < 15:
                    continue

                if _is_non_requirement_heading_or_criterion(sub_c):
                    continue

                # Qualifying condition:
                # 1. Contains explicit requirement ID
                # 2. Contains RFC 2119 imperatives / obligation modals
                # 3. OR is explicitly numbered (e.g. 2.1 ...)
                # 4. OR is in a formal requirement section and contains substantive specifications
                has_explicit_id = bool(re.search(r'\bREQ-[A-Z0-9]+-\d{3,4}\b', sub_c, re.IGNORECASE))
                has_imperatives = bool(imperative_pattern.search(sub_c))
                has_numbering = bool(numbered_clause_pattern.match(sub_c))

                if has_explicit_id or has_imperatives or has_numbering or (is_req_section and len(sub_c.split()) >= 6):
                    clauses.append(
                        RawClause(
                            clause_id="",  # Will be assigned canonical sequential ID during deduplication
                            text=sub_c,
                            source_page=b.page_number,
                            source_section=b.section_title
                        )
                    )

    return clauses


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
    """Computes a normalized signature for deduplication."""
    cleaned = re.sub(r'[^a-z0-9]', '', text.lower())
    return cleaned[:100]


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
