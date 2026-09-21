import os
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import re
from app.rag.vector_store import VectorStoreManager
from app.core.config import settings

logger = logging.getLogger(__name__)


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
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves company knowledge chunks matching the query.
        Applies strict similarity threshold gating:
        distance in cosine space is (1 - similarity).
        So similarity = 1 - distance.
        Only items with hybrid_score >= threshold are returned.
        Preserves full source traceability (doc_id, title, page, section, chunk_id, score).
        """
        k = top_k or settings.RAG_TOP_K
        min_similarity = threshold if threshold is not None else settings.SIMILARITY_THRESHOLD

        results = self.vector_store.query(query_text=query, n_results=k)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        valid_evidence: List[Dict[str, Any]] = []

        for doc_text, meta, dist in zip(documents, metadatas, distances):
            cos_sim = max(0.0, 1.0 - dist)

            # Hybrid scoring: Combine vector similarity with lexical token overlap
            q_tokens = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', query.lower()))
            d_tokens = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', doc_text.lower()))
            overlap_ratio = len(q_tokens & d_tokens) / max(len(q_tokens), 1)

            hybrid_score = round((cos_sim * 0.4) + (overlap_ratio * 0.6), 4)

            if hybrid_score >= min_similarity:
                valid_evidence.append({
                    "evidence_text": doc_text,
                    "similarity": hybrid_score,
                    "document_title": meta.get("title", "Unknown Document"),
                    "filename": meta.get("filename", "Unknown File"),
                    "category": meta.get("category", "General"),
                    "company_doc_id": meta.get("company_doc_id", ""),
                    "chunk_id": meta.get("chunk_id", ""),
                    "page_number": meta.get("page_number", 1),
                    "section": meta.get("section", meta.get("category", "General"))
                })

        return valid_evidence

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
