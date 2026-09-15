import React, { useState } from 'react';
import { Layers, Database, LayoutDashboard, Sparkles } from 'lucide-react';
import { Dashboard } from './pages/Dashboard';
import { RFPWorkspace } from './pages/RFPWorkspace';
import { KnowledgeBaseManager } from './components/knowledge/KnowledgeBaseManager';

export function App() {
  const [currentPage, setCurrentPage] = useState<'dashboard' | 'workspace' | 'knowledge'>('dashboard');
  const [selectedRfpId, setSelectedRfpId] = useState<string | null>(null);

  const navigateToWorkspace = (rfpId: string) => {
    setSelectedRfpId(rfpId);
    setCurrentPage('workspace');
  };

  const navigateToDashboard = () => {
    setSelectedRfpId(null);
    setCurrentPage('dashboard');
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      {/* Global Top Navbar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3 cursor-pointer" onClick={navigateToDashboard}>
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-600 to-indigo-600 flex items-center justify-center text-white shadow-sm shadow-sky-500/20">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-black text-sm tracking-tight text-slate-900 leading-none">
                AGENTIC RFP RESPONSE
              </h1>
              <span className="text-[10px] text-slate-400 font-mono tracking-wider uppercase font-semibold">
                Multi-Agent LangGraph System
              </span>
            </div>
          </div>

          <nav className="flex items-center gap-1.5">
            <button
              onClick={navigateToDashboard}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                currentPage === 'dashboard' || currentPage === 'workspace'
                  ? 'bg-slate-100 text-slate-900'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              <LayoutDashboard className="w-4 h-4 text-sky-600" />
              Projects
            </button>

            <button
              onClick={() => setCurrentPage('knowledge')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                currentPage === 'knowledge'
                  ? 'bg-slate-100 text-slate-900'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              <Database className="w-4 h-4 text-indigo-600" />
              Knowledge Base (RAG)
            </button>
          </nav>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {currentPage === 'dashboard' && (
          <Dashboard
            onSelectRFP={navigateToWorkspace}
            onNavigateKnowledge={() => setCurrentPage('knowledge')}
          />
        )}

        {currentPage === 'workspace' && selectedRfpId && (
          <RFPWorkspace
            rfpId={selectedRfpId}
            onBack={navigateToDashboard}
          />
        )}

        {currentPage === 'knowledge' && (
          <KnowledgeBaseManager />
        )}
      </main>

      {/* Global Footer */}
      <footer className="border-t border-slate-200 bg-white py-4 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2 text-[11px] text-slate-400">
          <p>Agentic AI RFP Analysis & Proposal Response System &bull; Production Architecture</p>
          <p className="font-mono">Backend: FastAPI + LangGraph &bull; Frontend: React + Tailwind</p>
        </div>
      </footer>
    </div>
  );
}

export default App;
