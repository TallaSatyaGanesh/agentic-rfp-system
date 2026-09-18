import os
import tempfile
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from app.agents.extractor_agent import extract_rfp_node
from app.agents.classifier_agent import classify_requirements_node
from app.agents.state import RFPProposalState


def _create_16_req_pdf(output_path: str):
    """Helper to generate a 16-requirement PDF for regression testing."""
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("REQUEST FOR PROPOSAL - ENTERPRISE SOFTWARE", styles['Heading1']))
    story.append(Paragraph("System Specification & Commercial Requirements", styles['Heading2']))
    story.append(Spacer(1, 12))

    lines = [
        "1. Technical Specifications",
        "REQ-TECH-001: The system shall provide web-based user interface.",
        "REQ-TECH-002: The platform must support RESTful API integration.",
        "REQ-TECH-003: The system shall enforce role-based access control.",
        "REQ-TECH-004: Automated daily database backups must be supported.",
        "REQ-TECH-005: System availability must meet 99.9% uptime SLA.",
        "REQ-TECH-006: Data encryption at rest and in transit is required.",

        "2. Security & Compliance",
        "REQ-CERT-001: The vendor must hold valid ISO 27001 certification.",
        "REQ-CERT-002: The solution must comply with SOC 2 Type II audit standards.",

        "3. Vendor Qualifications",
        "REQ-ELIG-001: Vendor must have minimum 3 years enterprise deployment experience.",
        "REQ-ELIG-002: Vendor must provide 3 reference case studies.",

        "4. Commercial & Delivery Terms",
        "REQ-COMM-001: Pricing must be fixed implementation plus annual support.",
        "REQ-COMM-002: All pricing quotes shall be in USD currency.",
        "REQ-DEL-001: System deployment must be completed within 12 weeks.",
        "REQ-DEL-002: Vendor must provide post-launch support for 90 days.",

        "5. Documentation & Legal",
        "REQ-DOC-001: Comprehensive administrator and user manuals must be delivered.",
        "REQ-CONTRACT-001: Liquidated damages for delay shall not exceed 10% of contract value."
    ]

    for line in lines:
        if line.startswith(("1.", "2.", "3.", "4.", "5.")):
            story.append(Paragraph(line, styles['Heading2']))
        else:
            story.append(Paragraph(line, styles['Normal']))
        story.append(Spacer(1, 6))

    doc.build(story)


def _create_unnumbered_custom_rfp_pdf(output_path: str):
    """Helper to generate an unnumbered, custom-structured RFP PDF without explicit REQ IDs."""
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("TENDER DOCUMENT: GLOBAL LOGISTICS PLATFORM", styles['Heading1']))
    story.append(Paragraph("Scope of Work & Vendor Commitments", styles['Heading2']))
    story.append(Spacer(1, 12))

    paragraphs = [
        "Section A: Platform Functional Expectations",
        "The proposed cloud platform must support real-time cargo tracking and telemetry ingestion across all major freight routes.",
        "The vendor is required to provide automated notification alerts via email and SMS whenever shipment anomalies occur.",
        "All data processing nodes shall maintain automatic failover capabilities to ensure uninterrupted service delivery.",

        "Section B: Governance and Security Audits",
        "The contractor must possess current SOC 2 Type II attestation and agree to annual third-party security audits.",
        "The solution is required to enforce multi-factor authentication for all administrative portal logins.",

        "Section C: Project Execution & Delivery",
        "Full platform deployment and integration with legacy ERP systems must be completed within 14 weeks of contract signing.",
        "The vendor shall conduct dedicated training sessions for internal operations personnel prior to formal go-live.",

        "Section D: Financial & Legal Commitments",
        "The financial proposal shall specify a fixed lump-sum implementation fee along with itemized operational support rates.",
        "The contractor agrees to indemnify the client against third-party intellectual property infringement claims."
    ]

    for p in paragraphs:
        if p.startswith("Section"):
            story.append(Paragraph(p, styles['Heading2']))
        else:
            story.append(Paragraph(p, styles['Normal']))
        story.append(Spacer(1, 6))

    doc.build(story)


