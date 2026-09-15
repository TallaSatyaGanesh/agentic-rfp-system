import os
import uuid
import shutil
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import CompanyDocument
from app.models.schemas import CompanyDocResponse
from app.services.document_parser import DocumentParserService
from app.rag.retriever import KnowledgeBaseRetriever
from app.rag.vector_store import VectorStoreManager
from app.core.config import settings

router = APIRouter(prefix="/api/company-knowledge", tags=["Company Knowledge Base (RAG)"])

@router.post("/upload", response_model=CompanyDocResponse)
async def upload_company_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: str = Form("General"),
    db: Session = Depends(get_db)
):
    """
    Uploads company document, parses text, and chunks/indexes into ChromaDB.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".doc", ".txt"]:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files are supported.")

    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    upload_dir = os.path.join(settings.UPLOAD_DIR, "company")
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, f"{doc_id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Parse content
    blocks = DocumentParserService.parse_document(file_path)
    full_text = "\n\n".join([b.text for b in blocks])
    doc_title = title or os.path.splitext(file.filename)[0].replace("_", " ").title()

    # Index into ChromaDB
    retriever = KnowledgeBaseRetriever()
    chunk_count = retriever.index_document(
        doc_id=doc_id,
        title=doc_title,
        filename=file.filename,
        content=full_text,
        category=category
    )

    # Save to SQLite
    company_doc = CompanyDocument(
        id=doc_id,
        title=doc_title,
        filename=file.filename,
        file_path=file_path,
        category=category,
        chunk_count=chunk_count
    )
    db.add(company_doc)
    db.commit()
    db.refresh(company_doc)

    return CompanyDocResponse(
        id=company_doc.id,
        title=company_doc.title,
        filename=company_doc.filename,
        category=company_doc.category,
        chunk_count=company_doc.chunk_count,
        indexed_at=company_doc.indexed_at
    )

@router.get("", response_model=List[CompanyDocResponse])
def list_company_documents(db: Session = Depends(get_db)):
    """Lists all indexed company collateral documents."""
    docs = db.query(CompanyDocument).order_by(CompanyDocument.indexed_at.desc()).all()
    return [
        CompanyDocResponse(
            id=d.id,
            title=d.title,
            filename=d.filename,
            category=d.category,
            chunk_count=d.chunk_count,
            indexed_at=d.indexed_at
        )
        for d in docs
    ]

@router.post("/query")
def test_query_rag(payload: Dict[str, Any]):
    """
    Test endpoint to evaluate semantic search queries against the knowledge base.
    Returns matching evidence chunks and similarity scores.
    """
    query_text = payload.get("query", "")
    threshold = payload.get("threshold", settings.SIMILARITY_THRESHOLD)
    top_k = payload.get("top_k", settings.RAG_TOP_K)

    retriever = KnowledgeBaseRetriever()
    results = retriever.retrieve_relevant_evidence(query=query_text, top_k=top_k, threshold=threshold)
    
    return {
        "query": query_text,
        "results_count": len(results),
        "threshold_applied": threshold,
        "results": results
    }

@router.delete("/clear")
def clear_knowledge_base(db: Session = Depends(get_db)):
    """Clears all company documents from ChromaDB and the database."""
    VectorStoreManager.get_instance().clear()
    db.query(CompanyDocument).delete()
    db.commit()
    return {"message": "Knowledge base cleared successfully."}
