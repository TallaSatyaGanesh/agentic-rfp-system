import os
import uuid
import shutil
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import RFPDocument, Requirement, ComplianceRecord, RiskRecord, ClarificationQuestion, Proposal
from app.models.schemas import RFPUploadResponse
from app.services.document_parser import DocumentParserService
from app.services.exporter import ProposalExporterService
from app.services.storage_service import StorageService
from app.core.config import settings

router = APIRouter(prefix="/api/rfp", tags=["RFP Documents"])

RUNNING_WORKFLOW_STATUSES = {
    "PROCESSING",
    "EXTRACTING",
    "CLASSIFYING",
    "ANALYZING_COMPLIANCE",
    "ASSESSING_RISKS",
    "WRITING_PROPOSAL",
    "REVISING",
    "REVIEWING",
    "RESUMING",
    "ANALYZING",
}

PROTECTED_PROJECT_STATUSES = {
    "APPROVED_FOR_EXPORT",
    "COMPLETED",
}

@router.post("/upload", response_model=RFPUploadResponse)
async def upload_rfp(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Accepts PDF or DOCX RFP document, saves to storage, and registers project in database.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".doc", ".txt"]:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files are supported.")

    rfp_id = f"rfp_{uuid.uuid4().hex[:10]}"
    file_bytes = await file.read()
    
    # Save locally and sync to Supabase Storage if configured
    file_path = StorageService.upload_rfp_document(rfp_id, file.filename, file_bytes)

    file_size = len(file_bytes)
    page_count = DocumentParserService.get_page_count(file_path)
    title = os.path.splitext(file.filename)[0].replace("_", " ").title()

    rfp_record = RFPDocument(
        id=rfp_id,
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        page_count=page_count,
        title=title,
        status="UPLOADED"
    )
    db.add(rfp_record)
    db.commit()
    db.refresh(rfp_record)

    return RFPUploadResponse(
        rfp_id=rfp_id,
        filename=file.filename,
        file_size=file_size,
        page_count=page_count,
        status="UPLOADED",
        message="Document uploaded and registered successfully."
    )

@router.get("", response_model=List[dict])
def list_rfps(include_archived: bool = False, db: Session = Depends(get_db)):
    """Lists all RFPs registered in the system. Excludes archived RFPs by default."""
    query = db.query(RFPDocument)
    if not include_archived:
        query = query.filter(RFPDocument.archived_at.is_(None))
    records = query.order_by(RFPDocument.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "title": r.title,
            "issuer": r.issuer,
            "page_count": r.page_count,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "archived_at": r.archived_at.isoformat() if r.archived_at else None,
        }
        for r in records
    ]

@router.post("/{rfp_id}/archive")
def archive_rfp(rfp_id: str, db: Session = Depends(get_db)):
    """
    Safely archives an inactive, rejected, aborted, or stale RFP project.
    Prevents archiving actively executing pipelines or approved/completed projects.
    """
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")
    
    current_status = (rfp.status or "").upper()
    if current_status in RUNNING_WORKFLOW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot archive RFP while workflow is actively executing (status: {rfp.status})."
        )
    
    if current_status in PROTECTED_PROJECT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot archive approved/completed project (status: {rfp.status})."
        )
    
    if rfp.archived_at is not None:
        return {
            "id": rfp.id,
            "message": "RFP is already archived.",
            "archived_at": rfp.archived_at.isoformat()
        }
    
    rfp.archived_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rfp)
    return {
        "id": rfp.id,
        "message": "RFP project archived successfully.",
        "archived_at": rfp.archived_at.isoformat()
    }

@router.post("/{rfp_id}/unarchive")
def unarchive_rfp(rfp_id: str, db: Session = Depends(get_db)):
    """
    Restores an archived RFP project back to the active list.
    """
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")
    
    rfp.archived_at = None
    db.commit()
    db.refresh(rfp)
    return {
        "id": rfp.id,
        "message": "RFP project unarchived successfully.",
        "archived_at": None
    }

@router.get("/{rfp_id}")
def get_rfp_details(rfp_id: str, db: Session = Depends(get_db)):
    """Retrieves metadata and processing summary for an RFP."""
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")
    
    req_count = db.query(Requirement).filter(Requirement.rfp_id == rfp_id).count()
    risk_count = db.query(RiskRecord).filter(RiskRecord.rfp_id == rfp_id).count()
    proposal_count = db.query(Proposal).filter(Proposal.rfp_id == rfp_id).count()

    return {
        "id": rfp.id,
        "title": rfp.title,
        "issuer": rfp.issuer,
        "submission_deadline": rfp.submission_deadline,
        "filename": rfp.filename,
        "page_count": rfp.page_count,
        "status": rfp.status,
        "created_at": rfp.created_at.isoformat(),
        "archived_at": rfp.archived_at.isoformat() if rfp.archived_at else None,
        "summary_counts": {
            "requirements": req_count,
            "risks": risk_count,
            "proposals": proposal_count
        }
    }

@router.get("/{rfp_id}/requirements")
def get_requirements(rfp_id: str, db: Session = Depends(get_db)):
    """Returns classified requirements for an RFP."""
    reqs = db.query(Requirement).filter(Requirement.rfp_id == rfp_id).all()
    return [
        {
            "id": r.id,
            "req_code": r.req_code,
            "category": r.category,
            "priority": r.priority,
            "is_mandatory": r.is_mandatory,
            "text": r.text,
            "source_page": r.source_page,
            "source_section": r.source_section
        }
        for r in reqs
    ]

