import pytest
from app.agents.extractor_agent import _is_non_requirement_heading_or_criterion, _clean_clause_text
from app.agents.classifier_agent import _determine_category, _determine_mandatory


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
        "The Service Provider shall hand over all database dumps and system manuals upon contract expiry.",
        "The system will facilitate notification of status of application through SMS and email of applicant in automated mode.",
        "Separate role based secured Login with 2FA will be provided to all the Stakeholders.",
        "The RCS web portal/Web Application will have all the modules as per the requirements of the office.",
        "Audit Trail Application will allow the admin users to track all activities, manage log files and create audit trail reports.",
        "Service provider shall provide the Server Administration service to keep servers stable, reliable and their operation efficient."
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
        "<Specify details of past projects executed in the last 3 fiscal years>",
        "Appeals <Mention the other additional module required to be developed as per your States Requirement> 40% of the total bid value"
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
    manual_steps = [
        "Click on the submit button to download the generated PDF acknowledgment receipt.",
        "Select the appropriate branch code from the dropdown list and click next.",
        "User clicks the login icon and enters credentials on the portal screen.",
        "User will be registered himself by filling his basic details in registration form",
        "Registration form will forward to department",
        "After approval, User id and password will be generated and shared on registered mail id and mobile number",
        "If both password match, password will be changed",
        "If the society wants to raise a request for sales officer for society, then same will be requested from the application.",
        "Concerning officer will accept and issue the order related to the request raised",
        "Society will fill the request for the conduction of election",
        "Concerning officer will be able to view the details of request raised.",
        "The COOPERATIVE SOCITIES must also conduct an Annual General Meeting before filing the annual return.",
        "25 | P a g e Annual Return Filing The process for filing annual returns for a COOPERATIVE SOCITIES through the portal involves representative logging in..."
    ]
    for step in manual_steps:
        assert _is_non_requirement_heading_or_criterion(step), f"Expected manual step '{step}' to be rejected."

    system_capabilities = [
        "The system shall generate downloadable PDF acknowledgment receipts upon transaction submission.",
        "The application must provide dropdown filtering of branch codes for reporting modules.",
        "The platform must enforce two-factor authentication during administrative user login.",
        "The system will facilitate notification of status of application through SMS and email of applicant in automated mode.",
        "Separate role based secured Login with 2FA will be provided to all the Stakeholders.",
        "System will have provision to retrieve password.",
        "Audit Trail Application will allow the admin users to track all activities, manage log files and create audit trail reports.",
        "The portal will be responsive and be able to successfully render over major web browsers on desktop, laptop and mobile."
    ]
    for cap in system_capabilities:
        assert not _is_non_requirement_heading_or_criterion(cap), f"Expected capability '{cap}' to be accepted."


def test_paired_buyer_disclaimer_vs_vendor_warranty():
    """Validates exclusion of buyer informational disclaimers while preserving genuine vendor warranties."""
    disclaimers = [
        "The Client does not make any representation or warranty as to the accuracy, reliability or completeness of this RFP.",
        "RCS accepts no liability for any loss or damage arising from any inaccuracy in this tender document.",
        "Neither the department nor its employees make any warranty or representation regarding this solicitation.",
        "The authority disclaims all warranties regarding the completeness of the project information.",
        "Subject to any law to the contrary, and to the maximum extent permitted by law, RCS-<State_Name> and its officers, employees, contractors, agents, and advisers disclaim all liability from any loss or damage.",
        "No binding legal relationship will exist between any of the bidders and RCS-<State_Name> until the issues of purchase order.",
        "On completion of the Contract, the security deposit amount will be refunded to the Contractor without interest."
    ]
    for clause in disclaimers:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected disclaimer '{clause}' to be rejected."

    vendor_warranties = [
        "The vendor shall warrant that the supplied software application is free from defects, vulnerabilities, and malware for 12 months.",
        "The contractor shall provide warranty support and fix all severity-1 defects within 4 hours.",
        "The Service Provider warrants that the platform complies with all statutory data privacy laws.",
        "The Vendor shall warrant and assume full liability for any data loss or system corruption caused by its software."
    ]
    for clause in vendor_warranties:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor warranty '{clause}' to be accepted."


def test_paired_recipient_investigation_vs_vendor_assessment_deliverable():
    """Validates exclusion of recipient due diligence preambles while preserving genuine vendor assessments/deliverables."""
    recipient_advisories = [
        "Each recipient must conduct its own independent investigation and analysis of the information contained in this RFP.",
        "Recipients should verify the accuracy, reliability and completeness of the RFP data before submitting a response.",
        "Prospective bidders are advised to make their own inquiries regarding site conditions and local regulations.",
        "Recipient will, by responding to RCS-<State_Name> for RFP, be deemed to have accepted the terms as stated in this RFP."
    ]
    for clause in recipient_advisories:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected recipient advisory '{clause}' to be rejected."

    vendor_assessments = [
        "The contractor must conduct an initial infrastructure assessment and submit a gap analysis report within 30 days.",
        "The vendor shall carry out security vulnerability assessments on the deployed portal on a quarterly basis.",
        "The Service Provider is required to perform database performance tuning and submit monthly optimization reports."
    ]
    for clause in vendor_assessments:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor assessment '{clause}' to be accepted."


