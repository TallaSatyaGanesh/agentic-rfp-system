# Agentic AI RFP Analysis & Proposal Response System

An enterprise-grade, production-quality multi-agent system built with **FastAPI**, **LangGraph**, **ChromaDB**, and **React + TypeScript + Tailwind CSS**.

The system automates the end-to-end response lifecycle for RFPs, RFQs, and government tenders: extracting requirements, classifying clauses, auditing company compliance via grounded RAG, calculating contractual risks, drafting structured proposals, executing red team critique and revision loops, and enforcing human-in-the-loop authorization gates.

---

## High-Level Architecture Diagram

```
+-----------------------------------------------------------------------------------------+
|                                 USER / PROPOSAL MANAGER                                 |
+-----------------------------------------------------------------------------------------+
                                 |                            ^
            1. Upload RFP &      |                            |  Live SSE Workflow Updates
            Company Collateral   |                            |  & Human-in-the-Loop Alerts
                                 v                            |
+-----------------------------------------------------------------------------------------+
|                           FRONTEND: REACT + TS + TAILWIND                               |
|  [Upload Zone] -> [Live Agent Visualizer] -> [Compliance Matrix] -> [Proposal Studio]   |
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
|   | Agent 1: Extraction      | -> Reconstructs hierarchy, extracts candidate clauses    |
|   +------------+-------------+                                                          |
|                |                                                                        |
|                v                                                                        |
|   +--------------------------+                                                          |
|   | Agent 2: Classification  | -> Categorizes (Tech/Sec/Legal), assigns REQ-IDs         |
|   +------------+-------------+                                                          |
|                |                                                                        |
|                +---------------------------------------+                                |
|                |                                       |                                |
|                v                                       v                                |
|   +--------------------------+           +-----------------------------+                |
|   | Agent 3: Compliance      |           | Agent 4: Risk &             |                |
|   | (Queries ChromaDB RAG)   |           | Clarification               |                |
|   +------------+-------------+           +-------------+---------------+                |
|                |                                       |                                |
|                +-------------------+-------------------+                                |
|                                    |                                                    |
|                                    v                                                    |
|                   [ GATE 1: HUMAN GO / NO-GO INTERRUPT ]                                |
|                                    | (Proceed)                                          |
|                                    v                                                    |
|   +----------------------------------------------------------+                          |
|   | Agent 5: Proposal Writer                                 |<-----------+             |
|   | (Generates structured draft with citations & gap alerts) |            |             |
|   +----------------------------+-----------------------------+            |             |
|                                |                                          |             |
|                                v                                          |             |
|   +----------------------------------------------------------+            | (Revises    |
|   | Agent 6: Reviewer / Critic                               |            |  if score   |
|   | (Scores proposal 0-100, fact-checks against context)     |------------+  < 80)      |
|   +----------------------------+-----------------------------+                          |
|                                | (Score >= 80 or Max Revisions)                         |
|                                v                                                        |
|                 [ GATE 2: HUMAN FINAL SIGN-OFF INTERRUPT ]                              |
|                                | (Approved)                                             |
|                                v                                                        |
|   +----------------------------------------------------------+                          |
|   | Export Engine -> Compiles Formatted DOCX / PDF           |                          |
|   +----------------------------------------------------------+                          |
|                                                                                         |
|   CHECKPOINTER: MemorySaver / SqliteSaver (Persists thread state across interrupts)    |
+-----------------------------------------------------------------------------------------+
                                 |                                 |
                                 v                                 v
+------------------------------------------------+ +--------------------------------------+
|             CHROMADB VECTOR STORE              | |           SQLITE DATABASE            |
|  - Company Case Studies & Technical Docs       | |  - RFP Metadata & Classified Reqs    |
|  - Security Policies (SOC2 / ISO 27001)        | |  - Compliance Records & Risk Matrix  |
|  - Zero-Network Local Fast Hashing Fallback    | |  - Proposal Drafts & Review Scores   |
+------------------------------------------------+ +--------------------------------------+
```

---

## The 6 Specialized AI Agents

1. **RFP Document Extraction Agent (`extractor_agent.py`):** Parses raw document hierarchy (pages, headings, tables), extracts metadata (issuer, deadline, evaluation criteria), and identifies discrete candidate clauses.
2. **Requirement Classification Agent (`classifier_agent.py`):** Normalizes clauses into canonical IDs (`REQ-TECH-001`, `REQ-SEC-002`), categorizes into Technical, Security, Functional, Legal, or Management, and flags mandatory (`SHALL`/`MUST`) status.
3. **Compliance Analysis Agent (`compliance_agent.py`):** Queries the ChromaDB company knowledge base using hybrid semantic + lexical retrieval. Assigns verdicts (`COMPLIANT`, `PARTIALLY_COMPLIANT`, `NON_COMPLIANT`, or `INFORMATION_REQUIRED`) with verified citations.
4. **Risk & Clarification Agent (`risk_agent.py`):** Uncovers contract risks (unlimited liability, aggressive SLAs, missing collateral) and formulates formal, numbered clarification questions to submit to the tender issuer.
5. **Proposal Writer Agent (`writer_agent.py`):** Authors professional, section-by-section proposal drafts. Embeds source citations (`[RFP p.X §Y]` and `[Company Doc Z]`) and prominent `[INFORMATION REQUIRED]` callouts.
6. **Reviewer / Critic Agent (`reviewer_agent.py`):** Red team reviewer that grades the proposal across 4 criteria (Compliance Alignment, Technical Feasibility, Grounding, Clarity). Triggers an automated revision cycle if score $< 80$.

---

## Human-in-the-Loop (HITL) Architecture

The system features two mandatory human gates managed via LangGraph interrupts:
- **Gate 1: Bid Go / No-Go Decision:** Pauses before heavy proposal writing. The proposal manager reviews the compliance score and high-severity risks to either authorize the bid (with custom strategic guidance) or terminate early to save costs.
- **Gate 2: Final Proposal Sign-Off:** Pauses after the Reviewer Agent evaluates the final draft. Allows the human manager to inspect the score, approve for export, or request specific changes.

---

## Hallucination Prevention & Traceability

- **Strict Fallback:** If company collateral does not explicitly verify a requirement, the system outputs `INFORMATION_REQUIRED`. The model is programmatically barred from inventing capabilities.
- **End-to-End Citation Chain:**
  `RFP Document [p.14 §3.2]` $\rightarrow$ `REQ-ID [REQ-TECH-008]` $\rightarrow$ `Company Evidence [SOC2_Report.pdf p.18]` $\rightarrow$ `Proposal Text`.
- **Amber Alert Callouts:** All missing data is styled prominently in both the UI and exported DOCX deliverables.

---

## Quickstart & Local Development

### 1. Backend Setup
```bash
cd backend
# Create virtual environment with Python 3.12
py -3.12 -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run unit and integration tests
$env:PYTHONPATH = "backend"
pytest -v tests

# Start FastAPI server
uvicorn app.main:app --reload --port 8000
```
API Documentation is available at: `http://localhost:8000/docs`

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Web application runs at: `http://localhost:5173`

---

## Deployment Target

- **Backend:** Ready for **Render** via included `backend/Dockerfile` (Web Service, persistent disk mount on `/app/storage`).
- **Frontend:** Ready for **Vercel** with included `frontend/vercel.json` SPA routing rewrite. Set `VITE_API_BASE_URL` to your Render backend URL.
