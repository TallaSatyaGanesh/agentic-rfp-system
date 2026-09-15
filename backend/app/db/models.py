from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class RFPDocument(Base):
    __tablename__ = "rfp_documents"

    id = Column(String(50), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, default=0)
    page_count = Column(Integer, default=0)
    title = Column(String(255), default="Untitled RFP")
    issuer = Column(String(255), default="Unknown Issuer")
    submission_deadline = Column(String(100), nullable=True)
    status = Column(String(50), default="UPLOADED")  # UPLOADED, PROCESSING, ANALYZED, PROPOSAL_DRAFTED, COMPLETED, FAILED
    created_at = Column(DateTime, default=utc_now)

    requirements = relationship("Requirement", back_populates="rfp", cascade="all, delete-orphan")
    risks = relationship("RiskRecord", back_populates="rfp", cascade="all, delete-orphan")
    clarifications = relationship("ClarificationQuestion", back_populates="rfp", cascade="all, delete-orphan")
    proposals = relationship("Proposal", back_populates="rfp", cascade="all, delete-orphan")

class CompanyDocument(Base):
    __tablename__ = "company_documents"

    id = Column(String(50), primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    category = Column(String(100), default="General")  # Security, Technical, Case Study, Certification, Financial
    chunk_count = Column(Integer, default=0)
    indexed_at = Column(DateTime, default=utc_now)

class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(String(50), primary_key=True, index=True)
    rfp_id = Column(String(50), ForeignKey("rfp_documents.id"), nullable=False)
    req_code = Column(String(50), nullable=False, index=True)  # e.g., REQ-TECH-001
    category = Column(String(50), default="Technical")  # Technical, Functional, Security, Legal, Management
    priority = Column(String(20), default="Medium")  # High, Medium, Low
    is_mandatory = Column(Boolean, default=True)
    text = Column(Text, nullable=False)
    source_page = Column(Integer, default=1)
    source_section = Column(String(255), default="General Requirements")

    rfp = relationship("RFPDocument", back_populates="requirements")
    compliance = relationship("ComplianceRecord", back_populates="requirement", uselist=False, cascade="all, delete-orphan")

class ComplianceRecord(Base):
    __tablename__ = "compliance_records"

    id = Column(String(50), primary_key=True, index=True)
    requirement_id = Column(String(50), ForeignKey("requirements.id"), nullable=False)
    status = Column(String(30), default="INFORMATION_REQUIRED")  # COMPLIANT, PARTIALLY_COMPLIANT, NON_COMPLIANT, INFORMATION_REQUIRED
    confidence = Column(Float, default=0.0)
    evidence_text = Column(Text, nullable=True)
    company_source_doc = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    requirement = relationship("Requirement", back_populates="compliance")

class RiskRecord(Base):
    __tablename__ = "risk_records"

    id = Column(String(50), primary_key=True, index=True)
    rfp_id = Column(String(50), ForeignKey("rfp_documents.id"), nullable=False)
    category = Column(String(50), default="Operational")  # Technical, Operational, Financial, Legal, Timeline
    severity = Column(String(20), default="Medium")  # High, Medium, Low
    likelihood = Column(String(20), default="Medium")  # High, Medium, Low
    description = Column(Text, nullable=False)
    mitigation_strategy = Column(Text, nullable=False)
    rfp_reference = Column(String(255), nullable=True)

    rfp = relationship("RFPDocument", back_populates="risks")

class ClarificationQuestion(Base):
    __tablename__ = "clarification_questions"

    id = Column(String(50), primary_key=True, index=True)
    rfp_id = Column(String(50), ForeignKey("rfp_documents.id"), nullable=False)
    q_number = Column(Integer, default=1)
    rfp_section_reference = Column(String(255), default="General")
    question_text = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)

    rfp = relationship("RFPDocument", back_populates="clarifications")

class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(String(50), primary_key=True, index=True)
    rfp_id = Column(String(50), ForeignKey("rfp_documents.id"), nullable=False)
    version = Column(Integer, default=1)
    title = Column(String(255), default="Proposal Response")
    executive_summary = Column(Text, nullable=True)
    content_markdown = Column(Text, nullable=False)
    review_score = Column(Integer, default=0)
    review_feedback_json = Column(Text, nullable=True)
    status = Column(String(50), default="DRAFT")  # DRAFT, IN_REVIEW, APPROVED, REJECTED
    created_at = Column(DateTime, default=utc_now)

    rfp = relationship("RFPDocument", back_populates="proposals")
