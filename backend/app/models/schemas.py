import uuid
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime, timezone

# ==========================================
# 1. DOCUMENT EXTRACTION SCHEMAS
# ==========================================
class ExtractedBlock(BaseModel):
    text: str
    page_number: int
    section_title: str = "General"
    block_type: str = "paragraph"  # heading, paragraph, table, list_item

class RFPMetadata(BaseModel):
    title: str = Field(..., description="The title of the RFP / Tender")
    issuer: str = Field(..., description="The organization or client issuing the RFP")
    submission_deadline: Optional[str] = Field(None, description="Deadline date and time for submission")
    budget_or_scope: Optional[str] = Field(None, description="Estimated budget or engagement scope if mentioned")
    evaluation_criteria: List[str] = Field(default_factory=list, description="Stated criteria used to score proposals")
    summary: str = Field(..., description="High-level executive summary of the RFP objective")

class RawClause(BaseModel):
    clause_id: str
    text: str
    source_page: int
    source_section: str

class ExtractionAgentOutput(BaseModel):
    metadata: RFPMetadata
    clauses: List[RawClause]

# ==========================================
# 2. REQUIREMENT CLASSIFICATION SCHEMAS
# ==========================================
class ClassifiedRequirement(BaseModel):
    req_code: str = Field(..., description="Canonical requirement code e.g. REQ-TECH-001")
    category: str = Field(
        ...,
        description="Requirement category: Technical, Commercial, Contractual, Administrative, Certification, Delivery, Documentation, Submission, Eligibility"
    )
    priority: Literal["High", "Medium", "Low"] = "Medium"
    is_mandatory: bool = Field(False, description="True if requirement uses explicit mandatory modals (SHALL, MUST, MANDATORY); False if optional (SHOULD, MAY) or ambiguous")
    mandatory_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence in mandatory determination (1.0 for explicit modal, 0.0 for ambiguous)")
    mandatory_reasoning: str = Field("", description="Evidence distinguishing explicit mandatory, explicit optional, and inferred/ambiguous status")
    text: str = Field(..., description="Cleaned requirement statement")
    original_text: Optional[str] = Field(None, description="Original raw clause text from source")
    normalized_description: Optional[str] = Field(None, description="Concise normalized requirement description")
    source_clause_id: Optional[str] = Field(None, description="Source clause ID from Agent 1 e.g. CLAUSE-001")
    source_page: int = Field(1, description="Page number where requirement was found")
    source_section: str = Field("General", description="Section title where requirement was found")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score of the classification")
    reasoning: Optional[str] = Field(None, description="Rationale for category determination")

class ClassificationAgentOutput(BaseModel):
    requirements: List[ClassifiedRequirement]

# ==========================================
# 3. COMPLIANCE ANALYSIS SCHEMAS
# ==========================================
class ComplianceItem(BaseModel):
    req_code: str
    requirement_text: str
    category: str
    status: Literal["COMPLIANT", "PARTIALLY_COMPLIANT", "NON_COMPLIANT", "INFORMATION_REQUIRED"]
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score of the compliance match")
    evidence_text: Optional[str] = Field(None, description="Verbatim evidence snippet from company knowledge base")
    company_source_doc: Optional[str] = Field(None, description="Filename or title of company document cited")
    company_doc_id: Optional[str] = Field(None, description="Company document ID in knowledge base")
    chunk_id: Optional[str] = Field(None, description="Vector store chunk ID")
    source_page: Optional[int] = Field(None, description="Page number within company document if available")
    source_section: Optional[str] = Field(None, description="Section within company document if available")
    similarity_score: Optional[float] = Field(None, description="Retrieval similarity score (0.0 - 1.0)")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="All contributing company evidence sources")
    notes: Optional[str] = Field(None, description="Reasoning or explanation of gaps")

class ComplianceAgentOutput(BaseModel):
    matrix: List[ComplianceItem]
    overall_compliance_percentage: float
    gap_count: int

