import os
import logging
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
import re
from app.rag.vector_store import VectorStoreManager
from app.core.config import settings

logger = logging.getLogger(__name__)


RAG_STOP_WORDS = {
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "what", "our", "do", "we", "by", "be", "this",
    "that", "from", "as", "it", "its", "all", "can", "must", "shall", "should",
    "will", "may", "would", "could", "vendor", "bidder", "provider", "company",
    "platform", "solution", "system", "requirement", "requirements", "provide",
    "provides", "support", "supports", "into", "onto", "such", "than", "then",
    "each", "every", "both", "either", "neither", "nor", "not", "any", "some",
    "via", "per", "using", "used", "which", "who", "whom", "whose", "where",
    "when", "why", "how", "before", "after", "during", "while", "ensure", "ensures"
}


def sanitize_requirement_query(text: str) -> str:
    """
    Strips structural requirement identifiers, section numbers, category labels,
    and generic RFP filler phrases to produce a clean semantic retrieval query.
    Works universally across arbitrary RFP ID schemes (e.g. REQ-TECH-001, R-SEC-99,
    Section 4.1.2, CLAUSE-2.1, SCHEDULE-PHASE-1, MANDATORY-REQ-001, A11) or un-prefixed natural language text.
    Preserves true domain terms like 'Role-based', 'Web-based', 'RESTful', 'Real-time'.
    """
    if not text:
        return ""
    cleaned = text.strip()

    # 1. Strip leading requirement codes / section numbers:
    # Requires known prefix keyword OR embedded digit in the code token (prevents stripping 'Web-based', 'Role-based')
    cleaned = re.sub(
        r'^(?:(?:Section|Clause|Schedule|Mandatory|Optional|Part|Annex|Appendix|Item|Article|Provision)\s+[\w\.\-]+|\b(?:REQ|RFP|RFQ|SEC|DOC|TECH|DEL|COMM|CERT|ELIG|SUB|CON|OPT|MAN|MANDATORY|CLAUSE|SCHEDULE|PART|FIELD|INTEG|TRAIN|CRYPTO|DAT|SYS|AUTH|ENC|AUDIT|R)(?:[-_][A-Za-z0-9\.]+)+\b|\b[A-Za-z0-9]+(?:[-_][A-Za-z0-9\.]*)+(?:[-_]\d+)+\b|\b[A-Za-z]\d{1,4}\b|\b\d+(?:\.\d+)+\b)\s*[:\.\-]?\s*',
        '',
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    # 2. Strip leading category labels if directly followed by requirement text
    cleaned = re.sub(
        r'^(?:Technical|Functional|Security|Compliance|Documentation|Delivery|Commercial|Eligibility|Submission|Contractual|Legal|General)\s*[:\.\-]?\s*',
        '',
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    # 3. Strip leading generic RFP requirement boilerplate e.g. "Vendor MUST provide", "The platform SHALL support"
    cleaned = re.sub(
        r'^(?:(?:The|Our)\s+)?(?:vendor|bidder|contractor|platform|solution|system|company|service|software)\s+(?:must|shall|should|will|is\s+required\s+to|needs\s+to|agrees\s+to)?\s*(?:provide|support|ensure|maintain|deliver|demonstrate|implement|feature|include)?\s*',
        '',
        cleaned,
        flags=re.IGNORECASE
    ).strip()
    cleaned = re.sub(r'^(?:a|an|the)\s+', '', cleaned, flags=re.IGNORECASE).strip()

    return cleaned or text.strip()


def _stem_token(tok: str) -> str:
    """Basic deterministic morphological stemming for English suffix variations."""
    t = tok.lower().strip(".-")
    for suffix in ["tions", "tion", "ments", "ment", "abilities", "ability", "ings", "ing", "ers", "er", "ies", "ied", "ed", "ses", "es", "s"]:
        if t.endswith(suffix) and len(t) - len(suffix) >= 3:
            return t[:-len(suffix)]
    return t


def extract_content_tokens(text: str) -> Set[str]:
    """
    Extracts substantive alphanumeric canonical content tokens from text,
    ignoring structural ID codes (e.g. req-tech-001, r-sec-99, clause-2.1) and stopwords.
    Preserves numbers and specification metrics (e.g. '9001', '27001', '16').
    Normalizes words to canonical morphological stems to ensure symmetric vocabulary alignment.
    """
    raw_tokens = re.findall(r'\b[a-zA-Z0-9_\-\.]{2,}\b', text.lower())
    content: Set[str] = set()
    for tok in raw_tokens:
        tok_clean = tok.strip(".-")
        if not tok_clean or len(tok_clean) < 2:
            continue
        if tok_clean in RAG_STOP_WORDS:
            continue
        # Skip structural ID codes (e.g. req-tech-001, r-sec-99, schedule-phase-1, clause-2.1)
        if re.match(r'^(?:req|rfp|sec|doc|tech|del|comm|cert|elig|sub|con|opt|man|mandatory|clause|schedule|part|field|integ|train|crypto)[-_][a-z0-9_\.-]+$', tok_clean):
            continue
        if "-" in tok_clean:
            for sub in tok_clean.split("-"):
                sub_clean = sub.strip(".-")
                if sub_clean and len(sub_clean) >= 2 and sub_clean not in RAG_STOP_WORDS:
                    content.add(_stem_token(sub_clean))
        else:
            content.add(_stem_token(tok_clean))
    return content


# Explicit non-compliance and limitation patterns for snippet extraction
NON_COMPLIANT_PATTERNS = re.compile(
    r'\b(?:(?:do|does|did|is|are|was|were|can|could|will|would)\s+(?:not|never)\s+(?:currently\s+|presently\s+|natively\s+|directly\s+)?(?:support|provide|offer|feature|hold|comply|guarantee|include)|'
    r'not\s+(?:currently\s+|presently\s+|natively\s+)?(?:supported|provided|offered|held|certified|available|compliant|included)|'
    r'unsupported|out\s+of\s+scope|explicitly\s+excluded|no\s+plans\s+to\s+support|cannot\s+comply|cannot\s+provide|cannot\s+support|unheld|business\s+hours\s+only)\b',
    re.IGNORECASE
)

PARTIAL_COMPLIANT_PATTERNS = re.compile(
    r'\b(?:partially\s+supported|partial\s+support|limited\s+support|requires\s+custom|workaround|'
    r'conditional|planned\s+for|roadmap|beta|add-on\s+required|subject\s+to\s+third[- ]party|'
    r'available\s+only\s+during\s+business\s+hours|business\s+hours\s+only|'
    r'partially\s+compliant)\b',
    re.IGNORECASE
)

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


def extract_relevant_evidence_snippet(
    query_or_req: str,
    evidence_text: Optional[str],
    status: Optional[str] = None,
    max_length: int = 240
) -> str:
    """
    Extracts a concise, evidence-grounded sentence or context window from a retrieved knowledge chunk.
    Prioritizes candidate units with strong requirement token overlap, specification/metric alignment,
    and status-specific semantic matches (e.g. refusal statements for NON_COMPLIANT items).
    Invariance to section/paragraph ordering: avoids naive prefix slicing.
    """
    if not evidence_text or not evidence_text.strip():
        return ""

    clean_ev = evidence_text.strip()

    # Segment evidence into candidate units (paragraphs, bullet points, and individual sentences)
    raw_paras = [p.strip() for p in re.split(r'\n\s*\n', clean_ev) if p.strip()]
    candidate_units: List[str] = []
    seen_units: Set[str] = set()

    for p in raw_paras:
        # Check bullet points / numbered list lines
        lines = [line.strip() for line in p.split("\n") if line.strip()]
        for line in lines:
            cleaned_line = re.sub(r'^[-*•\d\.\)\s]+', '', line).strip()
            if len(cleaned_line) >= 15 and cleaned_line.lower() not in seen_units:
                candidate_units.append(line.strip())
                seen_units.add(cleaned_line.lower())

        # Check individual sentences
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', p) if s.strip()]
        for s in sentences:
            cleaned_s = re.sub(r'^[-*•\d\.\)\s]+', '', s).strip()
            if len(cleaned_s) >= 15 and cleaned_s.lower() not in seen_units:
                candidate_units.append(s.strip())
                seen_units.add(cleaned_s.lower())

        # Whole paragraph if reasonably concise
        if len(p) <= max_length and p.lower() not in seen_units:
            candidate_units.append(p)
            seen_units.add(p.lower())

    if not candidate_units:
        candidate_units = [clean_ev]

    sanitized_q = sanitize_requirement_query(query_or_req)
    req_tokens = extract_content_tokens(sanitized_q or query_or_req)
    # Extract numerical, acronym, and hyphenated specification tokens (e.g. 27001, 99.95%, 16, 24/7, aes-256)
    spec_tokens = set(re.findall(
        r'\b(?:\d+(?:\.\d+)*%?|[a-z0-9]+-[a-z0-9]+|\b(?:24/7|24x7|mfa|rbac|sso|saml|oidc|aes|tls|fips|rto|rpo|sla)\b)\b',
        (sanitized_q or query_or_req).lower()
    ))

    scored_candidates = []
    norm_status = (status or "").upper()

    for unit in candidate_units:
        unit_clean = re.sub(r'^[-*•\d\.\)\s]+', '', unit).strip()
        unit_tokens = extract_content_tokens(unit_clean)
        token_overlap = len(req_tokens & unit_tokens)

        unit_lower = unit_clean.lower()
        spec_overlap = sum(1 for tok in spec_tokens if tok in unit_lower)

        has_non_comp = bool(NON_COMPLIANT_PATTERNS.search(unit_clean))
        has_partial = bool(PARTIAL_COMPLIANT_PATTERNS.search(unit_clean))
        has_affirmative = bool(AFFIRMATIVE_PATTERNS.search(unit_clean))

        score = 0.0
        score += (token_overlap * 2.0)
        score += (spec_overlap * 3.5)

        if norm_status == "NON_COMPLIANT":
            if has_non_comp:
                score += 8.0
                if token_overlap > 0 or spec_overlap > 0:
                    score += 4.0
            if has_affirmative and not has_non_comp and token_overlap == 0:
                score -= 4.0
        elif norm_status == "PARTIALLY_COMPLIANT":
            if has_partial:
                score += 8.0
            elif has_non_comp:
                score += 4.0
        elif norm_status == "COMPLIANT":
            if has_affirmative:
                score += 4.0
            if has_non_comp and not has_affirmative:
                score -= 6.0
        else:
            if has_non_comp or has_partial or has_affirmative:
                score += 2.0

        scored_candidates.append((score, token_overlap, spec_overlap, unit_clean))

    scored_candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    best_score, best_tok, best_spec, best_unit = scored_candidates[0] if scored_candidates else (0, 0, 0, "")

    if best_score > 0 and best_unit:
        selected = best_unit
    else:
        # Fallback when no candidate scored positively
        if norm_status == "NON_COMPLIANT":
            for _, _, _, u in scored_candidates:
                if NON_COMPLIANT_PATTERNS.search(u):
                    selected = u
                    break
            else:
                return "Documented limitation in company collateral indicates requirement is unsupported."
        elif norm_status == "PARTIALLY_COMPLIANT":
            for _, _, _, u in scored_candidates:
                if PARTIAL_COMPLIANT_PATTERNS.search(u):
                    selected = u
                    break
            else:
                return "Documented partial capability."
        elif len(clean_ev) <= max_length:
            selected = clean_ev
        else:
            selected = candidate_units[0].strip()

    clean_selected = re.sub(r'^\s*[-*•]\s*', '', selected).strip()
    clean_selected = re.sub(r'\s+', ' ', clean_selected)

    if len(clean_selected) > max_length:
        truncated = clean_selected[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > int(max_length * 0.7):
            clean_selected = truncated[:last_space].rstrip('.,;-') + "..."
        else:
            clean_selected = truncated.rstrip('.,;-') + "..."

    return clean_selected


class KnowledgeBaseRetriever:
    def __init__(self):
        self.vector_store = VectorStoreManager.get_instance()

    @classmethod
    def chunk_document_sections(
        cls,
        text: str,
        chunk_size: int = 600,
        overlap: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Splits text into section-aware semantic chunks.
        Recognizes numbered section headings (e.g. '1.', '2.', '3.1'), markdown headings ('#', '##'),
        and standalone section headers, preventing unrelated document sections from being merged into one chunk.
        """
        if not text or not text.strip():
            return []

        section_pattern = re.compile(
            r'^(?:'
            r'#{1,6}\s+(?P<h_md>[^\n]+)|'
            r'(?P<h_num>(?:(?:\d+\.){1,4}\s+|\b(?:Section|Chapter|Article|Clause|Schedule|Part|Appendix|Annex)\s+(?:\d+|[A-Z])(?:\.[\w\-]+)*\s*[:\.\-]?\s*)[^\n]+)'
            r')$',
            re.MULTILINE
        )

        matches = list(section_pattern.finditer(text))
        sections: List[Dict[str, str]] = []

        if matches:
            first_start = matches[0].start()
            if first_start > 0:
                preamble = text[:first_start].strip()
                if preamble:
                    sections.append({
                        "section": "Overview",
                        "text": preamble
                    })

            for i, match in enumerate(matches):
                header_line = match.group(0).strip()
                clean_title = re.sub(r'^#{1,6}\s+', '', header_line).strip()
                start_pos = match.start()
                end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                sec_text = text[start_pos:end_pos].strip()
                if sec_text:
                    sections.append({
                        "section": clean_title,
                        "text": sec_text
                    })
        else:
            sections = [{"section": "General", "text": text.strip()}]

        chunks: List[Dict[str, Any]] = []

        for sec in sections:
            sec_title = sec["section"]
            sec_text = sec["text"]

            if len(sec_text) <= chunk_size:
                chunks.append({
                    "text": sec_text,
                    "section": sec_title
                })
            else:
                paragraphs = [p.strip() for p in sec_text.split("\n\n") if p.strip()]
                current_chunk = ""
                for p in paragraphs:
                    if len(current_chunk) + len(p) <= chunk_size:
                        current_chunk = f"{current_chunk}\n\n{p}".strip()
                    else:
                        if current_chunk:
                            chunks.append({
                                "text": current_chunk,
                                "section": sec_title
                            })
                        if len(p) > chunk_size:
                            sentences = re.split(r'(?<=[.!?])\s+', p)
                            sub_chunk = ""
                            for s in sentences:
                                if len(sub_chunk) + len(s) <= chunk_size:
                                    sub_chunk = f"{sub_chunk} {s}".strip()
                                else:
                                    if sub_chunk:
                                        chunks.append({
                                            "text": sub_chunk,
                                            "section": sec_title
                                        })
                                    sub_chunk = s
                            current_chunk = sub_chunk
                        else:
                            current_chunk = p
                if current_chunk:
                    chunks.append({
                        "text": current_chunk,
                        "section": sec_title
                    })

        if not chunks and text.strip():
            chunks = [{"text": text.strip()[:chunk_size], "section": "General"}]

        return chunks

    @classmethod
    def chunk_text(cls, text: str, chunk_size: int = 600, overlap: int = 100) -> List[str]:
        """
        Splits text into semantic chunks. Preserves backward compatibility.
        """
        return [c["text"] for c in cls.chunk_document_sections(text, chunk_size=chunk_size, overlap=overlap)]

    def index_document(
        self,
        doc_id: str,
        title: str,
        filename: str,
        content: str,
        category: str = "General",
        page_number: Optional[int] = 1,
        section: Optional[str] = None
    ) -> int:
        """
        Chunks and indexes a company collateral document into ChromaDB.
        Preserves document ID, title, filename, page, and section metadata.
        Guarantees idempotency by clearing existing chunks for doc_id first.
        Returns the number of chunks indexed.
        """
        # Guardrail: Never allow RFP/tender documents to be indexed as company collateral
        lower_file = filename.lower()
        if (any(term in lower_file for term in ["rfp", "tender", "rfq", "solicitation"]) or category.lower() in ["rfp", "tender"]) and not doc_id.startswith("comp_"):
            raise ValueError(f"RFP document '{filename}' cannot be indexed into company knowledge base.")

        chunk_items = self.chunk_document_sections(content)
        if not chunk_items:
            return 0

        # Idempotency guarantee: purge existing chunks for this doc_id before re-adding
        try:
            if self.vector_store._collection:
                self.vector_store._collection.delete(where={"company_doc_id": doc_id})
        except Exception:
            pass

        texts = []
        metadatas = []
        ids = []

        for idx, chunk_info in enumerate(chunk_items):
            chunk_id = f"{doc_id}_chunk_{idx}"
            chunk_text = chunk_info["text"]
            chunk_section = chunk_info.get("section")
            if not chunk_section or chunk_section == "General":
                chunk_section = section or category

            metadata = {
                "company_doc_id": doc_id,
                "chunk_id": chunk_id,
                "title": title,
                "filename": filename,
                "category": category,
                "page_number": page_number if page_number is not None else 1,
                "section": chunk_section,
                "chunk_index": idx,
                "total_chunks": len(chunk_items),
                "is_company_collateral": True
            }
            texts.append(chunk_text)
            metadatas.append(metadata)
            ids.append(chunk_id)

        self.vector_store.add_documents(
            texts=texts,
            metadatas=metadatas,
            ids=ids
        )
        return len(chunk_items)

    def retrieve_relevant_evidence(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
        fallback_queries: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves company knowledge chunks matching the query using stopword-aware hybrid scoring.
        Applies multi-query candidate pooling to maximize recall while preserving source traceability.
        Only items with hybrid_score >= threshold are returned.
        """
        k = top_k or settings.RAG_TOP_K
        min_similarity = threshold if threshold is not None else settings.SIMILARITY_THRESHOLD

        # 1. Build list of candidate queries (Sanitized query + Raw query + Optional domain keywords)
        sanitized = sanitize_requirement_query(query)
        queries_to_run = [sanitized] if sanitized else []
        if query and query != sanitized and query not in queries_to_run:
            queries_to_run.append(query)
        if fallback_queries:
            for fq in fallback_queries:
                if fq and fq.strip() and fq.strip() not in queries_to_run:
                    queries_to_run.append(fq.strip())

        if not queries_to_run:
            return []

        # 2. Pool candidate chunks from all query representations
        candidates_by_chunk_id: Dict[str, Dict[str, Any]] = {}

        for q_str in queries_to_run:
            results = self.vector_store.query(query_text=q_str, n_results=max(k, 8))
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            q_content = extract_content_tokens(q_str)
            if not q_content:
                q_content = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{2,}\b', q_str.lower()))

            for doc_text, meta, dist in zip(documents, metadatas, distances):
                cos_sim = max(0.0, 1.0 - dist)
                meta_ctx = f"{meta.get('title', '')} {meta.get('category', '')} {meta.get('section', '')}"
                d_tokens = extract_content_tokens(f"{meta_ctx} {doc_text}".strip())
                if not d_tokens:
                    d_tokens = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{2,}\b', f"{meta_ctx} {doc_text}".lower()))
                overlap_ratio = len(q_content & d_tokens) / max(len(q_content), 1)

                # Balanced hybrid score combining dense vector cosine similarity and substantive lexical overlap
                hybrid_score = round((cos_sim * 0.50) + (overlap_ratio * 0.50), 4)
                chunk_id = meta.get("chunk_id", f"{meta.get('company_doc_id', '')}_{hash(doc_text)}")
                # Deduplicate by normalized text to ensure distinct evidence chunks across collections
                dedup_key = doc_text.strip()

                candidate_entry = {
                    "evidence_text": doc_text,
                    "similarity": hybrid_score,
                    "document_title": meta.get("title", "Unknown Document"),
                    "filename": meta.get("filename", "Unknown File"),
                    "category": meta.get("category", "General"),
                    "company_doc_id": meta.get("company_doc_id", ""),
                    "chunk_id": chunk_id,
                    "page_number": meta.get("page_number", 1),
                    "section": meta.get("section", meta.get("category", "General"))
                }

                # Keep candidate with highest hybrid score across query runs
                if dedup_key not in candidates_by_chunk_id or hybrid_score > candidates_by_chunk_id[dedup_key]["similarity"]:
                    candidates_by_chunk_id[dedup_key] = candidate_entry

        # 3. Filter candidates meeting the minimum similarity threshold and sort descending
        valid_evidence = [
            cand for cand in candidates_by_chunk_id.values()
            if cand["similarity"] >= min_similarity
        ]
        valid_evidence.sort(key=lambda x: x["similarity"], reverse=True)

        return valid_evidence[:k]

    def sync_knowledge_base_from_db(self, db) -> int:
        """
        Idempotently synchronizes ChromaDB vector store from persistent CompanyDocument records.
        If ChromaDB is empty or missing vectors for registered documents, restores file content
        from local disk or Supabase Storage and re-indexes them.
        Returns the total number of documents synchronized.
        """
        from app.db.models import CompanyDocument
        from app.services.storage_service import StorageService
        from app.services.document_parser import DocumentParserService

        docs = db.query(CompanyDocument).all()
        if not docs:
            return 0

        existing_doc_ids = set()
        try:
            if self.vector_store._collection:
                coll_data = self.vector_store._collection.get(include=["metadatas"])
                for meta in coll_data.get("metadatas", []):
                    cid = meta.get("company_doc_id")
                    if cid:
                        existing_doc_ids.add(cid)
        except Exception as e:
            logger.warning(f"[KnowledgeBaseRetriever] Error checking ChromaDB collection: {e}")

        synced_count = 0
        for doc in docs:
            # If already indexed, skip for idempotency
            if doc.id in existing_doc_ids:
                continue

            local_file = StorageService.ensure_local_company_file(
                file_path=doc.file_path,
                doc_id=doc.id,
                filename=doc.filename
            )

            # Fallback to root workspace collateral files if not found
            if not local_file or not os.path.exists(local_file):
                root_fallback = Path(settings.UPLOAD_DIR).parent.parent.parent / doc.filename
                if os.path.exists(root_fallback):
                    local_file = str(root_fallback)

            if local_file and os.path.exists(local_file):
                try:
                    blocks = DocumentParserService.parse_document(local_file)
                    full_text = "\n\n".join([b.text for b in blocks])
                    if full_text.strip():
                        chunks = self.index_document(
                            doc_id=doc.id,
                            title=doc.title,
                            filename=doc.filename,
                            content=full_text,
                            category=doc.category
                        )
                        synced_count += 1
                        logger.info(
                            f"[KnowledgeBaseRetriever] Auto-synchronized {doc.id} ({doc.title}) into ChromaDB ({chunks} chunks)."
                        )
                except Exception as ex:
                    logger.error(f"[KnowledgeBaseRetriever] Error indexing {doc.id} ({doc.filename}): {ex}")
            else:
                logger.warning(f"[KnowledgeBaseRetriever] Could not locate file for company doc {doc.id} ({doc.filename}).")

        return synced_count
