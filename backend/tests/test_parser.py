import pytest
import os
from app.services.document_parser import DocumentParserService

def test_document_parser_txt():
    sample_file = os.path.abspath("sample_data/sample_rfp_enterprise_cloud.txt")
    assert os.path.exists(sample_file), f"Sample file not found at {sample_file}"

    blocks = DocumentParserService.parse_document(sample_file)
    assert len(blocks) > 0, "Parser returned zero blocks"
    
    # Check that sections are captured
    sections = {b.section_title for b in blocks}
    assert any("TECHNICAL" in s.upper() for s in sections)
    assert any("SECURITY" in s.upper() for s in sections)
    assert any("LEGAL" in s.upper() for s in sections)
    
    # Check that page numbers are populated
    assert all(b.page_number >= 1 for b in blocks)
    print(f"\n[Test Passed] Parsed {len(blocks)} blocks across {len(sections)} sections.")