def test_paired_preliminary_examination_vs_vendor_audit_cooperation():
    """Validates exclusion of committee examination procedures while preserving vendor audit obligations."""
    committee_actions = [
        "Preliminary examination of bids will be conducted by the RCS to determine whether bids are complete and responsive.",
        "The duly constituted Evaluation Committee will evaluate technical proposals vis-à-vis tender compliance.",
        "Tender scrutiny committee will examine the technical bids on the opening date to ensure all documents are present.",
        "RCS-<State_Name>/Committee will examine the Bids to determine whether they are complete, the documents have been properly signed.",
        "Prior to the detailed evaluation, RCS-<State_Name>/Committee will determine the substantial responsiveness of each Bid to the Bidding document.",
        "If a Bid is not substantially responsive, it will be rejected by RCS-<State_Name>/Committee and may not subsequently be made responsive.",
        "Prior to the expiration of the period of bid validity, the RCS-<State_Name> will notify the successful Bidder in writing that its bid has been accepted.",
        "The notification of award will constitute the formation of the Contract"
    ]
    for clause in committee_actions:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected committee action '{clause}' to be rejected."

    vendor_audits = [
        "The vendor shall allow technical audits and preliminary inspection of the system architecture by the designated authority.",
        "The Service Provider shall facilitate compliance audits and provide access to system logs upon request.",
        "The contractor must cooperate with the third-party security auditor during quarterly vulnerability scans.",
        "The Contractor shall examine all system server logs daily and remediate detected security anomalies.",
        "The Vendor will notify the client project manager within 15 minutes of any critical system outage."
    ]
    for clause in vendor_audits:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor audit '{clause}' to be accepted."


def test_paired_selection_outcome_vs_vendor_eligibility_criteria():
    """Validates exclusion of selection outcomes/rejections while preserving vendor eligibility criteria."""
    selection_outcomes = [
        "Only one bidder will be selected for the desired job based on the highest combined score.",
        "The bid will be rejected outright by the RCS if the information provided is found to be incorrect or incomplete.",
        "Single bidder will be selected for the work upon commercial evaluation.",
        "Incomplete bids will be rejected outright.",
        "The Bidder is expected to examine all instructions, forms, terms and specifications in the Bidding Document.",
        "Failure to furnish all information required by the Bidding Document or to submit a Bid not substantially responsive will be at the Bidder's risk."
    ]
    for clause in selection_outcomes:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected selection outcome '{clause}' to be rejected."

    eligibility_criteria = [
        "The bidder must be a registered legal entity with minimum 5 years of experience in enterprise software development.",
        "The bidder must submit an undertaking that the company has not been blacklisted or debarred by any government department.",
        "The vendor must possess an active CMMI Level 3 or higher certification at the time of bid submission."
    ]
    for clause in eligibility_criteria:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected eligibility criterion '{clause}' to be accepted."


def test_paired_scoring_formula_vs_vendor_performance_metric():
    """Validates exclusion of QCBS scoring formulas while preserving vendor SLA/performance metrics."""
    scoring_formulas = [
        "The proposal with the lowest cost will be given a financial score of 100 with proportional scores to other bidders.",
        "Proposals will be ranked as H-1, H-2 based on combined quality and cost score under QCBS 70:30 methodology.",
        "Proposals with the highest technical marks shall be given a score of 100.",
        "Technical proposals scoring less than 70% marks will be rejected.",
        "Similarly, proposals with the highest technical marks (as allotted by the evaluation committee) shall be given a score of 100 (Hundred) and other proposals be given technical scores that are proportional to their marks.",
        "The proposal securing the highest combined marks and ranked H-1 will be invited for negotiations, if required and shall be recommended for award of contract.",
        "The Evaluated Bid Score (B) will be calculated for each responsive Bid using the following formula, which permits a comprehensive assessment.",
        "Financial proposal, as per the details in Annexure – III, of technically qualified bidders will be opened and evaluated.",
        "On the basis of the combined weighted score for quality and cost, the bidder shall be ranked in terms of the total score obtained.",
        "In the case of a single technically qualified bidder, financial proposal of that bidder only will be evaluated, and work may be assigned to that vendor after due negotiation.",
        "15 | P a g e will be H-1."
    ]
    for clause in scoring_formulas:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected scoring formula '{clause}' to be rejected."

    performance_metrics = [
        "The vendor must achieve a minimum customer satisfaction score of 90% across quarterly support reviews.",
        "The platform shall support benchmark testing achieving a score of at least 5000 transactions per second.",
        "The Service Provider must maintain 99.95% API availability measured on a monthly basis.",
        "The application shall maintain an automated performance benchmark score of at least 95 under full user load."
    ]
    for clause in performance_metrics:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected performance metric '{clause}' to be accepted."


