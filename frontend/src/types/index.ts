// ==========================================
// CANONICAL ENUMS & LITERALS
// ==========================================

export type RequirementCategory =
  | 'Technical'
  | 'Commercial'
  | 'Contractual'
  | 'Administrative'
  | 'Certification'
  | 'Delivery'
  | 'Documentation'
  | 'Submission'
  | 'Eligibility';

export type RiskSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export type ComplianceStatus =
  | 'COMPLIANT'
  | 'PARTIALLY_COMPLIANT'
  | 'NON_COMPLIANT'
  | 'INFORMATION_REQUIRED';

export type ResponseType =
  | 'COMPLIANT_RESPONSE'
  | 'PARTIAL_RESPONSE'
  | 'EXCEPTION_RESPONSE'
  | 'INFORMATION_REQUIRED_RESPONSE';

export type ReviewStatus =
  | 'APPROVED'
  | 'REVISION_REQUIRED'
  | 'HUMAN_REVIEW_REQUIRED';

export type WorkflowState =
  | 'NOT_STARTED'
  | 'PENDING'
  | 'PROCESSING'
  | 'RESUMING'
  | 'EXTRACTING'
  | 'CLASSIFYING'
  | 'ANALYZING_COMPLIANCE'
  | 'ASSESSING_RISKS'
  | 'AWAITING_GO_NOGO'
  | 'ABORTED_NO_GO'
  | 'WRITING_PROPOSAL'
  | 'REVISING'
  | 'REVIEWING'
  | 'AWAITING_FINAL_APPROVAL'
  | 'HUMAN_REVIEW_REQUIRED'
  | 'APPROVED_FOR_EXPORT'
  | 'REJECTED'
  | 'COMPLETED'
  | 'FAILED';

// ==========================================
// 1. RFP INGESTION & SUMMARY
// ==========================================

export interface RFPDocumentSummary {
  id: string;
  filename: string;
  title: string;
  issuer: string;
  page_count: number;
  status: string;
  created_at: string;
  archived_at?: string | null;
  submission_deadline?: string;
  summary_counts?: {
    requirements: number;
    risks: number;
    proposals: number;
  };
}

// ==========================================
// 2. REQUIREMENT CLASSIFICATION
// ==========================================

export interface RequirementItem {
  id?: string;
  req_code: string;
  category: RequirementCategory;
  priority: 'High' | 'Medium' | 'Low';
  is_mandatory: boolean;
  text: string;
  source_page: number;
  source_section: string;
  original_text?: string | null;
  normalized_description?: string | null;
  source_clause_id?: string | null;
  confidence?: number;
  reasoning?: string | null;
  mandatory_confidence?: number;
  mandatory_reasoning?: string;
}

// ==========================================
// 3. COMPLIANCE MATRIX (RAG AUDIT) & CITATIONS
// ==========================================

export interface Citation {
  company_doc_id?: string;
  document_title?: string;
  filename?: string;
  chunk_id?: string;
  source_page?: number;
  source_section?: string;
  similarity_score?: number;
  snippet?: string;
}

export interface ComplianceItem {
  id?: string;
  req_code: string;
  requirement_text: string;
  category: string;
  status: ComplianceStatus;
  confidence: number;
  evidence_text: string | null;
  company_source_doc: string | null;
  company_doc_id?: string | null;
  chunk_id?: string | null;
  source_page?: number | null;
  source_section?: string | null;
  similarity_score?: number | null;
  citations?: Citation[];
  notes: string | null;
  is_mandatory?: boolean;
}

// ==========================================
// 4. RISK & CLARIFICATION
// ==========================================

export interface RiskItem {
  id?: string;
  risk_id?: string | null;
  category: string;
  severity: RiskSeverity;
  likelihood: 'High' | 'Medium' | 'Low' | 'HIGH' | 'MEDIUM' | 'LOW';
  description: string;
  mitigation_strategy: string;
  rfp_reference?: string | null;
  requirement_id?: string | null;
  requirement_text?: string | null;
  title?: string | null;
  impact?: string | null;
  recommended_action?: string | null;
  compliance_status?: string | null;
  company_doc_id?: string | null;
  chunk_id?: string | null;
  source_page?: number | null;
  source_section?: string | null;
  citations?: Citation[];
}

export interface ClarificationQuestion {
  id?: string;
  clarification_id?: string | null;
  q_number: number;
  rfp_section_reference: string;
  question_text: string;
  rationale: string;
  requirement_id?: string | null;
  question?: string | null;
  reason?: string | null;
  priority?: string | null;
  target_owner?: string | null;
  clarification_type?: 'ISSUER_CLARIFICATION' | 'INTERNAL_INFORMATION_REQUEST' | string;
  compliance_status?: string | null;
  citations?: Citation[];
}

// ==========================================
// 5. PROPOSAL WRITER
// ==========================================

