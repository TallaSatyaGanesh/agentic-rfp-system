import os
import tempfile
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from app.agents.extractor_agent import extract_rfp_node, _is_non_requirement_heading_or_criterion
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


def test_gov_defense_pws_style_rfp():
    """Verify Gov/Defense style Performance Work Statement (PWS) without tables extracts genuine requirements."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "defense_pws_rfp.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("PERFORMANCE WORK STATEMENT (PWS)", styles['Heading1']))
        story.append(Paragraph("Tactical Data Network Modernization", styles['Heading2']))
        story.append(Spacer(1, 10))

        story.append(Paragraph("1.0 Scope of Work", styles['Heading2']))
        story.append(Paragraph("The Contractor shall provide engineering and cybersecurity services for tactical data nodes.", styles['Normal']))
        story.append(Paragraph("The Contractor must assign a dedicated Key Personnel Lead holding an active Top Secret clearance.", styles['Normal']))
        story.append(Spacer(1, 8))

        story.append(Paragraph("2.0 Technical Specifications", styles['Heading2']))
        story.append(Paragraph("The system shall implement FIPS 140-3 validated cryptographic modules.", styles['Normal']))
        story.append(Paragraph("The network architecture must support zero-loss failover within 50 milliseconds.", styles['Normal']))
        story.append(Spacer(1, 8))

        story.append(Paragraph("3.0 Deliverables & Reporting", styles['Heading2']))
        story.append(Paragraph("The Contractor shall submit monthly status reports (MSR) no later than the 5th business day of each month.", styles['Normal']))
        story.append(Paragraph("The vendor is required to deliver finalized architecture design documents within 60 days of award.", styles['Normal']))

        doc.build(story)

        state: RFPProposalState = {
            "rfp_id": "test_defense_pws",
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

        extract_result = extract_rfp_node(state)
        raw_clauses = extract_result["raw_clauses"]

        assert len(raw_clauses) == 6, f"Expected 6 raw clauses from PWS, got {len(raw_clauses)}"

        state["raw_clauses"] = raw_clauses
        classify_result = classify_requirements_node(state)
        classified_reqs = classify_result["requirements"]

        assert len(classified_reqs) == 6
        for r in classified_reqs:
            assert r["req_code"].startswith("REQ-")
            assert len(r["text"]) > 15


def test_annexure_schedule_based_rfp():
    """Verify RFP structured into Annexures and Schedules extracts requirements accurately."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "annexure_rfp.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("GLOBAL TENDER NOTICE", styles['Heading1']))
        story.append(Paragraph("Notice Inviting Tender (NIT) No: GT-2026-88", styles['Heading2']))
        story.append(Spacer(1, 10))

        story.append(Paragraph("Annexure A: Functional Specifications", styles['Heading2']))
        story.append(Paragraph("The application must provide automated report generation in PDF and Excel formats.", styles['Normal']))
        story.append(Paragraph("The platform shall maintain 99.95% system uptime throughout the contract term.", styles['Normal']))
        story.append(Spacer(1, 8))

        story.append(Paragraph("Schedule B: Commercial and Pricing Schedule", styles['Heading2']))
        story.append(Paragraph("Bidders shall provide a fixed-rate pricing structure valid for 24 months.", styles['Normal']))
        story.append(Paragraph("All invoices must be submitted electronically with milestone completion certificates.", styles['Normal']))

        doc.build(story)

        state: RFPProposalState = {
            "rfp_id": "test_annexure_rfp",
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

        extract_result = extract_rfp_node(state)
        raw_clauses = extract_result["raw_clauses"]

        assert len(raw_clauses) == 4, f"Expected 4 raw clauses from Annexure RFP, got {len(raw_clauses)}"

        state["raw_clauses"] = raw_clauses
        classify_result = classify_requirements_node(state)
        classified_reqs = classify_result["requirements"]

        assert len(classified_reqs) == 4
        categories = {r["category"] for r in classified_reqs}
        assert "Technical" in categories
        assert "Commercial" in categories


def test_buyer_and_evaluation_committee_action_disambiguation():
    """Verify that buyer actions and evaluation committee procedures are NOT extracted as vendor requirements."""
    statements = [
        "Duly constituted Evaluation Committee will evaluate the proposal vis-a-vis compliance with the requirements.",
        "The Procurement Committee shall open the technical bids in the presence of bidders' representatives.",
        "The Client reserves the right to accept or reject any proposal and to annul the bidding process at any time.",
        "The Tender Scrutiny Committee will determine whether each bid meets the minimum eligibility criteria.",
        "The Competent Authority may allocate marks based on technical demonstrations."
    ]

    for stmt in statements:
        assert _is_non_requirement_heading_or_criterion(stmt) is True, f"Failed to filter buyer/committee action: {stmt}"


def test_scoring_marks_and_qcbs_formula_disambiguation():
    """Verify that scoring tables, QCBS formulas, and marks allocation rules are NOT extracted as vendor requirements."""
    statements = [
        "Proposal with the highest technical marks shall be given a score of 100.",
        "The total score, both technical and financial, shall be obtained by weighing the quality and cost scores.",
        "The proposal obtaining the highest total combined score in evaluation of quality and cost will be ranked as H-1.",
        "Financial proposals will be evaluated based on the QCBS methodology with 70:30 weightage.",
        "Technical Architecture (30 Marks)",
        "Relevant Project Experience: More than 100 deployments - 20 Marks",
        "Proposals will be evaluated based on technical capability (80%) and commercial competitiveness (20%)."
    ]

    for stmt in statements:
        assert _is_non_requirement_heading_or_criterion(stmt) is True, f"Failed to filter scoring/QCBS formula: {stmt}"


def test_end_user_ui_journey_and_walkthrough_disambiguation():
    """Verify that end-user UI interaction narratives are NOT extracted as vendor requirements."""
    statements = [
        "User will enter user id and password to log in to the portal.",
        "Applicant will register with the portal entering their basic organization details.",
        "User fills the responses to the fields and attaches all the required documents.",
        "If required, the user can click on edit button to revise the submission.",
        "The user selects the district from the dropdown menu and clicks search button.",
        "User will be able to change his password by using change password feature.",
        "The system opens the Registration page with multiple sections."
    ]

    for stmt in statements:
        assert _is_non_requirement_heading_or_criterion(stmt) is True, f"Failed to filter end-user UI journey: {stmt}"


def test_tender_deposit_and_emd_mechanics_disambiguation():
    """Verify that bidding deposit mechanics and EMD payment logistics are NOT extracted as vendor requirements."""
    statements = [
        "The online payment of EMD shall be made through RTGS as per the details given below.",
        "Online payment of EMD by cheque, TDR or FDR will not be accepted.",
        "A Bank Guarantee of equivalent amount from any Nationalized bank favoring PAO should be valid for 6 months.",
        "MSEs in India registered with appropriate authority shall be exempted from EMD.",
        "The bidder should submit the Bid-Security Declaration as per the format given below.",
        "Without EMD, tender will be summarily rejected."
    ]

    for stmt in statements:
        assert _is_non_requirement_heading_or_criterion(stmt) is True, f"Failed to filter EMD/tender deposit mechanic: {stmt}"


def test_form_template_placeholders_and_column_sequences():
    """Verify that form templates, column numbering sequences, and drafting notes are NOT extracted as requirements."""
    statements = [
        "1 2 3 4 5 6 7 8 9 TOTAL COST (A) INR Please add/delete rows if required",
        "1 2 3 4 Please add/delete rows if required",
        "Total Cost in Words: __________________________________________________",
        "Each State RCS office needs to define the requirements here by suitably changing the contents given below",
        "Proforma Technical Proposal (Annexure II)",
        "Proforma Financial Proposal (Annexure III)"
    ]

    for stmt in statements:
        assert _is_non_requirement_heading_or_criterion(stmt) is True, f"Failed to filter form artifact: {stmt}"


def test_unseen_healthcare_ehr_rfp_generalization():
    """
    Verify complete generalization on an unseen, multi-section Healthcare EHR RFP
    with complex mixed sections (Buyer Committee rules, User walkthroughs, and genuine clinical requirements).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "Healthcare_EHR_Solicitation.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("HOSPITAL AUTHORITY SOLICITATION: ENTERPRISE EHR SYSTEM", styles['Heading1']))
        story.append(Paragraph("Notice Inviting Tender Ref: HA-EHR-2026-99", styles['Heading2']))
        story.append(Spacer(1, 10))

        # Section 1: Committee / Evaluation (Must be excluded)
        story.append(Paragraph("Section 1: Bid Evaluation & Award Process", styles['Heading2']))
        story.append(Paragraph("The Clinical Evaluation Committee will evaluate technical proposals based on demonstrations.", styles['Normal']))
        story.append(Paragraph("Proposals scoring above 80% technical marks will qualify for commercial bid opening.", styles['Normal']))
        story.append(Paragraph("The final vendor selection will be ranked H-1 according to the QCBS 70:30 formula.", styles['Normal']))
        story.append(Spacer(1, 8))

        # Section 2: Clinical Workflow Narrative (Must be excluded)
        story.append(Paragraph("Section 2: Doctor and Nurse Portal User Walkthrough", styles['Heading2']))
        story.append(Paragraph("The physician will log in with their employee ID and select the outpatient clinic department.", styles['Normal']))
        story.append(Paragraph("The nurse fills the vital signs form and clicks on the submit button.", styles['Normal']))
        story.append(Paragraph("The user can click on the print prescription icon to generate a paper copy.", styles['Normal']))
        story.append(Spacer(1, 8))

        # Section 3: Genuine Clinical Specifications (Must be extracted!)
        story.append(Paragraph("Section 3: Clinical & Technical Specifications", styles['Heading2']))
        story.append(Paragraph("The EHR platform must support HL7 FHIR Release 4 APIs for interoperability with lab instruments.", styles['Normal']))
        story.append(Paragraph("The system shall enforce HIPAA-compliant AES-256 encryption for all electronic protected health information (ePHI) at rest.", styles['Normal']))
        story.append(Paragraph("The database must support automated sub-minute failover to a standby disaster recovery node.", styles['Normal']))
        story.append(Spacer(1, 8))

        # Section 4: Mandatory Security Standards (Must be extracted!)
        story.append(Paragraph("Section 4: Mandatory Security Standards", styles['Heading2']))
        story.append(Paragraph("The vendor must maintain active ISO 27701 and SOC 2 Type II certifications throughout the contract.", styles['Normal']))
        story.append(Paragraph("Role-based access control with biometric or hardware token multi-factor authentication is required.", styles['Normal']))
        story.append(Spacer(1, 8))

        # Section 5: Commercial Terms & SLA (Must be extracted!)
        story.append(Paragraph("Section 5: Commercial Terms, SLA & Legal", styles['Heading2']))
        story.append(Paragraph("All commercial pricing shall be structured as a fixed annual subscription fee.", styles['Normal']))
        story.append(Paragraph("The system availability shall maintain an uptime of at least 99.99% for critical emergency care modules.", styles['Normal']))
        story.append(Paragraph("The contractor agrees to indemnify the hospital authority against any third-party data breach liabilities.", styles['Normal']))

        doc.build(story)

        state: RFPProposalState = {
            "rfp_id": "test_unseen_healthcare",
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

        # Exactly 8 genuine requirements should be extracted (Sections 3, 4, 5)
        # Zero committee actions (Section 1) and zero user click steps (Section 2)
        assert len(raw_clauses) == 8, f"Expected exactly 8 genuine clinical/technical requirements, got {len(raw_clauses)}"

        all_text = " ".join(c["text"] for c in raw_clauses)

        # Confirm non-requirements are NOT present
        assert "Clinical Evaluation Committee will evaluate" not in all_text
        assert "QCBS 70:30 formula" not in all_text
        assert "physician will log in" not in all_text
        assert "nurse fills the vital signs form" not in all_text
        assert "clicks on the submit button" not in all_text

        # Confirm genuine requirements ARE present
        assert "HL7 FHIR Release 4 APIs" in all_text
        assert "HIPAA-compliant AES-256 encryption" in all_text
        assert "ISO 27701 and SOC 2 Type II" in all_text
        assert "99.99%" in all_text
        assert "indemnify the hospital" in all_text

        # 2. Classification Phase
        state["raw_clauses"] = raw_clauses
        classify_result = classify_requirements_node(state)
        classified_reqs = classify_result["requirements"]

        assert len(classified_reqs) == 8
        categories = {r["category"] for r in classified_reqs}
        assert "Technical" in categories
        assert "Certification" in categories
        assert "Commercial" in categories
        assert "Contractual" in categories