def test_paired_prebid_meeting_vs_vendor_progress_meeting_obligation():
    """Validates exclusion of pre-bid meeting logistics while preserving vendor progress meeting obligations."""
    prebid_logistics = [
        "Pre-Bid Conference shall be scheduled on the date and time specified in the Time Schedule.",
        "Pre-bid meeting will be virtual and any change in schedule shall be notified through email.",
        "In case of any change in the schedule of the Pre-Bid conference, the changed schedule shall be notified of through email.",
        "Queries received after the due date for pre-bid clarifications will not be entertained.",
        "The queries must be submitted in Microsoft Excel format as follows Sr. Clause No. Page number Existing Provision Clarification to be Sought Name of Bidder",
        "During the Pre-Bid conferences, the Bidders will be free to seek clarifications and make suggestions for consideration of the RCS.",
        "The point/s, not finding place in C.S.D. issued after the Pre-Bid Conference, is/or deemed to have been rejected by the RCS."
    ]
    for clause in prebid_logistics:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected prebid logistics '{clause}' to be rejected."

    vendor_meetings = [
        "The vendor shall participate in weekly project progress review meetings and submit minutes within 24 hours.",
        "The project manager nominated by the contractor shall attend monthly steering committee review sessions.",
        "The Service Provider must conduct quarterly executive governance meetings to review SLA performance.",
        "The Service Provider shall deliver all milestone progress reports via email on the first Monday of each month."
    ]
    for clause in vendor_meetings:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor meeting '{clause}' to be accepted."


def test_semantic_category_determination():
    """Validates that requirements are classified into the accurate semantic categories."""
    category_cases = [
        # Certification
        ("The vendor must maintain active ISO 27001 and SOC 2 Type II certifications.", "Certification"),
        ("The cloud infrastructure must be hosted in a Tier-III CERT-In empanelled datacenter.", "Certification"),
        ("The Bidder must have a valid certificate of CMMI Level 5 (In Development).", "Certification"),
        # Contractual
        ("The Service Provider shall indemnify the authority against any third-party IP infringement claims.", "Contractual"),
        ("Liquidated damages of 0.5% per week of delay shall apply up to a maximum of 10% of contract value.", "Contractual"),
        ("The bidder must submit a Performance Bank Guarantee (PBG) equivalent to 5% of contract value.", "Contractual"),
        ("Warranty Support of ONE Year after successful completion and GO LIVE of application", "Contractual"),
        ("The successful bidder shall enter into an Agreement with the RCS-<State_Name>, in the format prescribed, within 15 days of being notified to do so.", "Contractual"),
        ("The Bidder shall be deemed to have complied with all clauses & Annexures in the RFP document under all sections.", "Contractual"),
        ("The Service Provider shall be legally bound to hand over all the project related documents, data and information upon exit.", "Contractual"),
        ("Providing support throughout the period of Development, Warranty & O&M period.", "Contractual"),
        # Commercial
        ("Data migration from legacy systems shall be performed at no additional cost to the client.", "Commercial"),
        ("Payments shall be processed on a pro-rata milestone basis upon verification of deliverables.", "Commercial"),
        ("The financial quote must include all applicable taxes, levies, and operational expenses in INR.", "Commercial"),
        ("The Commercial bid shall be on a fixed price basis, inclusive of all taxes and levies at site.", "Commercial"),
        ("Payment for any broken period shall be made on a pro- rata basis.", "Commercial"),
        ("All upward revisions of specifications shall be carried out within the lump sum contract price without any impact to the client.", "Commercial"),
        # Delivery
        ("The vendor shall conduct comprehensive classroom and hands-on training for 50 administrative users.", "Delivery"),
        ("Complete platform deployment and UAT signoff must be concluded within 16 weeks of contract signing.", "Delivery"),
        ("The System Integrator will also provide the training/handholding to all the stakeholders.", "Delivery"),
        ("The SI shall also be responsible to provide helpdesk support for the smooth rollout/implementation.", "Delivery"),
        ("The successful bidder shall nominate a Project manager for the entire period of the contract.", "Delivery"),
        ("Successful bidder shall submit a detailed project implementation plan and clearly spell out important milestones of project immediately after the award of work.", "Delivery"),
        ("Total project development duration should not exceed 3 months from the date of contract signing.", "Delivery"),
        # Documentation
        ("The vendor must deliver weekly status reports, monthly SLA compliance dashboards, and user manuals.", "Documentation"),
        ("Documented RESTful API specifications and database schema runbooks must be submitted prior to go-live.", "Documentation"),
        ("An Availability and Performance Report will be provided by the vendor on monthly basis.", "Documentation"),
        # Submission
        ("Bids must be submitted electronically through the e-procurement portal before the submission deadline.", "Submission"),
        ("Bid shall be submitted on email shared by the RCS office.", "Submission"),
        ("The bidder shall upload the technical and commercial bid on GeM before the closing time.", "Submission"),
        ("Both the proposals must be submitted in separate password protected files (PDF and ZIP) to the email:", "Submission"),
        ("The bids prepared by the bidder and all correspondence shall be in the English language.", "Submission"),
        ("There should be no handwritten material, corrections or alterations in the offer.", "Submission"),
        ("In case terms and conditions are not acceptable, the bidder should clearly specify deviation in Technical Bid with Form - Statement of Deviations from Bid Terms and conditions.", "Submission"),
        ("All bidders need to comply with Terms and Conditions and provide necessary documentation/proof to support the credentials.", "Submission"),
        ("Bids of only those Bidders who quote for the complete Scope of Work and Supply of Goods/Services shall be considered.", "Submission"),
        ("The information provided by the Bidder must be true and correct", "Submission"),
        # Eligibility
        ("The bidder must have an average annual turnover of at least 50 Crores over the last 3 financial years.", "Eligibility"),
        ("The bidder must have successfully executed at least 3 similar enterprise cloud migration projects.", "Eligibility"),
        ("The bidder must be a company registered in India under Indian Companies Act 1956 or 2013.", "Eligibility"),
        ("The bidder should have been in operation for at least 7 years in IT consulting.", "Eligibility"),
        ("The bidder should have been in operation for a period of at least 7 (Seven) years in India at the date of submission of bid.", "Eligibility"),
        ("The Bidder must have experience of Design, Development, implementation / Support and Maintenance of e-governance project with any Government (Central /State/ PSU) department in India during the last Five years as on bid submission date with minimum TWO project worth at-least INR 1 crore each and FOUR Projects each of value 50 Lakh or more.", "Eligibility"),
        ("The Bidder should have a positive net worth in the last financial year.", "Eligibility"),
        ("The Bidder should have a positive net worth in the last financial year as evidenced by the audited accounts of the company and should be profitable for each of the last three years.", "Eligibility"),
        # Administrative
        ("The proposal must include the name, official address, GST registration, and PAN of the authorized signatory.", "Administrative"),
        # Technical
        ("The database shall support active-active clustering with automated failover and zero data loss.", "Technical"),
        ("The system shall enforce role-based access control (RBAC) with granular permission sets.", "Technical"),
        ("The RCS Portal/ database will be linked with the National Cooperative Database (NCD) for real time updation.", "Technical"),
        ("Reports should also be available as On-Screen Reports with the capability of exporting it to any user defined format such as word, excel pdf, etc. & print and email feature.", "Technical")
    ]

    for clause, expected_cat in category_cases:
        cat, rationale = _determine_category(clause, "General")
        assert cat == expected_cat, f"Expected category '{expected_cat}' for '{clause}', got '{cat}' (Rationale: {rationale})"


