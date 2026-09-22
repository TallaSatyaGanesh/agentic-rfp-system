import React, { useState } from 'react';
import { AlertTriangle, ShieldAlert, HelpCircle, Copy, Check, FileText } from 'lucide-react';
import { RiskItem, ClarificationQuestion } from '../../types';

interface Props {
  risks: RiskItem[];
  clarifications: ClarificationQuestion[];
  rfpTitle: string;
}

export const RiskRegisterPanel: React.FC<Props> = ({ risks, clarifications, rfpTitle }) => {
  const [copied, setCopied] = useState(false);

  const criticalAndHighRisks = risks.filter((r) => r.severity === 'CRITICAL' || r.severity === 'HIGH');
  const medRisks = risks.filter((r) => r.severity === 'MEDIUM');
  const lowRisks = risks.filter((r) => r.severity === 'LOW');

  const copyClarificationLetter = () => {
    let letter = `FORMAL VENDOR CLARIFICATION QUESTIONS\nProject: ${rfpTitle}\nDate: ${new Date().toLocaleDateString()}\n\n`;
    clarifications.forEach((q) => {
      letter += `Question ${q.q_number} [Reference: ${q.rfp_section_reference}]\n`;
      letter += `Query: ${q.question_text}\n`;
      letter += `Rationale: ${q.rationale}\n\n`;
    });

    navigator.clipboard.writeText(letter);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Risk Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-5 rounded-xl border border-rose-200 bg-rose-50/60 shadow-sm flex items-center justify-between">
          <div>
            <span className="text-xs font-bold text-rose-800 uppercase tracking-wider">Critical / High Risks</span>
            <h4 className="text-2xl font-black text-rose-900 mt-1">{criticalAndHighRisks.length}</h4>
            <p className="text-[11px] text-rose-700 mt-0.5">Requires executive mitigation or legal carve-outs</p>
          </div>
          <div className="p-3 bg-rose-200/60 text-rose-800 rounded-xl">
            <ShieldAlert className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 rounded-xl border border-amber-200 bg-amber-50/60 shadow-sm flex items-center justify-between">
          <div>
            <span className="text-xs font-bold text-amber-800 uppercase tracking-wider">Medium Risks</span>
            <h4 className="text-2xl font-black text-amber-900 mt-1">{medRisks.length}</h4>
            <p className="text-[11px] text-amber-700 mt-0.5">Manageable via delivery sprint planning</p>
          </div>
          <div className="p-3 bg-amber-200/60 text-amber-800 rounded-xl">
            <AlertTriangle className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 rounded-xl border border-sky-200 bg-sky-50/60 shadow-sm flex items-center justify-between">
          <div>
            <span className="text-xs font-bold text-sky-800 uppercase tracking-wider">Clarification Queries</span>
            <h4 className="text-2xl font-black text-sky-900 mt-1">{clarifications.length}</h4>
            <p className="text-[11px] text-sky-700 mt-0.5">Structured for tender committee submission</p>
          </div>
          <div className="p-3 bg-sky-200/60 text-sky-800 rounded-xl">
            <HelpCircle className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Risk Register Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
            Project & Contractual Risk Register
          </h3>
          <span className="text-xs text-slate-500 font-medium">Total Risks Identified: {risks.length}</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-100 text-slate-700 font-bold border-b border-slate-200 uppercase text-[11px]">
              <tr>
                <th className="py-3 px-4">Category</th>
                <th className="py-3 px-4">Severity</th>
                <th className="py-3 px-4">Likelihood</th>
                <th className="py-3 px-4">Risk Description</th>
                <th className="py-3 px-4">Actionable Mitigation Strategy</th>
                <th className="py-3 px-4">Reference</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {risks.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400 italic">
                    No risks identified yet. Complete risk assessment workflow stage to populate register.
                  </td>
                </tr>
              ) : (
                risks.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50/60 transition">
                    <td className="py-3 px-4 font-semibold text-slate-800">
                      <div>{r.category}</div>
                      {r.requirement_id && (
                        <div className="text-[10px] font-mono text-slate-400 font-normal">{r.requirement_id}</div>
                      )}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          r.severity === 'CRITICAL'
                            ? 'bg-rose-200 text-rose-900 border border-rose-300 font-extrabold'
                            : r.severity === 'HIGH'
                            ? 'bg-rose-100 text-rose-800 border border-rose-200'
                            : r.severity === 'MEDIUM'
                            ? 'bg-amber-100 text-amber-800 border border-amber-200'
                            : 'bg-slate-100 text-slate-700'
                        }`}
                      >
                        {r.severity}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-600">{r.likelihood}</td>
                    <td className="py-3 px-4 max-w-sm text-slate-800 font-medium">{r.description}</td>
                    <td className="py-3 px-4 max-w-md text-slate-700">{r.mitigation_strategy}</td>
                    <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">{r.rfp_reference || 'N/A'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Formal Clarification Questions Panel */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-200 mb-6">
          <div>
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <FileText className="w-4 h-4 text-sky-600" />
              Formal Clarification Questions for Tender Authority
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Drafted by the Risk Agent to resolve ambiguities and contractual uncertainties
            </p>
          </div>

          <button
            onClick={copyClarificationLetter}
            disabled={clarifications.length === 0}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-700 border border-slate-300 transition"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? 'Copied to Clipboard!' : 'Copy Clarification Letter'}
          </button>
        </div>

        <div className="space-y-4">
          {clarifications.length === 0 ? (
            <div className="py-6 text-center text-slate-400 text-xs italic">
              No formal clarification questions generated yet.
            </div>
          ) : (
            clarifications.map((q) => (
              <div key={q.id} className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-sky-700">Question #{q.q_number}</span>
                  <span className="text-[11px] font-mono bg-white px-2 py-0.5 rounded border border-slate-200 text-slate-500">
                    {q.rfp_section_reference}
                  </span>
                </div>
                <p className="text-xs font-semibold text-slate-900">{q.question_text}</p>
                <p className="text-[11px] text-slate-500 italic">Rationale: {q.rationale}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
