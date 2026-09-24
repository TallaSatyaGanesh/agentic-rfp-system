import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import fitz  # PyMuPDF
import docx
from app.models.schemas import ExtractedBlock

class DocumentParserService:
    @staticmethod
    def get_file_extension(file_path: str) -> str:
        return Path(file_path).suffix.lower()

    @classmethod
    def parse_document(cls, file_path: str) -> List[ExtractedBlock]:
        """
        Parses a PDF or DOCX document and returns a list of ExtractedBlocks
        annotated with page numbers, section titles, and block types.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document not found at {file_path}")

        ext = cls.get_file_extension(file_path)
        if ext == ".pdf":
            return cls._parse_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            return cls._parse_docx(file_path)
        elif ext in [".txt", ".md"]:
            return cls._parse_text(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}. Only PDF, DOCX, and TXT are supported.")

    @classmethod
    def get_page_count(cls, file_path: str) -> int:
        ext = cls.get_file_extension(file_path)
        if ext == ".pdf":
            try:
                doc = fitz.open(file_path)
                count = len(doc)
                doc.close()
                return count
            except Exception:
                return 1
        elif ext in [".docx", ".doc"]:
            # Approximation for DOCX (roughly 400 words per page)
            try:
                doc = docx.Document(file_path)
                words = sum(len(p.text.split()) for p in doc.paragraphs)
                return max(1, (words // 400) + 1)
            except Exception:
                return 1
        return 1

    @classmethod
    def _parse_pdf(cls, file_path: str) -> List[ExtractedBlock]:
        doc = fitz.open(file_path)
        blocks_out: List[ExtractedBlock] = []
        current_section = "Introduction & General Information"
        num_pages = len(doc)

        import re

        # Pass 1: Extract all raw blocks with page geometry
        raw_page_blocks: List[Dict[str, Any]] = []
        margin_text_counts: Dict[str, int] = {}

        for page_num in range(num_pages):
            page = doc[page_num]
            page_index = page_num + 1
            page_height = page.rect.height
            page_blocks = page.get_text("blocks")

            for b in page_blocks:
                # b = (x0, y0, x1, y1, text, block_no, block_type)
                text = b[4].strip()
                if not text:
                    continue

                x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
                is_top_margin = (y0 <= 40)
                is_bottom_margin = (y1 >= (page_height - 40))

                # Track normalized short strings in extreme margins for multi-page documents
                if (is_top_margin or is_bottom_margin) and len(text) < 140 and len(text.split("\n")) <= 2:
                    # Normalize digits for page numbers e.g. "Page 1 of 50" -> "page # of #"
                    norm_margin_str = re.sub(r'\d+', '#', text.lower().strip())
                    margin_text_counts[norm_margin_str] = margin_text_counts.get(norm_margin_str, 0) + 1

                raw_page_blocks.append({
                    "text": text,
                    "page_index": page_index,
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "page_height": page_height,
                    "is_top_margin": is_top_margin,
                    "is_bottom_margin": is_bottom_margin
                })

        # Pass 2: Filter recurring headers/footers and identify headings / TOC entries
        for rb in raw_page_blocks:
            text = rb["text"]
            page_index = rb["page_index"]
            is_top = rb["is_top_margin"]
            is_bottom = rb["is_bottom_margin"]

            # Check if block is a recurring running header/footer in margin area
            if (is_top or is_bottom) and num_pages >= 3 and len(text) < 140 and len(text.split("\n")) <= 2:
                norm_margin_str = re.sub(r'\d+', '#', text.lower().strip())
                # If seen across multiple pages or matches standalone page numbering format in margins
                is_page_num_artifact = bool(
                    re.match(r'^(?:page\s+)?#(?:\s+of\s+#)?$', norm_margin_str)
                    or re.match(r'^#\s*\|\s*p\s*a\s*g\s*e$', norm_margin_str)
                )
                if margin_text_counts.get(norm_margin_str, 0) >= 2 or is_page_num_artifact:
                    # Skip running header/footer layout noise
                    continue

            lines = text.split("\n")
            first_line = lines[0].strip()
            is_heading = False

            # Check for Table of Contents dot leaders: e.g. "4.1 Section Title ........ 7" or "Scope … 12"
            is_toc_entry = bool(re.search(r'(?:\.{2,}|…+|\s*\.\s*\.\s*|\s*[-–—]{3,}|\t+)\s*\d+\s*$', text))

            # Heading detection heuristic:
            # - Requires explicit section keyword or dot notation after number (e.g. "1. Introduction", "1.1 General Terms", "SECTION 1", "PART 1")
            # - Guards against date stamps (e.g. "25.02.2026"), bracketed subtitles (e.g. "[Instructions to Bidder]"), and requirement list numbers (e.g. "3 projects not less than 2.5 Cr")
            is_date_line = bool(re.match(r'^\s*\d{1,4}[\.\/\-]\d{1,2}[\.\/\-]\d{2,4}\b', first_line))
            is_bracketed_subtitle = first_line.startswith(('[', '(', '<'))

            is_section_header = not is_date_line and not is_bracketed_subtitle and bool(
                (
                    re.match(r'^(?:(?:SECTION|CHAPTER|APPENDIX|ANNEXURE|ATTACHMENT|EXHIBIT)\s+(?:(?:\d+(?:\.\d+)*|[A-Z0-9\-_]+)[:\.]?)|(?:VOLUME|PART|SCHEDULE)\s+(?:\d+(?:\.\d+)*|[A-Z]\b|[-–—:]|(?-i:[IVXLCDM]+))|\d+(?:\.\d+)+\.?|\d+\.)\s+[A-Za-z0-9\s&,\.\-–—:/()\[\]\'"’“”<>_]+$', first_line, re.IGNORECASE)
                    and not re.search(r'\b(?:project|projects|month|months|year|years|day|days|hour|hours|crore|cr|lakh|percent|%|shall|must|not\s+less\s+than|minimum|executive|developer|engineer|manager|architect|expert|specialist|officer|consultant|personnel|staff|manpower|resource)\b', first_line, re.IGNORECASE)
                )
                or (
                    first_line.isupper()
                    and 5 <= len(first_line) <= 80
                    and len(first_line.split()) >= 2
                    and not first_line.startswith("REQ-")
                    and not first_line.endswith(':')
                    and first_line not in ["YES", "NO", "N/A", "TRUE", "FALSE", "MANDATORY", "OPTIONAL"]
                    and not re.search(r'\b(?:PROJECT|PROJECTS|MONTH|MONTHS|YEAR|YEARS|DAY|DAYS|CRORE|CR|LAKH|SHALL|MUST|NOT\s+LESS\s+THAN|MINIMUM|DIRECTORATE|GOVERNMENT|MINISTRY|DEPARTMENT|CENTRE|CENTER|AUTHORITY|AGENCY|CORPORATION|LIMITED|LTD|COMMISSION|NOTWITHSTANDING|NOTHWITHSTANDING|IFSC|ACCOUNT|NOTE|DISCLAIMER|WHEREAS|HEREIN|HEREOF)\b', first_line)
                )
            )

            if is_section_header and not is_toc_entry:
                current_section = first_line
                blocks_out.append(
                    ExtractedBlock(
                        text=first_line,
                        page_number=page_index,
                        section_title=current_section,
                        block_type="heading"
                    )
                )
                rest_text = "\n".join(lines[1:]).strip()
                if rest_text:
                    blocks_out.append(
                        ExtractedBlock(
                            text=rest_text,
                            page_number=page_index,
                            section_title=current_section,
                            block_type="paragraph"
                        )
                    )
            else:
                block_type = "toc" if is_toc_entry else "paragraph"
                blocks_out.append(
                    ExtractedBlock(
                        text=text,
                        page_number=page_index,
                        section_title=current_section,
                        block_type=block_type
                    )
                )

        doc.close()

        # Merge broken paragraph fragments within same page & section
        merged_blocks: List[ExtractedBlock] = []
        for b in blocks_out:
            if not merged_blocks:
                merged_blocks.append(b)
                continue

            prev = merged_blocks[-1]
            prev_text = prev.text.rstrip()
            curr_text = b.text.lstrip()

            starts_with_bullet = bool(re.match(r'^(?:[•o\-\*\uf0b7\uf0a7§\xa7]|\d+(?:[\.\)]|\s+[A-Z])|\([0-9a-zA-Z]\)|[a-zA-Z][\.\)]|REQ-|Sl\s*#)', curr_text))
            is_prev_contact = bool(re.search(r'(?:@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+|\b(?:post\s+office|pin\s*[-:\d]|fax\b|phone\b|mobile\b|plot\s+no)\b)', prev_text, re.IGNORECASE))
            ends_with_terminal = prev_text.endswith(('.', '!', '?', ':', ';')) and not prev_text.endswith(('etc.', 'i.e.', 'e.g.', 'vs.', 'OR', 'AND', 'Clause', 'clause', 'Section', 'section', 'Rule', 'rule', 'Article', 'article', 'No.', 'no.'))
            ends_with_hyphen = prev_text.endswith(('-', '–', '—'))
            ends_with_conjunction = bool(re.search(r'\b(?:OR|AND|Clause|clause|Section|section|Article|article|Rule|rule|with|for|as|on|including|to|in|of)\s*$', prev_text))

            if (
                prev.page_number == b.page_number
                and prev.section_title == b.section_title
                and prev.block_type == "paragraph"
                and b.block_type == "paragraph"
                and not starts_with_bullet
                and not is_prev_contact
                and (not ends_with_terminal or ends_with_hyphen or ends_with_conjunction)
            ):
                if ends_with_hyphen:
                    prev.text = prev_text[:-1] + curr_text
                else:
                    prev.text = prev_text + " " + curr_text
            else:
                merged_blocks.append(b)

        return merged_blocks

    @classmethod
    def _parse_docx(cls, file_path: str) -> List[ExtractedBlock]:
        doc = docx.Document(file_path)
        blocks_out: List[ExtractedBlock] = []
        current_section = "General Requirements"
        current_page = 1
        word_count = 0

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue

            word_count += len(text.split())
            current_page = max(1, (word_count // 400) + 1)

            style_name = p.style.name.lower() if p.style else ""
            is_heading = "heading" in style_name or "title" in style_name

            if is_heading:
                current_section = text

            blocks_out.append(
                ExtractedBlock(
                    text=text,
                    page_number=current_page,
                    section_title=current_section,
                    block_type="heading" if is_heading else "paragraph"
                )
            )

        # Also extract table contents
        for table in doc.tables:
            table_text = []
            for row in table.rows:
                row_data = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_data:
                    table_text.append(" | ".join(row_data))
            if table_text:
                full_table = "\n".join(table_text)
                blocks_out.append(
                    ExtractedBlock(
                        text=full_table,
                        page_number=current_page,
                        section_title=current_section,
                        block_type="table"
                    )
                )

        return blocks_out

    @classmethod
    def _parse_text(cls, file_path: str) -> List[ExtractedBlock]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [line.strip() for line in f.readlines()]

        blocks_out: List[ExtractedBlock] = []
        current_section = "General Information"
        current_page = 1
        line_count = 0

        for line in lines:
            if not line:
                continue
            line_count += 1
            current_page = (line_count // 15) + 1

            if (
                line.startswith("#")
                or line.upper().startswith("SECTION ")
                or (len(line) < 90 and line.isupper() and not line.endswith("."))
            ):
                current_section = line.lstrip("#").strip()
                blocks_out.append(
                    ExtractedBlock(
                        text=line,
                        page_number=current_page,
                        section_title=current_section,
                        block_type="heading"
                    )
                )
            else:
                blocks_out.append(
                    ExtractedBlock(
                        text=line,
                        page_number=current_page,
                        section_title=current_section,
                        block_type="paragraph"
                    )
                )
        return blocks_out
