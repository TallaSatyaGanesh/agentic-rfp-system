from typing import TypedDict, List, Optional, Literal, Dict, Any
from app.models.schemas import (
    RFPMetadata,
    RawClause,
    ClassifiedRequirement,
    ComplianceItem,
    RiskItem,
    ClarificationQuestion,
    ProposalDraft,
    ReviewReport,
    ReviewFinding
)

class RFPProposalState(TypedDict):
    # Identifiers & Raw Inputs
    rfp_id: str
    file_path: str
    
    # Ingestion & Extraction (Agent 1)
    metadata: Optional[Dict[str, Any]]
    raw_clauses: List[Dict[str, Any]]
    
    # Requirement Classification (Agent 2)
    requirements: List[Dict[str, Any]]
    
    # Compliance Analysis (Agent 3)
    compliance_matrix: List[Dict[str, Any]]
    overall_compliance_score: float
    
    # Risk & Clarifications (Agent 4)
    risks: List[Dict[str, Any]]
    clarification_questions: List[Dict[str, Any]]
    
    # Human-in-the-Loop Gate 1: Go / No-Go
    go_nogo_decision: Optional[Literal["GO", "NO_GO"]]
    go_nogo_notes: Optional[str]
    
    # Proposal Generation (Agent 5)
    proposal_drafts: List[Dict[str, Any]]
    current_version: int
    
    # Review & Critique (Agent 6)
    review_reports: List[Dict[str, Any]]
    revision_count: int
    max_revisions: int
    
    # Human-in-the-Loop Gate 2: Final Approval
    final_approval_decision: Optional[Literal["APPROVED", "CHANGES_REQUESTED", "REJECTED"]]
    human_feedback: Optional[str]
    
    # Execution Telemetry & Status
    active_agent: str
    workflow_status: Literal[
        "PENDING",
        "EXTRACTING",
        "CLASSIFYING",
        "ANALYZING_COMPLIANCE",
        "ASSESSING_RISKS",
        "AWAITING_GO_NOGO",
        "ABORTED_NO_GO",
        "WRITING_PROPOSAL",
        "REVIEWING",
        "REVISING",
        "AWAITING_FINAL_APPROVAL",
        "HUMAN_REVIEW_REQUIRED",
        "APPROVED_FOR_EXPORT",
        "REJECTED",
        "FAILED"
    ]
    logs: List[Dict[str, Any]]
    error: Optional[str]
