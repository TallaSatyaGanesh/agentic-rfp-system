import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  Search,
  Filter,
  ChevronRight,
  X,
  BookOpen,
  RotateCcw,
  FileText
} from 'lucide-react';
import { ComplianceItem, ComplianceStatus, RequirementCategory } from '../../types';

interface Props {
  items: ComplianceItem[];
}

const CATEGORIES: ('ALL' | RequirementCategory)[] = [
  'ALL',
  'Technical',
  'Commercial',
  'Contractual',
  'Administrative',
  'Certification',
  'Delivery',
  'Documentation',
  'Submission',
  'Eligibility'
];

const STATUSES: ('ALL' | ComplianceStatus)[] = [
  'ALL',
  'COMPLIANT',
  'PARTIALLY_COMPLIANT',
  'NON_COMPLIANT',
  'INFORMATION_REQUIRED'
];

export const ComplianceMatrixTable: React.FC<Props> = ({ items }) => {
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [selectedMandatory, setSelectedMandatory] = useState<string>('ALL');
  const [activeItem, setActiveItem] = useState<ComplianceItem | null>(null);

  const resetFilters = () => {
    setSearch('');
    setSelectedCategory('ALL');
    setSelectedStatus('ALL');
    setSelectedMandatory('ALL');
  };

  const hasActiveFilters =
    search.trim() !== '' ||
    selectedCategory !== 'ALL' ||
    selectedStatus !== 'ALL' ||
    selectedMandatory !== 'ALL';

  const counts = {
    total: items.length,
    compliant: items.filter((i) => i.status === 'COMPLIANT').length,
    partial: items.filter((i) => i.status === 'PARTIALLY_COMPLIANT').length,
    nonCompliant: items.filter((i) => i.status === 'NON_COMPLIANT').length,
    infoRequired: items.filter((i) => i.status === 'INFORMATION_REQUIRED').length
  };

  const filtered = items.filter((item) => {
    const query = search.trim().toLowerCase();
    const matchesSearch =
      !query ||
      item.req_code.toLowerCase().includes(query) ||
      item.requirement_text.toLowerCase().includes(query) ||
      (item.company_source_doc ? item.company_source_doc.toLowerCase().includes(query) : false) ||
      (item.notes ? item.notes.toLowerCase().includes(query) : false) ||
      (item.citations
        ? item.citations.some(
            (c) =>
              (c.document_title ? c.document_title.toLowerCase().includes(query) : false) ||
              (c.snippet ? c.snippet.toLowerCase().includes(query) : false)
          )
        : false);

    const matchesCat =
      selectedCategory === 'ALL' ||
      item.category.toLowerCase() === selectedCategory.toLowerCase();

    const matchesStatus =
      selectedStatus === 'ALL' || item.status === selectedStatus;

    const matchesMandatory =
      selectedMandatory === 'ALL' ||
      (selectedMandatory === 'MANDATORY' && item.is_mandatory === true) ||
      (selectedMandatory === 'OPTIONAL' && item.is_mandatory === false);

    return matchesSearch && matchesCat && matchesStatus && matchesMandatory;
  });

  const getStatusBadge = (status: ComplianceStatus) => {
    switch (status) {
      case 'COMPLIANT':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            COMPLIANT
          </span>
        );
      case 'PARTIALLY_COMPLIANT':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            PARTIALLY COMPLIANT
          </span>
        );
      case 'NON_COMPLIANT':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">
            <XCircle className="w-3.5 h-3.5 text-rose-600" />
            NON-COMPLIANT
          </span>
        );
      case 'INFORMATION_REQUIRED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-orange-100 text-orange-900 border border-orange-300 animate-pulse">
            <HelpCircle className="w-3.5 h-3.5 text-orange-600" />
            INFORMATION REQUIRED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Search & Filter Header */}
      <div className="p-5 border-b border-slate-200 bg-slate-50/50 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search requirements, evidence, or citations..."
              className="w-full text-xs pl-9 pr-4 py-2 border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-sky-500 focus:outline-none"
            />
          </div>

          {/* Metric Badges */}
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
            <span className="px-2.5 py-1 rounded-md bg-slate-100 text-slate-700">
              Total: {counts.total}
            </span>
            <span className="px-2.5 py-1 rounded-md bg-emerald-100 text-emerald-800">
              Compliant: {counts.compliant}
            </span>
            <span className="px-2.5 py-1 rounded-md bg-amber-100 text-amber-800">
              Partial: {counts.partial}
            </span>
            <span className="px-2.5 py-1 rounded-md bg-orange-100 text-orange-900">
              Info Needed: {counts.infoRequired}
            </span>
            <span className="px-2.5 py-1 rounded-md bg-rose-100 text-rose-800">
              Non-Compliant: {counts.nonCompliant}
            </span>
          </div>
        </div>

        {/* Filter Controls */}
        <div className="space-y-2 pt-2 border-t border-slate-200/60">
          {/* Status Filter */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 mr-2 text-xs font-bold text-slate-500">
              <Filter className="w-3.5 h-3.5" /> Status:
            </div>
            {STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => setSelectedStatus(s)}
                className={`text-xs px-2.5 py-1 rounded-md font-medium transition ${
                  selectedStatus === s
                    ? 'bg-slate-800 text-white shadow-sm'
                    : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                }`}
              >
                {s === 'ALL' ? 'ALL STATUSES' : s.replace(/_/g, ' ')}
              </button>
            ))}
          </div>

          {/* Category Filter */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 mr-2 text-xs font-bold text-slate-500">
              Category:
            </div>
            {CATEGORIES.map((c) => (
              <button
                key={c}
                onClick={() => setSelectedCategory(c)}
                className={`text-xs px-2.5 py-1 rounded-md font-medium transition ${
                  selectedCategory === c
                    ? 'bg-sky-600 text-white shadow-sm'
                    : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                }`}
              >
                {c === 'ALL' ? 'ALL CATEGORIES' : c}
              </button>
            ))}

            {hasActiveFilters && (
              <button
                onClick={resetFilters}
                className="inline-flex items-center gap-1 text-xs text-rose-600 hover:text-rose-800 font-semibold ml-auto px-2 py-1"
                title="Reset all filters"
              >
                <RotateCcw className="w-3 h-3" /> Reset Filters
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Table */}
      {items.length === 0 ? (
        <div className="p-12 text-center text-slate-500 space-y-3">
          <BookOpen className="w-10 h-10 text-slate-300 mx-auto" />
          <h4 className="text-sm font-bold text-slate-700">No Compliance Records Found</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Run the multi-agent workflow to extract requirements and perform the automated RAG compliance evaluation against company collateral.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-100/75 text-slate-700 font-bold border-b border-slate-200 uppercase tracking-wider text-[11px]">
              <tr>
                <th className="py-3 px-4">Req Code</th>
                <th className="py-3 px-4">Category</th>
                <th className="py-3 px-4">Requirement Statement</th>
                <th className="py-3 px-4">Verdict</th>
                <th className="py-3 px-4">Knowledge Base Evidence / Limitation</th>
                <th className="py-3 px-4 text-right">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-500">
                    <div className="space-y-2">
                      <p className="text-xs font-medium">No requirements match the current filters.</p>
                      <button
                        onClick={resetFilters}
                        className="inline-flex items-center gap-1 text-xs text-sky-600 hover:text-sky-800 font-semibold"
                      >
                        <RotateCcw className="w-3.5 h-3.5" /> Reset Filters
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                filtered.map((item) => (
                  <tr
                    key={item.id || item.req_code}
                    className="hover:bg-sky-50/40 transition cursor-pointer"
                    onClick={() => setActiveItem(item)}
                  >
                    <td className="py-3 px-4 font-mono font-bold text-sky-700 whitespace-nowrap">
                      <div>{item.req_code}</div>
                      {item.is_mandatory !== undefined && (
                        <span
                          className={`inline-block mt-0.5 px-1.5 py-0.2 rounded text-[9px] font-bold uppercase tracking-wider ${
                            item.is_mandatory
                              ? 'bg-rose-100 text-rose-700'
                              : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {item.is_mandatory ? 'Mandatory' : 'Optional'}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700">
                        {item.category}
                      </span>
                    </td>
                    <td className="py-3 px-4 max-w-md">
                      <p className="line-clamp-2 text-slate-800 font-medium">{item.requirement_text}</p>
                      <span className="text-[10px] text-slate-400">
                        Page {item.source_page ?? 1} &bull; {item.source_section || 'General'}
                      </span>
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      {getStatusBadge(item.status)}
                    </td>
                    <td className="py-3 px-4 max-w-xs">
                      {item.status === 'COMPLIANT' ? (
                        item.company_source_doc ? (
                          <div className="text-slate-700">
                            <span className="font-semibold text-slate-900 block truncate">
                              {item.company_source_doc}
                            </span>
                            <span className="text-[10px] text-emerald-600 font-mono">
                              Match: {(item.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-emerald-700 text-[11px] font-medium">
                            Grounded in verified capabilities
                          </span>
                        )
                      ) : item.status === 'PARTIALLY_COMPLIANT' ? (
                        <div className="text-amber-900">
                          <span className="font-semibold block truncate">
                            {item.notes || 'Partial coverage identified'}
                          </span>
                          <span className="text-[10px] text-amber-700">
                            {item.company_source_doc ? `Ref: ${item.company_source_doc}` : 'Scope limitation applies'}
                          </span>
                        </div>
                      ) : item.status === 'NON_COMPLIANT' ? (
                        <div className="text-rose-900">
                          <span className="font-semibold block truncate">
                            {item.notes || 'Requirement unsupported'}
                          </span>
                          <span className="text-[10px] text-rose-700">
                            Exception required
                          </span>
                        </div>
                      ) : (
                        <div className="text-orange-900">
                          <span className="font-semibold block truncate">
                            {item.notes || 'Information required'}
                          </span>
                          <span className="text-[10px] text-orange-700 italic">
                            Verification collateral needed
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-700">
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Slide-over Detail Drawer */}
      {activeItem && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40 backdrop-blur-xs">
          <div className="bg-white w-full max-w-lg h-full shadow-2xl p-6 overflow-y-auto flex flex-col justify-between animate-in slide-in-from-right duration-200">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-slate-200 mb-6">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-sky-600">{activeItem.req_code}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                      {activeItem.category}
                    </span>
                    {activeItem.is_mandatory !== undefined && (
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                          activeItem.is_mandatory
                            ? 'bg-rose-100 text-rose-700'
                            : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {activeItem.is_mandatory ? 'Mandatory' : 'Optional'}
                      </span>
                    )}
                  </div>
                  <h3 className="font-bold text-base text-slate-900 mt-1">
                    Requirement Traceability & Compliance Deep Dive
                  </h3>
                </div>
                <button
                  onClick={() => setActiveItem(null)}
                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-6 text-xs">
                {/* Status Callout */}
                <div className="flex items-center justify-between p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                  <div>
                    <span className="font-bold text-slate-600 block">Compliance Verdict:</span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Match Confidence: {(activeItem.confidence * 100).toFixed(1)}%
                      {activeItem.similarity_score !== undefined && activeItem.similarity_score !== null && (
                        <span> &bull; Retrieval: {(activeItem.similarity_score * 100).toFixed(1)}%</span>
                      )}
                    </span>
                  </div>
                  {getStatusBadge(activeItem.status)}
                </div>

                {/* Original RFP Source */}
                <div>
                  <h4 className="font-bold text-slate-900 mb-2 uppercase text-[11px] tracking-wider text-slate-500">
                    Source RFP Specification
                  </h4>
                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-800 leading-relaxed font-serif">
                    "{activeItem.requirement_text}"
                  </div>
                  <div className="mt-2 flex items-center gap-4 text-[11px] text-slate-500 font-mono">
                    <span>Source Page: <strong>{activeItem.source_page ?? 'N/A'}</strong></span>
                    <span>Section: <strong>{activeItem.source_section || 'General'}</strong></span>
                  </div>
                </div>

                {/* Status-Specific Grounding Section */}
                <div>
                  <h4 className="font-bold text-slate-900 mb-2 uppercase text-[11px] tracking-wider text-slate-500">
                    {activeItem.status === 'COMPLIANT'
                      ? 'Verified Company Knowledge Evidence'
                      : activeItem.status === 'PARTIALLY_COMPLIANT'
                      ? 'Scope Limitation & Gap Analysis'
                      : activeItem.status === 'NON_COMPLIANT'
                      ? 'Non-Compliance Justification & Exception'
                      : 'Information Required & Verification Need'}
                  </h4>

                  {activeItem.status === 'COMPLIANT' && (
                    activeItem.evidence_text ? (
                      <div className="p-4 rounded-xl bg-emerald-50/60 border border-emerald-200 text-emerald-950 space-y-2">
                        <p className="font-sans leading-relaxed">{activeItem.evidence_text}</p>
                        <div className="pt-2 border-t border-emerald-200/60 flex items-center justify-between text-[10px] text-emerald-800 font-mono">
                          <span>Document: <strong>{activeItem.company_source_doc || 'Knowledge Base'}</strong></span>
                          <span>Confidence: <strong>{(activeItem.confidence * 100).toFixed(1)}%</strong></span>
                        </div>
                      </div>
                    ) : (
                      <div className="p-4 rounded-xl bg-emerald-50/60 border border-emerald-200 text-emerald-950">
                        <p className="font-semibold">Compliant with verified standard procedures.</p>
                        {activeItem.company_source_doc && (
                          <p className="text-[11px] text-emerald-800 mt-1">Source: {activeItem.company_source_doc}</p>
                        )}
                      </div>
                    )
                  )}

                  {activeItem.status === 'PARTIALLY_COMPLIANT' && (
                    <div className="p-4 rounded-xl bg-amber-50/60 border border-amber-200 text-amber-950 space-y-3">
                      <div>
                        <span className="font-bold text-amber-900 block text-[11px] uppercase tracking-wider">Identified Limitation:</span>
                        <p className="font-sans leading-relaxed mt-1">
                          {activeItem.notes || 'The company partially supports this requirement with specific scope limitations.'}
                        </p>
                      </div>
                      {activeItem.evidence_text && (
                        <div className="pt-2 border-t border-amber-200/60">
                          <span className="font-semibold text-amber-900 block text-[10px]">Verified Supporting Portion:</span>
                          <p className="font-sans text-[11px] text-amber-900 mt-0.5 italic">"{activeItem.evidence_text}"</p>
                        </div>
                      )}
                      {activeItem.company_source_doc && (
                        <div className="text-[10px] text-amber-800 font-mono">
                          Source Document: {activeItem.company_source_doc}
                        </div>
                      )}
                    </div>
                  )}

                  {activeItem.status === 'NON_COMPLIANT' && (
                    <div className="p-4 rounded-xl bg-rose-50/60 border border-rose-200 text-rose-950 space-y-2">
                      <p className="font-semibold text-rose-900">Formal Exception Required</p>
                      <p className="font-sans leading-relaxed">
                        {activeItem.notes || 'The company knowledge base confirms this capability is currently unsupported.'}
                      </p>
                      <p className="text-[10px] text-rose-700 italic pt-1 border-t border-rose-200/60">
                        Proposal generator will address this requirement as an exception without making unsupported capability claims.
                      </p>
                    </div>
                  )}

                  {activeItem.status === 'INFORMATION_REQUIRED' && (
                    <div className="p-4 rounded-xl bg-orange-50/60 border border-orange-200 text-orange-950 space-y-2">
                      <p className="font-semibold text-orange-900 flex items-center gap-1.5">
                        <HelpCircle className="w-4 h-4 text-orange-600" />
                        Verification or Collateral Required
                      </p>
                      <p className="font-sans leading-relaxed">
                        {activeItem.notes || 'No verified collateral confirming this requirement was found in the knowledge base. Requires internal SME verification or tender clarification.'}
                      </p>
                      <p className="text-[10px] text-orange-800 italic pt-1 border-t border-orange-200/60">
                        Proposal writer is restricted from inventing affirmative capability commitments for this requirement until verified.
                      </p>
                    </div>
                  )}
                </div>

                {/* Additional Auditor Notes if applicable */}
                {activeItem.notes && activeItem.status === 'COMPLIANT' && (
                  <div>
                    <h4 className="font-bold text-slate-900 mb-2 uppercase text-[11px] tracking-wider text-slate-500">
                      Auditor Evaluation Notes
                    </h4>
                    <p className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-slate-600 leading-relaxed">
                      {activeItem.notes}
                    </p>
                  </div>
                )}

                {/* Granular Source Citations & Provenance */}
                <div>
                  <h4 className="font-bold text-slate-900 mb-2 uppercase text-[11px] tracking-wider text-slate-500 flex items-center justify-between">
                    <span>Source Citations & Provenance</span>
                    <span className="text-[10px] font-mono text-slate-400">
                      {activeItem.citations?.length || 0} Citation{(activeItem.citations?.length || 0) === 1 ? '' : 's'}
                    </span>
                  </h4>

                  {activeItem.citations && activeItem.citations.length > 0 ? (
                    <div className="space-y-3">
                      {activeItem.citations.map((cit, idx) => (
                        <div
                          key={cit.chunk_id || `${activeItem.req_code}-cit-${idx}`}
                          className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50 space-y-1.5"
                        >
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-semibold text-slate-900 flex items-center gap-1">
                              <FileText className="w-3.5 h-3.5 text-sky-600" />
                              {cit.document_title || cit.filename || 'Company Collateral'}
                            </span>
                            {cit.similarity_score !== undefined && (
                              <span className="font-mono text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                                Match: {(cit.similarity_score * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>

                          {cit.snippet && (
                            <p className="text-[11px] text-slate-700 font-sans leading-relaxed italic bg-white p-2.5 rounded border border-slate-200/80">
                              "{cit.snippet}"
                            </p>
                          )}

                          <div className="flex items-center gap-3 text-[10px] text-slate-500 font-mono">
                            <span>Page: <strong>{cit.source_page ?? 'N/A'}</strong></span>
                            <span>Section: <strong>{cit.source_section || 'General'}</strong></span>
                            {cit.company_doc_id && (
                              <span className="truncate max-w-[120px]" title={cit.company_doc_id}>
                                Doc: {cit.company_doc_id}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-slate-500 text-[11px] italic">
                      No granular chunk citations attached for this requirement.
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="pt-6 border-t border-slate-200 mt-6">
              <button
                onClick={() => setActiveItem(null)}
                className="w-full py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg font-bold text-xs"
              >
                Close Drawer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
