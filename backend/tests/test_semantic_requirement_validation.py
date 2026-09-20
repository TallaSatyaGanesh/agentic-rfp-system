import pytest
from app.agents.extractor_agent import _is_non_requirement_heading_or_criterion, extract_rfp_node
from app.agents.classifier_agent import _determine_category, _determine_mandatory, classify_requirements_node
from app.agents.state import RFPProposalState


def test_genuine_vendor_system_obligations_accepted():
    """Validates that genuine vendor/system obligations are accepted."""
    vendor_obligations = [
        "The vendor shall provide 24x7 monitoring and incident resolution services.",
        "The system shall support RESTful API integration with OAuth 2.0 authentication.",
        "The Service Provider must maintain 99.9% uptime SLA across all primary regions.",
        "The platform must support automated daily database backups with 30-day retention.",
        "The contractor shall submit monthly SLA performance reports to the authority.",
        "The application will facilitate real-time telemetry processing and anomaly alerting.",
        "The bidder must conduct hands-on training workshops for technical staff.",
        "The vendor is required to implement end-to-end data encryption at rest using AES-256.",
        "The Service Provider shall hand over all database dumps and system manuals upon contract expiry."
    ]
    for clause in vendor_obligations:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected '{clause}' to be accepted as a requirement."


def test_buyer_responsibilities_rejected():
    """Validates that buyer/client internal responsibilities and actions are rejected."""
    buyer_clauses = [
        "The RCS Office must include the requirements of the other schemes as part of the RFP.",
        "The RCS <State_Name> shall also nominate the Nodal officer for coordinating the project.",
        "RCS will take up the optimization of cloud resources post-implementation.",
        "RCS shall have the right to retain the performance bank guarantee in case of dispute.",
        "RCS shall make payments to the Service Provider within 30 days of invoice receipt.",
        "The Department will review and approve the submitted test reports within two weeks.",
        "The Buyer shall provide office space and network connectivity for on-site personnel.",
        "RCS will not make any payment for data migration activities.",
        "Client shall designate a single point of contact for project escalation."
    ]
    for clause in buyer_clauses:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected buyer clause '{clause}' to be rejected."


def test_objectives_and_context_rejected():
    """Validates that pure background narrative and strategic objectives are rejected."""
    context_clauses = [
        "Following strategic objectives will be achieved through this modernization initiative.",
        "The above solution is designed with flexibility to adapt to future technological trends.",
        "The vision of this program is to achieve digital empowerment across all administrative blocks.",
        "This project aims at establishing a robust digital backbone for cooperative institutions.",
        "Over the years, the department has undertaken various IT enablement programs.",
        "First six months period will come under D3 implementation phase."
    ]
    for clause in context_clauses:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected context/objective clause '{clause}' to be rejected."


def test_template_placeholders_and_drafting_instructions_rejected():
    """Validates that placeholder drafting instructions and template formats are rejected."""
    placeholder_clauses = [
        "<Define the new modules required for the state cooperative society platform>",
        "(Sample Format – To be executed on a non-judicial stamped paper of appropriate value)",
        "<Insert Bidder Company Name, Registered Address, and CIN Number Here>",
        "[Please attach certified copy of Board Resolution / Power of Attorney]",
        "WHEREAS We, the undersigned Bidder, having read and examined the tender...",
        "<Specify details of past projects executed in the last 3 fiscal years>"
    ]
    for clause in placeholder_clauses:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected placeholder instruction '{clause}' to be rejected."


def test_form_and_signature_artifacts_rejected():
    """Validates that form artifacts, signature blocks, and tabular column labels are rejected."""
    form_artifacts = [
        "Date Signature of Authorized Signatory Place Name and Designation",
        "Place: New Delhi Date: 12-04-2024 Signature of Tenderer with Seal",
        "Sl. No. Parameter Minimum Specification Bidder Compliance (Yes/No) Remarks",
        "Name of the Authorized Signatory: Designation: Contact Number: Email Address:",
        "Authorized Signatory [In the capacity of duly authorized to sign bid]"
    ]
    for clause in form_artifacts:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected form artifact '{clause}' to be rejected."


def test_end_user_manual_steps_vs_system_capabilities():
    """Validates filtering of end-user manual steps while preserving system functionality."""
    # Manual end-user workflow steps
    manual_steps = [
        "Click on the submit button to download the generated PDF acknowledgment receipt.",
        "Select the appropriate branch code from the dropdown list and click next.",
        "User clicks the login icon and enters credentials on the portal screen."
    ]
    for step in manual_steps:
        assert _is_non_requirement_heading_or_criterion(step), f"Expected manual step '{step}' to be rejected."

    # Underlying system capabilities (must be accepted)
    system_capabilities = [
        "The system shall generate downloadable PDF acknowledgment receipts upon transaction submission.",
        "The application must provide dropdown filtering of branch codes for reporting modules.",
        "The platform must enforce two-factor authentication during administrative user login."
    ]
    for cap in system_capabilities:
        assert not _is_non_requirement_heading_or_criterion(cap), f"Expected capability '{cap}' to be accepted."


