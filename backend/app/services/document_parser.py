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

        for page_num in range(len(doc)):
            page = doc[page_num]
            # page_num is 0-indexed in fitz, so 1-indexed for citations
            page_index = page_num + 1
            
            # Extract text blocks with layout info
            page_blocks = page.get_text("blocks")
            
            for b in page_blocks:
                # b = (x0, y0, x1, y1, text, block_no, block_type)
                text = b[4].strip()
                if not text:
                    continue

                # Heading detection heuristic:
                # Short line (< 90 chars), doesn't end with a period, often capitalized or numbered
                lines = text.split("\n")
                first_line = lines[0].strip()
                is_heading = False

                if len(first_line) < 90 and (
                    first_line.isupper()
                    or any(first_line.startswith(prefix) for prefix in ["Section", "Part", "Chapter", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."])
                    or not first_line.endswith((".", ":", ";"))
                ) and len(lines) <= 2:
                    current_section = first_line
                    is_heading = True

                blocks_out.append(
                    ExtractedBlock(
                        text=text,
                        page_number=page_index,
                        section_title=current_section,
                        block_type="heading" if is_heading else "paragraph"
                    )
                )

        doc.close()
        return blocks_out

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
