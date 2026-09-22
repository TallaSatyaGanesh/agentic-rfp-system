import React from 'react';
import {
  FileText,
  Layers,
  ShieldCheck,
  AlertTriangle,
  PenTool,
  CheckCircle2,
  UserCheck,
  RefreshCw,
  Clock,
  AlertOctagon,
  XCircle,
  LucideIcon
} from 'lucide-react';
import { WorkflowStatus, WorkflowState, SSEConnectionStatus } from '../../types';

interface Props {
  status: WorkflowStatus | null;
  onOpenApproval: () => void;
  connectionStatus?: SSEConnectionStatus;
  onRetryWorkflow?: () => void;
  starting?: boolean;
}

type NodeVisualState =
  | 'pending'
  | 'running'
  | 'completed'
  | 'awaiting_action'
  | 'human_review_required'
  | 'failed'
  | 'aborted'
  | 'rejected'
  | 'disabled';

interface PipelineNode {
  id: string;
  name: string;
  desc: string;
  icon: LucideIcon;
  isGate?: boolean;
  activeKeywords: string[];
  doneKeywords: WorkflowState[];
}

export const WorkflowVisualizer: React.FC<Props> = ({
  status,
  onOpenApproval,
  connectionStatus = 'disconnected',
  onRetryWorkflow,
  starting = false
}) => {
  const activeAgent = status?.active_agent || 'None';
  const workflowStatus: WorkflowState = status?.status || 'NOT_STARTED';
  const isInterrupted = status?.is_interrupted || false;
  const interruptType = status?.interrupt_type;
  const currentVersion = status?.current_version || 0;
  const revisionCount = Math.max(status?.revision_count || 0, Math.max(0, currentVersion - 1));

  const isHumanReviewRequired = workflowStatus === 'HUMAN_REVIEW_REQUIRED';
  const isAwaitingAction =
    isInterrupted ||
    isHumanReviewRequired ||
    workflowStatus === 'AWAITING_GO_NOGO' ||
    workflowStatus === 'AWAITING_FINAL_APPROVAL';

  const nodes: PipelineNode[] = [
    {
      id: 'extract',
      name: '1. Extraction Agent',
      desc: 'Document hierarchy & clause parsing',
      icon: FileText,
      activeKeywords: ['Extraction', 'EXTRACTING'],
      doneKeywords: [
        'CLASSIFYING',
        'ANALYZING_COMPLIANCE',
        'ASSESSING_RISKS',
        'AWAITING_GO_NOGO',
        'ABORTED_NO_GO',
        'WRITING_PROPOSAL',
        'REVIEWING',
        'REVISING',
        'AWAITING_FINAL_APPROVAL',
        'HUMAN_REVIEW_REQUIRED',
        'APPROVED_FOR_EXPORT',
        'REJECTED',
        'COMPLETED'
      ]
    },
    {
      id: 'classify',
      name: '2. Classification Agent',
      desc: 'REQ-ID assignment & categories',
      icon: Layers,
      activeKeywords: ['Classification', 'CLASSIFYING'],
      doneKeywords: [
        'ANALYZING_COMPLIANCE',
        'ASSESSING_RISKS',
        'AWAITING_GO_NOGO',
        'ABORTED_NO_GO',
        'WRITING_PROPOSAL',
        'REVIEWING',
        'REVISING',
        'AWAITING_FINAL_APPROVAL',
        'HUMAN_REVIEW_REQUIRED',
        'APPROVED_FOR_EXPORT',
        'REJECTED',
        'COMPLETED'
      ]
    },
    {
      id: 'compliance',
      name: '3. Compliance Agent',
      desc: 'RAG audit against company knowledge',
      icon: ShieldCheck,
      activeKeywords: ['Compliance', 'ANALYZING_COMPLIANCE'],
      doneKeywords: [
        'ASSESSING_RISKS',
        'AWAITING_GO_NOGO',
        'ABORTED_NO_GO',
        'WRITING_PROPOSAL',
        'REVIEWING',
        'REVISING',
        'AWAITING_FINAL_APPROVAL',
        'HUMAN_REVIEW_REQUIRED',
        'APPROVED_FOR_EXPORT',
        'REJECTED',
        'COMPLETED'
      ]
    },
    {
      id: 'risk',
      name: '4. Risk & Clarification',
      desc: 'Contract terms & tender questions',
      icon: AlertTriangle,
      activeKeywords: ['Risk', 'ASSESSING_RISKS'],
      doneKeywords: [
        'AWAITING_GO_NOGO',
        'ABORTED_NO_GO',
        'WRITING_PROPOSAL',
        'REVIEWING',
        'REVISING',
        'AWAITING_FINAL_APPROVAL',
        'HUMAN_REVIEW_REQUIRED',
        'APPROVED_FOR_EXPORT',
        'REJECTED',
        'COMPLETED'
      ]
    },
    {
      id: 'gate1',
      name: 'Human Gate 1: Go / No-Go',
      desc: 'Mandatory bid qualification checkpoint',
      icon: UserCheck,
      isGate: true,
      activeKeywords: ['AWAITING_GO_NOGO'],
      doneKeywords: [
        'WRITING_PROPOSAL',
        'REVIEWING',
        'REVISING',
        'AWAITING_FINAL_APPROVAL',
        'HUMAN_REVIEW_REQUIRED',
        'APPROVED_FOR_EXPORT',
        'REJECTED',
        'COMPLETED'
      ]
    },
    {
      id: 'writer',
      name: '5. Proposal Writer',
      desc:
        workflowStatus === 'REVISING'
          ? `Revising draft (v${Math.max(currentVersion, 1)})`
          : `Structured response (v${Math.max(currentVersion, 1)})`,
      icon: PenTool,
      activeKeywords: ['Writer', 'WRITING_PROPOSAL', 'REVISING'],
      doneKeywords: [
        'REVIEWING',
        'AWAITING_FINAL_APPROVAL',
        'HUMAN_REVIEW_REQUIRED',
        'APPROVED_FOR_EXPORT',
        'REJECTED',
        'COMPLETED'
      ]
    },
    {
      id: 'reviewer',
      name: '6. Reviewer / Critic',
      desc: `Red team review (Cycle ${revisionCount}/2)`,
      icon: RefreshCw,
      activeKeywords: ['Reviewer', 'REVIEWING'],
      doneKeywords: [
        'AWAITING_FINAL_APPROVAL',
        'HUMAN_REVIEW_REQUIRED',
        'APPROVED_FOR_EXPORT',
        'REJECTED',
        'COMPLETED'
      ]
    },
    {
      id: 'gate2',
      name: 'Human Gate 2: Final Sign-off',
      desc: isHumanReviewRequired ? 'Escalated review required' : 'Proposal validation & export release',
      icon: isHumanReviewRequired ? AlertOctagon : CheckCircle2,
      isGate: true,
      activeKeywords: ['AWAITING_FINAL_APPROVAL', 'HUMAN_REVIEW_REQUIRED'],
      doneKeywords: ['APPROVED_FOR_EXPORT', 'COMPLETED']
    }
  ];

  const getNodeState = (node: PipelineNode): NodeVisualState => {
    // 1. Workflow Failure
    if (workflowStatus === 'FAILED') {
      const isFailedActive = node.activeKeywords.some(
        (k) => activeAgent.includes(k) || k === activeAgent
      );
      if (isFailedActive) {
        return 'failed';
      }
      if (node.doneKeywords.includes(workflowStatus)) {
        return 'completed';
      }
      return 'disabled';
    }

    // 2. Terminal workflow abort at Gate 1
    if (workflowStatus === 'ABORTED_NO_GO') {
      if (node.id === 'gate1') return 'aborted';
      if (['writer', 'reviewer', 'gate2'].includes(node.id)) return 'disabled';
    }

    // 3. Terminal workflow rejection at Gate 2
    if (workflowStatus === 'REJECTED' && node.id === 'gate2') {
      return 'rejected';
    }

    // 4. Dedicated HUMAN_REVIEW_REQUIRED state on Gate 2
    if (node.id === 'gate2' && isHumanReviewRequired) {
      return 'human_review_required';
    }

    // 5. Interrupted / awaiting human gates
    if (node.isGate) {
      if (
        node.id === 'gate1' &&
        (interruptType === 'GO_NOGO' || workflowStatus === 'AWAITING_GO_NOGO')
      ) {
        return 'awaiting_action';
      }
      if (
        node.id === 'gate2' &&
        (interruptType === 'FINAL_APPROVAL' || workflowStatus === 'AWAITING_FINAL_APPROVAL')
      ) {
        return 'awaiting_action';
      }
    }

    // 6. Active agent execution
    if (node.activeKeywords.some((k) => activeAgent.includes(k) || workflowStatus === k)) {
      return 'running';
    }

    // 7. Completed stages
    if (node.doneKeywords.includes(workflowStatus)) {
      return 'completed';
    }

    return 'pending';
  };

  return (
    <div className="space-y-6">
      {/* Visual Pipeline Grid */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-100">
          <div>
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-sky-500 animate-pulse"></span>
              Multi-Agent Orchestration Pipeline (LangGraph)
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Deterministic state machine with automated revision loops and human approval checkpoints
            </p>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            {/* SSE Connection Health Badge */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${
                connectionStatus === 'connected'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : connectionStatus === 'reconnecting'
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : connectionStatus === 'completed'
                  ? 'bg-sky-50 text-sky-700 border-sky-200'
                  : 'bg-slate-100 text-slate-600 border-slate-200'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  connectionStatus === 'connected'
                    ? 'bg-emerald-500 animate-pulse'
                    : connectionStatus === 'reconnecting'
                    ? 'bg-amber-500 animate-ping'
                    : connectionStatus === 'completed'
                    ? 'bg-sky-500'
                    : 'bg-slate-400'
                }`}
              />
              {connectionStatus === 'connected'
                ? 'SSE Live'
                : connectionStatus === 'reconnecting'
                ? 'Reconnecting...'
                : connectionStatus === 'completed'
                ? 'Stream Complete'
                : 'Offline (Polling)'}
            </span>

            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-700">
              Active: {activeAgent}
            </span>

            {revisionCount > 0 && (
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-purple-100 text-purple-800 border border-purple-200">
                Revision: Cycle {revisionCount}/2
              </span>
            )}

            {isAwaitingAction && (
              <button
                onClick={onOpenApproval}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white shadow-sm transition ${
                  isHumanReviewRequired
                    ? 'bg-rose-600 hover:bg-rose-700 ring-2 ring-rose-300 animate-bounce'
                    : 'bg-amber-500 hover:bg-amber-600 ring-2 ring-amber-300 animate-bounce'
                }`}
              >
                {isHumanReviewRequired ? <AlertOctagon className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
                {isHumanReviewRequired ? 'Escalation Required' : 'Action Required'}
              </button>
            )}
          </div>
        </div>

        {/* Dedicated State Banners */}
        {workflowStatus === 'FAILED' && (
          <div className="mb-6 p-4 rounded-xl border border-rose-300 bg-rose-50 text-rose-900 flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in fade-in duration-200">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-600 mt-0.5 shrink-0" />
              <div>
                <h4 className="text-sm font-bold text-rose-900">Workflow Execution Failed</h4>
                <p className="text-xs text-rose-700 mt-0.5">
                  {status?.error || 'An error occurred during agent orchestration. You can retry or re-run the workflow.'}
                </p>
              </div>
            </div>
            {onRetryWorkflow && (
              <button
                onClick={onRetryWorkflow}
                disabled={starting}
                className="px-4 py-2 text-xs font-bold rounded-lg bg-rose-600 hover:bg-rose-700 disabled:bg-slate-300 text-white shadow-sm shrink-0 flex items-center justify-center gap-1.5 transition"
              >
                <RefreshCw className={`w-4 h-4 ${starting ? 'animate-spin' : ''}`} />
                {starting ? 'Retrying...' : 'Retry Workflow'}
              </button>
            )}
          </div>
        )}

        {isHumanReviewRequired && (
          <div className="mb-6 p-4 rounded-xl border border-rose-300 bg-rose-50/90 text-rose-900 flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in fade-in duration-200">
            <div className="flex items-start gap-3">
              <AlertOctagon className="w-5 h-5 text-rose-600 mt-0.5 shrink-0" />
              <div>
                <h4 className="text-sm font-bold text-rose-900">Mandatory Human Escalation Required</h4>
                <p className="text-xs text-rose-700 mt-0.5">
                  The Reviewer Agent detected unresolved critical findings or the maximum automated revision limit (2/2) has been reached. A human proposal manager must evaluate the proposal to approve, request changes, or reject.
                </p>
              </div>
            </div>
            <button
              onClick={onOpenApproval}
              className="px-4 py-2 text-xs font-bold rounded-lg bg-rose-600 hover:bg-rose-700 text-white shadow-sm shrink-0 flex items-center justify-center gap-1.5 transition"
            >
              <AlertOctagon className="w-4 h-4" />
              Review Escalation
            </button>
          </div>
        )}

        {workflowStatus === 'APPROVED_FOR_EXPORT' && (
          <div className="mb-6 p-4 rounded-xl border border-emerald-300 bg-emerald-50 text-emerald-900 flex items-center gap-3 animate-in fade-in duration-200">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
            <div>
              <h4 className="text-sm font-bold text-emerald-900">Proposal Approved for Export</h4>
              <p className="text-xs text-emerald-700 mt-0.5">
                Draft v{Math.max(currentVersion, 1)} has passed human sign-off and is ready for export.
              </p>
            </div>
          </div>
        )}

        {workflowStatus === 'ABORTED_NO_GO' && (
          <div className="mb-6 p-4 rounded-xl border border-rose-300 bg-rose-50 text-rose-900 flex items-center gap-3 animate-in fade-in duration-200">
            <XCircle className="w-5 h-5 text-rose-600 shrink-0" />
            <div>
              <h4 className="text-sm font-bold text-rose-900">Bid Aborted at Gate 1 (NO-GO Decision)</h4>
              <p className="text-xs text-rose-700 mt-0.5">
                The qualification review concluded with a NO-GO decision. Proposal authoring and review were halted.
              </p>
            </div>
          </div>
        )}

        {workflowStatus === 'REJECTED' && (
          <div className="mb-6 p-4 rounded-xl border border-rose-300 bg-rose-50 text-rose-900 flex items-center gap-3 animate-in fade-in duration-200">
            <XCircle className="w-5 h-5 text-rose-600 shrink-0" />
            <div>
              <h4 className="text-sm font-bold text-rose-900">Proposal Rejected at Gate 2</h4>
              <p className="text-xs text-rose-700 mt-0.5">
                The proposal was rejected by the human reviewer and will not be exported.
              </p>
            </div>
          </div>
        )}

        {/* Node Pipeline Flow */}
        <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {nodes.map((node) => {
            const state = getNodeState(node);
            const Icon = node.icon;

            let borderClass = 'border-slate-200 bg-slate-50 text-slate-400';
            let badgeClass = 'bg-slate-200 text-slate-500';
            let statusText = 'Pending';

            if (state === 'running') {
              borderClass = 'border-sky-500 bg-sky-50/50 text-sky-700 shadow-sm ring-2 ring-sky-200';
              badgeClass = 'bg-sky-500 text-white animate-pulse';
              statusText = 'Active';
            } else if (state === 'completed') {
              borderClass = 'border-emerald-500 bg-emerald-50/30 text-emerald-800';
              badgeClass = 'bg-emerald-600 text-white';
              statusText = 'Done';
            } else if (state === 'awaiting_action') {
              borderClass = 'border-amber-500 bg-amber-50 text-amber-900 ring-2 ring-amber-300 animate-pulse';
              badgeClass = 'bg-amber-500 text-white';
              statusText = 'Approval';
            } else if (state === 'human_review_required') {
              borderClass = 'border-rose-500 bg-rose-50 text-rose-900 ring-2 ring-rose-300 animate-pulse';
              badgeClass = 'bg-rose-600 text-white animate-pulse';
              statusText = 'Escalated';
            } else if (state === 'failed') {
              borderClass = 'border-rose-500 bg-rose-50/80 text-rose-900 shadow-sm ring-2 ring-rose-200';
              badgeClass = 'bg-rose-700 text-white animate-pulse';
              statusText = 'Failed';
            } else if (state === 'aborted') {
              borderClass = 'border-rose-300 bg-rose-50 text-rose-700';
              badgeClass = 'bg-rose-500 text-white';
              statusText = 'Aborted';
            } else if (state === 'rejected') {
              borderClass = 'border-rose-300 bg-rose-50 text-rose-700';
              badgeClass = 'bg-rose-500 text-white';
              statusText = 'Rejected';
            } else if (state === 'disabled') {
              borderClass = 'border-slate-200 bg-slate-100/50 text-slate-400 opacity-60';
              badgeClass = 'bg-slate-200 text-slate-400';
              statusText = 'Skipped';
            }

            return (
              <div
                key={node.id}
                className={`relative p-3 rounded-lg border text-left transition-all duration-200 flex flex-col justify-between ${borderClass}`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div
                      className={`p-1.5 rounded-md ${
                        state === 'running'
                          ? 'bg-sky-100 text-sky-700'
                          : state === 'completed'
                          ? 'bg-emerald-100 text-emerald-700'
                          : state === 'human_review_required' || state === 'failed'
                          ? 'bg-rose-100 text-rose-700'
                          : state === 'awaiting_action'
                          ? 'bg-amber-100 text-amber-700'
                          : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                    </div>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${badgeClass}`}>
                      {statusText}
                    </span>
                  </div>

                  <h4 className="text-xs font-bold text-slate-800 line-clamp-1">{node.name}</h4>
                  <p className="text-[11px] text-slate-500 mt-1 line-clamp-2 leading-tight">{node.desc}</p>
                </div>

                {node.isGate && (state === 'awaiting_action' || state === 'human_review_required') && (
                  <button
                    onClick={onOpenApproval}
                    className={`mt-3 w-full py-1 text-[11px] font-bold rounded shadow-sm text-white transition ${
                      state === 'human_review_required'
                        ? 'bg-rose-600 hover:bg-rose-700'
                        : 'bg-amber-500 hover:bg-amber-600'
                    }`}
                  >
                    {state === 'human_review_required' ? 'Review Escalation' : 'Review Now'}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Execution Telemetry Log Console */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 text-slate-300 shadow-inner">
        <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-sky-400" />
            <span className="text-xs font-mono font-bold text-slate-200 uppercase tracking-wider">
              Agent Execution & State Telemetry
            </span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono">
            Status: <strong className="text-sky-300">{workflowStatus}</strong>
          </span>
        </div>

        <div className="space-y-2 max-h-48 overflow-y-auto font-mono text-xs pr-2">
          {!status?.logs || status.logs.length === 0 ? (
            <p className="text-slate-500 italic">No agent execution logs recorded yet. Start workflow to begin.</p>
          ) : (
            status.logs.map((log, i) => {
              const isHuman =
                log.agent.toLowerCase().includes('human') ||
                log.agent.toLowerCase().includes('manager');
              const isSystem = log.agent.toLowerCase().includes('system');

              return (
                <div
                  key={`${log.timestamp}_${log.agent}_${i}`}
                  className={`flex items-start gap-2 border-l-2 pl-2.5 py-0.5 ${
                    isHuman
                      ? 'border-amber-500/70 bg-amber-950/20'
                      : isSystem
                      ? 'border-slate-500/70'
                      : 'border-sky-500/40'
                  }`}
                >
                  <span className="text-slate-500 text-[10px] whitespace-nowrap">
                    {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ''}
                  </span>
                  <span
                    className={`font-bold whitespace-nowrap ${
                      isHuman
                        ? 'text-amber-300'
                        : isSystem
                        ? 'text-slate-400'
                        : 'text-sky-400'
                    }`}
                  >
                    [{log.agent}]
                  </span>
                  <span className="text-slate-200">{log.action}</span>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