def test_paired_buyer_disclaimer_vs_vendor_warranty():
    """Validates exclusion of buyer informational disclaimers while preserving genuine vendor warranties."""
    # Negative examples (must be excluded)
    disclaimers = [
        "The Client does not make any representation or warranty as to the accuracy, reliability or completeness of this RFP.",
        "RCS accepts no liability for any loss or damage arising from any inaccuracy in this tender document.",
        "Neither the department nor its employees make any warranty or representation regarding this solicitation.",
        "The authority disclaims all warranties regarding the completeness of the project information."
    ]
    for clause in disclaimers:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected disclaimer '{clause}' to be rejected."

    # Positive examples (must remain)
    vendor_warranties = [
        "The vendor shall warrant that the supplied software application is free from defects, vulnerabilities, and malware for 12 months.",
        "The contractor shall provide warranty support and fix all severity-1 defects within 4 hours.",
        "The Service Provider warrants that the platform complies with all statutory data privacy laws."
    ]
    for clause in vendor_warranties:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor warranty '{clause}' to be accepted."


def test_paired_recipient_investigation_vs_vendor_assessment_deliverable():
    """Validates exclusion of recipient due diligence preambles while preserving genuine vendor assessments/deliverables."""
    # Negative examples (must be excluded)
    recipient_advisories = [
        "Each recipient must conduct its own independent investigation and analysis of the information contained in this RFP.",
        "Recipients should verify the accuracy, reliability and completeness of the RFP data before submitting a response.",
        "Prospective bidders are advised to make their own inquiries regarding site conditions and local regulations."
    ]
    for clause in recipient_advisories:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected recipient advisory '{clause}' to be rejected."

    # Positive examples (must remain)
    vendor_assessments = [
        "The contractor must conduct an initial infrastructure assessment and submit a gap analysis report within 30 days.",
        "The vendor shall carry out security vulnerability assessments on the deployed portal on a quarterly basis.",
        "The Service Provider is required to perform database performance tuning and submit monthly optimization reports."
    ]
    for clause in vendor_assessments:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor assessment '{clause}' to be accepted."


def test_paired_preliminary_examination_vs_vendor_audit_cooperation():
    """Validates exclusion of committee examination procedures while preserving vendor audit obligations."""
    # Negative examples (must be excluded)
    committee_actions = [
        "Preliminary examination of bids will be conducted by the RCS to determine whether bids are complete and responsive.",
        "The duly constituted Evaluation Committee will evaluate technical proposals vis-à-vis tender compliance.",
        "Tender scrutiny committee will examine the technical bids on the opening date to ensure all documents are present."
    ]
    for clause in committee_actions:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected committee action '{clause}' to be rejected."

    # Positive examples (must remain)
    vendor_audits = [
        "The vendor shall allow technical audits and preliminary inspection of the system architecture by the designated authority.",
        "The Service Provider shall facilitate compliance audits and provide access to system logs upon request.",
        "The contractor must cooperate with the third-party security auditor during quarterly vulnerability scans."
    ]
    for clause in vendor_audits:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor audit '{clause}' to be accepted."


def test_paired_selection_outcome_vs_vendor_eligibility_criteria():
    """Validates exclusion of selection outcomes/rejections while preserving vendor eligibility criteria."""
    # Negative examples (must be excluded)
    selection_outcomes = [
        "Only one bidder will be selected for the desired job based on the highest combined score.",
        "The bid will be rejected outright by the RCS if the information provided is found to be incorrect or incomplete.",
        "Single bidder will be selected for the work upon commercial evaluation."
    ]
    for clause in selection_outcomes:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected selection outcome '{clause}' to be rejected."

    # Positive examples (must remain)
    eligibility_criteria = [
        "The bidder must be a registered legal entity with minimum 5 years of experience in enterprise software development.",
        "The bidder must submit an undertaking that the company has not been blacklisted or debarred by any government department.",
        "The vendor must possess an active CMMI Level 3 or higher certification at the time of bid submission."
    ]
    for clause in eligibility_criteria:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected eligibility criterion '{clause}' to be accepted."


def test_paired_scoring_formula_vs_vendor_performance_metric():
    """Validates exclusion of QCBS scoring formulas while preserving vendor SLA/performance metrics."""
    # Negative examples (must be excluded)
    scoring_formulas = [
        "The proposal with the lowest cost will be given a financial score of 100 with proportional scores to other bidders.",
        "Proposals will be ranked as H-1, H-2 based on combined quality and cost score under QCBS 70:30 methodology.",
        "Proposals with the highest technical marks shall be given a score of 100.",
        "Technical proposals scoring less than 70% marks will be rejected."
    ]
    for clause in scoring_formulas:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected scoring formula '{clause}' to be rejected."

    # Positive examples (must remain)
    performance_metrics = [
        "The vendor must achieve a minimum customer satisfaction score of 90% across quarterly support reviews.",
        "The platform shall support benchmark testing achieving a score of at least 5000 transactions per second.",
        "The Service Provider must maintain 99.95% API availability measured on a monthly basis."
    ]
    for clause in performance_metrics:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected performance metric '{clause}' to be accepted."


