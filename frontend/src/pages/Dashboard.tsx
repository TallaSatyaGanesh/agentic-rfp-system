import React, { useState, useEffect } from 'react';
import { FileText, Plus, ArrowRight, ShieldCheck, AlertCircle, Clock, Database } from 'lucide-react';
import { RFPDocumentSummary } from '../types';
import { api } from '../services/api';
import { DocumentUploadModal } from '../components/ingestion/DocumentUploadModal';

interface Props {
  onSelectRFP: (rfpId: string) => void;
  onNavigateKnowledge: () => void;
}

export const Dashboard: React.FC<Props> = ({ onSelectRFP, onNavigateKnowledge }) => {
  const [rfps, setRfps] = useState<RFPDocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  useEffect(() => {
    loadRFPs();
  }, []);

  const loadRFPs = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.listRFPs();
      setRfps(data);
    } catch (err) {
      console.error('Failed to load RFPs:', err);
      setError('Unable to load RFP projects. Please verify the backend server is running.');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const s = (status || 'UPLOADED').toUpperCase();

    switch (s) {
      case 'UPLOADED':
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
            UPLOADED
          </span>
        );
      case 'ANALYZING':
      case 'PROCESSING':
      case 'RESUMING':
      case 'EXTRACTING':
      case 'CLASSIFYING':
      case 'ANALYZING_COMPLIANCE':
      case 'ASSESSING_RISKS':
      case 'WRITING_PROPOSAL':
      case 'REVISING':
      case 'REVIEWING':
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-sky-100 text-sky-800 border border-sky-200 animate-pulse">
            ANALYZING
          </span>
        );
      case 'AWAITING_GO_NOGO':
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
            AWAITING GO/NO-GO
          </span>
        );
      case 'AWAITING_FINAL_APPROVAL':
      case 'HUMAN_REVIEW_REQUIRED':
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-indigo-100 text-indigo-800 border border-indigo-200">
            AWAITING FINAL APPROVAL
          </span>
        );
      case 'APPROVED_FOR_EXPORT':
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            APPROVED FOR EXPORT
          </span>
        );
      case 'COMPLETED':
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            COMPLETED
          </span>
        );
      case 'ABORTED_NO_GO':
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
            ABORTED (NO-GO)
          </span>
        );
      case 'REJECTED':
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
            REJECTED
          </span>
        );
      case 'FAILED':
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
            FAILED
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
            {s.replace(/_/g, ' ')}
          </span>
        );
    }
  };

  return (
    <div className="space-y-8">
      {/* Top Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-sky-950 to-slate-900 rounded-2xl p-8 text-white shadow-md relative overflow-hidden">
        <div className="relative z-10 max-w-2xl">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-sky-500/20 text-sky-300 border border-sky-500/30 mb-3">
            Autonomous Multi-Agent System &bull; LangGraph Orchestrated
          </span>
          <h2 className="text-2xl sm:text-3xl font-black tracking-tight">
            Agentic RFP Analysis & Proposal Response System
          </h2>
          <p className="text-slate-300 text-xs sm:text-sm mt-2 leading-relaxed">
            Ingest complex RFPs, extract requirements, audit compliance against verified company collateral via RAG,
            identify contractual risks, and generate scored, iterative proposal responses with human-in-the-loop sign-off.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              onClick={() => setIsUploadOpen(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 font-bold text-xs shadow-md transition"
            >
              <Plus className="w-4 h-4" /> New RFP Analysis
            </button>
            <button
              onClick={onNavigateKnowledge}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-semibold text-xs border border-white/20 transition"
            >
              <Database className="w-4 h-4 text-sky-400" /> Manage Company Knowledge Base
            </button>
          </div>
        </div>

        {/* Decorative background glow */}
        <div className="absolute right-0 top-0 -mt-8 -mr-8 w-80 h-80 bg-sky-500/10 rounded-full blur-3xl pointer-events-none"></div>
      </div>

      {/* Projects List Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-slate-900">Active RFP Projects</h3>
          <p className="text-xs text-slate-500">Track multi-agent analysis status and proposal outputs</p>
        </div>
        <button
          onClick={loadRFPs}
          className="text-xs font-semibold text-sky-600 hover:text-sky-700"
        >
          Refresh List
        </button>
      </div>

      {/* Grid of Projects */}
      {error && !loading && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={loadRFPs}
            className="px-3 py-1 rounded bg-rose-200 hover:bg-rose-300 text-rose-900 font-bold transition"
          >
            Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-xs text-slate-400">Loading RFP projects...</div>
      ) : rfps.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center shadow-sm">
          <FileText className="w-12 h-12 text-slate-300 mx-auto mb-3" />
          <h4 className="text-sm font-bold text-slate-800">No RFP Projects Uploaded Yet</h4>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            Click "New RFP Analysis" to upload a PDF or DOCX tender document and initiate the multi-agent workflow.
          </p>
          <button
            onClick={() => setIsUploadOpen(true)}
            className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold rounded-lg shadow-sm"
          >
            <Plus className="w-4 h-4" /> Upload First RFP
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {rfps.map((rfp) => (
            <div
              key={rfp.id}
              onClick={() => onSelectRFP(rfp.id)}
              className="bg-white rounded-xl border border-slate-200 hover:border-sky-400 p-5 shadow-sm hover:shadow-md transition cursor-pointer flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="font-mono text-[10px] font-bold text-slate-400">{rfp.id}</span>
                  {getStatusBadge(rfp.status)}
                </div>

                <h4
                  className="font-bold text-sm text-slate-900 group-hover:text-sky-600 line-clamp-2 transition mb-1 break-all"
                  title={rfp.filename}
                >
                  {rfp.filename || rfp.title}
                </h4>
                <p className="text-xs text-slate-500 line-clamp-1 mb-4">
                  Issuer: <strong>{rfp.issuer}</strong>
                </p>

                <div className="flex items-center gap-4 text-[11px] text-slate-500 border-t border-slate-100 pt-3">
                  <span>Pages: <strong>{rfp.page_count}</strong></span>
                  <span>Due: <strong>{rfp.submission_deadline || 'Open'}</strong></span>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-bold text-sky-600 group-hover:translate-x-1 transition">
                <span>Open Workspace</span>
                <ArrowRight className="w-4 h-4" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Upload Modal */}
      <DocumentUploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploaded={(rfpId) => {
          loadRFPs();
          onSelectRFP(rfpId);
        }}
      />
    </div>
  );
};
