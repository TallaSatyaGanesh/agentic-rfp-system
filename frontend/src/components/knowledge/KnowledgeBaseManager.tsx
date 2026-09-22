import React, { useState, useEffect } from 'react';
import { Database, Upload, Search, FileText, CheckCircle2, AlertCircle, Trash2 } from 'lucide-react';
import { CompanyDoc, RAGChunk } from '../../types';
import { api } from '../../services/api';

export const KnowledgeBaseManager: React.FC = () => {
  const [docs, setDocs] = useState<CompanyDoc[]>([]);
  const [uploading, setUploading] = useState(false);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('Technical');
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // RAG Query Playground state
  const [query, setQuery] = useState('');
  const [querying, setQuerying] = useState(false);
  const [testResults, setTestResults] = useState<RAGChunk[]>([]);
  const [queryError, setQueryError] = useState<string | null>(null);

  useEffect(() => {
    loadDocs();
  }, []);

  const loadDocs = async () => {
    try {
      const data = await api.listCompanyDocs();
      setDocs(data);
    } catch (err) {
      console.error('Failed to load company docs:', err);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    try {
      setUploading(true);
      setUploadError(null);
      await api.uploadCompanyDoc(file, title, category);
      setTitle('');
      setFile(null);
      await loadDocs();
    } catch (err) {
      console.error('Failed to upload document:', err);
      setUploadError('Upload failed. Please ensure file is a valid PDF, DOCX, or TXT document.');
    } finally {
      setUploading(false);
    }
  };

  const handleTestQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    try {
      setQuerying(true);
      setQueryError(null);
      const res = await api.testQueryRAG(query, 0.20);
      setTestResults(res.results || []);
    } catch (err) {
      console.error('Query test failed:', err);
      setQueryError('RAG query failed. Please verify the backend vector store is available.');
    } finally {
      setQuerying(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Upload & Indexing Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-100 mb-6">
          <div className="p-2.5 rounded-xl bg-sky-100 text-sky-700">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-base text-slate-900">Demo Company Knowledge Base & Grounding RAG</h3>
            <p className="text-xs text-slate-500">
              Upload verified corporate policies, white papers, and past proposals to prevent hallucinations.
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Demonstration knowledge base — synthetic data used for assignment evaluation. Replace with authorized company documents for production deployment.
            </p>
          </div>
        </div>

        {uploadError && (
          <div className="mb-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{uploadError}</span>
            </div>
            <button
              onClick={() => setUploadError(null)}
              className="text-rose-500 hover:text-rose-700 font-bold ml-2"
            >
              &times;
            </button>
          </div>
        )}

        <form onSubmit={handleUpload} className="grid grid-cols-1 sm:grid-cols-4 gap-4 items-end">
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Document Title</label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., SOC2 Type II Audit Summary"
              className="w-full text-xs p-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Category</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full text-xs p-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none bg-white"
            >
              <option value="Technical">Technical Architecture</option>
              <option value="Security">Security & Compliance</option>
              <option value="Case Study">Past Performance & Case Study</option>
              <option value="Legal">Legal & Standard SLAs</option>
              <option value="General">General Collateral</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">File (PDF, DOCX, TXT)</label>
            <input
              type="file"
              required
              accept=".pdf,.docx,.txt"
              onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
              className="w-full text-xs text-slate-500 file:mr-2 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200"
            />
          </div>

          <div>
            <button
              type="submit"
              disabled={uploading || !file}
              className="w-full py-2.5 bg-sky-600 hover:bg-sky-700 disabled:bg-slate-300 text-white font-bold text-xs rounded-lg shadow-sm flex items-center justify-center gap-1.5 transition"
            >
              <Upload className="w-4 h-4" />
              {uploading ? 'Chunking & Indexing...' : 'Upload & Index'}
            </button>
          </div>
        </form>
      </div>

      {/* Indexed Documents Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
            Indexed Company Collateral ({docs.length})
          </h4>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-100/60 text-slate-700 font-bold border-b border-slate-200 uppercase text-[11px]">
              <tr>
                <th className="py-3 px-4">Document Title</th>
                <th className="py-3 px-4">Category</th>
                <th className="py-3 px-4">Filename</th>
                <th className="py-3 px-4">Chunks Indexed</th>
                <th className="py-3 px-4">Indexed At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {docs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400 italic">
                    No documents indexed yet. Upload company collateral above.
                  </td>
                </tr>
              ) : (
                docs.map((d) => (
                  <tr key={d.id} className="hover:bg-slate-50">
                    <td className="py-3 px-4 font-bold text-slate-800 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-sky-600 shrink-0" />
                      {d.title}
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                        {d.category}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-500 font-mono text-[11px]">{d.filename}</td>
                    <td className="py-3 px-4 font-mono font-bold text-emerald-700">{d.chunk_count} chunks</td>
                    <td className="py-3 px-4 text-slate-400">
                      {new Date(d.indexed_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Interactive RAG Playground */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div>
          <h4 className="font-bold text-sm text-slate-900 flex items-center gap-2">
            <Search className="w-4 h-4 text-sky-600" />
            Interactive RAG Semantic Search & Grounding Test Playground
          </h4>
          <p className="text-xs text-slate-500 mt-0.5">
            Test how the Compliance Agent retrieves evidence and enforces the zero-hallucination threshold
          </p>
        </div>

        <form onSubmit={handleTestQuery} className="flex gap-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask a technical or compliance question (e.g., 'What is our uptime SLA?')..."
            className="flex-1 text-xs p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={querying || !query.trim()}
            className="px-5 py-2.5 bg-slate-800 hover:bg-slate-900 text-white font-bold text-xs rounded-lg shadow-sm transition"
          >
            {querying ? 'Searching...' : 'Run RAG Query'}
          </button>
        </form>

        {queryError && (
          <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{queryError}</span>
            </div>
            <button
              onClick={() => setQueryError(null)}
              className="text-rose-500 hover:text-rose-700 font-bold ml-2"
            >
              &times;
            </button>
          </div>
        )}

        {testResults.length > 0 && (
          <div className="mt-4 space-y-3 pt-4 border-t border-slate-100">
            <span className="text-xs font-bold text-slate-700">Retrieved Grounding Evidence Chunks:</span>
            {testResults.map((r, i) => (
              <div key={i} className="p-3.5 rounded-xl border border-emerald-200 bg-emerald-50/50 text-xs space-y-2">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-bold text-emerald-900">{r.document_title}</span>
                  <span className="font-mono px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold">
                    Similarity Match: {(r.similarity * 100).toFixed(1)}%
                  </span>
                </div>
                <p className="text-slate-800 leading-relaxed font-sans">{r.evidence_text}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