# ==========================================
# 4. RISK & CLARIFICATION SCHEMAS
# ==========================================
class RiskItem(BaseModel):
    category: str = Field(default="Operational", description="Category: Technical, Operational, Financial, Legal, Timeline, Compliance, Contractual, etc.")
    severity: str = Field(default="Medium", description="Severity: CRITICAL, HIGH, MEDIUM, LOW")
    likelihood: str = Field(default="Medium", description="Likelihood: High, Medium, Low")
    description: str = Field(..., description="Actionable explanation of the risk, cause, and evidence")
    mitigation_strategy: str = Field(default="", description="Proposed mitigation strategy or actionable next steps")
    rfp_reference: Optional[str] = Field(None, description="RFP clause, requirement code, or section reference")
    
    # Traceability & Enriched Fields (Backward-compatible with defaults)
    risk_id: Optional[str] = Field(None, description="Unique risk identifier e.g. RISK-001")
    id: Optional[str] = Field(None, description="Identifier for UI table compatibility")
    requirement_id: Optional[str] = Field(None, description="Originating requirement code e.g. REQ-TECH-001")
    requirement_text: Optional[str] = Field(None, description="Originating requirement text snippet")
    title: Optional[str] = Field(None, description="Short summary title of the risk")
    impact: Optional[str] = Field(None, description="Business, contractual, or proposal impact")
    recommended_action: Optional[str] = Field(None, description="Actionable recommendation for proposal manager")
    compliance_status: Optional[str] = Field(None, description="Compliance status from Agent 3")
    company_doc_id: Optional[str] = Field(None, description="Cited company document ID")
    chunk_id: Optional[str] = Field(None, description="Cited company chunk ID")
    source_page: Optional[int] = Field(None, description="Source page number from RFP or collateral")
    source_section: Optional[str] = Field(None, description="Source section from RFP or collateral")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="Traceable citations to company evidence")

class ClarificationQuestion(BaseModel):
    q_number: int = Field(default=1, description="Sequential question number")
    rfp_section_reference: str = Field(default="General", description="RFP section or requirement code reference")
    question_text: str = Field(..., description="Specific question for client tender authority or internal bid team")
    rationale: str = Field(..., description="Business or technical rationale explaining why clarification is required")
    
    # Traceability & Enriched Fields (Backward-compatible with defaults)
    clarification_id: Optional[str] = Field(None, description="Unique clarification identifier e.g. CLR-001")
    id: Optional[str] = Field(None, description="Identifier for UI compatibility")
    requirement_id: Optional[str] = Field(None, description="Originating requirement code e.g. REQ-TECH-001")
    question: Optional[str] = Field(None, description="Alias for question_text")
    reason: Optional[str] = Field(None, description="Alias for rationale")
    priority: Optional[str] = Field(default="Medium", description="Priority: CRITICAL, HIGH, MEDIUM, LOW")
    target_owner: Optional[str] = Field(default="Bid Manager", description="Target team or owner to answer (e.g. Legal, Technical, Issuer)")
    clarification_type: str = Field(
        default="ISSUER_CLARIFICATION",
        description="Type: 'ISSUER_CLARIFICATION' (directed to client/tender authority) or 'INTERNAL_INFORMATION_REQUEST' (directed to internal SME/bid team)"
    )
    compliance_status: Optional[str] = Field(None, description="Compliance status from Agent 3")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="Supporting evidence citations")

class RiskAndClarificationOutput(BaseModel):
    risks: List[RiskItem] = Field(default_factory=list)
    clarification_questions: List[ClarificationQuestion] = Field(default_factory=list)

# ==========================================
# 5. PROPOSAL WRITER SCHEMAS
# ==========================================
class ProposalSection(BaseModel):
    section_title: str
    content_markdown: str
    rfp_citations: List[str] = Field(default_factory=list)
    company_citations: List[str] = Field(default_factory=list)
    information_required_alerts: List[str] = Field(default_factory=list)

class RequirementResponse(BaseModel):
    requirement_id: str = Field(..., description="Target requirement code e.g. REQ-TECH-001")
    requirement_text: str = Field(..., description="Verbatim requirement text snippet")
    category: str = Field(default="General", description="Requirement category")
    is_mandatory: bool = Field(default=False, description="Mandatory or optional flag")
    compliance_status: str = Field(..., description="COMPLIANT, PARTIALLY_COMPLIANT, NON_COMPLIANT, INFORMATION_REQUIRED")
    response_type: Literal[
        "COMPLIANT_RESPONSE",
        "PARTIAL_RESPONSE",
        "EXCEPTION_RESPONSE",
        "INFORMATION_REQUIRED_RESPONSE"
    ] = Field(..., description="Appropriate response type for compliance status")
    response: str = Field(..., description="Professional, evidence-grounded response text")
    company_doc_id: Optional[str] = Field(None, description="Referenced company document ID")
    chunk_id: Optional[str] = Field(None, description="Referenced company chunk ID")
    source_page: Optional[int] = Field(None, description="RFP source page")
    source_section: Optional[str] = Field(None, description="RFP source section")
    evidence_snippet: Optional[str] = Field(None, description="Verbatim company evidence snippet")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="Machine-readable company citations")
    assumptions: List[str] = Field(default_factory=list, description="Explicit assumptions if applicable")
    clarification_required: Optional[str] = Field(None, description="Clarification or verification request note if applicable")
    risk_summary: Optional[str] = Field(None, description="Summary of associated risk from Agent 4 if present")

