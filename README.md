# Brightcone.ai — Agentic AI RFP Analysis & Proposal Response System

[![CI / CD](https://img.shields.io/badge/System-Production%20Ready-emerald.svg)](https://github.com/TallaSatyaGanesh/agentic-rfp-system)
[![Frontend](https://img.shields.io/badge/Frontend-Vercel%20Live-black.svg)](https://rfp-proposal-frontend.vercel.app)
[![Backend](https://img.shields.io/badge/Backend-Render%20Live-46E3B7.svg)](https://rfp-proposal-backend.onrender.com)
[![Swagger](https://img.shields.io/badge/API-Swagger%20Docs-blue.svg)](https://rfp-proposal-backend.onrender.com/docs)
[![License](https://img.shields.io/badge/License-MIT-gray.svg)](LICENSE)

An enterprise-grade, multi-agent AI system built with **FastAPI**, **LangGraph**, **ChromaDB**, and **React + TypeScript + Tailwind CSS**.

The system automates the end-to-end response lifecycle for complex RFPs, RFQs, and government tenders: extracting requirements, classifying clauses, auditing company compliance via grounded RAG, calculating contractual risks, formulating clarification questions, drafting structured proposals, executing red team critique and revision loops, and enforcing human-in-the-loop (HITL) authorization gates.

---

## 🌐 Live Production Deployments & Links

- **Frontend Application (Vercel):** [https://rfp-proposal-frontend.vercel.app](https://rfp-proposal-frontend.vercel.app)
- **Backend API Gateway (Render):** [https://rfp-proposal-backend.onrender.com](https://rfp-proposal-backend.onrender.com)
- **Interactive Swagger Documentation:** [https://rfp-proposal-backend.onrender.com/docs](https://rfp-proposal-backend.onrender.com/docs)
- **Health Check Path:** [https://rfp-proposal-backend.onrender.com/health](https://rfp-proposal-backend.onrender.com/health)
- **GitHub Repository:** [https://github.com/TallaSatyaGanesh/agentic-rfp-system](https://github.com/TallaSatyaGanesh/agentic-rfp-system)

---

## 🎯 Problem Statement & Core Value

Responding to enterprise and government RFPs is traditionally a slow, fragmented, and high-risk process:
- **Length & Complexity:** Tenders span 50–300+ pages of dense legal, technical, and operational obligations.
- **Scattered Evidence:** Enterprise collateral (security whitepapers, SOC 2 / ISO certifications, case studies) is siloed across departments.
- **Risk of Disqualification:** Overlooking a single mandatory requirement (`SHALL`/`MUST`) results in immediate non-compliance disqualification.
- **Contractual & SLA Pitfalls:** Uncapped liabilities, liquidated damages, and unrealistic deployment timelines are easily missed.
- **Hallucination Risk:** Generative AI solutions often fabricate organizational capabilities or commit to unverified features without grounding.

**Brightcone.ai solves this** via a coordinated 6-agent LangGraph workflow backed by strict vector grounding (ChromaDB), automated red-team critique cycles, end-to-end source traceability, and two mandatory human-in-the-loop authorization gates.

---

## 🏗️ System Architecture

```
+-----------------------------------------------------------------------------------------+
|                                 USER / PROPOSAL MANAGER                                 |
+-----------------------------------------------------------------------------------------+
                                 |                            ^
            1. Upload RFP &      |                            |  Live SSE Workflow Updates
            Company Collateral   |                            |  & Human-in-the-Loop Alerts
                                 v                            |
+-----------------------------------------------------------------------------------------+
|                           FRONTEND: REACT 18 + TS + TAILWIND                            |
|    [Dashboard] -> [Agent Visualizer] -> [Compliance Matrix] -> [Proposal Studio]         |
+-----------------------------------------------------------------------------------------+
                                 |                            ^
             REST Requests /     |                            |  SSE Event Stream
             Human Decisions     v                            |  (Active agent, logs, tokens)
+-----------------------------------------------------------------------------------------+
|                               BACKEND: FASTAPI API GATEWAY                              |
+-----------------------------------------------------------------------------------------+
                                 |
                                 v
+-----------------------------------------------------------------------------------------+
|                        LANGGRAPH MULTI-AGENT STATE MACHINE                              |
|                                                                                         |
|   +--------------------------+                                                          |
|   | Agent 1: Ingestion &     | -> Parses PDF/DOCX/TXT hierarchy, extracts metadata      |
|   | Extraction Agent         |    and discrete candidate requirement clauses            |
|   +------------+-------------+                                                          |
|                |                                                                        |
|                v                                                                        |
|   +--------------------------+                                                          |
|   | Agent 2: Classification  | -> Categorizes clauses into 9 canonical categories,      |
|   | Agent                    |    assigns REQ-IDs, and flags mandatory modals           |
|   +------------+-------------+                                                          |
|                |                                                                        |
|                v                                                                        |
|   +--------------------------+                                                          |
|   | Agent 3: Compliance &    | -> RAG audit against ChromaDB company knowledge base.    |
|   | Gap Analysis Agent       |    Assigns 4 canonical statuses with verbatim citations  |
|   +------------+-------------+                                                          |
|                |                                                                        |
|                v                                                                        |
|   +--------------------------+                                                          |
|   | Agent 4: Risk &          | -> Assesses contractual risks (CRITICAL/HIGH/MED/LOW)   |
|   | Clarification Agent      |    and drafts structured clarification questions         |
|   +------------+-------------+                                                          |
|                |                                                                        |
|                v                                                                        |
|   ===================================================================================   |
|   [ HITL GATE 1: HUMAN GO / NO-GO EXECUTIVE INTERRUPT (AWAITING_GO_NOGO) ]             |
|   ===================================================================================   |
|          | (NO_GO)                                              | (GO)                  |
|          v                                                      v                       |
|   +--------------------------+               +--------------------------------------+   |
|   | Abort Workflow           |               | Agent 5: Proposal Writer Agent       |   |
|   | (Status: ABORTED_NO_GO)  |               | (Drafts 6 structured sections with   |   |
|   | (DOCX Export Blocked)    |               |  grounded citations and gap alerts)  |   |
|   +--------------------------+               +------------------+-------------------+   |
|                                                                 |                       |
|                                                                 v                       |
|                                              +--------------------------------------+   |
|                                              | Agent 6: Proposal Reviewer / Critic  |   |
|                                              | (Scores proposal 0-100 across 4      |   |
|                                              |  rubric criteria; red-team checks)   |   |
|                                              +------------------+-------------------+   |
|                                                                 |                       |
|                      +------------------------------------------+                       |
|                      |                                                                  |
|                      | Score < 80 & Revisions < MAX_REVISION_CYCLES                     |
|                      +---------------------------------------------------> (Revision)   |
|                      |                                                                  |
|                      | Score >= 80 or Max Revisions Reached                             |
|                      v                                                                  |
|   ===================================================================================   |
|   [ HITL GATE 2: HUMAN FINAL SIGN-OFF INTERRUPT (AWAITING_FINAL_APPROVAL) ]             |
|   ===================================================================================   |
|          | (CHANGES_REQUESTED)                     | (APPROVED)                         |
|          +--------------------------------------+  v                                    |
|                                                 +-----------------------------------+   |
|                                                 | Status: APPROVED_FOR_EXPORT       |   |
|                                                 | DOCX Export Engine Unlocked       |   |
|                                                 +-----------------------------------+   |
+-----------------------------------------------------------------------------------------+
                                 |                                 |
                                 v                                 v
+------------------------------------------------+ +--------------------------------------+
|             CHROMADB VECTOR STORE              | |           SQLITE DATABASE            |
|  - Company Collateral & Case Studies           | |  - RFP Metadata & Classified Reqs    |
|  - Security Policies (SOC 2, ISO 27001)        | |  - Compliance Matrix & Risk Register |
|  - Semantic Search (sentence-transformers)     | |  - Proposals, Reviews & Audit Trails |
+------------------------------------------------+ +--------------------------------------+
```

---

## 🤖 The 6 Specialized AI Agents

Each agent has a single, strictly bounded role with typed Pydantic inputs and outputs:

### 1. RFP Document Extraction Agent (`extractor_agent.py`)
- **Role:** Ingests unstructured tenders (PDF, DOCX, TXT) and parses structural hierarchy (pages, headings, paragraphs, tables).
- **Output:** Extracts tender metadata (title, issuer, deadline, budget, evaluation criteria, executive summary) and discrete candidate clauses with source page and section coordinates.

### 2. Requirement Classification Agent (`classifier_agent.py`)
- **Role:** Normalizes candidate clauses into structured requirements with canonical codes (`REQ-TECH-001`, `REQ-COMM-002`).
- **Exact 9 Requirement Categories:**
  1. `Technical` — Architecture, software stack, performance, scalability, APIs.
  2. `Commercial` — Pricing models, payment schedules, licensing, penalties.
  3. `Contractual` — Terms, indemnification, liabilities, warranties, governing law.
  4. `Administrative` — Bid submission formats, forms, contacts, timelines.
  5. `Certification` — ISO 27001, SOC 2 Type II, FedRAMP, PCI-DSS credentials.
  6. `Delivery` — Milestones, project management, deployment schedules.
  7. `Documentation` — Architecture diagrams, user manuals, training collateral.
  8. `Submission` — RFP closing dates, portal guidelines, bond requirements.
  9. `Eligibility` — Minimum vendor turnover, operational years, experience thresholds.
- **Modality Detection:** Categorizes requirements as mandatory (`SHALL`, `MUST`, `REQUIRED`) or optional (`SHOULD`, `MAY`, `NICE TO HAVE`) with confidence scores and reasoning.

### 3. Compliance Analysis Agent (`compliance_agent.py`)
- **Role:** Audits every classified requirement against the ChromaDB company knowledge base.
- **Exact 4 Compliance Statuses:**
  1. `COMPLIANT` — Collateral explicitly confirms satisfaction with high similarity.
  2. `PARTIALLY_COMPLIANT` — Collateral confirms partial fulfillment or requires caveats.
  3. `NON_COMPLIANT` — Company collateral explicitly disclaims capability or contradicts requirement.
  4. `INFORMATION_REQUIRED` — Collateral lacks evidence; triggers anti-hallucination gap preservation.
- **Traceability:** Pairs each verdict with verbatim evidence excerpts, cited source documents, chunk IDs, and confidence ratings.

### 4. Risk & Clarification Agent (`risk_agent.py`)
- **Role:** Evaluates high-liability contract terms, aggressive delivery timelines, ungrounded technical gaps, and regulatory penalties.
- **Risk Severity Levels:** `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
- **Clarification Formulation:** Drafts formal, numbered clarification questions (`CLR-001`) with specific RFP section references, rationale, target owner, and priority to submit to the issuing authority.

### 5. Proposal Writer Agent (`writer_agent.py`)
- **Role:** Drafts a complete, professional, publication-ready proposal grounded strictly in verified company collateral.
- **Core Proposal Sections:**
  1. Executive Summary & Value Proposition
  2. Solution Architecture & Technical Approach
  3. Implementation Plan, Milestones & Governance
  4. Security, Compliance & Data Sovereignty
  5. Commercial Pricing, ROI & Service Level Agreements
  6. Company Credentials, Case Studies & Past Performance
- **Requirement-by-Requirement Responses:** Pairs each requirement with tailored responses (`COMPLIANT_RESPONSE`, `PARTIAL_RESPONSE`, `EXCEPTION_RESPONSE`, `INFORMATION_REQUIRED_RESPONSE`), assumptions, and embedded citations.

### 6. Proposal Reviewer / Critic Agent (`reviewer_agent.py`)
- **Role:** Acts as an autonomous red-team evaluator grading proposal quality before human sign-off.
- **Rubric Scoring (0–100 Scale, 4 Criteria @ 25 pts each):**
  1. *Compliance Alignment* — Completeness of requirement coverage.
  2. *Technical Depth & Feasibility* — Realistic engineering approaches.
  3. *Grounding & Hallucination Defense* — Absence of unverified claims.
  4. *Professionalism & Clarity* — Tone, structure, and executive polish.
- **Automated Revision Loop:** If score $< 80$ and revisions $< 	ext{MAX\_REVISION\_CYCLES}$ (default: 2), the reviewer formulates actionable revision instructions and routes execution back to Agent 5.

---

## 🚦 Human-in-the-Loop (HITL) Governance

The workflow embeds two mandatory human decision gates using LangGraph state interrupts:

```
[Agent 1 -> Agent 2 -> Agent 3 -> Agent 4]
                   |
                   v
   [ GATE 1: Go / No-Go Decision ]
         |                   |
    (NO_GO)                 (GO)
         v                   v
   [ABORTED_NO_GO]     [Agent 5 -> Agent 6]
                             |
                     (Review Loop < 80)
                             |
                             v
               [ GATE 2: Proposal Approval ]
                     |               |
             (CHANGES_REQ)       (APPROVED)
                     v               v
               [Re-draft]    [APPROVED_FOR_EXPORT]
                                     |
                                     v
                                [DOCX Export]
```

1. **Gate 1: Go / No-Go Executive Review (`AWAITING_GO_NOGO`)**
   - Pauses execution immediately after Agent 4 completes risk assessment.
   - The bid manager inspects the overall compliance percentage, critical risks, and clarifications.
   - **`NO_GO`:** Sets status to `ABORTED_NO_GO`, terminates the pipeline, avoids expensive proposal drafting costs, and blocks DOCX export.
   - **`GO`:** Authorizes proposal generation with optional strategic bid guidance.

2. **Gate 2: Final Proposal Sign-Off (`AWAITING_FINAL_APPROVAL`)**
   - Pauses after Agent 6 reviews the proposal and assigns a quality score.
   - The manager can view revision history, diff scores, and reviewer findings.
   - **`APPROVED`:** Transitions RFP to `APPROVED_FOR_EXPORT` and unlocks the DOCX export engine.
   - **`CHANGES_REQUESTED`:** Sends human feedback back to Agent 5 for a targeted re-draft.
   - **`REJECTED`:** Rejects the submission and stops the workflow.

---

## 🛡️ Anti-Hallucination & Traceability Architecture

- **Strict Evidence Fallback:** If company collateral does not explicitly verify a requirement above the similarity threshold (`SIMILARITY_THRESHOLD=0.35`), Agent 3 assigns `INFORMATION_REQUIRED`. The system is programmatically prevented from inventing capabilities.
- **Bidirectional Traceability Chain:**
  $$	ext{RFP Document [p.X §Y]} \longleftrightarrow 	ext{Requirement [REQ-TECH-002]} \longleftrightarrow 	ext{Evidence Chunk [Whitepaper p.1]} \longleftrightarrow 	ext{Proposal Section}$$
- **Data Segregation Guardrail:** The knowledge base endpoint explicitly rejects RFP tenders uploaded into the company collateral store, preventing cross-contamination between tender specifications and internal capabilities.
- **Amber Warning Callouts:** Unverified items and missing evidence are rendered with visual warnings in the UI and styled callout boxes in generated DOCX exports.

---

## 🔌 API Endpoints Reference

The FastAPI gateway exposes 18 REST and streaming endpoints:

### RFP & Project Management
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/rfp/upload` | Upload and ingest RFP document (PDF, DOCX, TXT) |
| `GET` | `/api/rfp` | List all active RFP projects and high-level summaries |
| `GET` | `/api/rfp/{rfp_id}` | Get detailed RFP workspace payload and statistics |
| `GET` | `/api/rfp/{rfp_id}/requirements` | List classified requirements with categories & modals |
| `GET` | `/api/rfp/{rfp_id}/compliance-matrix` | List compliance records with citations & evidence snippets |
| `GET` | `/api/rfp/{rfp_id}/risks` | Retrieve risk register and drafted clarification questions |
| `GET` | `/api/rfp/{rfp_id}/proposals` | List proposal draft revisions, markdown, and review scores |
| `GET` | `/api/rfp/{rfp_id}/export/{format}` | Export final proposal document (format: `docx`) |
| `DELETE` | `/api/rfp/{rfp_id}` | Delete RFP document, vector embeddings, and records |

### Multi-Agent Workflow & HITL
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/workflow/{rfp_id}/start` | Trigger or restart the 6-agent LangGraph workflow |
| `POST` | `/api/workflow/{rfp_id}/go-nogo` | Submit HITL Gate 1 decision (`GO` or `NO_GO`) |
| `POST` | `/api/workflow/{rfp_id}/final-approval` | Submit HITL Gate 2 decision (`APPROVED`, `CHANGES_REQUESTED`, `REJECTED`) |
| `GET` | `/api/workflow/{rfp_id}/status` | Query current workflow state, active agent, and version |
| `GET` | `/api/workflow/{rfp_id}/stream` | Server-Sent Events (SSE) telemetry stream for real-time updates |

### Company Knowledge Base & RAG
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/company-knowledge/upload` | Upload and vectorize company collateral into ChromaDB |
| `GET` | `/api/company-knowledge` | List all indexed collateral documents and chunk counts |
| `POST` | `/api/company-knowledge/query` | Test semantic similarity query against ChromaDB |
| `DELETE` | `/api/company-knowledge/clear` | Clear vector store collection and document records |

### System Health & Gateway
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | API root gateway metadata and docs link |
| `GET` | `/health` | Health check endpoint (status, environment, database) |

---

## 💻 Technology Stack

- **Backend:** Python 3.12, FastAPI, Uvicorn, LangGraph, LangChain Core, Pydantic v2.
- **RAG & Embeddings:** ChromaDB, `sentence-transformers` (`all-MiniLM-L6-v2`), PyPDF, `python-docx`.
- **Database & Checkpointing:** SQLite (SQLAlchemy ORM), LangGraph `MemorySaver` checkpointer.
- **Export Engine:** `python-docx` with custom XML table styling, headers, and metadata formatting.
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons, Axios.
- **Streaming:** Native HTML5 Server-Sent Events (`EventSource`) with reactive state updates.
- **Hosting & Infrastructure:** Render (Docker Web Service) + Vercel (Static SPA with rewrites).

---

## 🚀 Local Development Setup

### Prerequisites
- Python 3.12+ installed
- Node.js 18+ and npm installed
- Git

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your LLM configuration (or use defaults for mock mode)

# Run test suite
pytest -v tests

# Start FastAPI server
uvicorn app.main:app --reload --port 8000
```
Backend will be available at: `http://localhost:8000` (Swagger docs: `http://localhost:8000/docs`).

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install npm dependencies
npm install

# Configure environment variables
cp .env.example .env
# Ensure VITE_API_BASE_URL=http://localhost:8000 for local development

# Start Vite development server
npm run dev
```
Frontend will be available at: `http://localhost:5173`.

---

## 🔐 Environment Variables

### Backend Configuration (`backend/.env`)

```ini
# Environment & Server
ENVIRONMENT=production
PORT=8000
CORS_ORIGINS=https://rfp-proposal-frontend.vercel.app,http://localhost:5173

# LLM Provider Configuration
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Optional: Google Gemini Provider
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-1.5-flash

# Storage & Paths
DATABASE_URL=sqlite:///./storage/rfp_system.db
CHROMA_PERSIST_DIRECTORY=./storage/chromadb
UPLOAD_DIR=./storage/uploads
EXPORT_DIR=./storage/exports

# Workflow Governance Thresholds
SIMILARITY_THRESHOLD=0.35
RAG_TOP_K=4
MAX_REVISION_CYCLES=2
REVIEW_PASS_SCORE=80
```

> **Security Note:** Never commit `.env` files to git. In production (Render), these values are securely configured through Render's Environment Variable dashboard.

### Frontend Configuration (`frontend/.env`)

```ini
# Production Backend Target (Render)
VITE_API_BASE_URL=https://rfp-proposal-backend.onrender.com
```

---

## 🚢 Production Deployment Architecture

### Backend Deployment (Render Web Service)
- **Repository Root:** `backend/`
- **Build Target:** `Dockerfile` (Multi-stage Python 3.12 Slim)
- **Health Check Path:** `/health`
- **Instance Type:** Free Web Service
- **Storage:** Persistent SQLite & ChromaDB directory structure in `/app/storage`

### Frontend Deployment (Vercel)
- **Framework Preset:** Vite
- **Root Directory:** `frontend/`
- **Build Command:** `npm run build`
- **Output Directory:** `dist`
- **SPA Routing:** Configured via `frontend/vercel.json` rewrites (`/* -> /index.html`)
- **Environment Variable:** `VITE_API_BASE_URL=https://rfp-proposal-backend.onrender.com`

---

## 🎬 End-to-End Demo Workflow

To evaluate the system live:

1. **Access the Application:** Open [https://rfp-proposal-frontend.vercel.app](https://rfp-proposal-frontend.vercel.app).
2. **Review Existing Projects:** The dashboard loads pre-seeded RFPs across various states (`APPROVED_FOR_EXPORT`, `AWAITING_GO_NOGO`, `ABORTED_NO_GO`).
3. **Inspect Completed Workspace:** Click on an approved RFP (e.g. *Enterprise Cloud Modernization & Distributed Logistics Platform*):
   - **Agent Visualizer:** View the completed 6-agent execution timeline.
   - **Requirements Breakdown:** Filter across the 9 canonical categories and view mandatory flags.
   - **Compliance Matrix:** Audit verdicts, confidence scores, and cited evidence snippets.
   - **Risk Register & Clarifications:** Inspect identified risks and formal questions.
   - **Proposal Studio:** Read full markdown proposal drafts, reviewer rubric scores (v1 vs v2), and critique findings.
   - **Download Deliverable:** Click **Export DOCX** to download the assembled Word proposal.
4. **Execute a New Ingestion:**
   - Click **Upload RFP** on the dashboard.
   - Select a sample tender document or paste RFP text.
   - Click **Start Multi-Agent Workflow** to watch the real-time SSE execution stream.
   - When execution pauses at **HITL Gate 1**, inspect the risk matrix and submit a **GO** decision.
   - Watch Agent 5 draft the proposal and Agent 6 execute the review cycle.
   - At **HITL Gate 2**, approve the final draft and export the resulting `.docx` package.

---

## ⚠️ Known Deployment Characteristics & Limitations

- **Render Free Tier Spin-Down:** On the free tier, Render automatically spins down the web service after 15 minutes of inactivity. The initial cold start may take 45–60 seconds to respond. Once awake, response latency is nominal.
- **ChromaDB In-Process Embedding:** Embeddings are generated using in-process sentence transformers or OpenAI embeddings. For optimal latency on free-tier memory constraints (512MB RAM), batch document queries are capped at `top_k=4`.
- **Ephemeral Storage on Redeploy:** Persistent disk attachments are supported on Render paid tiers; on free instances, storage resets upon full container redeployment unless mounted to persistent storage.

---

## 📄 License & Attribution

Brightcone.ai Agentic AI RFP Analysis & Proposal Response System. Built for automated RFP compliance and high-conviction proposal generation. Distributed under the MIT License.
