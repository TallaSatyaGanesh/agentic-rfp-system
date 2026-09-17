import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session
from app.db.database import get_db, SessionLocal
from app.db.models import RFPDocument, Requirement, ComplianceRecord, RiskRecord, ClarificationQuestion, Proposal
from app.agents.graph import rfp_graph, checkpointer
from app.agents.state import RFPProposalState
from app.models.schemas import GoNoGoRequest, FinalApprovalRequest

router = APIRouter(prefix="/api/workflow", tags=["Workflow Execution & HITL"])

# In-memory broadcast queues for live SSE streams
workflow_event_queues: Dict[str, asyncio.Queue] = {}

def get_event_queue(rfp_id: str) -> asyncio.Queue:
    if rfp_id not in workflow_event_queues:
        workflow_event_queues[rfp_id] = asyncio.Queue()
    return workflow_event_queues[rfp_id]

async def broadcast_event(rfp_id: str, event_type: str, data: Dict[str, Any]):
    q = get_event_queue(rfp_id)
    payload = {
        "event": event_type,
        "rfp_id": rfp_id,
        "timestamp": datetime.utcnow().isoformat(),
        "data": data
    }
    await q.put(payload)

def _persist_workflow_results_to_db(rfp_id: str, final_state: Dict[str, Any]):
    """Synchronizes LangGraph state to SQLite relational tables."""
    db = SessionLocal()
    try:
        rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
        if not rfp:
            return

        # Update RFP Metadata
        meta = final_state.get("metadata") or {}
        if meta.get("title"):
            rfp.title = meta["title"]
        if meta.get("issuer"):
            rfp.issuer = meta["issuer"]
        if meta.get("submission_deadline"):
            rfp.submission_deadline = meta["submission_deadline"]
        rfp.status = final_state.get("workflow_status", "COMPLETED")

        # Save Requirements & Compliance
        requirements_data = final_state.get("requirements") or []
        compliance_data = {c.get("req_code"): c for c in (final_state.get("compliance_matrix") or [])}

        for r_item in requirements_data:
            req_code = r_item.get("req_code")
            existing_req = db.query(Requirement).filter(
                Requirement.rfp_id == rfp_id, Requirement.req_code == req_code
            ).first()

            if not existing_req:
                existing_req = Requirement(
                    id=f"{rfp_id}_{req_code}",
                    rfp_id=rfp_id,
                    req_code=req_code,
                    category=r_item.get("category", "Technical"),
                    priority=r_item.get("priority", "Medium"),
                    is_mandatory=r_item.get("is_mandatory", True),
                    text=r_item.get("text", ""),
                    source_page=r_item.get("source_page", 1),
                    source_section=r_item.get("source_section", "General")
                )
                db.add(existing_req)
                db.flush()

            # Attach compliance record if exists
            comp_info = compliance_data.get(req_code)
            if comp_info:
                existing_comp = db.query(ComplianceRecord).filter(
                    ComplianceRecord.requirement_id == existing_req.id
                ).first()
                if not existing_comp:
                    existing_comp = ComplianceRecord(
                        id=f"comp_{existing_req.id}",
                        requirement_id=existing_req.id,
                        status=comp_info.get("status", "INFORMATION_REQUIRED"),
                        confidence=comp_info.get("confidence", 0.0),
                        evidence_text=comp_info.get("evidence_text"),
                        company_source_doc=comp_info.get("company_source_doc"),
                        notes=comp_info.get("notes")
                    )
                    db.add(existing_comp)

        # Save Risks
        for r_idx, r_item in enumerate(final_state.get("risks") or []):
            risk_id = f"{rfp_id}_risk_{r_idx}"
            if not db.query(RiskRecord).filter(RiskRecord.id == risk_id).first():
                db.add(RiskRecord(
                    id=risk_id,
                    rfp_id=rfp_id,
                    category=r_item.get("category", "Operational"),
                    severity=r_item.get("severity", "Medium"),
                    likelihood=r_item.get("likelihood", "Medium"),
                    description=r_item.get("description", ""),
                    mitigation_strategy=r_item.get("mitigation_strategy", ""),
                    rfp_reference=r_item.get("rfp_reference")
                ))

        # Save Clarifications
        for q_item in final_state.get("clarification_questions") or []:
            q_id = f"{rfp_id}_q_{q_item.get('q_number', 1)}"
            if not db.query(ClarificationQuestion).filter(ClarificationQuestion.id == q_id).first():
                db.add(ClarificationQuestion(
                    id=q_id,
                    rfp_id=rfp_id,
                    q_number=q_item.get("q_number", 1),
                    rfp_section_reference=q_item.get("rfp_section_reference", "General"),
                    question_text=q_item.get("question_text", ""),
                    rationale=q_item.get("rationale", "")
                ))

        # Save Proposals
        for p_draft in final_state.get("proposal_drafts") or []:
            version = p_draft.get("version", 1)
            p_id = f"{rfp_id}_proposal_v{version}"
            
            # Review feedback matching this version
            review_feedback_str = None
            review_score = 0
            reviews = final_state.get("review_reports") or []
            if len(reviews) >= version:
                rev = reviews[version - 1]
                review_score = rev.get("overall_score", 0)
                review_feedback_str = json.dumps(rev)

            existing_prop = db.query(Proposal).filter(Proposal.id == p_id).first()
            if not existing_prop:
                db.add(Proposal(
                    id=p_id,
                    rfp_id=rfp_id,
                    version=version,
                    title=p_draft.get("title", "Proposal Response"),
                    executive_summary=p_draft.get("executive_summary", ""),
                    content_markdown=p_draft.get("full_markdown", ""),
                    review_score=review_score,
                    review_feedback_json=review_feedback_str,
                    status="APPROVED" if final_state.get("workflow_status") == "APPROVED_FOR_EXPORT" else "DRAFT"
                ))
            else:
                existing_prop.review_score = review_score
                existing_prop.review_feedback_json = review_feedback_str
                if final_state.get("workflow_status") == "APPROVED_FOR_EXPORT":
                    existing_prop.status = "APPROVED"

        db.commit()
    except Exception as e:
        print(f"[DB Sync Error] {e}")
        db.rollback()
    finally:
        db.close()

