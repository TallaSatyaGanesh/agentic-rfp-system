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

    # 3. Strip leading generic RFP requirement boilerplate e.g. "The vendor MUST provide", "The platform SHALL support"
    cleaned = re.sub(
        r'^(?:The\s+(?:vendor|bidder|contractor|platform|solution|system|company|service|software)\s+(?:must|shall|should|will|is\s+required\s+to|needs\s+to|agrees\s+to)\s+(?:provide|support|ensure|maintain|deliver|demonstrate|implement|feature|include)?\s*)',
        '',
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    return cleaned or text.strip()


def extract_content_tokens(text: str) -> Set[str]:
    """
    Extracts substantive alphanumeric content tokens from text,
    ignoring structural ID codes (e.g. req-tech-001, r-sec-99, clause-2.1) and stopwords.
    Preserves numbers and specification metrics (e.g. '9001', '27001', '16').
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
        content.add(tok_clean)
        # Add subparts of hyphenated terms if meaningful
        if "-" in tok_clean:
            for sub in tok_clean.split("-"):
                sub_clean = sub.strip(".-")
                if sub_clean and len(sub_clean) >= 2 and sub_clean not in RAG_STOP_WORDS:
                    content.add(sub_clean)
    return content


class KnowledgeBaseRetriever:
    def __init__(self):
        self.vector_store = VectorStoreManager.get_instance()

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 600, overlap: int = 100) -> List[str]:
        """
        Splits text into overlapping semantic chunks based on sentences/paragraphs.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: List[str] = []
        current_chunk = ""

        for p in paragraphs:
            if len(current_chunk) + len(p) <= chunk_size:
                current_chunk = f"{current_chunk}\n\n{p}".strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                # If paragraph itself is larger than chunk_size, split by sentences
                if len(p) > chunk_size:
                    sentences = re.split(r'(?<=[.!?]) +', p)
                    sub_chunk = ""
                    for s in sentences:
                        if len(sub_chunk) + len(s) <= chunk_size:
                            sub_chunk = f"{sub_chunk} {s}".strip()
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            sub_chunk = s
                    current_chunk = sub_chunk
                else:
                    current_chunk = p

        if current_chunk:
            chunks.append(current_chunk)

        # Fallback if no chunks generated
        if not chunks and text.strip():
            chunks = [text.strip()[:chunk_size]]

        return chunks

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

        chunks = self.chunk_text(content)
        if not chunks:
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

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{idx}"
            metadata = {
                "company_doc_id": doc_id,
                "chunk_id": chunk_id,
                "title": title,
                "filename": filename,
                "category": category,
                "page_number": page_number if page_number is not None else 1,
                "section": section if section else category,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "is_company_collateral": True
            }
            texts.append(chunk)
            metadatas.append(metadata)
            ids.append(chunk_id)

        self.vector_store.add_documents(
            texts=texts,
            metadatas=metadatas,
            ids=ids
        )
        return len(chunks)

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
                d_tokens = extract_content_tokens(doc_text)
                if not d_tokens:
                    d_tokens = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{2,}\b', doc_text.lower()))
                overlap_ratio = len(q_content & d_tokens) / max(len(q_content), 1)

                hybrid_score = round((cos_sim * 0.4) + (overlap_ratio * 0.6), 4)
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
