import os
from typing import Dict, Any, List
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
from app.core.config import settings

class ProposalExporterService:
    @staticmethod
    def export_to_docx(
        rfp_metadata: Dict[str, Any],
        proposal_draft: Dict[str, Any],
        compliance_matrix: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
        clarifications: List[Dict[str, Any]],
        output_path: str
    ) -> str:
        """
        Exports a professional enterprise proposal response in DOCX format.
        """
        doc = docx.Document()

        # Set standard 1 inch margins
        for section in doc.sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

        # Title / Cover Page Header
        title_para = doc.add_paragraph()
        title_run = title_para.add_run(proposal_draft.get("title", "PROPOSAL RESPONSE"))
        title_run.font.size = Pt(24)
        title_run.font.bold = True
        title_run.font.color.rgb = RGBColor(26, 54, 93)  # Navy blue
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        subtitle_para = doc.add_paragraph()
        sub_run = subtitle_para.add_run(
            f"Submitted in Response to RFP: {rfp_metadata.get('title', 'Enterprise Tender')}\n"
            f"Issued by: {rfp_metadata.get('issuer', 'Valued Client')} | Due: {rfp_metadata.get('submission_deadline', 'Specified')}"
        )
        sub_run.font.size = Pt(12)
        sub_run.font.italic = True
        subtitle_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph("\n" + "=" * 60 + "\n")

        # Sections from proposal draft
        sections = proposal_draft.get("sections", [])
        if sections:
            for sec in sections:
                h = doc.add_heading(sec.get("section_title", "Section"), level=1)
                h.style.font.color.rgb = RGBColor(30, 64, 175)
                
                content = sec.get("content_markdown", "")
                paragraphs = content.split("\n\n")
                for p_text in paragraphs:
                    p_text_clean = p_text.strip()
                    if not p_text_clean:
                        continue

                    # Special styling for INFORMATION REQUIRED callouts
                    if "INFORMATION REQUIRED" in p_text_clean:
                        callout = doc.add_paragraph()
                        c_run = callout.add_run("⚠️ " + p_text_clean.replace(">", "").strip())
                        c_run.font.bold = True
                        c_run.font.color.rgb = RGBColor(180, 83, 9)  # Amber-700
                    elif p_text_clean.startswith("### "):
                        doc.add_heading(p_text_clean.replace("### ", ""), level=2)
                    elif p_text_clean.startswith("#### "):
                        doc.add_heading(p_text_clean.replace("#### ", ""), level=3)
                    elif p_text_clean.startswith("- "):
                        items = p_text_clean.split("\n")
                        for it in items:
                            if it.startswith("- "):
                                p = doc.add_paragraph(it.replace("- ", ""), style='List Bullet')
                    else:
                        doc.add_paragraph(p_text_clean)
        else:
            # Fallback to full markdown text
            for line in proposal_draft.get("full_markdown", "").split("\n"):
                doc.add_paragraph(line)

        # Append Formal Compliance Matrix Table
        doc.add_page_break()
        mat_heading = doc.add_heading("Appendix A: Formal Requirement Compliance Matrix", level=1)
        mat_heading.style.font.color.rgb = RGBColor(30, 64, 175)

        if compliance_matrix:
            table = doc.add_table(rows=1, cols=4)
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.style = 'Light Shading Accent 1'

            hdr_cells = table.rows[0].cells
            headers = ["Req ID", "Category", "Compliance Verdict", "Source Evidence / Action Required"]
            for i, header_text in enumerate(headers):
                hdr_cells[i].text = header_text
                hdr_cells[i].paragraphs[0].runs[0].font.bold = True

            for item in compliance_matrix:
                row_cells = table.add_row().cells
                row_cells[0].text = item.get("req_code", "")
                row_cells[1].text = item.get("category", "")
                
                # Color coded verdict
                status = item.get("status", "")
                row_cells[2].text = status
                verdict_run = row_cells[2].paragraphs[0].runs[0]
                verdict_run.font.bold = True
                if status == "COMPLIANT":
                    verdict_run.font.color.rgb = RGBColor(22, 101, 52)
                elif status == "PARTIALLY_COMPLIANT":
                    verdict_run.font.color.rgb = RGBColor(161, 98, 7)
                elif status == "NON_COMPLIANT":
                    verdict_run.font.color.rgb = RGBColor(185, 28, 28)
                else:
                    verdict_run.font.color.rgb = RGBColor(194, 65, 12)

                evidence = item.get("company_source_doc") or item.get("notes") or "Evidence Required"
                row_cells[3].text = evidence

        # Ensure directory exists and save
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        doc.save(output_path)
        return output_path
