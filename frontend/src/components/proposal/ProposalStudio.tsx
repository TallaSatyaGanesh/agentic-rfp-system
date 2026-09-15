import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Download,
  Award,
  ShieldAlert,
  CheckCircle,
  RefreshCw,
  Layers,
  FileText,
  AlertTriangle,
  XCircle,
  HelpCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Search,
  Filter,
  Info
} from 'lucide-react';
import {
  ProposalDraft,
  ProposalSection,
  RequirementResponse,
  ReviewReport,
  ReviewFinding,
  RubricScore,
  ResponseType,
  ReviewStatus,
  RiskSeverity,
  Citation
} from '../../types';
import { api } from '../../services/api';

interface Props {
  rfpId: string;
  proposals: ProposalDraft[];
}

function parseReviewData(input: string | ReviewReport | null | undefined): ReviewReport | null {
  if (!input) return null;
  if (typeof input !== 'string') {
    return input;
  }
  try {
    const data = JSON.parse(input);
    if (data && typeof data === 'object') {
      return data;
    }
  } catch {
    return null;
  }
  return null;
}

export const ProposalStudio: React.FC<Props> = ({ rfpId, proposals }) => {
  const [selectedVersion, setSelectedVersion] = useState<number>(
    proposals.length > 0 ? proposals[proposals.length - 1].version : 1
  );
  const [activeTab, setActiveTab] = useState<'document' | 'responses' | 'review'>('document');
  const [findingSeverityFilter, setFindingSeverityFilter] = useState<string>('ALL');
  const [findingSearch, setFindingSearch] = useState<string>('');
  const [responseTypeFilter, setResponseTypeFilter] = useState<string>('ALL');
  const [responseSearch, setResponseSearch] = useState<string>('');
  const [expandedResponse, setExpandedResponse] = useState<string | null>(null);

  if (!proposals || proposals.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-12 text-center shadow-sm">
        <Layers className="w-12 h-12 text-slate-300 mx-auto mb-3" />
        <h3 className="text-base font-bold text-slate-800">No Proposal Drafts Generated Yet</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
          Start the multi-agent workflow to trigger extraction, compliance audit, proposal drafting, and reviewer critique.
        </p>
      </div>
    );
  }

  const currentDraft = proposals.find((p) => p.version === selectedVersion) || proposals[proposals.length - 1];
  const reviewData: ReviewReport | null = parseReviewData(currentDraft.review_feedback);

  const requirementResponses: RequirementResponse[] = currentDraft.requirement_responses || [];
  const sections: ProposalSection[] = currentDraft.sections || [];
  const reviewScore = reviewData?.score ?? reviewData?.overall_score ?? currentDraft.review_score ?? 0;
  const reviewStatus: ReviewStatus | null = reviewData?.overall_status ?? null;
  const findings: ReviewFinding[] = reviewData?.findings || [];
  const rubricScores: RubricScore[] = reviewData?.rubric_scores || [];

  const filteredFindings = findings.filter((f) => {
    const matchesSev = findingSeverityFilter === 'ALL' || f.severity === findingSeverityFilter;
    const query = findingSearch.trim().toLowerCase();
    const matchesSearch =
      !query ||
      f.description.toLowerCase().includes(query) ||
      f.category.toLowerCase().includes(query) ||
      (f.requirement_id ? f.requirement_id.toLowerCase().includes(query) : false) ||
      f.recommended_action.toLowerCase().includes(query);
    return matchesSev && matchesSearch;
  });

  const filteredResponses = requirementResponses.filter((r) => {
    const matchesType = responseTypeFilter === 'ALL' || r.response_type === responseTypeFilter;
    const query = responseSearch.trim().toLowerCase();
    const matchesSearch =
      !query ||
      r.requirement_id.toLowerCase().includes(query) ||
      (r.requirement_text ? r.requirement_text.toLowerCase().includes(query) : false) ||
      (r.response ? r.response.toLowerCase().includes(query) : false) ||
      (r.response_text ? r.response_text.toLowerCase().includes(query) : false) ||
      (r.category ? r.category.toLowerCase().includes(query) : false);
    return matchesType && matchesSearch;
  });

  const getResponseTypeBadge = (type: ResponseType) => {
    switch (type) {
      case 'COMPLIANT_RESPONSE':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            COMPLIANT RESPONSE
          </span>
        );
      case 'PARTIAL_RESPONSE':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
            <AlertTriangle className="w-3 h-3 text-amber-600" />
            PARTIAL RESPONSE
          </span>
        );
      case 'EXCEPTION_RESPONSE':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
            <XCircle className="w-3 h-3 text-rose-600" />
            EXCEPTION RESPONSE
          </span>
        );
      case 'INFORMATION_REQUIRED_RESPONSE':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-900 border border-orange-300">
            <HelpCircle className="w-3 h-3 text-orange-600" />
            INFORMATION REQUIRED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
            {type}
          </span>
        );
    }
  };

  const getReviewStatusBadge = (status: ReviewStatus | null) => {
    switch (status) {
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />
            APPROVED FOR SUBMISSION
          </span>
        );
      case 'REVISION_REQUIRED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">
            <RefreshCw className="w-3.5 h-3.5 text-amber-600" />
            REVISION REQUIRED
          </span>
        );
      case 'HUMAN_REVIEW_REQUIRED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-900 border border-rose-300 animate-pulse">
            <ShieldAlert className="w-3.5 h-3.5 text-rose-600" />
            HUMAN REVIEW REQUIRED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-200">
            REVIEW PENDING
          </span>
        );
    }
  };

  const getFindingSeverityBadge = (severity: RiskSeverity) => {
    switch (severity) {
      case 'CRITICAL':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-black bg-rose-100 text-rose-800 border border-rose-300">
            CRITICAL
          </span>
        );
      case 'HIGH':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-800 border border-orange-200">
            HIGH
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-200">
            MEDIUM
          </span>
        );
      case 'LOW':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
            LOW
          </span>
        );
    }
  };

  const isApproved = currentDraft.status === 'APPROVED' || reviewStatus === 'APPROVED';

  return (
    <div className="space-y-6">
      {/* Top Controls Bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        {/* Version Switcher */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider mr-1">Version:</span>
          {proposals.map((p) => (
            <button
              key={p.version}
              onClick={() => setSelectedVersion(p.version)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                selectedVersion === p.version
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
              }`}
            >
              Draft v{p.version}
              {p.version === 1 ? ' (Initial)' : ' (Revised)'}
            </button>
          ))}
          <span className="text-xs text-slate-400 ml-2 font-mono">
            Status: <strong className={isApproved ? 'text-emerald-700' : 'text-slate-700'}>{currentDraft.status || 'DRAFT'}</strong>
          </span>
        </div>

        {/* View Switcher Tabs */}
        <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-lg">
          <button
            onClick={() => setActiveTab('document')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold transition ${
              activeTab === 'document'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            Proposal Document
          </button>
          <button
            onClick={() => setActiveTab('responses')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold transition ${
              activeTab === 'responses'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Requirement Responses
            {requirementResponses.length > 0 && (
              <span className="text-[10px] bg-slate-200 px-1.5 py-0.2 rounded-full">
                {requirementResponses.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('review')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold transition ${
              activeTab === 'review'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Award className="w-3.5 h-3.5" />
            Reviewer Critique
            {reviewData && (
              <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                reviewScore >= 80 ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
              }`}>
                {reviewScore}
              </span>
            )}
          </button>
        </div>

        {/* Export Button */}
        <a
          href={api.getExportUrl(rfpId, 'docx')}
          target="_blank"
          rel="noopener noreferrer"
          className={`inline-flex items-center gap-2 px-4 py-2 text-white text-xs font-bold rounded-lg shadow-sm transition ${
            isApproved
              ? 'bg-emerald-600 hover:bg-emerald-700'
              : 'bg-slate-700 hover:bg-slate-800'
          }`}
        >
          <Download className="w-4 h-4" />
          {isApproved ? 'Export Approved Proposal (DOCX)' : 'Export Proposal Draft (DOCX)'}
        </a>
      </div>

      {/* Reviewer Scorecard Banner (Always prominent when reviewData exists) */}
      {reviewData && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-4 border-b border-slate-100">
            <div className="flex items-center gap-4">
              <div
                className={`w-16 h-16 rounded-2xl flex flex-col items-center justify-center font-black text-white shadow-md ${
                  reviewScore >= 80
                    ? 'bg-emerald-600'
                    : reviewScore >= 60
                    ? 'bg-amber-600'
                    : 'bg-rose-600'
                }`}
              >
                <span className="text-2xl leading-none">{reviewScore}</span>
                <span className="text-[10px] uppercase font-bold opacity-80 mt-0.5">/ 100</span>
              </div>
              <div>
                <div className="flex items-center gap-2.5">
                  <h4 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Award className="w-5 h-5 text-amber-500" />
                    Agent 6 Reviewer & Critic Evaluation
                  </h4>
                  {getReviewStatusBadge(reviewStatus)}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Evaluated Draft v{currentDraft.version} &bull; Findings: <strong>{findings.length}</strong>{' '}
                  &bull; Critical: <strong>{reviewData.critical_findings?.length || 0}</strong>
                  {reviewData.reviewed_at && (
                    <span> &bull; Reviewed at: {new Date(reviewData.reviewed_at).toLocaleTimeString()}</span>
                  )}
                </p>
              </div>
            </div>

            {/* Rubric Breakdown Grid */}
            {rubricScores.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                {rubricScores.map((r, idx) => (
                  <div key={idx} className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                    <span className="text-[10px] text-slate-500 font-bold block truncate">{r.criterion}</span>
                    <span className="text-sm font-black text-slate-800">{r.score} / 25</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Actionable Directives */}
          {reviewData.actionable_revision_instructions && reviewData.actionable_revision_instructions.length > 0 && (
            <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 text-xs text-amber-950">
              <h5 className="font-bold flex items-center gap-1.5 mb-2 text-amber-900">
                <RefreshCw className="w-4 h-4 text-amber-600" />
                Actionable Revision Directives:
              </h5>
              <ul className="list-disc list-inside space-y-1 text-amber-900">
                {reviewData.actionable_revision_instructions.map((inst, i) => (
                  <li key={i}>{inst}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* TAB 1: Rendered Document View */}
      {activeTab === 'document' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-8 max-w-4xl mx-auto space-y-6">
          <div className="border-b border-slate-200 pb-4">
            <h2 className="text-xl font-black text-slate-900">{currentDraft.title || 'Proposal Response'}</h2>
            <p className="text-xs text-slate-500 mt-1">
              Draft Version {currentDraft.version} &bull; Generated by Proposal Writer Agent
            </p>
          </div>

          {sections.length > 0 ? (
            <div className="space-y-8">
              {sections.map((sec, idx) => (
                <section key={idx} className="border-b border-slate-100 pb-6 last:border-0">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-sky-800 mb-3">
                    {sec.section_title}
                  </h3>
                  <article className="prose prose-slate prose-sm max-w-none prose-headings:font-bold prose-table:text-xs">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {sec.content_markdown}
                    </ReactMarkdown>
                  </article>

                  {sec.information_required_alerts && sec.information_required_alerts.length > 0 && (
                    <div className="mt-3 p-3 rounded-lg bg-orange-50 border border-orange-200 text-orange-900 text-xs">
                      <strong className="block mb-1">Information Required Alerts:</strong>
                      <ul className="list-disc list-inside space-y-0.5">
                        {sec.information_required_alerts.map((al, aIdx) => (
                          <li key={aIdx}>{al}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </section>
              ))}
            </div>
          ) : (
            <article className="prose prose-slate prose-sm max-w-none prose-headings:font-bold prose-h2:border-b prose-h2:border-slate-200 prose-h2:pb-2 prose-h2:mt-8 prose-table:text-xs">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  blockquote: ({ node, ...props }) => (
                    <div className="my-4 p-4 rounded-xl bg-orange-50 border-l-4 border-orange-500 text-orange-950 shadow-xs">
                      {props.children}
                    </div>
                  ),
                  table: ({ node, ...props }) => (
                    <div className="overflow-x-auto my-4 border border-slate-200 rounded-lg">
                      <table className="w-full text-left divide-y divide-slate-200" {...props} />
                    </div>
                  ),
                  th: ({ node, ...props }) => (
                    <th className="bg-slate-100 p-2.5 font-bold text-slate-700 text-xs" {...props} />
                  ),
                  td: ({ node, ...props }) => (
                    <td className="p-2.5 text-xs text-slate-700" {...props} />
                  )
                }}
              >
                {currentDraft.content_markdown || currentDraft.full_markdown || 'No content available for this proposal draft.'}
              </ReactMarkdown>
            </article>
          )}
        </div>
      )}

      {/* TAB 2: Structured Requirement Responses & Provenance View */}
      {activeTab === 'responses' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-5 border-b border-slate-200 bg-slate-50/50 space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="relative flex-1 max-w-md">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={responseSearch}
                  onChange={(e) => setResponseSearch(e.target.value)}
                  placeholder="Search requirement statements, responses, or codes..."
                  className="w-full text-xs pl-9 pr-4 py-2 border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-sky-500 focus:outline-none"
                />
              </div>

              <div className="flex items-center gap-2 text-xs font-semibold text-slate-600">
                <span>Showing {filteredResponses.length} of {requirementResponses.length} responses</span>
              </div>
            </div>

            {/* Filter by Response Type */}
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-200/60">
              <span className="text-xs font-bold text-slate-500 flex items-center gap-1 mr-1">
                <Filter className="w-3.5 h-3.5" /> Response Type:
              </span>
              {[
                'ALL',
                'COMPLIANT_RESPONSE',
                'PARTIAL_RESPONSE',
                'EXCEPTION_RESPONSE',
                'INFORMATION_REQUIRED_RESPONSE'
              ].map((rt) => (
                <button
                  key={rt}
                  onClick={() => setResponseTypeFilter(rt)}
                  className={`text-xs px-2.5 py-1 rounded-md font-medium transition ${
                    responseTypeFilter === rt
                      ? 'bg-slate-800 text-white shadow-sm'
                      : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {rt === 'ALL' ? 'ALL TYPES' : rt.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          </div>

          {requirementResponses.length === 0 ? (
            <div className="p-12 text-center text-slate-500 space-y-2">
              <FileText className="w-8 h-8 text-slate-300 mx-auto" />
              <p className="text-xs font-medium">No granular requirement responses attached to this draft.</p>
              <p className="text-[11px] text-slate-400">View the Proposal Document tab to inspect the complete full proposal text.</p>
            </div>
          ) : filteredResponses.length === 0 ? (
            <div className="p-12 text-center text-slate-500 space-y-2">
              <p className="text-xs font-medium">No requirement responses match the current search or type filter.</p>
              <button
                onClick={() => {
                  setResponseSearch('');
                  setResponseTypeFilter('ALL');
                }}
                className="text-xs text-sky-600 font-semibold hover:underline"
              >
                Reset Filters
              </button>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {filteredResponses.map((resp) => {
                const isExpanded = expandedResponse === resp.requirement_id;
                const citationsList: Citation[] = resp.citations || [];

                return (
                  <div key={resp.requirement_id} className="p-5 hover:bg-slate-50/50 transition space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-sky-700 bg-sky-50 px-2 py-0.5 rounded border border-sky-200">
                          {resp.requirement_id}
                        </span>
                        <span className="text-xs font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                          {resp.category || 'General'}
                        </span>
                        {resp.is_mandatory !== undefined && (
                          <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded uppercase ${
                            resp.is_mandatory ? 'bg-rose-100 text-rose-800' : 'bg-slate-100 text-slate-600'
                          }`}>
                            {resp.is_mandatory ? 'Mandatory' : 'Optional'}
                          </span>
                        )}
                      </div>
                      <div>{getResponseTypeBadge(resp.response_type)}</div>
                    </div>

                    {/* Source Specification */}
                    <div className="text-xs text-slate-700">
                      <p className="font-serif italic bg-slate-50 p-2.5 rounded border border-slate-200/70 text-slate-800">
                        "{resp.requirement_text}"
                      </p>
                      <span className="text-[10px] text-slate-400 font-mono mt-1 block">
                        Page {resp.source_page ?? 'N/A'} &bull; Section: {resp.source_section || 'General'}
                      </span>
                    </div>

                    {/* Grounded Response Text */}
                    <div className="text-xs space-y-1">
                      <span className="font-bold text-slate-900 block text-[11px] uppercase tracking-wider">
                        Proposal Response Statement:
                      </span>
                      <p className="text-slate-800 leading-relaxed font-sans bg-white p-3 rounded-lg border border-slate-200">
                        {resp.response || resp.response_text || 'No response text recorded.'}
                      </p>
                    </div>

                    {/* Status-specific Callouts */}
                    {resp.response_type === 'PARTIAL_RESPONSE' && (
                      <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900">
                        <strong className="block mb-0.5 text-amber-950">Scope Limitation:</strong>
                        <p>This response preserves an explicit scope boundary. Full compliance is not claimed.</p>
                      </div>
                    )}

                    {resp.response_type === 'EXCEPTION_RESPONSE' && (
                      <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-900">
                        <strong className="block mb-0.5 text-rose-950">Exception Treatment:</strong>
                        <p>This requirement is recorded as a formal non-compliant exception without making false capability claims.</p>
                      </div>
                    )}

                    {resp.response_type === 'INFORMATION_REQUIRED_RESPONSE' && (
                      <div className="p-3 rounded-lg bg-orange-50 border border-orange-200 text-xs text-orange-950">
                        <strong className="block mb-0.5 text-orange-900">Verification Collateral Required:</strong>
                        <p>{resp.clarification_required || 'Internal confirmation or issuer clarification needed. No affirmative claims made.'}</p>
                      </div>
                    )}

                    {/* Citations & Provenance Toggle */}
                    <div className="pt-2">
                      <button
                        onClick={() => setExpandedResponse(isExpanded ? null : resp.requirement_id)}
                        className="inline-flex items-center gap-1 text-xs text-sky-700 hover:text-sky-900 font-semibold"
                      >
                        {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        {citationsList.length > 0
                          ? `Source Provenance (${citationsList.length} Citation${citationsList.length === 1 ? '' : 's'})`
                          : 'Source Provenance Metadata'}
                      </button>

                      {isExpanded && (
                        <div className="mt-2 p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs space-y-2">
                          {citationsList.length > 0 ? (
                            citationsList.map((cit, cIdx) => (
                              <div key={cIdx} className="p-2.5 bg-white rounded border border-slate-200 space-y-1">
                                <div className="flex items-center justify-between">
                                  <span className="font-bold text-slate-900">
                                    {cit.document_title || cit.filename || 'Company Collateral'}
                                  </span>
                                  {cit.similarity_score !== undefined && (
                                    <span className="text-[10px] font-mono text-emerald-700 bg-emerald-50 px-1 rounded">
                                      Match: {(cit.similarity_score * 100).toFixed(0)}%
                                    </span>
                                  )}
                                </div>
                                {cit.snippet && (
                                  <p className="text-[11px] text-slate-600 italic">"{cit.snippet}"</p>
                                )}
                                <div className="text-[10px] text-slate-400 font-mono flex items-center gap-2">
                                  <span>Page {cit.source_page ?? 'N/A'}</span>
                                  <span>&bull;</span>
                                  <span>Section: {cit.source_section || 'General'}</span>
                                  {cit.company_doc_id && (
                                    <>
                                      <span>&bull;</span>
                                      <span className="truncate max-w-[120px]">Doc ID: {cit.company_doc_id}</span>
                                    </>
                                  )}
                                </div>
                              </div>
                            ))
                          ) : resp.company_doc_id ? (
                            <p className="text-slate-600 font-mono text-[11px]">
                              Company Collateral ID: <strong>{resp.company_doc_id}</strong>
                            </p>
                          ) : (
                            <p className="text-slate-500 italic text-[11px]">
                              No granular chunk citations attached for this response.
                            </p>
                          )}

                          {resp.risk_summary && (
                            <div className="pt-2 border-t border-slate-200 text-slate-700">
                              <strong className="text-amber-800">Associated Risk:</strong> {resp.risk_summary}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: Reviewer Critique & Scorecard View */}
      {activeTab === 'review' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
            <div>
              <h3 className="text-base font-bold text-slate-900">Review Findings & Recommendations</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Detailed quality assurance audit conducted by the independent Reviewer/Critic Agent
              </p>
            </div>
            {reviewData && getReviewStatusBadge(reviewStatus)}
          </div>

          {!reviewData ? (
            <div className="p-12 text-center text-slate-500 space-y-2">
              <Award className="w-8 h-8 text-slate-300 mx-auto" />
              <p className="text-xs font-medium">No review report generated for this proposal version.</p>
              <p className="text-[11px] text-slate-400">Run the review agent in the multi-agent pipeline to generate structured findings.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Summary Callout */}
              {reviewData.summary && (
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-800 leading-relaxed">
                  <strong className="block text-slate-900 mb-1 uppercase text-[11px] tracking-wider">Executive Review Summary:</strong>
                  {reviewData.summary}
                </div>
              )}

              {/* Critical Findings Alert if present */}
              {reviewData.critical_findings && reviewData.critical_findings.length > 0 && (
                <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-950 space-y-2">
                  <h4 className="font-bold text-rose-900 flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4 text-rose-600" />
                    Critical Deal-Breaker Findings ({reviewData.critical_findings.length})
                  </h4>
                  <p className="text-[11px] text-rose-800">
                    These issues require immediate remediation or executive human sign-off before submission.
                  </p>
                </div>
              )}

              {/* Finding Filters */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2 border-t border-slate-200">
                <div className="relative flex-1 max-w-sm">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={findingSearch}
                    onChange={(e) => setFindingSearch(e.target.value)}
                    placeholder="Search findings by text, category, or requirement..."
                    className="w-full text-xs pl-9 pr-4 py-1.5 border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-sky-500 focus:outline-none"
                  />
                </div>

                <div className="flex items-center gap-1.5 text-xs">
                  <span className="text-slate-500 font-bold mr-1">Severity:</span>
                  {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((sev) => (
                    <button
                      key={sev}
                      onClick={() => setFindingSeverityFilter(sev)}
                      className={`px-2 py-1 rounded text-xs font-semibold transition ${
                        findingSeverityFilter === sev
                          ? 'bg-slate-800 text-white shadow-xs'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {sev}
                    </button>
                  ))}
                </div>
              </div>

              {/* Findings List */}
              {findings.length === 0 ? (
                <div className="p-8 text-center text-slate-500 rounded-xl bg-slate-50 border border-slate-200">
                  <CheckCircle2 className="w-6 h-6 text-emerald-600 mx-auto mb-1" />
                  <p className="text-xs font-bold text-slate-800">Zero Critical or Quality Flaws Detected</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">The proposal draft satisfies all compliance, grounding, and formatting standards.</p>
                </div>
              ) : filteredFindings.length === 0 ? (
                <div className="p-8 text-center text-slate-500">
                  <p className="text-xs">No findings match the current severity or search filter.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {filteredFindings.map((f) => (
                    <div
                      key={f.finding_id}
                      className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-2.5 text-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          {getFindingSeverityBadge(f.severity)}
                          <span className="font-mono font-bold text-slate-700 bg-slate-200/70 px-2 py-0.5 rounded text-[10px]">
                            {f.category}
                          </span>
                          {f.requirement_id && (
                            <span className="font-mono font-bold text-sky-700 bg-sky-50 px-2 py-0.5 rounded border border-sky-200 text-[10px]">
                              {f.requirement_id}
                            </span>
                          )}
                        </div>
                        <span className="font-mono text-[10px] text-slate-400">ID: {f.finding_id}</span>
                      </div>

                      <p className="text-slate-900 font-medium leading-relaxed">{f.description}</p>

                      {f.evidence && (
                        <div className="p-2.5 rounded bg-white border border-slate-200 text-[11px] text-slate-700 italic">
                          <strong className="not-italic text-slate-900">Evidence:</strong> "{f.evidence}"
                        </div>
                      )}

                      <div className="p-2.5 rounded bg-sky-50/60 border border-sky-200 text-[11px] text-sky-950">
                        <strong className="text-sky-900">Recommended Action:</strong> {f.recommended_action}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