def test_paired_section_leadin_vs_genuine_requirement_with_leadin_phrase():
    """Validates exclusion of structural lead-ins while preserving genuine requirements containing lead-in phrases."""
    lead_ins = [
        "Following are the deliverables which will be responsibilities of successful vendor.",
        "The service provider is expected to provide the Server Administration & Management services as follows",
        "The deliverables and payment milestones are as below.",
        "The purpose of this Service Level Requirements/agreement (hereinafter referred to as SLA) is to clearly define the levels of service which shall be provided by the vendor to the authority."
    ]
    for clause in lead_ins:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected structural lead-in '{clause}' to be rejected."

    genuine_requirements = [
        "The service provider shall provide 24x7 Server Administration service to keep servers stable, reliable and their operation efficient.",
        "Total project development duration should not exceed 3 months from the date of contract signing.",
        "The vendor shall maintain minimum 99.5% monthly application uptime as defined in the SLA parameters.",
        "The contractor shall deliver the software modules as below within 90 days of work order."
    ]
    for clause in genuine_requirements:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected genuine requirement '{clause}' to be accepted."


def test_paired_template_placeholders_vs_genuine_portal_instructions():
    """Validates exclusion of template drafting guidance while preserving genuine bidder instructions."""
    template_placeholders = [
        "For other procurement methods – The respective States need to define the Bid submission process here.",
        "Bidder should enclose all documents as the terms and conditions given in the Bid document <States need to give the details of the procurement process here>",
        "Bid shall be submitted the Bid on < details of procurement portal>",
        "Bidder should enclose all documents as per NICSI norms OR Procedure & Submission of Bid (GEM)",
        "Bid shall be submitted the Bid on GeM"
    ]
    for clause in template_placeholders:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected template placeholder '{clause}' to be rejected."

    genuine_instructions = [
        "The bidder shall submit the techno-financial proposal to the designated authority email address.",
        "Bidders must submit proof of all the credentials as required for evaluation of eligibility criteria.",
        "The bidder should enclose all compliance against each annexure in technical bid."
    ]
    for clause in genuine_instructions:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected genuine instruction '{clause}' to be accepted."