def test_16_requirement_pdf_regression():
    """Regression Test: Verify 16-requirement PDF extraction, classification, and canonical ID mapping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "test_16_reqs.pdf")
        _create_16_req_pdf(pdf_path)

        state: RFPProposalState = {
            "rfp_id": "test_16_reqs_rfp",
            "file_path": pdf_path,
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

        # 1. Extraction Phase
        extract_result = extract_rfp_node(state)
        raw_clauses = extract_result["raw_clauses"]

        # Exactly 16 requirements extracted (zero section headings)
        assert len(raw_clauses) == 16, f"Expected 16 raw clauses, got {len(raw_clauses)}"

        # 2. Classification Phase
        state["raw_clauses"] = raw_clauses
        classify_result = classify_requirements_node(state)
        classified_reqs = classify_result["requirements"]

        assert len(classified_reqs) == 16, f"Expected 16 classified requirements, got {len(classified_reqs)}"

        # Verify explicit ID preservation
        req_codes = [r["req_code"] for r in classified_reqs]
        assert "REQ-TECH-001" in req_codes
        assert "REQ-CERT-001" in req_codes
        assert "REQ-COMM-001" in req_codes
        assert "REQ-DEL-001" in req_codes
        assert "REQ-DOC-001" in req_codes
        assert "REQ-CONTRACT-001" in req_codes


def test_unnumbered_custom_structure_rfp_regression():
    """Regression Test: Verify unnumbered RFP without explicit REQ IDs generates synthetic IDs dynamically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "test_unnumbered_rfp.pdf")
        _create_unnumbered_custom_rfp_pdf(pdf_path)

        state: RFPProposalState = {
            "rfp_id": "test_unnumbered_rfp",
            "file_path": pdf_path,
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

        # 1. Extraction Phase
        extract_result = extract_rfp_node(state)
        raw_clauses = extract_result["raw_clauses"]

        # Must extract all 9 substantive obligation clauses from the unnumbered prose
        assert len(raw_clauses) == 9, f"Expected 9 raw clauses from unnumbered RFP, got {len(raw_clauses)}"

        # 2. Classification Phase
        state["raw_clauses"] = raw_clauses
        classify_result = classify_requirements_node(state)
        classified_reqs = classify_result["requirements"]

        assert len(classified_reqs) == 9

        # Verify all requirements receive valid category-prefixed synthetic IDs
        for req in classified_reqs:
            code = req["req_code"]
            assert code.startswith("REQ-"), f"Requirement code must start with REQ-, got: {code}"
            assert req["category"] in [
                "Technical", "Commercial", "Contractual", "Administrative", 
                "Certification", "Delivery", "Documentation", "Submission", "Eligibility"
            ]

        # Verify specific categories present
        categories = {r["category"] for r in classified_reqs}
        assert "Technical" in categories
        assert "Certification" in categories
        assert "Delivery" in categories
        assert "Commercial" in categories
        assert "Contractual" in categories


def test_dynamic_extraction_without_fixed_count_assumption():
    """Verify general-purpose extraction adapts dynamically to arbitrary document length without hardcoded assumptions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "arbitrary_rfp.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("SOLICITATION DOCUMENT: ADAPTIVE TEST", styles['Heading1']),
            Paragraph("The vendor must deliver cloud hosting services.", styles['Normal']),
            Paragraph("The system shall guarantee 99.9% uptime.", styles['Normal']),
            Paragraph("All pricing must be submitted in USD.", styles['Normal'])
        ]
        doc.build(story)

        state: RFPProposalState = {
            "rfp_id": "test_arbitrary",
            "file_path": pdf_path,
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

        # Exactly 3 clauses extracted dynamically without any count hardcoding
        assert len(clauses) == 3
        for c in clauses:
            assert any(m in c["text"].lower() for m in ["must", "shall"])
