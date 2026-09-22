import os
from typing import Literal, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.agents.state import RFPProposalState
from app.agents.extractor_agent import extract_rfp_node
from app.agents.classifier_agent import classify_requirements_node
from app.agents.compliance_agent import analyze_compliance_node
from app.agents.risk_agent import assess_risks_node
from app.agents.writer_agent import write_proposal_node
from app.agents.reviewer_agent import review_proposal_node
from app.core.config import settings

def human_go_nogo_gate(state: RFPProposalState) -> Dict[str, Any]:
    """
    Human-in-the-Loop Gate 1
    Node that captures Go / No-Go decision from proposal manager.
    """
    decision = state.get("go_nogo_decision")
    if not decision:
        return {
            "active_agent": "Human Proposal Manager",
            "workflow_status": "AWAITING_GO_NOGO"
        }
    
    if decision == "NO_GO":
        return {
            "active_agent": "Human Proposal Manager",
            "workflow_status": "ABORTED_NO_GO"
        }
    return {
        "active_agent": "Human Proposal Manager",
        "workflow_status": "WRITING_PROPOSAL"
    }

def route_go_nogo(state: RFPProposalState) -> Literal["write_proposal", "abort_workflow"]:
    if state.get("go_nogo_decision") == "NO_GO":
        return "abort_workflow"
    return "write_proposal"

def abort_workflow(state: RFPProposalState) -> Dict[str, Any]:
    return {
        "workflow_status": "ABORTED_NO_GO",
        "active_agent": "System"
    }

def route_review_outcome(state: RFPProposalState) -> Literal["write_proposal", "human_final_approval_gate"]:
    reviews = state.get("review_reports", [])
    if not reviews:
        return "human_final_approval_gate"

    latest_review = reviews[-1]
    overall_status = latest_review.get("overall_status")
    if overall_status:
        needs_rev = (overall_status == "REVISION_REQUIRED")
    else:
        needs_rev = latest_review.get("needs_revision", False)

    rev_count = max(state.get("revision_count", 0), max(0, state.get("current_version", 1) - 1))
    max_rev = state.get("max_revisions", settings.MAX_REVISION_CYCLES)

    if needs_rev and rev_count < max_rev:
        return "write_proposal"
    return "human_final_approval_gate"

def human_final_approval_gate(state: RFPProposalState) -> Dict[str, Any]:
    """
    Human-in-the-Loop Gate 2
    Node that captures final sign-off or change requests.
    """
    decision = state.get("final_approval_decision")
    if not decision:
        return {
            "active_agent": "Human Proposal Manager",
            "workflow_status": "AWAITING_FINAL_APPROVAL"
        }

    rev_count = max(state.get("revision_count", 0), max(0, state.get("current_version", 1) - 1))
    max_rev = state.get("max_revisions", settings.MAX_REVISION_CYCLES)

    if decision == "APPROVED":
        return {
            "active_agent": "Human Proposal Manager",
            "workflow_status": "APPROVED_FOR_EXPORT"
        }
    elif decision == "CHANGES_REQUESTED":
        if rev_count < max_rev:
            return {
                "active_agent": "Human Proposal Manager",
                "workflow_status": "WRITING_PROPOSAL"
            }
        else:
            return {
                "active_agent": "Human Proposal Manager",
                "workflow_status": "HUMAN_REVIEW_REQUIRED"
            }
    else:
        return {
            "active_agent": "Human Proposal Manager",
            "workflow_status": "REJECTED"
        }

def route_final_approval(state: RFPProposalState) -> Literal["write_proposal", "__end__"]:
    rev_count = max(state.get("revision_count", 0), max(0, state.get("current_version", 1) - 1))
    max_rev = state.get("max_revisions", settings.MAX_REVISION_CYCLES)
    if state.get("final_approval_decision") == "CHANGES_REQUESTED" and rev_count < max_rev:
        return "write_proposal"
    return "__end__"

# Singleton checkpointer
checkpointer = MemorySaver()

def create_rfp_graph():
    """
    Compiles the LangGraph state machine with 6 agents and 2 human-in-the-loop gates.
    """
    workflow = StateGraph(RFPProposalState)

    # Add agent and gate nodes
    workflow.add_node("extract_rfp", extract_rfp_node)
    workflow.add_node("classify_requirements", classify_requirements_node)
    workflow.add_node("analyze_compliance", analyze_compliance_node)
    workflow.add_node("assess_risks", assess_risks_node)
    workflow.add_node("human_go_nogo_gate", human_go_nogo_gate)
    workflow.add_node("abort_workflow", abort_workflow)
    workflow.add_node("write_proposal", write_proposal_node)
    workflow.add_node("review_proposal", review_proposal_node)
    workflow.add_node("human_final_approval_gate", human_final_approval_gate)

    # Core execution pipeline edges
    workflow.set_entry_point("extract_rfp")
    workflow.add_edge("extract_rfp", "classify_requirements")
    workflow.add_edge("classify_requirements", "analyze_compliance")
    workflow.add_edge("analyze_compliance", "assess_risks")
    workflow.add_edge("assess_risks", "human_go_nogo_gate")

    # Gate 1 conditional routing
    workflow.add_conditional_edges(
        "human_go_nogo_gate",
        route_go_nogo,
        {
            "write_proposal": "write_proposal",
            "abort_workflow": "abort_workflow"
        }
    )
    workflow.add_edge("abort_workflow", END)

    # Proposal & Reviewer loop
    workflow.add_edge("write_proposal", "review_proposal")
    workflow.add_conditional_edges(
        "review_proposal",
        route_review_outcome,
        {
            "write_proposal": "write_proposal",
            "human_final_approval_gate": "human_final_approval_gate"
        }
    )

    # Gate 2 conditional routing
    workflow.add_conditional_edges(
        "human_final_approval_gate",
        route_final_approval,
        {
            "write_proposal": "write_proposal",
            "__end__": END
        }
    )

    # Compile with checkpointer and interrupt points
    app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_go_nogo_gate", "human_final_approval_gate"]
    )
    return app

# Singleton compiled graph instance
rfp_graph = create_rfp_graph()