class ProposalDraft(BaseModel):
    version: int = 1
    title: str
    executive_summary: str
    sections: List[ProposalSection] = Field(default_factory=list)
    full_markdown: str = ""
    requirement_responses: List[RequirementResponse] = Field(
        default_factory=list,
        description="Structured requirement-by-requirement proposal responses"
    )

# ==========================================
# 6. REVIEWER / CRITIC SCHEMAS
# ==========================================
class ReviewFinding(BaseModel):
    finding_id: str = Field(default_factory=lambda: f"fnd_{uuid.uuid4().hex[:8]}")
    requirement_id: Optional[str] = Field(None, description="Affected requirement ID if applicable")
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    category: str = Field(..., description="Category of finding (e.g. REQUIREMENT_COVERAGE, COMPLIANCE_CONSISTENCY, EVIDENCE_GROUNDING, UNGROUNDED_COMMITMENT, RISK_COVERAGE, CLARIFICATION_ISSUE, TRACEABILITY, PROPOSAL_QUALITY)")
    description: str = Field(..., description="Detailed description of the finding")
    evidence: Optional[str] = Field(None, description="Evidence or snippet illustrating the issue")
    recommended_action: str = Field(..., description="Actionable instruction to resolve the finding")

class RubricScore(BaseModel):
    criterion: str  # e.g., "Compliance Alignment", "Technical Depth & Feasibility", "Grounding & Hallucination Defense", "Professionalism & Clarity"
    score: int = Field(..., ge=0, le=25)
    feedback: str

class ReviewReport(BaseModel):
    review_id: str = Field(default_factory=lambda: f"rev_{uuid.uuid4().hex[:10]}")
    proposal_version: int = 1
    overall_status: Literal["APPROVED", "REVISION_REQUIRED", "HUMAN_REVIEW_REQUIRED"] = "REVISION_REQUIRED"
    approval_required: bool = False
    revision_required: bool = False
    score: int = Field(default=0, ge=0, le=100)
    summary: str = ""
    findings: List[ReviewFinding] = Field(default_factory=list)
    requirement_findings: Dict[str, List[ReviewFinding]] = Field(default_factory=dict)
    critical_findings: List[ReviewFinding] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    unsupported_claims: List[str] = Field(default_factory=list)
    traceability_issues: List[str] = Field(default_factory=list)
    risk_coverage_issues: List[str] = Field(default_factory=list)
    clarification_issues: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    reviewed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Backward compatibility fields
    overall_score: int = Field(default=0, ge=0, le=100)
    rubric_scores: List[RubricScore] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    critical_flaws: List[str] = Field(default_factory=list)
    ungrounded_or_hallucinated_claims: List[str] = Field(default_factory=list)
    missing_information_count: int = 0
    needs_revision: bool = False
    actionable_revision_instructions: List[str] = Field(default_factory=list)

# ==========================================
# 7. HUMAN-IN-THE-LOOP SCHEMAS
# ==========================================
class GoNoGoRequest(BaseModel):
    decision: Literal["GO", "NO_GO"]
    notes: Optional[str] = None

class FinalApprovalRequest(BaseModel):
    decision: Literal["APPROVED", "CHANGES_REQUESTED", "REJECTED"]
    feedback: Optional[str] = None

# ==========================================
# 8. API RESPONSE SCHEMAS
# ==========================================
class RFPUploadResponse(BaseModel):
    rfp_id: str
    filename: str
    file_size: int
    page_count: int
    status: str
    message: str

class WorkflowStatusResponse(BaseModel):
    rfp_id: str
    active_agent: str
    workflow_status: str
    current_version: int
    revision_count: int
    is_interrupted: bool
    interrupt_type: Optional[str] = None  # GO_NOGO or FINAL_APPROVAL
    interrupt_payload: Optional[Dict[str, Any]] = None

class CompanyDocResponse(BaseModel):
    id: str
    title: str
    filename: str
    category: str
    chunk_count: int
    indexed_at: datetime
