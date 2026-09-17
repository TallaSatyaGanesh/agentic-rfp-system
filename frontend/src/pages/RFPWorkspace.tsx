import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import {
  ArrowLeft,
  Play,
  Download,
  Layers,
  ShieldCheck,
  AlertTriangle,
  PenTool,
  RefreshCw,
  UserCheck,
  CheckCircle2,
  XCircle
} from 'lucide-react';
import {
  RFPDocumentSummary,
  ComplianceItem,
  RiskItem,
  ClarificationQuestion,
  ProposalDraft,
  WorkflowStatus,
  WorkflowState,
  SSEConnectionStatus,
  SSEEventPayload
} from '../types';
import { api } from '../services/api';
import { WorkflowEventSource } from '../services/sse';
import { WorkflowVisualizer } from '../components/workflow/WorkflowVisualizer';
import { HumanApprovalModal } from '../components/workflow/HumanApprovalModal';
import { ComplianceMatrixTable } from '../components/matrix/ComplianceMatrixTable';
import { RiskRegisterPanel } from '../components/risk/RiskRegisterPanel';
import { ProposalStudio } from '../components/proposal/ProposalStudio';

const ACTIVE_WORKFLOW_STATES: WorkflowState[] = [
  'PROCESSING',
  'RESUMING',
  'EXTRACTING',
  'CLASSIFYING',
  'ANALYZING_COMPLIANCE',
  'ASSESSING_RISKS',
  'WRITING_PROPOSAL',
  'REVISING',
  'REVIEWING',
];

const STATE_PRECEDENCE: Record<WorkflowState, number> = {
  NOT_STARTED: 0,
  PENDING: 1,
  PROCESSING: 1,
  RESUMING: 1,
  EXTRACTING: 2,
  CLASSIFYING: 3,
  ANALYZING_COMPLIANCE: 4,
  ASSESSING_RISKS: 5,
  AWAITING_GO_NOGO: 6,
  ABORTED_NO_GO: 10,
  WRITING_PROPOSAL: 7,
  REVISING: 7,
  REVIEWING: 8,
  AWAITING_FINAL_APPROVAL: 9,
  HUMAN_REVIEW_REQUIRED: 9,
  APPROVED_FOR_EXPORT: 10,
  REJECTED: 10,
  COMPLETED: 10,
  FAILED: 10,
};

function toWorkflowState(val: string): WorkflowState {
  switch (val) {
    case 'NOT_STARTED':
    case 'PENDING':
    case 'PROCESSING':
    case 'RESUMING':
    case 'EXTRACTING':
    case 'CLASSIFYING':
    case 'ANALYZING_COMPLIANCE':
    case 'ASSESSING_RISKS':
    case 'AWAITING_GO_NOGO':
    case 'ABORTED_NO_GO':
    case 'WRITING_PROPOSAL':
    case 'REVISING':
    case 'REVIEWING':
    case 'AWAITING_FINAL_APPROVAL':
    case 'HUMAN_REVIEW_REQUIRED':
    case 'APPROVED_FOR_EXPORT':
    case 'REJECTED':
    case 'COMPLETED':
    case 'FAILED':
      return val;
    default:
      return 'PENDING';
  }
}

interface Props {
  rfpId: string;
  onBack: () => void;
}