def test_paired_generic_form_filling_vs_genuine_form_system_specs():
    """Validates exclusion of generic form-filling template prompts while preserving genuine form/system capabilities."""
    generic_prompts = [
        "Technical details must be filled in.",
        "Correct technical information about the product and services being offered must be filled in.",
        "Responses must be filled in by the applicant."
    ]
    for clause in generic_prompts:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected generic form filling prompt '{clause}' to be rejected."

    genuine_form_specs = [
        "The system shall provide a configurable form builder supporting text, date, and dropdown fields.",
        "The platform must validate all mandatory form fields before submission.",
        "Dynamic form templates shall be maintainable by administrator users without system re-compilation."
    ]
    for clause in genuine_form_specs:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected genuine form requirement '{clause}' to be accepted."


def test_paired_vague_ui_narrative_vs_genuine_dynamic_form_generation():
    """Validates exclusion of vague UI field display statements while preserving dynamic form generation/logic capabilities."""
    vague_narratives = [
        "The system will display relevant fields in the form.",
        "The portal will display relevant fields in the form."
    ]
    for clause in vague_narratives:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected vague UI narrative '{clause}' to be rejected."

    genuine_ui_capabilities = [
        "The system shall dynamically generate form fields based on the selected applicant category and role.",
        "The system will display real-time dashboard analytics with interactive drill-down charts.",
        "The web portal will display encrypted audit trail logs to authorized compliance officers."
    ]
    for clause in genuine_ui_capabilities:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected genuine UI capability '{clause}' to be accepted."


def test_paired_prebid_query_deadline_vs_vendor_support_query_sla():
    """Validates exclusion of buyer pre-bid clarification query deadlines while preserving vendor support/query SLAs."""
    prebid_deadlines = [
        "The queries must reach the RCS-<State_Name> before “Last date for submission of written queries for clarifications on RFP document” as specified in the Time Schedule.",
        "Queries must reach the procuring entity before the last date for submission of queries.",
        "Written clarifications must reach the client before the last date for submission of written queries."
    ]
    for clause in prebid_deadlines:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected pre-bid clarification deadline '{clause}' to be rejected."

    vendor_query_slas = [
        "The vendor shall respond to all technical support queries within 2 hours of receipt.",
        "The helpdesk shall resolve high priority queries within 4 hours.",
        "The service provider must maintain an issue and query resolution log updated in real-time."
    ]
    for clause in vendor_query_slas:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor query SLA '{clause}' to be accepted."


def test_deduplication_and_supplementary_sentence_stitching():
    """Validates robust semantic deduplication and short supplementary delivery sentence stitching."""
    from app.agents.extractor_agent import _normalize_clause_sig, _stitch_blocks
    from app.services.document_parser import ExtractedBlock

    # 1. Deduplication signature test
    sig1 = _normalize_clause_sig("Bidder should enclose all compliance against each annexure in technical bid")
    sig2 = _normalize_clause_sig("The bidder should enclose all compliance against each annexure in technical bid.")
    assert sig1 == sig2, f"Expected normalized signatures to match: '{sig1}' vs '{sig2}'"

    # 2. Supplementary delivery sentence stitching
    b1 = ExtractedBlock(
        text="During UAT or after Go-Live training shall be provided by vendor to RCS-<State_Name>.",
        page_number=33,
        section_title="4.4 Go-Live & Training",
        block_type="paragraph"
    )
    b2 = ExtractedBlock(
        text="Training will be conducted on VC.",
        page_number=33,
        section_title="4.4 Go-Live & Training",
        block_type="paragraph"
    )
    stitched = _stitch_blocks([b1, b2])
    assert len(stitched) == 1, f"Expected 1 stitched block, got {len(stitched)}"
    assert "Training will be conducted on VC" in stitched[0].text


def test_paired_buyer_payment_policy_vs_vendor_cost_obligation():
    """Validates exclusion of buyer payment commitments while preserving vendor cost/pricing obligations."""
    buyer_commitments = [
        "In case RCS-<State_Name> wishes to procure additional tools or licenses the cost incurred on actual basis will be paid & procured by RCS-<State_Name>.",
        "Cost incurred on infrastructure upgrades will be borne by the department directly."
    ]
    for clause in buyer_commitments:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected buyer payment commitment '{clause}' to be rejected."

    vendor_cost_obligations = [
        "The selected bidder will be responsible for migration of entire data to new service provider without charging RCS-<State_Name> any cost.",
        "All such upward revisions of specifications shall be carried out within the lump sum contract price without any impact to the RCS-<State_Name>."
    ]
    for clause in vendor_cost_obligations:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor cost obligation '{clause}' to be accepted."


