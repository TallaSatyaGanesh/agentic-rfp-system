import os
import sys
import time
import httpx

BASE_URL = "http://127.0.0.1:8000"
client = httpx.Client(base_url=BASE_URL, timeout=60.0)

def log(msg: str):
    print(f"\n>>> [E2E] {msg}")

def run_e2e():
    # 1. Health check
    log("Checking Backend Health...")
    r = client.get("/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    log(f"Health OK: {r.json()}")

    # 2. Ingest Company Collateral
    log("Ingesting Company Knowledge Base Collateral...")
    collateral_files = [
        ("sample_data/company_collateral/cloud_capabilities.txt", "Enterprise Cloud Architecture", "Technical"),
        ("sample_data/company_collateral/security_and_compliance.txt", "Security & Compliance Whitepaper", "Security")
    ]
    for path, title, cat in collateral_files:
        if os.path.exists(path):
            with open(path, "rb") as f:
                r = client.post(
                    "/api/company-knowledge/upload",
                    files={"file": (os.path.basename(path), f, "text/plain")},
                    data={"title": title, "category": cat}
                )
                assert r.status_code == 200, f"Upload collateral failed: {r.text}"
                print(f"  Indexed: {title} ({r.json()['chunk_count']} chunks)")

    # 3. Query RAG
    log("Verifying RAG Knowledge Retrieval...")
    q_res = client.post("/api/company-knowledge/query", json={"query": "SOC 2 Type II compliance and AES 256 encryption"})
    assert q_res.status_code == 200
    results = q_res.json().get("results", [])
    assert len(results) > 0, "No RAG chunks retrieved!"
    log(f"RAG Retrieved {len(results)} chunks. Top match: {results[0]['document_title']} (score: {results[0]['similarity']:.3f})")

    # 4. Upload Sample RFP
    log("Uploading Sample RFP Document...")
    rfp_path = "sample_data/sample_rfp_enterprise_cloud.txt"
    with open(rfp_path, "rb") as f:
        r = client.post("/api/rfp/upload", files={"file": ("sample_rfp_enterprise_cloud.txt", f, "text/plain")})
        assert r.status_code == 200, f"RFP Upload failed: {r.text}"
        rfp_data = r.json()
        rfp_id = rfp_data["rfp_id"]
        log(f"RFP Uploaded. ID: {rfp_id}")

    # 5. Start LangGraph Multi-Agent Workflow
    log(f"Starting Multi-Agent Workflow for RFP {rfp_id}...")
    start_res = client.post(f"/api/workflow/{rfp_id}/start")
    assert start_res.status_code == 200, f"Start workflow failed: {start_res.text}"
    log("Workflow started. Polling status until Gate 1 (Bid Go/No-Go Decision)...")

    # 6. Poll for Gate 1 Interrupt
    max_wait = 60
    start_time = time.time()
    gate1_reached = False
    while time.time() - start_time < max_wait:
        st = client.get(f"/api/workflow/{rfp_id}/status").json()
        print(f"  Status: {st['status']} | Active Agent: {st['active_agent']} | Interrupted: {st['is_interrupted']} ({st['interrupt_type']})")
        if st["is_interrupted"] and st["interrupt_type"] == "GO_NOGO":
            gate1_reached = True
            break
        time.sleep(2)

    assert gate1_reached, "Timed out waiting for Gate 1 interrupt!"
    log("GATE 1 REACHED! Validating intermediate DB persistence...")

    # Validate DB state during Gate 1
    reqs = client.get(f"/api/rfp/{rfp_id}/requirements").json()
    compliance = client.get(f"/api/rfp/{rfp_id}/compliance-matrix").json()
    risks_data = client.get(f"/api/rfp/{rfp_id}/risks").json()

    print(f"  Requirements Extracted: {len(reqs)}")
    print(f"  Compliance Records: {len(compliance)}")
    print(f"  Risks Identified: {len(risks_data.get('risks', []))}")
    print(f"  Clarification Questions: {len(risks_data.get('clarification_questions', []))}")

    assert len(reqs) > 0, "No requirements found in DB at Gate 1!"
    assert len(compliance) > 0, "No compliance records found in DB at Gate 1!"

    # Show compliance sample
    c0 = compliance[0]
    print(f"  Sample Compliance: [{c0['req_code']}] Status: {c0['status']} | Source: {c0['company_source_doc']}")

    # 7. Resume Workflow at Gate 1 (Submit Human Go/No-Go Approval)
    log("Submitting Gate 1 Approval: 'GO' with notes 'Approved to proceed with proposal response.'")
    res1 = client.post(f"/api/workflow/{rfp_id}/resume", json={
        "decision": "GO",
        "notes": "Approved to proceed with proposal response."
    })
    assert res1.status_code == 200, f"Resume Gate 1 failed: {res1.text}"

    # 8. Poll for Gate 2 Interrupt (Final Approval)
    log("Polling for Gate 2 (Final Proposal Approval) - Writer Agent, Reviewer Agent & Revision Cycle running...")
    start_time = time.time()
    gate2_reached = False
    while time.time() - start_time < max_wait:
        st = client.get(f"/api/workflow/{rfp_id}/status").json()
        print(f"  Status: {st['status']} | Active Agent: {st['active_agent']} | Interrupted: {st['is_interrupted']} ({st['interrupt_type']}) | Ver: {st['current_version']} | Revs: {st['revision_count']}")
        if st["is_interrupted"] and st["interrupt_type"] == "FINAL_APPROVAL":
            gate2_reached = True
            break
        time.sleep(2)

    assert gate2_reached, "Timed out waiting for Gate 2 interrupt!"
    log("GATE 2 REACHED! Validating Proposal Drafts and Reviewer Scores...")

    proposals = client.get(f"/api/rfp/{rfp_id}/proposals").json()
    print(f"  Total Proposal Drafts in DB: {len(proposals)}")
    for p in proposals:
        print(f"  - Draft v{p['version']}: Score {p['review_score']}/100 | Status: {p['status']} | Summary: {p['executive_summary'][:90]}...")

    assert len(proposals) >= 2, f"Expected at least 2 drafts from revision cycle, got {len(proposals)}"
    assert proposals[1]["version"] == 2, "Second draft version should be 2"

    # 9. Resume Workflow at Gate 2 (Submit Final Sign-Off)
    log("Submitting Gate 2 Approval: 'APPROVED' with feedback 'Proposal reviewed and approved for export.'")
    res2 = client.post(f"/api/workflow/{rfp_id}/resume", json={
        "decision": "APPROVED",
        "feedback": "Proposal reviewed and approved for export."
    })
    assert res2.status_code == 200, f"Resume Gate 2 failed: {res2.text}"

    # 10. Poll for Completion
    log("Waiting for final workflow completion...")
    start_time = time.time()
    completed = False
    while time.time() - start_time < 30:
        st = client.get(f"/api/workflow/{rfp_id}/status").json()
        print(f"  Status: {st['status']} | Active Agent: {st['active_agent']} | Interrupted: {st['is_interrupted']}")
        if st["status"] in ["APPROVED_FOR_EXPORT", "COMPLETED"] and not st["is_interrupted"]:
            completed = True
            break
        time.sleep(1)

    assert completed, "Workflow did not reach final completed status!"
    log("WORKFLOW SUCCESSFULLY COMPLETED!")

    # 11. Test Proposal Export
    log("Testing DOCX Proposal Export...")
    exp_res = client.get(f"/api/rfp/{rfp_id}/export/docx")
    assert exp_res.status_code == 200, f"DOCX Export failed: {exp_res.status_code}"
    assert len(exp_res.content) > 1000, "DOCX file seems too small!"
    log(f"DOCX Export Successful! Downloaded {len(exp_res.content)} bytes.")

    print("\n==================================================")
    print("  ALL END-TO-END VERIFICATION CHECKS PASSED!  ")
    print("==================================================")

if __name__ == "__main__":
    run_e2e()