export interface RequirementResponse {
  requirement_id: string;
  response_type: ResponseType;
  response: string;
  response_text?: string;
  compliance_status: ComplianceStatus;
  evidence_snippet?: string | null;
  citations?: Citation[];
  company_doc_id?: string | null;
  chunk_id?: string | null;
  source_page?: number | null;
  source_section?: string | null;
  clarification_required?: string | null;
  risk_summary?: string | null;
  requirement_text?: string;
  category?: string;
  is_mandatory?: boolean;
  assumptions?: string[];
}

export interface ProposalSection {
  section_title: string;
  content_markdown: string;
  rfp_citations?: string[];
  company_citations?: string[];
  information_required_alerts?: string[];
}

export interface ProposalDraft {
  id?: string;
  version: number;
  title: string;
  executive_summary: string;
  content_markdown?: string;
  full_markdown?: string;
  sections?: ProposalSection[];
  requirement_responses?: RequirementResponse[];
  review_score?: number;
  review_feedback?: string | ReviewReport | null;
  status?: string;
  created_at?: string;
}

// ==========================================
// 6. REVIEWER / CRITIC
// ==========================================

export interface ReviewFinding {
  finding_id: string;
  requirement_id?: string | null;
  severity: RiskSeverity;
  category: string;
  description: string;
  evidence?: string | null;
  recommended_action: string;
}

export interface RubricScore {
  criterion: string;
  score: number;
  feedback: string;
}

export interface ReviewReport {
  review_id: string;
  proposal_version: number;
  overall_status: ReviewStatus;
  approval_required: boolean;
  revision_required: boolean;
  score: number;
  summary: string;
  findings: ReviewFinding[];
  critical_findings: ReviewFinding[];
  warnings: string[];
  unsupported_claims: string[];
  traceability_issues: string[];
  risk_coverage_issues: string[];
  clarification_issues: string[];
  missing_requirements: string[];
  recommended_actions: string[];

  // Optional backward compatibility & enriched fields
  overall_score?: number;
  rubric_scores?: RubricScore[];
  strengths?: string[];
  critical_flaws?: string[];
  needs_revision?: boolean;
  actionable_revision_instructions?: string[];
  reviewed_at?: string;
  requirement_findings?: Record<string, ReviewFinding[]>;
  ungrounded_or_hallucinated_claims?: string[];
  missing_information_count?: number;
}

// ==========================================
// 7. WORKFLOW & HITL
// ==========================================

export type WorkflowDecision = 'GO' | 'NO_GO' | 'APPROVED' | 'CHANGES_REQUESTED' | 'REJECTED';

export type SSEConnectionStatus =
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'completed'
  | 'failed';

export type SSEEventType =
  | 'status_change'
  | 'node_completed'
  | 'human_approval_required'
  | 'workflow_finished'
  | 'error';

export interface SSEStatusChangeData {
  active_agent: string;
  status: WorkflowState | string;
  message: string;
}

export interface SSENodeCompletedData {
  node: string;
  active_agent: string;
  status: WorkflowState | string;
  log?: {
    agent: string;
    timestamp: string;
    action: string;
  } | null;
  state_preview?: {
    requirements_count?: number;
    compliance_score?: number;
    current_version?: number;
  };
}

export interface SSEHumanApprovalRequiredData {
  gate: 'GO_NOGO' | 'FINAL_APPROVAL';
  title: string;
  description: string;
  data: {
    compliance_score?: number;
    requirements_count?: number;
    high_risks_count?: number;
    score?: number;
    version?: number;
    draft_title?: string;
  };
}

export interface SSEWorkflowFinishedData {
  status: WorkflowState | string;
}

export interface SSEErrorData {
  error: string;
}

export interface SSEEventPayload {
  event: SSEEventType | string;
  rfp_id: string;
  timestamp: string;
  data:
    | SSEStatusChangeData
    | SSENodeCompletedData
    | SSEHumanApprovalRequiredData
    | SSEWorkflowFinishedData
    | SSEErrorData
    | Record<string, string | number | boolean | null>;
}

export interface InterruptPayload {
  compliance_score?: number;
  requirements_count?: number;
  high_risks_count?: number;
  score?: number;
  version?: number;
  draft_title?: string;
  gate?: string;
  title?: string;
  description?: string;
}

export interface WorkflowStatus {
  status: WorkflowState;
  active_agent: string;
  is_interrupted: boolean;
  interrupt_type: 'GO_NOGO' | 'FINAL_APPROVAL' | null;
  current_version: number;
  revision_count: number;
  compliance_score?: number;
  workflow_status?: WorkflowState;
  rfp_id?: string;
  error?: string | null;
  interrupt_payload?: InterruptPayload;
  logs: Array<{
    agent: string;
    timestamp: string;
    action: string;
  }>;
}

// ==========================================
// 8. KNOWLEDGE BASE
// ==========================================

export interface CompanyDoc {
  id: string;
  title: string;
  filename: string;
  category: string;
  chunk_count: number;
  indexed_at: string;
}

export interface RAGChunk {
  evidence_text: string;
  similarity: number;
  document_title: string;
  filename: string;
  category: string;
  company_doc_id: string;
  chunk_id: string;
  page_number?: number;
  section?: string;
}

export interface RAGQueryResult {
  query: string;
  results_count: number;
  threshold_applied: number;
  results: RAGChunk[];
}
