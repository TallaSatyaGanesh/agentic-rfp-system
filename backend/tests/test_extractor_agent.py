import os
import tempfile
import pytest
from app.agents.extractor_agent import (
    extract_rfp_node,
    _fallback_metadata,
    _sanitize_metadata,
    PROHIBITED_FICTIONAL_STRINGS
)
from app.models.schemas import ExtractedBlock, RFPMetadata
from app.agents.state import RFPProposalState

def test_metadata_extracted_from_actual_document():
    """Requirement A: Metadata is extracted from actual document content."""
    rfp_path = os.path.abspath("sample_data/sample_rfp_enterprise_cloud.txt")
    assert os.path.exists(rfp_path)

    state: RFPProposalState = {
        "rfp_id": "test_rfp_001",
        "file_path": rfp_path,
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

    result = extract_rfp_node(state)
    meta = result["metadata"]

    # Must extract the real title, issuer, deadline, and evaluation criteria from sample_rfp_enterprise_cloud.txt
    assert "Enterprise Cloud Modernization" in meta["title"], f"Expected real title, got: {meta['title']}"
    assert "National Transit & Supply Chain Authority" in meta["issuer"], f"Expected real issuer, got: {meta['issuer']}"
    assert "November 15, 2026" in meta["submission_deadline"], f"Expected real deadline, got: {meta['submission_deadline']}"
    assert len(meta["evaluation_criteria"]) >= 4, f"Expected real evaluation criteria, got: {meta['evaluation_criteria']}"
    assert any("30%" in crit for crit in meta["evaluation_criteria"])
    assert any("25%" in crit for crit in meta["evaluation_criteria"])

    # Must NEVER contain any of the legacy fictional defaults
    for prohibited in PROHIBITED_FICTIONAL_STRINGS:
        assert prohibited.lower() not in meta["title"].lower()
        assert prohibited.lower() not in meta["issuer"].lower()
        if meta["submission_deadline"]:
            assert prohibited.lower() not in meta["submission_deadline"].lower()


def test_missing_metadata_becomes_information_required():
    """Requirement B: Missing metadata becomes INFORMATION REQUIRED rather than fabricated data."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        # Document with requirements but NO metadata headers (no title, no issuer, no deadline, no criteria)
        f.write("The cloud vendor SHALL encrypt all communications using TLS 1.3.\n")
        f.write("The platform MUST maintain an uptime of 99.9%.\n")
        temp_path = f.name

    try:
        state: RFPProposalState = {
            "rfp_id": "test_rfp_no_meta",
            "file_path": temp_path,
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

        result = extract_rfp_node(state)
        meta = result["metadata"]

        assert meta["title"] == "INFORMATION REQUIRED", f"Expected INFORMATION REQUIRED, got: {meta['title']}"
        assert meta["issuer"] == "INFORMATION REQUIRED", f"Expected INFORMATION REQUIRED, got: {meta['issuer']}"
        assert meta["submission_deadline"] is None, f"Expected None for missing deadline, got: {meta['submission_deadline']}"
        assert meta["budget_or_scope"] is None, f"Expected None for missing budget, got: {meta['budget_or_scope']}"
        assert meta["evaluation_criteria"] == [], f"Expected empty list for missing criteria, got: {meta['evaluation_criteria']}"

        # Ensure no legacy fictional strings were injected
        for prohibited in PROHIBITED_FICTIONAL_STRINGS:
            assert prohibited.lower() not in str(meta).lower()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_requirements_beyond_page_3_are_extracted(monkeypatch):
    """Requirement C: Requirements on pages beyond page 3 are extracted across the entire document."""
    from app.services.document_parser import DocumentParserService

    # Mock blocks simulating a 10-page document with requirements on pages 1, 4, 7, and 10
    mock_blocks = [
        ExtractedBlock(
            text="REQUEST FOR PROPOSAL\nTITLE: Multi-Region Platform\nISSUED BY: Department of Transport\nDUE DATE: Dec 1, 2026",
            page_number=1,
            section_title="General Information",
            block_type="heading"
        ),
        ExtractedBlock(
            text="1.1 Overview: The contractor SHALL provide system architecture documentation.",
            page_number=1,
            section_title="Section 1: Overview",
            block_type="paragraph"
        ),
        ExtractedBlock(
            text="4.1 Scalability: The system MUST support auto-scaling up to 50,000 requests per second.",
            page_number=4,
            section_title="Section 4: Advanced Scalability",
            block_type="paragraph"
        ),
        ExtractedBlock(
            text="7.2 Security Hardening: The vendor SHALL conduct third-party penetration testing quarterly.",
            page_number=7,
            section_title="Section 7: Security Governance",
            block_type="paragraph"
        ),
        ExtractedBlock(
            text="10.1 Indemnification: The contractor SHALL agree to mutual indemnification obligations.",
            page_number=10,
            section_title="Section 10: Legal & Indemnity",
            block_type="paragraph"
        ),
    ]

    monkeypatch.setattr(DocumentParserService, "parse_document", lambda path: mock_blocks)

    state: RFPProposalState = {
        "rfp_id": "test_multipage_rfp",
        "file_path": "dummy_path.txt",
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

    result = extract_rfp_node(state)
    clauses = result["raw_clauses"]

    # Verify that clauses beyond page 3 were extracted!
    pages_extracted = {c["source_page"] for c in clauses}
    assert 4 in pages_extracted, "Requirement on Page 4 was NOT extracted!"
    assert 7 in pages_extracted, "Requirement on Page 7 was NOT extracted!"
    assert 10 in pages_extracted, "Requirement on Page 10 was NOT extracted!"

    # Verify clause contents
    page_4_clause = next(c for c in clauses if c["source_page"] == 4)
    assert "50,000 requests per second" in page_4_clause["text"]
    assert page_4_clause["source_section"] == "Section 4: Advanced Scalability"

    page_10_clause = next(c for c in clauses if c["source_page"] == 10)
    assert "mutual indemnification" in page_10_clause["text"]
    assert page_10_clause["source_section"] == "Section 10: Legal & Indemnity"


def test_page_and_section_traceability():
    """Requirement D: Every RawClause preserves clause_id, text, source_page, and source_section."""
    rfp_path = os.path.abspath("sample_data/sample_rfp_enterprise_cloud.txt")
    state: RFPProposalState = {
        "rfp_id": "test_rfp_traceability",
        "file_path": rfp_path,
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

    result = extract_rfp_node(state)
    clauses = result["raw_clauses"]
    assert len(clauses) > 0

    for idx, c in enumerate(clauses, start=1):
        assert c["clause_id"] == f"CLAUSE-{idx:03d}", f"Invalid clause_id: {c['clause_id']}"
        assert isinstance(c["text"], str) and len(c["text"]) > 10, "Clause text must be non-empty string"
        assert isinstance(c["source_page"], int) and c["source_page"] >= 1, f"Invalid source_page: {c['source_page']}"
        assert isinstance(c["source_section"], str) and len(c["source_section"]) > 0, "source_section must be non-empty"


def test_multiple_requirement_sections_produce_multiple_raw_clauses():
    """Requirement E: A document containing multiple requirement sections produces multiple RawClause objects."""
    rfp_path = os.path.abspath("sample_data/sample_rfp_enterprise_cloud.txt")
    state: RFPProposalState = {
        "rfp_id": "test_rfp_multi_sections",
        "file_path": rfp_path,
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

    result = extract_rfp_node(state)
    clauses = result["raw_clauses"]

    # Verify multiple clauses exist
    assert len(clauses) >= 12, f"Expected at least 12 candidate clauses, got {len(clauses)}"

    # Check that clauses span across technical, security, functional, and legal sections
    all_sections = " ".join([c["source_section"].lower() for c in clauses])
    assert "technical" in all_sections or "infrastructure" in all_sections
    assert "security" in all_sections or "compliance" in all_sections
    assert "functional" in all_sections or "workflow" in all_sections
    assert "legal" in all_sections or "risk" in all_sections or "terms" in all_sections


def test_fallback_never_inserts_fictional_information():
    """Requirement F: The fallback never inserts fictional RFP or company information."""
    # Test 1: Empty blocks
    empty_meta = _fallback_metadata([], "")
    assert empty_meta.title == "INFORMATION REQUIRED"
    assert empty_meta.issuer == "INFORMATION REQUIRED"
    assert empty_meta.submission_deadline is None
    assert empty_meta.budget_or_scope is None
    assert empty_meta.evaluation_criteria == []
    assert empty_meta.summary == "INFORMATION REQUIRED"

    # Test 2: Unrelated random text
    random_blocks = [
        ExtractedBlock(
            text="The weather in July is typically sunny and warm with occasional rain.",
            page_number=1,
            section_title="Weather",
            block_type="paragraph"
        )
    ]
    random_meta = _fallback_metadata(random_blocks, random_blocks[0].text)
    assert random_meta.title == "INFORMATION REQUIRED"
    assert random_meta.issuer == "INFORMATION REQUIRED"
    assert random_meta.submission_deadline is None
    assert random_meta.budget_or_scope is None
    assert random_meta.evaluation_criteria == []

    # Test 3: Ensure none of the banned strings ever appear in metadata
    for prohibited in PROHIBITED_FICTIONAL_STRINGS:
        assert prohibited.lower() not in str(empty_meta.model_dump()).lower()
        assert prohibited.lower() not in str(random_meta.model_dump()).lower()
