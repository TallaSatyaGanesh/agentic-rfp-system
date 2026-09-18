import os
import tempfile
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.agents.extractor_agent import extract_rfp_node
from app.agents.classifier_agent import classify_requirements_node
from app.agents.compliance_agent import analyze_compliance_node
from app.agents.risk_agent import assess_risks_node
from app.agents.writer_agent import write_proposal_node
from app.agents.state import RFPProposalState


def _generate_test_rfp_agentic_system_pdf(output_path: str):
    """
    Generates the exact structure of Test_RFP_Agentic_System.pdf:
    1. Purpose: Introductory invitation text
    2. Scope of Work: High-level overview bullets
    3. Requirements: Dedicated formal table with 16 explicit requirements (REQ-TECH-001 to REQ-CON-001)
    4. Evaluation Criteria: Percentage weightings
    5. Timeline: Key dates and milestones
    6. Vendor Response Instructions: Proposal packaging and submission format
    """
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Document Header
    story.append(Paragraph("REQUEST FOR PROPOSAL (RFP)", styles['Heading1']))
    story.append(Paragraph("Enterprise Retail & Inventory Management Platform", styles['Heading2']))
    story.append(Spacer(1, 10))

    # 1. Purpose
    story.append(Paragraph("1. Purpose", styles['Heading2']))
    story.append(Paragraph(
        "ABC Retail & Logistics Pvt. Ltd. invites qualified technology vendors to submit proposals "
        "for implementing a modern, cloud-native inventory and supply chain management system across all distribution centers.",
        styles['Normal']
    ))
    story.append(Spacer(1, 8))

    # 2. Scope of Work (High-Level Overview Bullets)
    story.append(Paragraph("2. Scope of Work", styles['Heading2']))
    story.append(Paragraph("The vendor scope of engagement encompasses the following high-level areas:", styles['Normal']))
    story.append(Paragraph("• Provide a web-based application for inventory, order, product, and user management.", styles['Normal']))
    story.append(Paragraph("• Provide implementation, configuration, testing, deployment, documentation, and support.", styles['Normal']))
    story.append(Paragraph("• Integrate the platform with the customer existing REST-based order system.", styles['Normal']))
    story.append(Paragraph("• Provide training for up to 20 customer users.", styles['Normal']))
    story.append(Spacer(1, 8))

    # 3. Requirements Table (16 Formal Explicit Requirements)
    story.append(Paragraph("3. Requirements", styles['Heading2']))
    
    table_data = [
        ["Req ID", "Category", "Requirement Specification", "Mandatory"],
        ["REQ-TECH-001", "Technical", "Web-based inventory management application accessible via modern web browsers.", "Yes"],
        ["REQ-TECH-002", "Technical", "REST API integration for external inventory syncing with JSON payloads.", "Yes"],
        ["REQ-TECH-003", "Technical", "Role-based access control with granular permission tiers for Admin, Staff, and Auditor.", "Yes"],
        ["REQ-TECH-004", "Technical", "Automated daily database backups with 30-day retention schedule.", "Yes"],
        ["REQ-TECH-005", "Technical", "99.5% service availability uptime during core business operations.", "Yes"],
        ["REQ-TECH-006", "Technical", "Data encryption at rest using AES-256 and in transit using TLS 1.3.", "Yes"],
        ["REQ-TECH-007", "Technical", "Multi-factor authentication (MFA) enforcement for all administrative accounts.", "Yes"],
        ["REQ-TECH-008", "Technical", "Comprehensive audit logging for all transactional modifications and security events.", "Yes"],
        ["REQ-CERT-001", "Certification", "The vendor must hold valid ISO/IEC 27001 certification.", "Yes"],
        ["REQ-ELIG-001", "Eligibility", "Minimum 3 years of demonstrable corporate experience in enterprise cloud deployments.", "Yes"],
        ["REQ-COMM-001", "Commercial", "Fixed implementation fee and annual software support price breakdown.", "Yes"],
        ["REQ-COMM-002", "Commercial", "All commercial fee proposals must be quoted in INR currency.", "Yes"],
        ["REQ-DEL-001", "Delivery", "Full platform implementation completed within 16 weeks of contract signing.", "Yes"],
        ["REQ-DOC-001", "Documentation", "Comprehensive administrator manuals and end-user operational guides.", "Yes"],
        ["REQ-SUB-001", "Submission", "Proposals must be submitted electronically via the procurement portal before due date.", "Yes"],
        ["REQ-CON-001", "Contractual", "Liquidated damages for unexcused implementation delays capped at 10% of contract.", "Yes"]
    ]

    # Convert table text into Paragraphs for clean formatting
    formatted_table = []
    for row in table_data:
        formatted_table.append([Paragraph(cell, styles['Normal']) for cell in row])

    t = Table(formatted_table, colWidths=[90, 80, 290, 60])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # 4. Evaluation Criteria
    story.append(Paragraph("4. Evaluation Criteria", styles['Heading2']))
    story.append(Paragraph("Proposals will be evaluated based on the following weighting matrix:", styles['Normal']))
    story.append(Paragraph("1. Technical Architecture & Security (40%)", styles['Normal']))
    story.append(Paragraph("2. Vendor Track Record & Experience (25%)", styles['Normal']))
    story.append(Paragraph("3. Commercial Pricing Structure (20%)", styles['Normal']))
    story.append(Paragraph("4. Implementation Timeline (15%)", styles['Normal']))
    story.append(Spacer(1, 8))

    # 6. Timeline
    story.append(Paragraph("6. Timeline", styles['Heading2']))
    story.append(Paragraph("• RFP Issuance: October 1, 2026", styles['Normal']))
    story.append(Paragraph("• Submission Deadline: November 15, 2026", styles['Normal']))
    story.append(Paragraph("• Vendor Selection: December 1, 2026", styles['Normal']))
    story.append(Spacer(1, 8))

    # 7. Vendor Response
    story.append(Paragraph("7. Vendor Response", styles['Heading2']))
    story.append(Paragraph("Vendors should clearly state their compliance with each requirement.", styles['Normal']))
    story.append(Paragraph("Where a requirement cannot be fully confirmed, the vendor should identify the limitation and provide the information or clarification needed.", styles['Normal']))
    story.append(Paragraph("Vendors must not make unsupported claims.", styles['Normal']))

    doc.build(story)