async def run_workflow_async(rfp_id: str, file_path: str):
    """Executes the LangGraph workflow and streams events."""
    config = {"configurable": {"thread_id": rfp_id}}
    
    initial_state: RFPProposalState = {
        "rfp_id": rfp_id,
        "file_path": file_path,
        "metadata": None,
        "raw_clauses": [],
        "requirements": [],
        "compliance_matrix": [],
        "overall_compliance_score": 0.0,
        "risks": [],
        "clarification_questions": [],
        "go_nogo_decision": None,
        "go_nogo_notes": None,
        "proposal_drafts": [],
        "current_version": 0,
        "review_reports": [],
        "revision_count": 0,
        "max_revisions": 2,
        "final_approval_decision": None,
        "human_feedback": None,
        "active_agent": "Extraction Agent",
        "workflow_status": "EXTRACTING",
        "logs": [],
        "error": None
    }

    await broadcast_event(rfp_id, "status_change", {
        "active_agent": "Extraction Agent",
        "status": "EXTRACTING",
        "message": "Initiating document extraction and layout analysis..."
    })

    try:
        for output in rfp_graph.stream(initial_state, config, stream_mode="updates"):
            if not isinstance(output, dict):
                continue
            for node_name, state_update in output.items():
                if node_name == "__interrupt__" or not isinstance(state_update, dict):
                    continue
                active_agent = state_update.get("active_agent", node_name)
                status = state_update.get("workflow_status", "PROCESSING")
                logs = state_update.get("logs", [])
                latest_log = logs[-1] if logs else None

                await broadcast_event(rfp_id, "node_completed", {
                    "node": node_name,
                    "active_agent": active_agent,
                    "status": status,
                    "log": latest_log,
                    "state_preview": {
                        "requirements_count": len(state_update.get("requirements", [])),
                        "compliance_score": state_update.get("overall_compliance_score"),
                        "current_version": state_update.get("current_version")
                    }
                })

        # Check if paused at human gate
        current_state = rfp_graph.get_state(config)
        _persist_workflow_results_to_db(rfp_id, current_state.values)
        if current_state.next:
            next_node = current_state.next[0]
            if next_node == "human_go_nogo_gate":
                await broadcast_event(rfp_id, "human_approval_required", {
                    "gate": "GO_NOGO",
                    "title": "Bid Go / No-Go Decision Gate",
                    "description": "Compliance analysis and risk assessment completed. Please review findings and confirm whether to proceed.",
                    "data": {
                        "compliance_score": current_state.values.get("overall_compliance_score", 0),
                        "requirements_count": len(current_state.values.get("requirements", [])),
                        "high_risks_count": len([r for r in current_state.values.get("risks", []) if r.get("severity") == "High"])
                    }
                })
            elif next_node == "human_final_approval_gate":
                reviews = current_state.values.get("review_reports", [])
                latest_score = reviews[-1].get("overall_score", 0) if reviews else 0
                await broadcast_event(rfp_id, "human_approval_required", {
                    "gate": "FINAL_APPROVAL",
                    "title": "Final Proposal Sign-Off Gate",
                    "description": f"Proposal Draft v{current_state.values.get('current_version', 1)} completed review cycle with score {latest_score}/100. Approve for export or request changes.",
                    "data": {
                        "score": latest_score,
                        "version": current_state.values.get("current_version", 1),
                        "draft_title": current_state.values.get("proposal_drafts", [{}])[-1].get("title", "")
                    }
                })
        else:
            # Workflow completed
            await broadcast_event(rfp_id, "workflow_finished", {
                "status": current_state.values.get("workflow_status", "COMPLETED")
            })

    except Exception as e:
        print(f"[Workflow Runtime Error] {e}")
        db = SessionLocal()
        try:
            rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
            if rfp:
                rfp.status = "FAILED"
                db.commit()
        except Exception as dbe:
            print(f"[DB Error setting FAILED status] {dbe}")
            db.rollback()
        finally:
            db.close()
        await broadcast_event(rfp_id, "error", {"error": str(e)})