def test_paired_tender_administrative_rules_vs_bidder_submission_obligations():
    """Validates exclusion of tender evaluation/rejection meta-rules while preserving bidder obligations."""
    tender_meta_rules = [
        "Terms and conditions (General Conditions) of the bidder will not be considered as forming part of their Bids.",
        "The proposals received after the due date & time will not be considered.",
        "The offers containing erasures or alterations will not be considered.",
        "The Bidder shall prepare the bid based on details provided in the RFP documents.",
        "Deviations from or objections or reservations to critical provisions, such as those concerning Bid security, bid price, eligibility criteria, delivery schedule, SLA, insurance, Force Majeure etc. will be deemed to be a material deviation.",
        "Proposals not complying with the prescribed ‘Eligibility criteria’ and not submitted along with duly filled up annexures are liable to be rejected and will not be considered for further evaluation"
    ]
    for clause in tender_meta_rules:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected tender meta rule '{clause}' to be rejected."

    bidder_obligations = [
        "The bids prepared by the bidder and all correspondence relating to the bids shall be in the English language.",
        "There should be no handwritten material, corrections or alterations in the offer.",
        "Bids of only those Bidders who quote for the complete Scope of Work and Supply of Goods/Services shall be considered.",
        "The information provided by the Bidder must be true and correct",
        "The bidder should clearly specify deviation in Technical Bid with Form - Statement of Deviations from Bid Terms and conditions."
    ]
    for clause in bidder_obligations:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected bidder obligation '{clause}' to be accepted."


def test_mandatory_vs_optional_modal_parsing():
    """Validates mandatory vs optional extraction strictly based on modal keywords."""
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

    o_cases = [
        "The application should support dark mode theme.",
        "Automated report generation via email is preferable.",
        "The bidder may provide additional staging environments."
    ]
    for text in o_cases:
        is_m, prio, conf, reason = _determine_mandatory(text)
        assert is_m is False
        assert prio == "Low"

    ambiguous_cases = [
        "Database cluster configuration with PostgreSQL 15.",
        "Weekly meetings with the project steering committee."
    ]
    for text in ambiguous_cases:
        is_m, prio, conf, reason = _determine_mandatory(text)
        assert is_m is False
        assert conf == 0.0


def test_paired_buyer_bill_settlement_and_pbg_release_vs_vendor_handover():
    """Validates exclusion of buyer payment settlement and PBG release procedures while preserving vendor handover obligations."""
    buyer_settlement_procedures = [
        "The final bill under the project and shall be settled and PBG shall be released by RCS-<State_Name> only after successful data migration to new vendor selected by RCS-<State_Name> or to RCS-<State_Name> and after handing over the project related Documentation / data / information/ Reports, etc. to the satisfaction of RCS-<State_Name>.",
        "The final bill will be settled and PBG shall be released by the authority upon successful signoff.",
        "Final payment invoices shall be settled by the client within 30 days of deliverable acceptance.",
        "Security deposit shall be released by the employer after the defect liability period."
    ]
    for clause in buyer_settlement_procedures:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected buyer settlement procedure '{clause}' to be rejected."

    vendor_handover_obligations = [
        "The Service Provider shall be legally bound to hand over all the project related documents, data and all other project related information to RCS-<State_Name> or its authorized agency.",
        "The selected bidder will be responsible for migration of entire data (applications, databases, file storage, etc.) to new service provider without charging RCS-<State_Name> any cost.",
        "The successful Bidder will be required to provide a Performance Bank Guarantee for an amount equivalent to 3% of the contract value, in the form of Bank Guarantee from a scheduled commercial bank."
    ]
    for clause in vendor_handover_obligations:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected vendor obligation '{clause}' to be accepted."


def test_paired_existential_context_and_touchpoint_tautology_vs_genuine_system_specs():
    """Validates exclusion of existential infrastructure context and vague touchpoint tautologies while preserving concrete system specifications."""
    vague_context_statements = [
        "There will be external services like Mail Server, SMS Gateway, Email Gateway.",
        "There are multiple external systems such as Payment Gateway, SMS Gateway, and LDAP Server.",
        "User Touchpoints Web Portal will allow users to manage and access any information.",
        "Web Portal will allow users to manage and access any information.",
        "The application will provide access to all information."
    ]
    for clause in vague_context_statements:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected vague context statement '{clause}' to be rejected."

    genuine_specs = [
        "The system will facilitate notification of status of application through SMS and email of applicant in automated mode.",
        "Integration with external platforms (like e-Office, UIDAI, BharatVC, SMS, Digital Signature, and others if required)",
        "The portal will be responsive and be able to successfully render over major web browsers on desktop, laptop and mobile.",
        "Separate role based secured Login with 2FA will be provided to all the Stakeholders.",
        "Audit Trail Application will allow the admin users to track all activities, manage log files and create audit trail reports at documents."
    ]
    for clause in genuine_specs:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected genuine specification '{clause}' to be accepted."


def test_paired_password_features_vs_user_interaction_narratives():
    """Validates preservation of system authentication/password capabilities while filtering procedural user click narratives."""
    user_interaction_narratives = [
        "If user forgets his password, he will enter his registered email id",
        "Enter old password",
        "Enter new password",
        "Enter confirm password",
        "If both password match, password will be changed",
        "User will be able to change his password by using change password feature.",
        "User enters user id and password. After successful verification, applicant will login and redirected to user home page",
        "User clicks on Register button and selects role from dropdown"
    ]
    for clause in user_interaction_narratives:
        assert _is_non_requirement_heading_or_criterion(clause), f"Expected user interaction narrative '{clause}' to be rejected."

    system_auth_capabilities = [
        "System will have provision to retrieve password.",
        "System will verify the new password and confirm password.",
        "The platform shall support two-factor authentication (2FA) for all administrative users.",
        "The database shall support active-active clustering with automated failover and zero data loss."
    ]
    for clause in system_auth_capabilities:
        assert not _is_non_requirement_heading_or_criterion(clause), f"Expected system capability '{clause}' to be accepted."


