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


def test_toc_dot_leaders_and_page_numbers_rejected():
    """Verify that Table of Contents entries with dot leaders and target page numbers are rejected."""
    toc_lines = [
        "4.1 Volume-I [Instructions to Bidder] ........ 7",
        "8.3 Purchaser's Procurement Rights ........ 26",
        "5.2 Technical Specifications ... 14",
        "Scope of Services … 32",
        "Section 3: Financial & Commercial Guidelines . . . . . . 45",
        "Annexure A: Declaration Format ----------------- 52",
        "Schedule B: Key Deliverables\t\t\t\t\t\t\t60"
    ]
    for line in toc_lines:
        assert _is_non_requirement_heading_or_criterion(line) is True, f"Failed to filter TOC entry: {line}"


def test_bracketed_and_punctuated_headings_rejected():
    """Verify that section headings with square brackets, parentheses, apostrophes, and colons are rejected."""
    heading_lines = [
        "4.1 VOLUME-I [INSTRUCTIONS TO BIDDER]",
        "8.3 Purchaser's Procurement Rights",
        "Section 2 (Technical & Architecture Specifications)",
        "Chapter 3: System & Security Requirements",
        "PART 1 - GENERAL BIDDING CONDITIONS",
        "Annexure II: Proforma for Technical Proposal",
        "Volume II: Scope of Work and Technical Architecture"
    ]
    for line in heading_lines:
        assert _is_non_requirement_heading_or_criterion(line) is True, f"Failed to filter heading: {line}"


def test_document_reference_metadata_and_date_fragments_rejected():
    """Verify that standalone document reference numbers, publication notices, and date fragments are rejected."""
    metadata_lines = [
        "RFP Ref No.: OCAC-SEGP-SPD-0090-2025-26007",
        "Tender Notice No: 2026/IT-099",
        "NIT Ref: GOV-DATA-2026-X",
        "Bid Reference Number: GEM/2026/B/123456",
        "Date of Publication: 03.02.2026",
        "03.02.2026 by 5:00 PM",
        "Date: 15/03/2026",
        "FORM 1: BIDDER GENERAL INFORMATION",
        "ANNEXURE A - UNDERTAKING OF NON-BLACKLISTING",
        "PROFORMA 2: FINANCIAL TURNOVER CERTIFICATE"
    ]
    for line in metadata_lines:
        assert _is_non_requirement_heading_or_criterion(line) is True, f"Failed to filter metadata/form header: {line}"


def test_buyer_institutional_background_rejected():
    """Verify that buyer institutional corporate profiles and due diligence disclaimers are rejected."""
    narrative_lines = [
        "The Centre was established in 1985 as the designated technical directorate of the Department.",
        "The Authority is a statutory body corporate functioning under the administrative control of the Ministry.",
        "The Department acts as the nodal agency for e-governance initiatives in the state.",
        "Bidders must form their own conclusions and satisfy themselves regarding all aspects of the RFP requirements."
    ]
    for line in narrative_lines:
        assert _is_non_requirement_heading_or_criterion(line) is True, f"Failed to filter buyer background/disclaimer: {line}"


def test_genuine_actionable_requirements_retained():
    """Verify that all genuine, substantive requirement categories are preserved without being filtered."""
    requirements = [
        # Administrative / Eligibility
        "The bidder must be registered with GSTN and submit a copy of GST registration certificate along with PAN card.",
        "The bidder must have an average annual turnover of at least INR 13 Crores during the last three financial years.",
        "The bidder must have successfully executed at least three software development projects of value not less than INR 2.5 Crores each.",
        # Certification
        "The bidder must possess a valid CMMI DEV Level 3 or higher certification as on the date of bid submission.",
        "The vendor must maintain active ISO 27001 and ISO 9001 certifications throughout the contract duration.",
        # Commercial / Contractual
        "The bidder must submit an Earnest Money Deposit (EMD) of INR 5,00,000 online or as a Bank Guarantee.",
        "The successful bidder shall furnish a Performance Bank Guarantee (PBG) equivalent to 10% of total contract value.",
        "The proposal shall remain valid for a minimum period of 180 days from the last date of proposal submission.",
        # Delivery / Staffing
        "The bidder shall have or undertake to establish a fully operational project office in Bhubaneswar, Odisha within 30 days of award.",
        "The vendor must deploy a certified Project Manager and at least five senior solution architects for the implementation.",
        # Technical
        "The application must support role-based access control and provide RESTful APIs for integration with State Data Centre.",
        "The cloud platform shall guarantee 99.95% system uptime with automated sub-minute disaster recovery failover.",
        # Actionable requirement containing metadata words
        "The proposal must cite RFP Ref No. 2026-01 on the cover envelope and be submitted before 5:00 PM on the due date.",
        # Numbered actionable requirement
        "4.1 The system shall maintain 99.95% availability for all public-facing services."
    ]
    for req in requirements:
        assert _is_non_requirement_heading_or_criterion(req) is False, f"Erroneously filtered genuine requirement: {req}"