@router.get("/{rfp_id}/compliance-matrix")
def get_compliance_matrix(rfp_id: str, db: Session = Depends(get_db)):
    """Returns requirement-by-requirement compliance evaluation with evidence."""
    records = (
        db.query(ComplianceRecord)
        .join(Requirement, ComplianceRecord.requirement_id == Requirement.id)
        .filter(Requirement.rfp_id == rfp_id)
        .all()
    )
    return [
        {
            "id": c.id,
            "req_code": c.requirement.req_code,
            "requirement_text": c.requirement.text,
            "category": c.requirement.category,
            "status": c.status,
            "confidence": c.confidence,
            "evidence_text": c.evidence_text,
            "company_source_doc": c.company_source_doc,
            "notes": c.notes,
            "source_page": c.requirement.source_page,
            "source_section": c.requirement.source_section
        }
        for c in records
    ]

@router.get("/{rfp_id}/risks")
def get_risks_and_clarifications(rfp_id: str, db: Session = Depends(get_db)):
    """Returns the risk register and drafted clarification questions."""
    risks = db.query(RiskRecord).filter(RiskRecord.rfp_id == rfp_id).all()
    questions = db.query(ClarificationQuestion).filter(ClarificationQuestion.rfp_id == rfp_id).all()
    return {
        "risks": [
            {
                "id": r.id,
                "category": r.category,
                "severity": r.severity,
                "likelihood": r.likelihood,
                "description": r.description,
                "mitigation_strategy": r.mitigation_strategy,
                "rfp_reference": r.rfp_reference
            }
            for r in risks
        ],
        "clarification_questions": [
            {
                "id": q.id,
                "q_number": q.q_number,
                "rfp_section_reference": q.rfp_section_reference,
                "question_text": q.question_text,
                "rationale": q.rationale
            }
            for q in questions
        ]
    }

@router.get("/{rfp_id}/proposals")
def get_proposals(rfp_id: str, db: Session = Depends(get_db)):
    """Returns all proposal draft versions and reviewer critiques."""
    proposals = db.query(Proposal).filter(Proposal.rfp_id == rfp_id).order_by(Proposal.version.asc()).all()
    return [
        {
            "id": p.id,
            "version": p.version,
            "title": p.title,
            "executive_summary": p.executive_summary,
            "content_markdown": p.content_markdown,
            "review_score": p.review_score,
            "review_feedback": p.review_feedback_json,
            "status": p.status,
            "created_at": p.created_at.isoformat()
        }
        for p in proposals
    ]

@router.get("/{rfp_id}/export/{export_format}")
def export_proposal(rfp_id: str, export_format: str, db: Session = Depends(get_db)):
    """Generates and downloads the final proposal document as DOCX."""
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    proposal = db.query(Proposal).filter(Proposal.rfp_id == rfp_id).order_by(Proposal.version.desc()).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="No proposal generated yet for this RFP.")

    # Fetch compliance items and risks
    comp_records = (
        db.query(ComplianceRecord)
        .join(Requirement, ComplianceRecord.requirement_id == Requirement.id)
        .filter(Requirement.rfp_id == rfp_id)
        .all()
    )
    compliance_list = [
        {
            "req_code": c.requirement.req_code,
            "category": c.requirement.category,
            "requirement_text": c.requirement.text,
            "status": c.status,
            "confidence": c.confidence,
            "company_source_doc": c.company_source_doc,
            "evidence_text": c.evidence_text,
            "notes": c.notes,
        }
        for c in comp_records
    ]
    risks = [
        {
            "category": r.category,
            "severity": r.severity,
            "likelihood": r.likelihood,
            "description": r.description,
            "mitigation_strategy": r.mitigation_strategy,
            "rfp_reference": r.rfp_reference,
        }
        for r in rfp.risks
    ]
    clarifications = [
        {
            "q_number": q.q_number,
            "rfp_section_reference": q.rfp_section_reference,
            "question_text": q.question_text,
            "rationale": q.rationale,
        }
        for q in rfp.clarifications
    ]

    file_format = export_format.lower()
    if file_format in ["docx", "doc"]:
        out_filename = f"Proposal_{rfp.title.replace(' ', '_')}_v{proposal.version}.docx"
        out_path = os.path.join(settings.EXPORT_DIR, out_filename)
        
        ProposalExporterService.export_to_docx(
            rfp_metadata={"title": rfp.title, "issuer": rfp.issuer, "submission_deadline": rfp.submission_deadline},
            proposal_draft={"title": proposal.title, "full_markdown": proposal.content_markdown},
            compliance_matrix=compliance_list,
            risks=risks,
            clarifications=clarifications,
            output_path=out_path
        )

        # Archive to Supabase Storage if configured
        if os.path.exists(out_path):
            try:
                with open(out_path, "rb") as f:
                    StorageService.archive_proposal_export(out_filename, f.read())
            except Exception as e:
                pass

        return FileResponse(
            path=out_path,
            filename=out_filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {export_format}. Use 'docx'.")