def test_paired_administrative_tender_details_vs_technical_admin_features():
    """Validates classification of procurement administration details as Administrative while keeping technical admin IAM/privileges as Technical."""
    admin_paperwork_clauses = [
        "The proposal must include the name, official address, GST registration, and PAN of the authorized signatory.",
        "The bidder shall submit the power of attorney authorizing the signatory to bind the company.",
        "Provide primary liaison and executive contact information in the administrative form.",
        "The bidder shall provide company registration details and organizational chart."
    ]
    for clause in admin_paperwork_clauses:
        cat, reason = _determine_category(clause, "General")
        assert cat == "Administrative", f"Expected 'Administrative' for '{clause}', got '{cat}' ({reason})"

    technical_admin_clauses = [
        "The solution shall support two-factor authentication for privileged administrative accounts.",
        "The system shall maintain an audit trail for authentication events, appointment changes and administrative configuration changes.",
        "Access to production administrative functions shall be restricted to authorized personnel and protected by multi-factor authentication.",
        "The application must enforce role-based access control for administrative roles and clinic users.",
        "The platform shall provide administrative console access over encrypted TLS 1.3 connections."
    ]
    for clause in technical_admin_clauses:
        cat, reason = _determine_category(clause, "General")
        assert cat == "Technical", f"Expected 'Technical' for '{clause}', got '{cat}' ({reason})"


def test_paired_delivery_implementation_timelines_vs_technical_response_slas():
    """Validates classification of project implementation and deployment milestones as Delivery while keeping response/uptime SLAs as Technical."""
    delivery_timeline_clauses = [
        "The vendor shall complete implementation and production deployment within 14 weeks from contract commencement.",
        "Complete platform rollout and UAT signoff must be concluded within 90 days after contract award.",
        "The contractor shall complete delivery and installation within 6 months of work order issuance.",
        "The vendor shall conduct administrator and clinic-staff training before production deployment.",
        "The vendor shall migrate appointment master data supplied by Sunrise in an agreed electronic format before production go-live."
    ]
    for clause in delivery_timeline_clauses:
        cat, reason = _determine_category(clause, "General")
        assert cat == "Delivery", f"Expected 'Delivery' for '{clause}', got '{cat}' ({reason})"

    technical_sla_clauses = [
        "Critical production incidents shall receive an initial response within 30 minutes of logging.",
        "The service shall target monthly availability of at least 99.5%, excluding approved scheduled maintenance.",
        "The system shall process batch appointment synchronization jobs within 15 seconds."
    ]
    for clause in technical_sla_clauses:
        cat, reason = _determine_category(clause, "General")
        assert cat == "Technical", f"Expected 'Technical' for '{clause}', got '{cat}' ({reason})"


def test_paired_documentation_periodic_reports_vs_technical_reporting_features():
    """Validates classification of recurring deliverable reports as Documentation while keeping in-app UI reporting/dashboards as Technical."""
    doc_report_clauses = [
        "The vendor shall provide a monthly service report covering availability, incidents and support performance.",
        "The contractor shall submit quarterly performance reports and annual compliance audit summaries.",
        "The vendor must deliver weekly status reports, monthly SLA compliance dashboards, and user manuals.",
        "Documented RESTful API specifications and database schema runbooks must be submitted prior to go-live."
    ]
    for clause in doc_report_clauses:
        cat, reason = _determine_category(clause, "General")
        assert cat == "Documentation", f"Expected 'Documentation' for '{clause}', got '{cat}' ({reason})"

    technical_report_clauses = [
        "The platform shall provide dashboards and downloadable reports for appointment volume, cancellation rates and clinic-level utilization.",
        "Reports should also be available as On-Screen Reports with the capability of exporting it to any user defined format such as word, excel pdf, etc. & print and email feature.",
        "The application must support real-time data filtering and chart generation on the analytics screen."
    ]
    for clause in technical_report_clauses:
        cat, reason = _determine_category(clause, "General")
        assert cat == "Technical", f"Expected 'Technical' for '{clause}', got '{cat}' ({reason})"