def test_multipage_pdf_layout_sanitation_and_toc_suppression():
    """
    End-to-end multi-page PDF validation test:
    Generates a realistic 4-page procurement RFP containing:
    - Running headers/footers on all pages
    - Cover page metadata & document reference number
    - Table of Contents with dot leaders
    - Buyer institutional background narrative
    - Form header banners
    - 7 genuine actionable requirements across 6 categories
    Verifies that ONLY the 7 genuine requirements are extracted and classified.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "Enterprise_Tender_MultiPage.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # PAGE 1: Cover Page & Metadata
        story.append(Paragraph("REQUEST FOR PROPOSAL - ENTERPRISE STATE PORTAL", styles['Heading1']))
        story.append(Paragraph("RFP Ref No.: TENDER-EGOV-2026-0088", styles['Heading2']))
        story.append(Paragraph("Date of Publication: 03.02.2026", styles['Normal']))
        story.append(Spacer(1, 15))

        # Table of Contents
        story.append(Paragraph("TABLE OF CONTENTS", styles['Heading2']))
        story.append(Paragraph("4.1 Volume-I [Instructions to Bidder] ........ 7", styles['Normal']))
        story.append(Paragraph("8.3 Purchaser's Procurement Rights ........ 26", styles['Normal']))
        story.append(Paragraph("5.2 Technical Architecture Specifications ... 14", styles['Normal']))
        story.append(Spacer(1, 15))

        # Buyer Background (Informational preamble)
        story.append(Paragraph("The Centre was established in 1985 as the designated technical directorate of the Department.", styles['Normal']))
        story.append(Paragraph("Bidders must form their own conclusions and satisfy themselves regarding all aspects of the RFP requirements.", styles['Normal']))
        story.append(Spacer(1, 15))

        # PAGE 2: Eligibility & Certifications (Genuine Requirements)
        story.append(Paragraph("Section 2: Pre-Qualification Criteria", styles['Heading2']))
        story.append(Paragraph("The bidder must be registered with GSTN and submit a copy of GST registration certificate along with PAN card.", styles['Normal']))
        story.append(Paragraph("The bidder must have an average annual turnover of at least INR 13 Crores during the last three financial years.", styles['Normal']))
        story.append(Paragraph("The bidder must possess a valid CMMI DEV Level 3 or higher certification as on the date of bid submission.", styles['Normal']))
        story.append(Paragraph("The bidder must have successfully executed at least three software development projects of value not less than INR 2.5 Crores each.", styles['Normal']))
        story.append(Spacer(1, 15))

        # PAGE 3: Commercial & Delivery Requirements (Genuine Requirements)
        story.append(Paragraph("Section 3: Commercial & Delivery Terms", styles['Heading2']))
        story.append(Paragraph("The bidder must submit an Earnest Money Deposit (EMD) of INR 5,00,000 online or as a Bank Guarantee.", styles['Normal']))
        story.append(Paragraph("The successful bidder shall furnish a Performance Bank Guarantee (PBG) equivalent to 10% of total contract value.", styles['Normal']))
        story.append(Paragraph("The bidder shall have or undertake to establish a fully operational project office in Bhubaneswar, Odisha within 30 days of award.", styles['Normal']))
        story.append(Spacer(1, 15))

        # Form Header Banners (Must be filtered)
        story.append(Paragraph("FORM 1: BIDDER GENERAL INFORMATION", styles['Heading2']))
        story.append(Paragraph("ANNEXURE A - UNDERTAKING OF NON-BLACKLISTING", styles['Heading2']))

        doc.build(story)

        state: RFPProposalState = {
            "rfp_id": "test_multipage_sanitation",
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

        # Exactly the 7 genuine requirements must be extracted
        assert len(raw_clauses) == 7, f"Expected exactly 7 genuine requirements, got {len(raw_clauses)}"

        all_clause_text = " ".join(c["text"] for c in raw_clauses)

        # Confirm non-requirements are NOT extracted
        assert "Volume-I [Instructions to Bidder]" not in all_clause_text
        assert "Purchaser's Procurement Rights" not in all_clause_text
        assert "TENDER-EGOV-2026-0088" not in all_clause_text
        assert "designated technical directorate" not in all_clause_text
        assert "form their own conclusions" not in all_clause_text
        assert "FORM 1: BIDDER GENERAL INFORMATION" not in all_clause_text
        assert "ANNEXURE A - UNDERTAKING" not in all_clause_text

        # Confirm genuine requirements ARE extracted
        assert "GST registration certificate" in all_clause_text
        assert "13 Crores" in all_clause_text
        assert "CMMI DEV Level 3" in all_clause_text
        assert "2.5 Crores" in all_clause_text
        assert "5,00,000" in all_clause_text
        assert "10%" in all_clause_text
        assert "Bhubaneswar" in all_clause_text

        # 2. Classification Phase
        state["raw_clauses"] = raw_clauses
        classify_result = classify_requirements_node(state)
        classified_reqs = classify_result["requirements"]

        assert len(classified_reqs) == 7
        for req in classified_reqs:
            assert req["req_code"].startswith("REQ-")
            assert len(req["normalized_description"]) > 10


def test_buyer_statements_and_legal_disclaimers_filtered():
    """Verify that buyer statements, reservation rights, disclaimers, and procurement rights are rejected."""
    disclaimers = [
        "No commitment of any kind, contractual or otherwise shall exist unless and until a formal written contract has been executed.",
        "Any notification of preferred Bidder status by the Purchaser shall not give rise to any enforceable rights by the Bidder.",
        "This RFP supersedes and replaces any previous public documentation & communication, and Bidders should place no reliance and dependence on such communications.",
        "The Purchaser makes no commitment, explicit or implied, that this process will result in a business transaction with anyone.",
        "The decision of the Purchaser shall be final and binding on all matters relating to the RFP evaluation.",
        "Purchaser's Procurement Rights: The Purchaser reserves the right to accept any proposal and to reject any or all proposals.",
        "Failure of the successful bidder to agree with the Terms & Conditions shall constitute sufficient grounds for the annulment of the award.",
        "The Purchaser may terminate the contract at any time for its convenience with 30 days written notice.",
        "Corrigenda and/or addenda issued shall be deemed to be incorporated into this RFP."
    ]
    for line in disclaimers:
        assert _is_non_requirement_heading_or_criterion(line) is True, f"Failed to filter buyer disclaimer: {line}"


def test_generic_advice_and_reading_instructions_filtered():
    """Verify that generic reading advice and study instructions are rejected."""
    advice_lines = [
        "Bidders are advised to study all instructions, forms, terms, requirements and other information in the RFP documents carefully.",
        "This will lead to a reduction in the time required for bid submission process.",
        "No correspondence will be entertained by the Authority on the rejected bids.",
        "Bidders should get ready the bid documents to be submitted, scanned with 100 dpi which helps in reducing size of the document.",
        "To avoid the time and effort required in uploading, bidders can use My Documents space.",
        "Bidder should log into the website well in advance for bid submission so that bid gets uploaded well in time.",
        "Do not lend their DSC's to others which may lead to misuse.",
        "Prices should not be indicated in the pre-qualification bid and should only be indicated in the commercial proposal."
    ]
    for line in advice_lines:
        assert _is_non_requirement_heading_or_criterion(line) is True, f"Failed to filter generic advice: {line}"


def test_portal_and_process_mechanics_filtered():
    """Verify that portal walkthroughs, BOQ spreadsheets, and e-procurement mechanics are rejected."""
    mechanics_lines = [
        "Once you pay both fee, tenders will be moved to My Tenders list.",
        "Download the BOQ and complete the unprotected green cells with their respective financial quotes.",
        "Server time (which is displayed on the bidders' dashboard) will be considered as the standard time for referencing the deadlines.",
        "Bidders will be redirected to the payment gateway for online payment of tender fee.",
        "Click Complete (i.e. after clicking submit in the portal) to generate the bid submission acknowledgement.",
        "Upon enrolment, the bidders will be required to register their valid Digital Signature Certificate.",
        "Only Class III certificates with signing + encryption should be registered on the portal.",
        "The scanned copies of all original documents should be uploaded in PDF format on e-tender portal."
    ]
    for line in mechanics_lines:
        assert _is_non_requirement_heading_or_criterion(line) is True, f"Failed to filter portal mechanics: {line}"


def test_form_templates_and_proforma_declarations_filtered():
    """Verify that form column headers, placeholder templates, and first-person proforma declarations are rejected."""
    proforma_lines = [
        "Madam/Sir, I, the undersigned, offer to provide services in accordance with your Request for Proposal.",
        "We declare that our Bid Price is for the entire scope and includes all statutory taxes and duties.",
        "KNOW ALL MEN by these presents that We, having our registered office, do hereby submit this Bank Guarantee.",
        "We hereby nominate, constitute and appoint Shri ABC as our true and lawful attorney.",
        "Our proposal is binding upon us and subject to modifications resulting from contract negotiations.",
        "We understand that you are not bound to accept any proposal you may receive.",
        "Sl# RFP Document Reference Content of RFP Requiring Clarification Points of Clarification",
        "Name of the bidder: Address: Contact Person: Email: Phone: Mobile:",
        "Project Citation Format: Project Name: Value of contract: Status of assignment:",
        "Acceptance of Terms and Conditions (To be submitted on Bidder's Letter Head)",
        "<Name of the bidder> <Amount in figures> <insert date>"
    ]
    for line in proforma_lines:
        assert _is_non_requirement_heading_or_criterion(line) is True, f"Failed to filter proforma/template line: {line}"


def test_full_multipage_pipeline_with_odisha_patterns():
    """
    Validation Test: Comprehensive 5-page PDF containing all 5 classes of false positives
    alongside all 11 genuine bidder requirements (including net worth with 31.03.2025 date).
    Verifies that:
    1. Zero false positives from the 5 classes are extracted.
    2. Date '31.03.2025' does NOT fragment the net worth clause.
    3. All genuine requirements are cleanly extracted with exact source tracking.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "Full_Validation_RFP.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # PAGE 1: Preamble & Buyer Disclaimers & TOC
        story.append(Paragraph("REQUEST FOR PROPOSAL - STATE INTEGRATED PLATFORM", styles['Heading1']))
        story.append(Paragraph("RFP Ref No.: OCAC-SEGP-SPD-0090-2025-26007", styles['Heading2']))
        story.append(Paragraph("Date of Publication: 29.01.2026", styles['Normal']))
        story.append(Paragraph("4.1 Volume-I [Instructions to Bidder] ........ 7", styles['Normal']))
        story.append(Paragraph("8.3 Purchaser's Procurement Rights ........ 26", styles['Normal']))
        story.append(Paragraph("No commitment of any kind, contractual or otherwise shall exist unless and until a formal written contract is executed.", styles['Normal']))
        story.append(Paragraph("This RFP supersedes and replaces any previous public documentation.", styles['Normal']))
        story.append(Paragraph("The decision of Purchaser shall be final and binding.", styles['Normal']))
        story.append(Spacer(1, 12))

        # PAGE 2: Instructions & Portal Mechanics
        story.append(Paragraph("Section 1: General Instructions to Bidders", styles['Heading2']))
        story.append(Paragraph("Bidders are advised to study all instructions, forms, terms and specifications in the RFP.", styles['Normal']))
        story.append(Paragraph("Once you pay both fee, tenders will be moved to My Tenders list.", styles['Normal']))
        story.append(Paragraph("Download the BOQ and complete the unprotected green cells with financial quotes.", styles['Normal']))
        story.append(Paragraph("Server time displayed on the dashboard will be considered as standard time.", styles['Normal']))
        story.append(Paragraph("Click Complete after clicking submit in the portal.", styles['Normal']))
        # Genuine monetary instruction requirements in instructions section:
        story.append(Paragraph("The bidder shall submit a non-refundable tender document fee of INR 11,800 online through the payment gateway.", styles['Normal']))
        story.append(Paragraph("The proposal shall remain valid for a minimum period of 180 days from the proposal due date.", styles['Normal']))
        story.append(Spacer(1, 12))

        # PAGE 3: Prequalification Criteria (Genuine Requirements)
        story.append(Paragraph("7.1 PREQUALIFICATION CRITERIA (GENERAL BID)", styles['Heading2']))
        story.append(Paragraph("The bidder must be an entity registered under Companies Act with at least 5 years of operations in India and possessing valid GSTN registration.", styles['Normal']))
        story.append(Paragraph("The bidder must have an average annual turnover of at least INR 13 Crores during the last three financial years.", styles['Normal']))
        story.append(Paragraph("The bidder must have positive net worth as on 31.03.2025 as per audited financial statements.", styles['Normal']))
        story.append(Paragraph("The bidder must possess a valid CMMI DEV Level 3 or higher certification as on the date of submission.", styles['Normal']))
        story.append(Paragraph("The bidder must have successfully executed at least 1 project of value INR 5 Crores, or 2 projects of INR 4 Crores, or 3 projects of INR 2.5 Crores each in government sector.", styles['Normal']))
        story.append(Paragraph("The bidder shall have or establish a fully operational project office in Bhubaneswar, Odisha within 30 days of award.", styles['Normal']))
        story.append(Paragraph("The bidder must submit a Power of Attorney authorizing the signatory to sign the bid.", styles['Normal']))
        story.append(Spacer(1, 12))

        # PAGE 4: Commercial & Contractual Terms (Genuine Requirements)
        story.append(Paragraph("Section 8: Commercial & Contractual Terms", styles['Heading2']))
        story.append(Paragraph("The successful bidder shall furnish a Performance Bank Guarantee (PBG) equivalent to 3% of total contract value valid for 20 months.", styles['Normal']))
        story.append(Paragraph("The proposed architecture must enforce zero trust network access, AES-256 encryption at rest, and automated daily backup.", styles['Normal']))
        story.append(Paragraph("The vendor shall submit complete technical documentation and user training manuals prior to final user acceptance signoff.", styles['Normal']))
        story.append(Spacer(1, 12))

        # PAGE 5: Proforma & Form Templates (Must be filtered!)
        story.append(Paragraph("9.1 PRE-QUALIFICATION BID FORMATS", styles['Heading2']))
        story.append(Paragraph("Madam/Sir, I, the undersigned, offer to provide the services in accordance with your Request for Proposal.", styles['Normal']))
        story.append(Paragraph("We declare that our Bid Price is for the entire scope and includes all applicable taxes.", styles['Normal']))
        story.append(Paragraph("KNOW ALL MEN by these presents that We hereby submit our Bank Guarantee.", styles['Normal']))
        story.append(Paragraph("Sl# RFP Document Reference Content of RFP Requiring Clarification Points of Clarification", styles['Normal']))
        story.append(Paragraph("Name of the bidder: Address: Contact Person: Email: Phone: Mobile:", styles['Normal']))

        doc.build(story)

        state: RFPProposalState = {
            "rfp_id": "test_full_pipeline_odisha",
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

        # Exactly 12 genuine requirements:
        # Page 2: INR 11,800 fee, 180 days validity (2)
        # Page 3: 5 years + GSTN, 13 Cr turnover, Net worth 31.03.2025, CMMI DEV Level 3, 1@5Cr/2@4Cr/3@2.5Cr, Odisha office, Power of Attorney (7)
        # Page 4: PBG 3% 20 months, Zero trust architecture, Technical documentation (3)
        # Total = 12
        assert len(raw_clauses) == 12, f"Expected exactly 12 genuine requirements, got {len(raw_clauses)}"

        all_text = " ".join(c["text"] for c in raw_clauses)

        # Confirm false positives are ABSENT:
        assert "No commitment of any kind" not in all_text
        assert "supersedes and replaces" not in all_text
        assert "final and binding" not in all_text
        assert "Bidders are advised to study" not in all_text
        assert "My Tenders" not in all_text
        assert "Download the BOQ" not in all_text
        assert "Server time" not in all_text
        assert "Click Complete" not in all_text
        assert "Madam/Sir" not in all_text
        assert "We declare that our Bid Price" not in all_text
        assert "KNOW ALL MEN" not in all_text
        assert "Content of RFP Requiring Clarification" not in all_text

        # Confirm genuine requirements are PRESENT:
        assert "11,800" in all_text
        assert "180 days" in all_text
        assert "5 years of operations" in all_text
        assert "13 Crores" in all_text
        assert "positive net worth as on 31.03.2025" in all_text
        assert "CMMI DEV Level 3" in all_text
        assert "5 Crores" in all_text
        assert "Bhubaneswar, Odisha" in all_text
        assert "Power of Attorney" in all_text
        assert "3%" in all_text and "20 months" in all_text
        assert "zero trust network access" in all_text
        assert "technical documentation" in all_text

        # Verify net worth clause is NOT fragmented
        nw_clauses = [c["text"] for c in raw_clauses if "net worth" in c["text"].lower()]
        assert len(nw_clauses) == 1, f"Net worth clause was fragmented: {nw_clauses}"
        assert "31.03.2025" in nw_clauses[0]

        # 2. Classification Phase
        state["raw_clauses"] = raw_clauses
        classify_result = classify_requirements_node(state)
        classified_reqs = classify_result["requirements"]

        assert len(classified_reqs) == 12
        for req in classified_reqs:
            assert req["req_code"].startswith("REQ-")
            assert len(req["normalized_description"]) > 10


def test_five_newly_fixed_false_positive_families():
    """
    Verify filtering of the 5 newly identified false positive families:
    1. Buyer reservation/remedy actions (PBG invocation, cancellation, notification of unsuccessful bidders)
    2. Portal UI mechanics (uploaded documents display)
    3. Detached table evidence cells (bare noun phrases without active obligation)
    4. Dangling/incomplete structural fragments
    5. First-person proforma validity declarations
    """
    # 1. Buyer rights & remedy actions
    buyer_actions = [
        "OCAC reserves the rights to reject a proposal if the bidder is found to be non-compliant.",
        "OCAC shall invoke the performance guarantee in case of vendor breach.",
        "In such a case, OCAC shall invoke the PBG and blacklist the agency.",
        "Upon furnishing PBG, OCAC will notify each unsuccessful bidder and return their EMD."
    ]
    for text in buyer_actions:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter buyer action: {text}"

    # 2. Portal UI mechanics
    portal_mechanics = [
        "Already uploaded documents in this section will be displayed.",
        "Uploaded documents in this section can be viewed by the user."
    ]
    for text in portal_mechanics:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter portal display mechanic: {text}"

    # 3. Detached table evidence cells
    table_evidence = [
        "Copy of Certificate of Incorporation / Registration Certificate.",
        "Certificate from CA with Copy of Audited Balance Sheet.",
        "§ Copy of Work Order and Client Certificate.",
        "§ Documentary Evidence of Play Store active listing."
    ]
    for text in table_evidence:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter table evidence cell: {text}"

    # 4. Dangling / incomplete fragments
    dangling_fragments = [
        "Bidders must:",
        "The bidder shall:",
        "However, the bid should comply with State ICT Policy 2022, Clause",
        "In accordance with Section"
    ]
    for text in dangling_fragments:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter dangling fragment: {text}"

    # 5. First-person proforma declarations
    first_person_declarations = [
        "Our proposal will be valid for acceptance up to 180 Days and I confirm that this proposal will remain binding.",
        "I/We hereby declare that our proposal is valid for acceptance for 180 days."
    ]
    for text in first_person_declarations:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter first-person proforma declaration: {text}"

    # Verify genuine active requirements remain ACCEPTED (not filtered)
    genuine_requirements = [
        "The bidder shall submit Power of Attorney in the prescribed format.",
        "Copies of audited balance sheets and profit & loss statements should be enclosed with the bid.",
        "The successful bidder shall submit Performance Bank Guarantee of 3% of contract value.",
        "The bidder must have an average annual turnover of at least INR 13 Crores.",
        "The bidder shall have or establish a fully operational project office in Bhubaneswar, Odisha."
    ]
    for text in genuine_requirements:
        assert _is_non_requirement_heading_or_criterion(text) is False, f"Erroneously filtered genuine requirement: {text}"


def test_targeted_extraction_boundary_and_remedy_cleanup():
    """
    Regression Test:
    1. Buyer remedies (cancel order, forfeit EMD on failure) are rejected as standalone requirements.
    2. Buyer-only requirement notices (Purchaser will require selected bidder to provide PBG) are rejected.
    3. Buyer-side standalone acceptance form descriptions (Performance security shall be accepted in the form of...) are rejected.
    4. Table row labels and adjacent cell fragments are cleanly stripped from genuine requirements.
    5. Contact, address, and email header prefixes are cleanly stripped from genuine requirements.
    6. Genuine multi-sentence obligations (EMD, PBG with MSE/Startup rule, validity) are preserved as cohesive units.
    """
    from app.agents.extractor_agent import _clean_clause_text

    # 1. Buyer remedies rejected
    buyer_remedies = [
        "In case the selected bidder fails to submit performance guarantee within the time stipulated, OCAC at its discretion may cancel the order placed on the selected bidder and/or forfeit the EMD after giving prior written notice to rectify the same.",
        "Authority at its discretion may cancel the order and forfeit the bid security deposit.",
        "If the contractor fails to deliver, the purchaser shall forfeit the performance guarantee."
    ]
    for text in buyer_remedies:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter buyer remedy: {text}"

    # 2. Buyer requirement notice / preamble rejected
    buyer_notices = [
        "a) OCAC will require the selected bidder to provide a Performance Bank Guarantee (PBG), within 30 days from the date of notification of award",
        "The Purchaser will require the selected vendor to furnish a security deposit."
    ]
    for text in buyer_notices:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter buyer requirement notice: {text}"

    # 3. Buyer standalone acceptance formats rejected
    acceptance_formats = [
        "c) Performance security shall be accepted in the form of Insurance Surety Bond, account payee demand draft, fixed deposit receipt, bank guarantee including e- Bank Guarantee from any of the scheduled commercial banks or payment online.",
        "Payment of tender fee shall be accepted in the form of demand draft or RTGS.",
        "For MSEs/Startups, the PBG shall be as per OGFR Guideline."
    ]
    for text in acceptance_formats:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter standalone acceptance format: {text}"

    # 4. Table row label stripping
    table_contaminated = "18 Bidder comply with State ICT Policy 2022, 11 Power of Attorney for Authorized Signatory The bidder shall submit Power of Attorney, duly authorizing the person signing the documents to sign on behalf of the bidder and thereby binding the bidder."
    cleaned_table = _clean_clause_text(table_contaminated)
    assert cleaned_table == "The bidder shall submit Power of Attorney, duly authorizing the person signing the documents to sign on behalf of the bidder and thereby binding the bidder."
    assert _is_non_requirement_heading_or_criterion(cleaned_table) is False

    # 5. Header / address / email prefix stripping
    contact_contaminated = "Plot No. N-1/7-D, Acharya Vihar RRL Post Office, Bhubaneswar Odisha - 751013 gm_ocac@ocac.in f) Submission of proposal The proposals must be submitted online in the portal enivida.odisha.gov.in. Submission of proposals in other forms or portal shall not be considered. For details on submission of proposal in e-Nivida portal. For details, please refer to Clause No. 6.5 of this document."
    cleaned_contact = _clean_clause_text(contact_contaminated)
    assert cleaned_contact == "The proposals must be submitted online in the portal enivida.odisha.gov.in. Submission of proposals in other forms or portal shall not be considered."
    assert _is_non_requirement_heading_or_criterion(cleaned_contact) is True

    contact_with_fee = "Plot No. N-1/7-D, Acharya Vihar RRL Post Office, Bhubaneswar Odisha - 751013 gm_ocac@ocac.in The bidder must furnish along with its bid required bid processing fee amounting to ₹ 11,800/- online."
    cleaned_fee = _clean_clause_text(contact_with_fee)
    assert cleaned_fee == "The bidder must furnish along with its bid required bid processing fee amounting to ₹ 11,800/- online."
    assert _is_non_requirement_heading_or_criterion(cleaned_fee) is False

    # 6. Cohesive multi-sentence genuine requirements preserved
    genuine_cohesive = [
        "The bidder must furnish along with its bid required bid processing fee amounting to ₹ 11,800/- inclusive of GST @ 18% online through e-Nivida portal through e- Payment Gateway /or in shape of DD in favor of Odisha Computer Application Centre (OCAC), drawn in any scheduled commercial bank and payable at Bhubaneswar failing which the bid will be rejected.",
        "Bidders shall submit, along with their Bids, EMD of Rs. 20,00,000/- (Rupees Twenty lakhs) in the shape of Bank Draft OR Bank Guarantee (in the format specified in this RFP) issued by any scheduled bank in favor of Odisha Computer Application Centre” payable at Bhubaneswar and should be valid for 90 days from the due date of the tender / RFP. The EMD should be submitted in the General Bid.",
        "The selected bidder shall furnish a PBG equivalent to 3% of the total project cost, valid for 20 months from the date of submission. For MSEs/Startups, the PBG shall be as per OGFR Guideline.",
        "The selected bidder shall be responsible for extending the validity date and claim period of the Performance Guarantee as and when it is due on account of non- completion of the service during the work order period."
    ]
    for text in genuine_cohesive:
        cleaned = _clean_clause_text(text)
        assert _is_non_requirement_heading_or_criterion(cleaned) is False, f"Erroneously filtered genuine cohesive requirement: {text}"


def test_buyer_communication_and_template_drafting_filtering():
    """
    Regression Test:
    1. Buyer/admin non-correspondence notices are filtered (not treated as bidder requirements).
    2. Section headings with angle brackets and placeholders are filtered from requirement clauses.
    3. Template drafting guidance and module listing lead-in notes are filtered.
    4. Genuine bidder and system obligations remain accepted and classified.
    """
    from app.agents.extractor_agent import _is_non_requirement_heading_or_criterion

    # 1. Buyer communication & non-correspondence disclaimers (FILTERED)
    buyer_notices = [
        "No individual correspondence will be made with the Bidder in this regard.",
        "No correspondence will be entertained in this regard.",
        "No separate correspondence will be made with unsuccessful bidders.",
        "In this regard no individual correspondence will be made.",
        "No further communication will be sent to unsuccessful applicants.",
        "No correspondence will be entered into regarding the selection results."
    ]
    for text in buyer_notices:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter buyer communication notice: {text}"

    # 2. Section headings with placeholders & bracketed variables (FILTERED)
    section_headings = [
        "3.13 Key Processes and Functional Requirement of proposed RCS- <State_Name> Portal",
        "4.2 Technical Architecture & Infrastructure for <Department_Name>",
        "SECTION 5: <Module_Name> Functional Specifications",
        "3.14 Proposed ICT Platform for <Client_Agency>"
    ]
    for text in section_headings:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter section heading with placeholder: {text}"

    # 3. Template drafting guidance & module listing lead-in notes (FILTERED)
    drafting_guidelines = [
        "Below mentioned modules needs to be prepared for COOPERATIVE SOCITIES and RCS- <State_Name> Office Registration Process (Please define/Change the registration process as per your State’s requirements Act(s) and Rules)",
        "(Please define/Change the registration process as per your State's requirements Act(s) and Rules)",
        "Below mentioned modules needs to be prepared for COOPERATIVE SOCITIES and RCS- <State_Name> Office",
        "This process outlines the steps for registering a Multi-District/Village Cooperative Society with the RCS- <State_Name> office through the RCS portal.",
        "<Define the new modules required for State integration as per Department rules>",
        "Please specify the required modules as per your state requirements Act(s) and Rules."
    ]
    for text in drafting_guidelines:
        assert _is_non_requirement_heading_or_criterion(text) is True, f"Failed to filter drafting guideline: {text}"

    # 4. Genuine bidder & system obligations (PRESERVED / ACCEPTED)
    genuine_obligations = [
        "The applicant must have valid and verified login credentials and the user account should not be associated with any registered society.",
        "The system will facilitate notification of status of application through SMS and email of applicant in automated mode.",
        "The successful bidder shall enter into an Agreement with the buyer within 15 days of being notified.",
        "The successful Bidder will be required to provide a Performance Bank Guarantee for an amount equivalent to 3% of the contract value.",
        "The vendor must provide access for report viewing by the designated officers.",
        "Integration with external platforms (like e-Office, UIDAI, BharatVC, SMS, Digital Signature, and others if required) shall be implemented."
    ]
    for text in genuine_obligations:
        assert _is_non_requirement_heading_or_criterion(text) is False, f"Erroneously filtered genuine obligation: {text}"


def test_rfp_pdf_with_template_placeholders_and_buyer_disclaimers_e2e():
    """
    End-to-End Regression Test:
    Generates a PDF containing section headers with placeholders, drafting guidance,
    buyer non-correspondence notices, and genuine requirements.
    Verifies that only genuine requirements are extracted and classified.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "test_template_rfp.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("TENDER DOCUMENT: E-GOVERNANCE PORTAL", styles['Heading1']),
            Paragraph("2.1 Administrative Rules", styles['Heading2']),
            Paragraph("The bids prepared by the bidder and all documents relating to the bids shall be in the English language.", styles['Normal']),
            Paragraph("No individual correspondence will be made with the Bidder in this regard.", styles['Normal']),
            Paragraph("3.13 Key Processes and Functional Requirement of proposed RCS- <State_Name> Portal", styles['Heading2']),
            Paragraph("Below mentioned modules needs to be prepared for COOPERATIVE SOCITIES and RCS- <State_Name> Office Registration Process (Please define/Change the registration process as per your State’s requirements Act(s) and Rules)", styles['Normal']),
            Paragraph("The applicant must have valid and verified login credentials and the user account should not be associated with any registered society.", styles['Normal']),
            Paragraph("The system will facilitate notification of status of application through SMS and email of applicant in automated mode.", styles['Normal']),
            Paragraph("All data transmissions shall be encrypted using TLS 1.3.", styles['Normal']),
            Paragraph("The vendor must provide 24x7 helpdesk support during the warranty period.", styles['Normal'])
        ]
        doc.build(story)

        state: RFPProposalState = {
            "rfp_id": "test_template_rfp",
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
        extracted_texts = [c["text"] if isinstance(c, dict) else c.text for c in raw_clauses]

        # Verify false positives are completely ABSENT
        for t in extracted_texts:
            assert "No individual correspondence" not in t, f"False positive buyer notice extracted: {t}"
            assert "3.13 Key Processes" not in t, f"False positive section heading extracted: {t}"
            assert "Below mentioned modules needs to be prepared" not in t, f"False positive drafting guidance extracted: {t}"

        # Verify genuine requirements ARE extracted
        assert any("English language" in t for t in extracted_texts), "Missing English language submission requirement"
        assert any("SMS and email" in t for t in extracted_texts), "Missing SMS/email notification requirement"
        assert any("TLS 1.3" in t for t in extracted_texts), "Missing TLS encryption requirement"
        assert any("24x7 helpdesk" in t for t in extracted_texts), "Missing helpdesk support requirement"

        # 2. Classification Phase
        state["raw_clauses"] = raw_clauses
        classify_result = classify_requirements_node(state)
        classified_reqs = classify_result["requirements"]

        assert len(classified_reqs) == 4
        for req in classified_reqs:
            assert req["req_code"].startswith("REQ-")
            assert req["category"] in ["Technical", "Contractual", "Delivery", "Administrative", "Submission", "Commercial"]