export const RFPWorkspace: React.FC<Props> = ({ rfpId, onBack }) => {
  const [activeTab, setActiveTab] = useState<'workflow' | 'compliance' | 'risks' | 'proposal'>('workflow');
  const [rfp, setRfp] = useState<RFPDocumentSummary | null>(null);
  const [status, setStatus] = useState<WorkflowStatus | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<SSEConnectionStatus>('disconnected');
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [complianceItems, setComplianceItems] = useState<ComplianceItem[]>([]);
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [clarifications, setClarifications] = useState<ClarificationQuestion[]>([]);
  const [proposals, setProposals] = useState<ProposalDraft[]>([]);
  const [isApprovalOpen, setIsApprovalOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const sseRef = useRef<WorkflowEventSource | null>(null);

  const isWorkflowActive = status?.status ? ACTIVE_WORKFLOW_STATES.includes(status.status) : false;
  const isWorkflowCompleted =
    status?.status === 'APPROVED_FOR_EXPORT' ||
    status?.status === 'ABORTED_NO_GO' ||
    status?.status === 'REJECTED';

  useEffect(() => {
    loadAllData();

    // Connect to SSE stream with event envelope and connection health
    const sse = new WorkflowEventSource(
      rfpId,
      (eventType: string, envelope: SSEEventPayload) => {
        console.log(`[SSE Event: ${eventType}]`, envelope);

        // Immediate reactive update on status change
        if (eventType === 'status_change') {
          if ('status' in envelope.data && typeof envelope.data.status === 'string') {
            const nextState = toWorkflowState(envelope.data.status);
            const agent =
              'active_agent' in envelope.data && typeof envelope.data.active_agent === 'string'
                ? envelope.data.active_agent
                : '';
            setStatus((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                status: nextState,
                active_agent: agent || prev.active_agent
              };
            });
          }
        } else if (eventType === 'error') {
          if ('error' in envelope.data && typeof envelope.data.error === 'string') {
            const errorText = envelope.data.error;
            setWorkflowError(errorText);
            setStatus((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                status: 'FAILED',
                error: errorText
              };
            });
          }
        }

        // Authoritative status reload
        loadStatus();
        if (['node_completed', 'human_approval_required', 'workflow_finished'].includes(eventType)) {
          loadDataOutputs();
        }
      },
      (connStatus) => {
        setConnectionStatus(connStatus);
      }
    );

    sseRef.current = sse;
    sse.connect();

    return () => {
      sse.close();
      sseRef.current = null;
    };
  }, [rfpId]);

  // Fallback polling when SSE is disconnected/failed and workflow is running
  useEffect(() => {
    if (!isWorkflowActive) return;
    if (connectionStatus === 'connected') return;

    const interval = window.setInterval(() => {
      loadStatus();
    }, 3500);

    return () => {
      window.clearInterval(interval);
    };
  }, [isWorkflowActive, connectionStatus]);

  const loadAllData = async () => {
    await Promise.all([loadDetails(), loadStatus(), loadDataOutputs()]);
  };

  const loadDetails = async () => {
    try {
      const details = await api.getRFPDetails(rfpId);
      setRfp(details);
    } catch (err) {
      console.error('Failed to load RFP details:', err);
    }
  };

  const loadStatus = async () => {
    try {
      const st = await api.getWorkflowStatus(rfpId);
      setStatus((prev) => {
        if (!prev) return st;
        // Accept new run version immediately
        if (st.current_version > prev.current_version) return st;

        const prevP = STATE_PRECEDENCE[prev.status] ?? 0;
        const nextP = STATE_PRECEDENCE[st.status] ?? 0;

        // Prevent regressing state from more advanced stage during the same version/revision
        if (
          nextP < prevP &&
          prev.current_version === st.current_version &&
          prev.revision_count >= st.revision_count
        ) {
          return {
            ...prev,
            logs: st.logs && st.logs.length > 0 ? st.logs : prev.logs
          };
        }
        return st;
      });

      const ALLOWED_APPROVAL_STATES: WorkflowState[] = [
        'AWAITING_GO_NOGO',
        'AWAITING_FINAL_APPROVAL',
        'HUMAN_REVIEW_REQUIRED'
      ];

      if (st.is_interrupted && ALLOWED_APPROVAL_STATES.includes(st.status)) {
        setIsApprovalOpen(true);
      } else {
        setIsApprovalOpen(false);
      }
    } catch (err) {
      console.error('Failed to load status:', err);
    }
  };

  const loadDataOutputs = async () => {
    try {
      const [compRes, riskRes, propRes] = await Promise.allSettled([
        api.getComplianceMatrix(rfpId),
        api.getRisks(rfpId),
        api.getProposals(rfpId),
      ]);

      if (compRes.status === 'fulfilled') setComplianceItems(compRes.value);
      if (riskRes.status === 'fulfilled') {
        setRisks(riskRes.value.risks || []);
        setClarifications(riskRes.value.clarification_questions || []);
      }
      if (propRes.status === 'fulfilled') setProposals(propRes.value);
    } catch (err) {
      console.error('Failed to load data outputs:', err);
    }
  };

  const handleStartWorkflow = async () => {
    if (starting || isWorkflowActive) return;

    try {
      setStarting(true);
      setWorkflowError(null);
      await api.startWorkflow(rfpId);
      if (sseRef.current) {
        sseRef.current.connect();
      }
      await loadStatus();
    } catch (err) {
      console.error('Failed to start workflow:', err);
      let msg = 'Failed to start workflow. Please check server logs.';
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        if (typeof detail === 'string') {
          msg = detail;
        } else if (err.message) {
          msg = err.message;
        }
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setWorkflowError(msg);
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Workspace Header */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-4">
            <button
              onClick={onBack}
              className="p-2 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-600 transition mt-0.5"
              title="Back to Dashboard"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <div className="flex items-center gap-2.5 mb-1">
                <span className="font-mono text-xs font-bold text-sky-600 uppercase">{rfpId}</span>
                <span className="text-slate-300">&bull;</span>
                <span className="text-xs text-slate-500 font-medium">Pages: {rfp?.page_count || 1}</span>
                <span className="text-slate-300">&bull;</span>
                <span className="text-xs text-slate-500 font-medium">Due: {rfp?.submission_deadline || 'Open'}</span>
              </div>
              <h2 className="text-xl font-black text-slate-900 leading-tight">
                {rfp?.title || 'RFP Analysis Workspace'}
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">Issuer: <strong>{rfp?.issuer || 'Unknown'}</strong></p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {(status?.is_interrupted ||
              status?.status === 'HUMAN_REVIEW_REQUIRED' ||
              status?.status === 'AWAITING_GO_NOGO' ||
              status?.status === 'AWAITING_FINAL_APPROVAL') ? (
              <button
                onClick={() => setIsApprovalOpen(true)}
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-white font-bold text-xs shadow-md animate-bounce ${
                  status?.status === 'HUMAN_REVIEW_REQUIRED'
                    ? 'bg-rose-600 hover:bg-rose-700'
                    : 'bg-amber-500 hover:bg-amber-600'
                }`}
              >
                <UserCheck className="w-4 h-4" />{' '}
                {status?.status === 'HUMAN_REVIEW_REQUIRED'
                  ? 'Escalation Required (Human Gate)'
                  : 'Action Required (Human Gate)'}
              </button>
            ) : (
              <button
                onClick={handleStartWorkflow}
                disabled={starting || isWorkflowActive}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 disabled:bg-slate-300 text-white font-bold text-xs shadow-sm transition"
              >
                {isWorkflowActive ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" /> Agents Running...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current" />
                    {status?.status === 'FAILED'
                      ? 'Retry Workflow'
                      : isWorkflowCompleted
                      ? 'Re-run Workflow'
                      : 'Start Multi-Agent Workflow'}
                  </>
                )}
              </button>
            )}

            {proposals.length > 0 && (
              <a
                href={api.getExportUrl(rfpId, 'docx')}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 bg-slate-50 hover:bg-slate-100 text-slate-700 font-bold text-xs transition"
              >
                <Download className="w-4 h-4 text-emerald-600" /> Export DOCX
              </a>
            )}
          </div>
        </div>

        {/* Workflow Runtime Error Alert */}
        {workflowError && (
          <div className="mt-4 p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start justify-between gap-3 animate-in fade-in duration-200">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-rose-600 mt-0.5 shrink-0" />
              <div>
                <p className="font-bold text-rose-900">Workflow Notification</p>
                <p className="text-rose-700 mt-0.5">{workflowError}</p>
              </div>
            </div>
            <button
              onClick={() => setWorkflowError(null)}
              className="text-rose-400 hover:text-rose-700 font-bold text-base leading-none p-0.5"
              title="Dismiss alert"
            >
              &times;
            </button>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 mt-6 pt-4 border-t border-slate-100 overflow-x-auto">
          <button
            onClick={() => setActiveTab('workflow')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition whitespace-nowrap ${
              activeTab === 'workflow'
                ? 'bg-slate-900 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <Layers className="w-4 h-4" />
            Live Agent Pipeline
            {isWorkflowActive && (
              <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('compliance')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition whitespace-nowrap ${
              activeTab === 'compliance'
                ? 'bg-slate-900 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
            Compliance Matrix ({complianceItems.length})
          </button>

          <button
            onClick={() => setActiveTab('risks')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition whitespace-nowrap ${
              activeTab === 'risks'
                ? 'bg-slate-900 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            Risks & Clarifications ({risks.length})
          </button>

          <button
            onClick={() => setActiveTab('proposal')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition whitespace-nowrap ${
              activeTab === 'proposal'
                ? 'bg-slate-900 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <PenTool className="w-4 h-4 text-sky-500" />
            Proposal Studio & Reviewer ({proposals.length > 0 ? `v${proposals[proposals.length - 1].version}` : 'Draft'})
          </button>
        </div>
      </div>

      {/* Tab Panels */}
      <div>
        {activeTab === 'workflow' && (
          <WorkflowVisualizer
            status={status}
            onOpenApproval={() => setIsApprovalOpen(true)}
            connectionStatus={connectionStatus}
            onRetryWorkflow={handleStartWorkflow}
            starting={starting}
          />
        )}

        {activeTab === 'compliance' && (
          <ComplianceMatrixTable items={complianceItems} />
        )}

        {activeTab === 'risks' && (
          <RiskRegisterPanel
            risks={risks}
            clarifications={clarifications}
            rfpTitle={rfp?.title || 'RFP Response'}
          />
        )}

        {activeTab === 'proposal' && (
          <ProposalStudio rfpId={rfpId} proposals={proposals} />
        )}
      </div>

      {/* Human Approval Modal */}
      <HumanApprovalModal
        rfpId={rfpId}
        status={status}
        isOpen={isApprovalOpen}
        onClose={() => setIsApprovalOpen(false)}
        onResumed={() => {
          loadAllData();
        }}
        latestProposal={proposals.length > 0 ? proposals[proposals.length - 1] : null}
        risks={risks}
        complianceItems={complianceItems}
      />
    </div>
  );
};