def test_paired_contractual_performance_security_and_data_covenants_vs_technical_specs():
    """Validates classification of performance securities and data use restrictions as Contractual while keeping encryption/clustering as Technical."""
    contractual_clauses = [
        "A performance security of 5% of the contract value shall be submitted by the selected vendor in the form specified in the final agreement.",
        "The contractor shall furnish a security deposit equivalent to 3% of the total contract value.",
        "Patient-related information shall not be used by the vendor for advertising or unrelated commercial purposes.",
        "The vendor shall not use customer data for any marketing or unauthorized commercial exploitation.",
        "The bidder shall maintain confidentiality of information received from Sunrise during the engagement and after contract completion.",
        "The selected vendor shall execute the agreement and applicable confidentiality documents before access to production information is provided."
    ]
    for clause in contractual_clauses:
        cat, reason = _determine_category(clause, "General")
        assert cat == "Contractual", f"Expected 'Contractual' for '{clause}', got '{cat}' ({reason})"

    technical_security_clauses = [
        "The solution shall encrypt sensitive information at rest using an industry-standard encryption mechanism.",
        "The database shall support active-active clustering with automated failover and zero data loss.",
        "The platform must support encrypted data transmission using TLS 1.2 or higher."
    ]
    for clause in technical_security_clauses:
        cat, reason = _determine_category(clause, "General")
        assert cat == "Technical", f"Expected 'Technical' for '{clause}', got '{cat}' ({reason})"


def test_32_requirement_canonical_category_suite():
    """Comprehensive regression test ensuring all 32 requirements from the diagnostic map to their correct canonical categories."""
    suite = [
        ("Ref. Requirement A1 The proposed platform shall provide a web-based appointment management application accessible through current versions of Chrome, Edge and Firefox.", "Technical"),
        ("A2 The platform must support role-based access control for administrators, clinic staff and authorized care coordinators.", "Technical"),
        ("A3 The solution shall support two-factor authentication for privileged administrative accounts.", "Technical"),
        ("A4 The system shall maintain an audit trail for authentication events, appointment changes and administrative configuration changes.", "Technical"),
        ("A5 The platform must provide REST APIs for integration with hospital information systems and approved external services.", "Technical"),
        ("A6 The solution shall provide configurable SMS and email notifications for appointment confirmations, reminders and cancellations.", "Technical"),
        ("A7 The system shall support appointment creation, rescheduling, cancellation and availability management.", "Technical"),
        ("A8 The platform shall provide dashboards and downloadable reports for appointment volume, cancellation rates and clinic-level utilization.", "Technical"),
        ("A9 The vendor shall migrate appointment master data supplied by Sunrise in an agreed electronic format before production go-live.", "Delivery"),
        ("A10 The vendor shall conduct administrator and clinic-staff training before production deployment.", "Delivery"),
        ("A11 The vendor shall provide a helpdesk for incident logging and support during the contract term.", "Technical"),
        ("A12 The solution shall be deployed in a cloud environment approved by Sunrise and shall support encrypted data transmission using TLS 1.2 or higher.", "Technical"),
        ("The vendor shall complete implementation and production deployment within 14 weeks from contract commencement.", "Delivery"),
        ("The service shall target monthly availability of at least 99.5%, excluding approved scheduled maintenance.", "Technical"),
        ("Critical production incidents shall receive an initial response within 30 minutes of logging.", "Technical"),
        ("The vendor shall provide a monthly service report covering availability, incidents and support performance.", "Documentation"),
        ("Training sessions shall be conducted through online or on-site delivery as mutually agreed with the project team.", "Delivery"),
        ("The bidder must have at least five years of experience delivering enterprise software or digital platforms.", "Eligibility"),
        ("The bidder must demonstrate at least two completed projects of comparable scale involving healthcare or other regulated information.", "Eligibility"),
        ("The bidder shall provide two client references for comparable implementations.", "Eligibility"),
        ("The bidder shall submit audited financial statements for the latest two completed financial years.", "Eligibility"),
        ("The bidder must provide evidence of ISO 27001 or an equivalent recognized information-security certification.", "Certification"),
        ("The bidder shall submit a fixed implementation fee and a separate annual support fee.", "Commercial"),
        ("All quoted prices shall be stated in Indian Rupees and shall clearly identify applicable taxes.", "Commercial"),
        ("The bidder shall maintain confidentiality of information received from Sunrise during the engagement and after contract completion.", "Contractual"),
        ("The selected vendor shall execute the agreement and applicable confidentiality documents before access to production information is provided.", "Contractual"),
        ("A performance security of 5% of the contract value shall be submitted by the selected vendor in the form specified in the final agreement.", "Contractual"),
        ("Patient-related information shall not be used by the vendor for advertising or unrelated commercial purposes.", "Contractual"),
        ("The solution shall encrypt sensitive information at rest using an industry-standard encryption mechanism.", "Technical"),
        ("Access to production administrative functions shall be restricted to authorized personnel and protected by multi-factor authentication.", "Technical"),
        ("The vendor shall notify Sunrise of a confirmed security incident affecting the service within 24 hours of confirmation.", "Technical"),
        ("The vendor shall maintain documented backup and recovery procedures for production data.", "Technical"),
    ]
    for text, expected in suite:
        cat, reason = _determine_category(text, "General")
        assert cat == expected, f"Requirement '{text[:60]}...' expected '{expected}', got '{cat}' ({reason})"




