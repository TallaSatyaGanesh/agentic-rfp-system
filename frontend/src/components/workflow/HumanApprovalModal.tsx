import React, { useState } from 'react';
import axios from 'axios';
import {
  UserCheck,
  AlertCircle,
  ThumbsUp,
  ThumbsDown,
  RefreshCw,
  X,
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ShieldAlert,
  FileText,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import {
  WorkflowStatus,
  WorkflowDecision,
  ProposalDraft,
  ReviewReport,
  ReviewFinding,
  RiskItem,
  ComplianceItem
} from '../../types';
import { api } from '../../services/api';

interface Props {
  rfpId: string;
  status: WorkflowStatus | null;
  isOpen: boolean;
  onClose: () => void;
  onResumed: () => void;
  latestProposal?: ProposalDraft | null;
  risks?: RiskItem[];
  complianceItems?: ComplianceItem[];
}

export const HumanApprovalModal: React.FC<Props> = ({
  rfpId,
  status,
  isOpen,
  onClose,
  onResumed,
  latestProposal,
  risks = [],
  complianceItems = []
}) => {
  const [feedback, setFeedback] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [activeDecision, setActiveDecision] = useState<WorkflowDecision | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [expandedFindings, setExpandedFindings] = useState<Record<string, boolean>>({});

  const ALLOWED_APPROVAL_STATES = [
    'AWAITING_GO_NOGO',
    'AWAITING_FINAL_APPROVAL',
    'HUMAN_REVIEW_REQUIRED'
  ];

  if (!isOpen || !status || !ALLOWED_APPROVAL_STATES.includes(status.status)) return null;

  // Determine Gate Type explicitly
  const isGoNoGo = status.status === 'AWAITING_GO_NOGO' || (status.interrupt_type === 'GO_NOGO' && status.status !== 'AWAITING_FINAL_APPROVAL');
  const isFinalApproval =
    status.status === 'AWAITING_FINAL_APPROVAL' ||
    status.status === 'HUMAN_REVIEW_REQUIRED' ||
    (status.interrupt_type === 'FINAL_APPROVAL' && status.status !== 'AWAITING_GO_NOGO');

  if (!isGoNoGo && !isFinalApproval) return null;

  // Safely extract ReviewReport from latestProposal if present
  let reviewReport: ReviewReport | null = null;
  if (latestProposal?.review_feedback) {
    if (typeof latestProposal.review_feedback === 'object') {
      reviewReport = latestProposal.review_feedback;
    } else if (typeof latestProposal.review_feedback === 'string') {
      try {
        const parsed = JSON.parse(latestProposal.review_feedback);
        if (parsed && typeof parsed === 'object' && 'overall_status' in parsed) {
          reviewReport = parsed;
        }
      } catch {
        reviewReport = null;
      }
    }
  }

  const isHumanReviewRequired =
    status.status === 'HUMAN_REVIEW_REQUIRED' ||
    reviewReport?.overall_status === 'HUMAN_REVIEW_REQUIRED';

  // Extract metrics for Gate 1
  const complianceScore = status.compliance_score ?? 0;
  const criticalRisks = risks.filter((r) => (r.severity || '').toUpperCase() === 'CRITICAL');
  const highRisks = risks.filter((r) => (r.severity || '').toUpperCase() === 'HIGH');

  // Extract findings for Gate 2
  const allFindings: ReviewFinding[] = reviewReport?.findings || [];
  const criticalFindings: ReviewFinding[] = allFindings.filter((f) => (f.severity || '').toUpperCase() === 'CRITICAL');
  const highFindings: ReviewFinding[] = allFindings.filter((f) => (f.severity || '').toUpperCase() === 'HIGH');
  const otherFindings: ReviewFinding[] = allFindings.filter(
    (f) => (f.severity || '').toUpperCase() !== 'CRITICAL' && (f.severity || '').toUpperCase() !== 'HIGH'
  );

  const toggleFindingExpanded = (findingId: string) => {
    setExpandedFindings((prev) => ({
      ...prev,
      [findingId]: !prev[findingId]
    }));
  };

  const handleSubmit = async (decision: WorkflowDecision) => {
    if (submitting) return;

    setErrorMessage(null);
    setSuccessMessage(null);
    setActiveDecision(decision);
    setSubmitting(true);

    try {
      if (isGoNoGo) {
        await api.resumeWorkflow(rfpId, { decision, notes: feedback.trim() });
      } else {
        await api.resumeWorkflow(rfpId, { decision, feedback: feedback.trim() });
      }

      setSuccessMessage(`Decision "${decision}" accepted by orchestration pipeline.`);
      setTimeout(() => {
        onResumed();
        onClose();
      }, 500);
    } catch (err) {
      let msg = 'Failed to submit decision. Please check backend logs.';
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        if (typeof detail === 'string') {
          msg = detail;
        } else if (err.response?.status === 400) {
          msg =
            'Workflow is not currently awaiting human input at this checkpoint. The workflow may have already progressed.';
        } else if (err.response?.status === 404) {
          msg = 'RFP workflow session not found on server.';
        } else if (err.message) {
          msg = err.message;
        }
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setErrorMessage(msg);
    } finally {
      setSubmitting(false);
      setActiveDecision(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-2xl w-full my-8 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div
          className={`p-5 flex items-center justify-between text-white ${
            isHumanReviewRequired
              ? 'bg-rose-700'
              : isGoNoGo
              ? 'bg-amber-600'
              : 'bg-sky-700'
          }`}
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-white/20">
              {isHumanReviewRequired ? (
                <AlertOctagon className="w-5 h-5 text-white" />
              ) : (
                <UserCheck className="w-5 h-5 text-white" />
              )}
            </div>
            <div>
              <h3 className="font-bold text-base">
                {isGoNoGo
                  ? 'Human Gate 1: Bid Go / No-Go Decision'
                  : isHumanReviewRequired
                  ? 'Human Gate 2: Escalated Proposal Review Required'
                  : 'Human Gate 2: Final Proposal Sign-Off'}
              </h3>
              <p className="text-xs text-white/90 mt-0.5">
                {isGoNoGo
                  ? 'Mandatory qualification checkpoint prior to proposal authoring'
                  : isHumanReviewRequired
                  ? 'Critical findings or automated revision limit reached (Cycle 2/2). Human decision required.'
                  : 'Red Team critique completed. Executive authorization required for export release.'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={submitting}
            className="p-1.5 rounded-lg hover:bg-white/20 text-white transition disabled:opacity-50"
            title="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5 max-h-[75vh] overflow-y-auto">
          {/* Status / Success Alert */}
          {successMessage && (
            <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2.5 text-emerald-800 text-xs font-semibold">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Error Alert */}
          {errorMessage && (
            <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl flex items-start justify-between gap-2 text-rose-800 text-xs">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 mt-0.5 shrink-0" />
                <span>{errorMessage}</span>
              </div>
              <button
                onClick={() => setErrorMessage(null)}
                className="text-rose-500 hover:text-rose-700 font-bold ml-2"
              >
                &times;
              </button>
            </div>
          )}

          {/* Gate 1 Experience */}
          {isGoNoGo && (
            <div className="space-y-4">
              {/* Summary Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-center">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Compliance Score
                  </span>
                  <span className="text-xl font-black text-sky-700 mt-1 block">
                    {complianceScore}%
                  </span>
                </div>
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-center">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Total Requirements
                  </span>
                  <span className="text-xl font-black text-slate-800 mt-1 block">
                    {complianceItems.length}
                  </span>
                </div>
                <div className="p-3 rounded-xl border border-rose-200 bg-rose-50/60 text-center">
                  <span className="text-[10px] uppercase font-bold text-rose-600 block">
                    Critical Risks
                  </span>
                  <span className="text-xl font-black text-rose-700 mt-1 block">
                    {criticalRisks.length}
                  </span>
                </div>
                <div className="p-3 rounded-xl border border-amber-200 bg-amber-50/60 text-center">
                  <span className="text-[10px] uppercase font-bold text-amber-600 block">
                    High Risks
                  </span>
                  <span className="text-xl font-black text-amber-700 mt-1 block">
                    {highRisks.length}
                  </span>
                </div>
              </div>

              {/* Critical Risk Warnings */}
              {criticalRisks.length > 0 && (
                <div className="p-4 bg-rose-50 rounded-xl border border-rose-200">
                  <div className="flex items-start gap-2.5">
                    <ShieldAlert className="w-5 h-5 text-rose-600 mt-0.5 shrink-0" />
                    <div className="text-xs text-rose-900 leading-relaxed space-y-1 w-full">
                      <p className="font-bold text-rose-950">
                        Attention: {criticalRisks.length} Critical Risk(s) Detected
                      </p>
                      <ul className="list-disc list-inside space-y-1">
                        {criticalRisks.slice(0, 3).map((cr, idx) => (
                          <li key={idx} className="line-clamp-2">
                            <strong>{cr.category}:</strong> {cr.description}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {/* Input */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">
                  Strategic Guidance / Bid Notes for Proposal Writer (Optional):
                </label>
                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  disabled={submitting}
                  placeholder="e.g., Emphasize multi-region failover and SOC2 Type II compliance in executive summary..."
                  className="w-full text-xs p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none min-h-[90px] disabled:bg-slate-100"
                />
              </div>
            </div>
          )}

          {/* Gate 2 Experience */}
          {isFinalApproval && (
            <div className="space-y-4">
              {/* Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-center">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Proposal Version
                  </span>
                  <span className="text-xl font-black text-slate-800 mt-1 block">
                    v{status.current_version || latestProposal?.version || 1}
                  </span>
                </div>
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-center">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Review Score
                  </span>
                  <span className="text-xl font-black text-sky-700 mt-1 block">
                    {reviewReport?.score ?? latestProposal?.review_score ?? 0}/100
                  </span>
                </div>
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-center">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Review Status
                  </span>
                  <span
                    className={`text-xs font-bold px-2 py-1 rounded inline-block mt-2 ${
                      isHumanReviewRequired
                        ? 'bg-rose-100 text-rose-800'
                        : 'bg-emerald-100 text-emerald-800'
                    }`}
                  >
                    {reviewReport?.overall_status || (isHumanReviewRequired ? 'HUMAN_REVIEW_REQUIRED' : (latestProposal?.review_score ? 'REVIEWED' : 'PENDING_SIGN_OFF'))}
                  </span>
                </div>
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-center">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Revision Cycle
                  </span>
                  <span className="text-xl font-black text-purple-700 mt-1 block">
                    {status.revision_count}/2
                  </span>
                </div>
              </div>

              {/* Review Summary */}
              {reviewReport?.summary && (
                <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 leading-relaxed">
                  <p className="font-semibold text-slate-900 mb-1">Reviewer Summary:</p>
                  <p>{reviewReport.summary}</p>
                </div>
              )}

              {/* Critical / High Findings */}
              {criticalFindings.length > 0 || highFindings.length > 0 ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 text-rose-600" />
                      Priority Findings Requiring Evaluation ({criticalFindings.length + highFindings.length})
                    </h4>
                    <span className="text-[10px] text-slate-500 font-medium">
                      {criticalFindings.length} Critical, {highFindings.length} High
                    </span>
                  </div>

                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {[...criticalFindings, ...highFindings].map((finding) => {
                      const isExpanded = expandedFindings[finding.finding_id] || false;
                      const isCrit = (finding.severity || '').toUpperCase() === 'CRITICAL';

                      return (
                        <div
                          key={finding.finding_id}
                          className={`p-3 rounded-lg border text-xs leading-relaxed ${
                            isCrit
                              ? 'border-rose-300 bg-rose-50/70 text-rose-950'
                              : 'border-amber-300 bg-amber-50/70 text-amber-950'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span
                                className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                  isCrit ? 'bg-rose-600 text-white' : 'bg-amber-600 text-white'
                                }`}
                              >
                                {finding.severity}
                              </span>
                              <span className="font-semibold text-[11px] text-slate-800">
                                {finding.category}
                              </span>
                              {finding.requirement_id && (
                                <span className="font-mono text-[10px] px-1.5 py-0.2 rounded bg-white border border-slate-300 text-slate-700">
                                  {finding.requirement_id}
                                </span>
                              )}
                            </div>
                            {finding.evidence && (
                              <button
                                type="button"
                                onClick={() => toggleFindingExpanded(finding.finding_id)}
                                className="text-slate-500 hover:text-slate-700 flex items-center gap-1 text-[11px]"
                              >
                                {isExpanded ? (
                                  <ChevronUp className="w-3.5 h-3.5" />
                                ) : (
                                  <ChevronDown className="w-3.5 h-3.5" />
                                )}
                              </button>
                            )}
                          </div>

                          <p className="mt-1.5 font-medium text-slate-800">{finding.description}</p>

                          {finding.evidence && isExpanded && (
                            <div className="mt-2 p-2 bg-white/80 rounded border border-slate-200 text-[11px] italic text-slate-600">
                              <span className="font-bold not-italic text-slate-700 block text-[10px]">
                                Evidence / Snippet:
                              </span>
                              &ldquo;{finding.evidence}&rdquo;
                            </div>
                          )}

                          <div className="mt-2 pt-1.5 border-t border-slate-200/60 flex items-start gap-1.5 text-[11px] text-slate-700">
                            <strong className="text-slate-900 shrink-0">Recommendation:</strong>
                            <span>{finding.recommended_action}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-900 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>No critical or high severity defects flagged in current draft.</span>
                </div>
              )}

              {/* Unsupported Claims Warnings */}
              {reviewReport?.unsupported_claims && reviewReport.unsupported_claims.length > 0 && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900">
                  <p className="font-bold text-amber-950 mb-1">
                    Ungrounded Claims ({reviewReport.unsupported_claims.length}):
                  </p>
                  <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                    {reviewReport.unsupported_claims.map((claim, idx) => (
                      <li key={idx} className="line-clamp-2">
                        {claim}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Feedback Textarea */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">
                  Executive Feedback / Change Request Instructions (Required if requesting revision):
                </label>
                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  disabled={submitting}
                  placeholder="e.g., Provide exact RTO/RPO metrics in Section 3 and ground cloud region guarantees..."
                  className="w-full text-xs p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none min-h-[90px] disabled:bg-slate-100"
                />
              </div>

              {/* Escalation Override Notice */}
              {isHumanReviewRequired && criticalFindings.length > 0 && (
                <div className="p-3 bg-rose-50 border border-rose-300 rounded-lg text-[11px] text-rose-900 font-medium">
                  Caution: Approving this draft will authorize export despite unresolved critical findings.
                </div>
              )}
            </div>
          )}

          {/* Stale / Non-Gate State */}
          {!isGoNoGo && !isFinalApproval && (
            <div className="p-6 text-center space-y-3">
              <AlertCircle className="w-8 h-8 text-amber-500 mx-auto" />
              <h4 className="text-sm font-bold text-slate-800">Workflow Not Awaiting Decision</h4>
              <p className="text-xs text-slate-500">
                The current workflow status is <strong>{status.status}</strong>. This checkpoint is not actively awaiting input.
              </p>
              <button
                onClick={() => {
                  onResumed();
                  onClose();
                }}
                className="px-4 py-2 text-xs font-bold rounded-lg bg-slate-900 text-white hover:bg-slate-800 transition"
              >
                Refresh & Close
              </button>
            </div>
          )}
        </div>

        {/* Action Buttons Footer */}
        {(isGoNoGo || isFinalApproval) && (
          <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-3">
            {isGoNoGo ? (
              <>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => handleSubmit('NO_GO')}
                  className="px-4 py-2 text-xs font-bold rounded-lg border border-rose-300 bg-rose-50 text-rose-700 hover:bg-rose-100 flex items-center gap-1.5 transition disabled:opacity-50"
                >
                  {submitting && activeDecision === 'NO_GO' ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <ThumbsDown className="w-4 h-4" />
                  )}
                  Abort Bid (NO-GO)
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => handleSubmit('GO')}
                  className="px-5 py-2 text-xs font-bold rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm flex items-center gap-1.5 transition disabled:opacity-50"
                >
                  {submitting && activeDecision === 'GO' ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <ThumbsUp className="w-4 h-4" />
                  )}
                  Authorize Bid (GO)
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => handleSubmit('REJECTED')}
                  className="px-4 py-2 text-xs font-bold rounded-lg border border-rose-300 bg-rose-50 text-rose-700 hover:bg-rose-100 flex items-center gap-1.5 transition disabled:opacity-50"
                >
                  {submitting && activeDecision === 'REJECTED' ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <XCircle className="w-4 h-4" />
                  )}
                  Reject Proposal
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => handleSubmit('CHANGES_REQUESTED')}
                  className="px-4 py-2 text-xs font-bold rounded-lg border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 flex items-center gap-1.5 transition disabled:opacity-50"
                >
                  {submitting && activeDecision === 'CHANGES_REQUESTED' ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <RefreshCw className="w-4 h-4" />
                  )}
                  Request Changes
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => handleSubmit('APPROVED')}
                  className="px-5 py-2 text-xs font-bold rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm flex items-center gap-1.5 transition disabled:opacity-50"
                >
                  {submitting && activeDecision === 'APPROVED' ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="w-4 h-4" />
                  )}
                  Approve for Export
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