@router.post("/{rfp_id}/start")
async def start_workflow(
    rfp_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Initiates LangGraph multi-agent workflow for an uploaded RFP."""
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    import os
    if not rfp.file_path or not os.path.exists(rfp.file_path):
        rfp.status = "FAILED"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Document file not found at {rfp.file_path or 'unknown location'}"
        )

    rfp.status = "PROCESSING"
    db.commit()

    background_tasks.add_task(run_workflow_async, rfp_id, rfp.file_path)
    return {"message": "Workflow started successfully", "rfp_id": rfp_id}

@router.get("/{rfp_id}/status")
def get_workflow_status(rfp_id: str, db: Session = Depends(get_db)):
    """Returns current execution state and active checkpoint details."""
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()

    config = {"configurable": {"thread_id": rfp_id}}
    state = rfp_graph.get_state(config)
    
    if not state or not state.values:
        db_status = rfp.status if rfp else "NOT_STARTED"
        return {
            "status": db_status,
            "active_agent": "None",
            "is_interrupted": False,
            "interrupt_type": None,
            "current_version": 0,
            "revision_count": 0,
            "compliance_score": 0.0,
            "logs": []
        }

    status = state.values.get("workflow_status") or (rfp.status if rfp else "PROCESSING")

    # Strict interrupted rule: is_interrupted is True ONLY if state has next node AND status is one of the 3 approval states
    APPROVAL_STATES = {"AWAITING_GO_NOGO", "AWAITING_FINAL_APPROVAL", "HUMAN_REVIEW_REQUIRED"}
    is_interrupted = bool(state.next) and (status in APPROVAL_STATES)

    interrupt_type = None
    if is_interrupted:
        if "human_go_nogo_gate" in state.next or status == "AWAITING_GO_NOGO":
            interrupt_type = "GO_NOGO"
        elif "human_final_approval_gate" in state.next or status in ["AWAITING_FINAL_APPROVAL", "HUMAN_REVIEW_REQUIRED"]:
            interrupt_type = "FINAL_APPROVAL"

    return {
        "status": status,
        "active_agent": state.values.get("active_agent", "System"),
        "is_interrupted": is_interrupted,
        "interrupt_type": interrupt_type,
        "current_version": state.values.get("current_version", 0),
        "revision_count": state.values.get("revision_count", 0),
        "compliance_score": state.values.get("overall_compliance_score", 0.0),
        "logs": state.values.get("logs", [])[-10:]
    }

@router.post("/{rfp_id}/resume")
async def resume_workflow(
    rfp_id: str,
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks
):
    """
    Submits human decision (Go/No-Go or Final Sign-off) and resumes workflow.
    """
    config = {"configurable": {"thread_id": rfp_id}}
    current_state = rfp_graph.get_state(config)

    if not current_state.next:
        raise HTTPException(status_code=400, detail="Workflow is not currently awaiting human input.")

    next_node = current_state.next[0]

    if next_node == "human_go_nogo_gate":
        decision = payload.get("decision", "GO")
        notes = payload.get("notes", "")
        rfp_graph.update_state(config, {"go_nogo_decision": decision, "go_nogo_notes": notes})
    elif next_node == "human_final_approval_gate":
        decision = payload.get("decision", "APPROVED")
        feedback = payload.get("feedback", "")
        rfp_graph.update_state(config, {"final_approval_decision": decision, "human_feedback": feedback})

    # Continue streaming workflow from resumed checkpoint
    async def resume_stream():
        await broadcast_event(rfp_id, "status_change", {
            "active_agent": "System",
            "status": "RESUMING",
            "message": f"Human decision received ({payload.get('decision')}). Resuming workflow..."
        })
        for output in rfp_graph.stream(None, config, stream_mode="updates"):
            if not isinstance(output, dict):
                continue
            for node_name, state_update in output.items():
                if node_name == "__interrupt__" or not isinstance(state_update, dict):
                    continue
                await broadcast_event(rfp_id, "node_completed", {
                    "node": node_name,
                    "active_agent": state_update.get("active_agent", node_name),
                    "status": state_update.get("workflow_status", "PROCESSING"),
                    "log": (state_update.get("logs") or [None])[-1]
                })
        
        current_state = rfp_graph.get_state(config)
        _persist_workflow_results_to_db(rfp_id, current_state.values)
        if current_state.next:
            next_node = current_state.next[0]
            if next_node == "human_final_approval_gate":
                reviews = current_state.values.get("review_reports", [])
                latest_score = reviews[-1].get("overall_score", 0) if reviews else 0
                await broadcast_event(rfp_id, "human_approval_required", {
                    "gate": "FINAL_APPROVAL",
                    "title": "Final Proposal Sign-Off Gate",
                    "description": f"Proposal Draft v{current_state.values.get('current_version', 1)} completed review cycle with score {latest_score}/100. Approve for export or request changes.",
                    "data": {
                        "score": latest_score,
                        "version": current_state.values.get("current_version", 1),
                        "draft_title": current_state.values.get("proposal_drafts", [{}])[-1].get("title", "")
                    }
                })
        else:
            await broadcast_event(rfp_id, "workflow_finished", {
                "status": current_state.values.get("workflow_status", "COMPLETED")
            })

    background_tasks.add_task(resume_stream)
    return {"message": "Human input accepted. Resuming workflow execution."}

@router.get("/{rfp_id}/stream")
async def stream_workflow(rfp_id: str):
    """
    Server-Sent Events (SSE) endpoint providing real-time workflow telemetry.
    """
    q = get_event_queue(rfp_id)

    async def event_generator():
        while True:
            event = await q.get()
            yield {
                "event": event["event"],
                "data": json.dumps(event)
            }
            if event["event"] in ["workflow_finished", "error"]:
                break

    return EventSourceResponse(event_generator())