def test_current_16_requirement_rfp_end_to_end():
    """
    Tests A through F:
    A. Current Test_RFP_Agentic_System.pdf -> exactly 16 genuine requirements.
    B. Purpose text is not a requirement.
    C. Scope of Work overview bullets are not duplicated as formal requirements.
    D. Evaluation Criteria are not requirements.
    E. Timeline entries are not requirements.
    F. Vendor Response instructions are not requirements.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "Test_RFP_Agentic_System.pdf")
        _generate_test_rfp_agentic_system_pdf(pdf_path)

        state: RFPProposalState = {
            "rfp_id": "test_rfp_agentic_16",
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

        # Step 1: Extraction Agent
        extract_output = extract_rfp_node(state)
        raw_clauses = extract_output["raw_clauses"]

        # TEST A: Exactly 16 formal requirements extracted
        assert len(raw_clauses) == 16, f"Expected exactly 16 raw clauses, got {len(raw_clauses)}"

        # Step 2: Classification Agent
        state["raw_clauses"] = raw_clauses
        state["metadata"] = extract_output["metadata"]
        classify_output = classify_requirements_node(state)
        reqs = classify_output["requirements"]

        assert len(reqs) == 16, f"Expected exactly 16 classified requirements, got {len(reqs)}"

        all_req_text = " ".join([r["text"] for r in reqs])
        all_req_codes = [r["req_code"] for r in reqs]

        # TEST B: Purpose text is NOT a requirement
        assert "ABC Retail & Logistics Pvt. Ltd. invites qualified technology vendors" not in all_req_text

        # TEST C: Scope of Work overview bullets are NOT requirements
        assert "Provide training for up to 20 customer users." not in all_req_text
        assert "Provide implementation, configuration, testing, deployment" not in all_req_text

        # TEST D: Evaluation Criteria are NOT requirements
        assert "Technical Architecture & Security (40%)" not in all_req_text
        assert "Commercial Pricing Structure (20%)" not in all_req_text

        # TEST E: Timeline entries are NOT requirements
        assert "RFP Issuance: October 1, 2026" not in all_req_text
        assert "Vendor Selection: December 1, 2026" not in all_req_text

        # TEST F: Vendor Response instructions are NOT requirements
        assert "Vendors should clearly state their compliance with each requirement" not in all_req_text
        assert "Where a requirement cannot be fully confirmed" not in all_req_text
        assert "Vendors must not make unsupported claims" not in all_req_text

        # TEST I: Explicit IDs are preserved
        expected_ids = [
            "REQ-TECH-001", "REQ-TECH-002", "REQ-TECH-003", "REQ-TECH-004",
            "REQ-TECH-005", "REQ-TECH-006", "REQ-TECH-007", "REQ-TECH-008",
            "REQ-CERT-001", "REQ-ELIG-001", "REQ-COMM-001", "REQ-COMM-002",
            "REQ-DEL-001", "REQ-DOC-001", "REQ-SUB-001", "REQ-CON-001"
        ]
        for exp_id in expected_ids:
            assert exp_id in all_req_codes, f"Missing expected requirement ID: {exp_id}"

        # TEST J: Categories and mandatory status are preserved
        req_map = {r["req_code"]: r for r in reqs}
        assert req_map["REQ-TECH-001"]["category"] == "Technical"
        assert req_map["REQ-CERT-001"]["category"] == "Certification"
        assert req_map["REQ-ELIG-001"]["category"] == "Eligibility"
        assert req_map["REQ-COMM-001"]["category"] == "Commercial"
        assert req_map["REQ-DEL-001"]["category"] == "Delivery"
        assert req_map["REQ-DOC-001"]["category"] == "Documentation"
        assert req_map["REQ-SUB-001"]["category"] == "Submission"
        assert req_map["REQ-CON-001"]["category"] == "Contractual"

        # Step 3: Downstream Compliance, Risk, and Proposal Generation
        state["requirements"] = reqs
        compliance_output = analyze_compliance_node(state)
        state["compliance_matrix"] = compliance_output["compliance_matrix"]

        risk_output = assess_risks_node(state)
        state["risks"] = risk_output["risks"]
        state["clarification_questions"] = risk_output["clarification_questions"]

        # TEST K: Downstream risks and clarifications reference only valid requirement IDs
        valid_req_ids = set(all_req_codes)
        for risk in state["risks"]:
            assert risk["requirement_id"] in valid_req_ids, f"Risk references invalid ID: {risk['requirement_id']}"
        for clarif in state["clarification_questions"]:
            assert clarif["requirement_id"] in valid_req_ids, f"Clarification references invalid ID: {clarif['requirement_id']}"


def test_structurally_different_rfp_without_formal_requirements_table():
    """
    Tests G and H:
    G. A different RFP with NO formal Requirements section can still extract genuine requirements from Scope of Work or vendor-obligation sections.
    H. Unnumbered genuine requirements can still be extracted and assigned synthetic IDs.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "No_Formal_Table_RFP.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("REQUEST FOR PROPOSAL - FREIGHT TRACKING SYSTEM", styles['Heading1']))
        story.append(Spacer(1, 10))

        # Scope of Work containing the primary obligation clauses (no separate Requirements table)
        story.append(Paragraph("Scope of Work & Technical Approach", styles['Heading2']))
        story.append(Paragraph("The contractor must provide a container tracking platform supporting GPS telematics ingestion.", styles['Normal']))
        story.append(Paragraph("The platform shall automatically scale to handle 50,000 telemetry events per second.", styles['Normal']))
        story.append(Paragraph("The vendor is required to maintain 99.9% uptime SLA.", styles['Normal']))
        story.append(Paragraph("The vendor shall hold active SOC 2 Type II compliance.", styles['Normal']))
        story.append(Paragraph("All pricing shall be submitted as a fixed monthly SaaS subscription.", styles['Normal']))
        story.append(Paragraph("Implementation shall be concluded within 90 days of contract execution.", styles['Normal']))

        doc.build(story)

        state: RFPProposalState = {
            "rfp_id": "test_rfp_no_table",
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

        extract_output = extract_rfp_node(state)
        raw_clauses = extract_output["raw_clauses"]

        # All 6 unnumbered obligation clauses extracted dynamically
        assert len(raw_clauses) == 6, f"Expected 6 raw clauses from unnumbered Scope of Work, got {len(raw_clauses)}"

        state["raw_clauses"] = raw_clauses
        classify_output = classify_requirements_node(state)
        reqs = classify_output["requirements"]

        assert len(reqs) == 6

        # Synthetic IDs generated for all unnumbered requirements
        for r in reqs:
            assert r["req_code"].startswith("REQ-")
            assert r["category"] in ["Technical", "Commercial", "Certification", "Delivery", "Contractual"]


def test_non_standard_section_name_genuine_requirements():
    """Verify that an RFP with non-standard section names still extracts genuine requirements accurately."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "Non_Standard_Section_RFP.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("SOLICITATION: ADVANCED FLEET LOGISTICS", styles['Heading1']))
        story.append(Spacer(1, 10))

        # Completely non-standard section title
        story.append(Paragraph("Operational Capabilities & Field Enablement", styles['Heading2']))
        story.append(Paragraph("The vendor must provide on-site technical support during initial deployment.", styles['Normal']))
        story.append(Paragraph("The platform shall support real-time telemetry ingestion from 5,000 field devices.", styles['Normal']))
        story.append(Paragraph("The vendor is required to deliver monthly system health audit reports.", styles['Normal']))

        doc.build(story)

        state: RFPProposalState = {
            "rfp_id": "test_non_standard",
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

        extract_output = extract_rfp_node(state)
        raw_clauses = extract_output["raw_clauses"]

        assert len(raw_clauses) == 3, f"Expected 3 raw clauses from non-standard section, got {len(raw_clauses)}"

        state["raw_clauses"] = raw_clauses
        classify_output = classify_requirements_node(state)
        reqs = classify_output["requirements"]

        assert len(reqs) == 3
        for r in reqs:
            assert r["req_code"].startswith("REQ-")
            assert len(r["text"]) > 10