def test_paired_prebid_meeting_vs_vendor_progress_meeting_obligation():
    """Validates exclusion of pre-bid meeting logistics while preserving vendor progress meeting obligations."""
    # Negative examples (must be excluded)
    prebid_logistics = [
        "Pre-Bid Conference shall be scheduled on the date and time specified in the Time Schedule.",
        "Pre-bid meeting will be virtual and any change in schedule shall be notified through email.",
        "Queries received after the due date for pre-bid clarifications will not be entertained."
    ]
    for clause in prebid_logistics:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected prebid logistics '{clause}' to be rejected."

    # Positive examples (must remain)
    vendor_meetings = [
        "The vendor shall participate in weekly project progress review meetings and submit minutes within 24 hours.",
        "The project manager nominated by the contractor shall attend monthly steering committee review sessions.",
        "The Service Provider must conduct quarterly executive governance meetings to review SLA performance."
    ]
    for clause in vendor_meetings:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor meeting '{clause}' to be accepted."


def test_semantic_category_determination():
    """Validates that requirements are classified into the accurate semantic categories."""
    category_cases = [
        # Certification
        ("The vendor must maintain active ISO 27001 and SOC 2 Type II certifications.", "Certification"),
        ("The cloud infrastructure must be hosted in a Tier-III CERT-In empanelled datacenter.", "Certification"),
        # Contractual
        ("The Service Provider shall indemnify the authority against any third-party IP infringement claims.", "Contractual"),
        ("Liquidated damages of 0.5% per week of delay shall apply up to a maximum of 10% of contract value.", "Contractual"),
        ("The bidder must submit a Performance Bank Guarantee (PBG) equivalent to 5% of contract value.", "Contractual"),
        # Commercial
        ("Data migration from legacy systems shall be performed at no additional cost to the client.", "Commercial"),
        ("Payments shall be processed on a pro-rata milestone basis upon verification of deliverables.", "Commercial"),
        ("The financial quote must include all applicable taxes, levies, and operational expenses in INR.", "Commercial"),
        # Delivery
        ("The vendor shall conduct comprehensive classroom and hands-on training for 50 administrative users.", "Delivery"),
        ("Complete platform deployment and UAT signoff must be concluded within 16 weeks of contract signing.", "Delivery"),
        # Documentation
        ("The vendor must deliver weekly status reports, monthly SLA compliance dashboards, and user manuals.", "Documentation"),
        ("Documented RESTful API specifications and database schema runbooks must be submitted prior to go-live.", "Documentation"),
        # Submission (including portal upload and submission routes)
        ("Bids must be submitted electronically through the e-procurement portal before the submission deadline.", "Submission"),
        ("Bid shall be submitted on email shared by the RCS office.", "Submission"),
        ("The bidder shall upload the technical and commercial bid on GeM before the closing time.", "Submission"),
        # Eligibility (including corporate standing, legal registration, vintage, net worth)
        ("The bidder must have an average annual turnover of at least 50 Crores over the last 3 financial years.", "Eligibility"),
        ("The bidder must have successfully executed at least 3 similar enterprise cloud migration projects.", "Eligibility"),
        ("The bidder must be a company registered in India under Indian Companies Act 1956 or 2013.", "Eligibility"),
        ("The bidder should have been in operation for at least 7 years in IT consulting.", "Eligibility"),
        ("The Bidder should have a positive net worth in the last financial year.", "Eligibility"),
        # Administrative
        ("The proposal must include the name, official address, GST registration, and PAN of the authorized signatory.", "Administrative"),
        # Technical
        ("The database shall support active-active clustering with automated failover and zero data loss.", "Technical"),
        ("The system shall enforce role-based access control (RBAC) with granular permission sets.", "Technical")
    ]

    for clause, expected_cat in category_cases:
        cat, rationale = _determine_category(clause, "General")
        assert cat == expected_cat, f"Expected category '{expected_cat}' for '{clause}', got '{cat}' (Rationale: {rationale})"


def test_mandatory_vs_optional_modal_parsing():
    """Validates mandatory vs optional extraction strictly based on modal keywords."""
    # Mandatory cases
    m_cases = [
        "The vendor shall provide 24x7 support.",
        "The system must enforce encryption at rest.",
        "Database replication is mandatory for high availability.",
        "The contractor undertakes to maintain audit logs."
    ]
    for text in m_cases:
        is_m, prio, conf, reason = _determine_mandatory(text)
        assert is_m is True
        assert prio == "High"
        assert conf > 0.5

    # Optional cases
    o_cases = [
        "The application should support dark mode theme.",
        "Automated report generation via email is preferable.",
        "The bidder may provide additional staging environments."
    ]
    for text in o_cases:
        is_m, prio, conf, reason = _determine_mandatory(text)
        assert is_m is False
        assert prio == "Low"

    # Ambiguous / non-modal cases
    ambiguous_cases = [
        "Database cluster configuration with PostgreSQL 15.",
        "Weekly meetings with the project steering committee."
    ]
    for text in ambiguous_cases:
        is_m, prio, conf, reason = _determine_mandatory(text)
        assert is_m is False
        assert conf == 0.0
