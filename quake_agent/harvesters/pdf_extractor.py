from __future__ import annotations
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

class PDFExtractor:
    """
    Extracts text, page images, and metadata from local PDF documents.
    Supports pypdf, fitz (PyMuPDF), pdf2image, or raw fallback.
    """

    def __init__(self, output_dir: Optional[str | Path] = None):
        self.output_dir = Path(output_dir) if output_dir else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_text(self, pdf_path: str | Path) -> str:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            return ""

        text_content = []

        # Try pypdf / PyPDF2
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            for i, page in enumerate(reader.pages):
                txt = page.extract_text()
                if txt:
                    text_content.append(f"--- Page {i+1} ---\n{txt}")
            if text_content:
                return "\n\n".join(text_content)
        except Exception:
            pass

        # Try PyMuPDF (fitz)
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            for i, page in enumerate(doc):
                txt = page.get_text()
                if txt:
                    text_content.append(f"--- Page {i+1} ---\n{txt}")
            doc.close()
            if text_content:
                return "\n\n".join(text_content)
        except Exception:
            pass

        # Try pdftotext CLI (poppler)
        try:
            import subprocess
            res = subprocess.run(["pdftotext", str(pdf_path), "-"], capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

        # Fallback reading raw text strings
        try:
            raw_bytes = pdf_path.read_bytes()
            import re
            strings = re.findall(rb"[a-zA-Z0-9\s.,!?-]{6,}", raw_bytes)
            decoded = [s.decode("latin1", errors="ignore") for s in strings[:100]]
            return " ".join(decoded)
        except Exception:
            return ""

    def extract_page_images(self, pdf_path: str | Path, target_dir: Optional[str | Path] = None) -> List[Path]:
        pdf_path = Path(pdf_path)
        out_dir = Path(target_dir) if target_dir else (self.output_dir or pdf_path.parent / f"{pdf_path.stem}_images")
        out_dir.mkdir(parents=True, exist_ok=True)

        extracted_images = []

        # Method 1: PyMuPDF raster rendering
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=150)
                img_path = out_dir / f"page_{i+1}.png"
                pix.save(str(img_path))
                extracted_images.append(img_path)
            doc.close()
            if extracted_images:
                return extracted_images
        except Exception:
            pass

        # Method 2: pdf2image
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(str(pdf_path), dpi=150)
            for i, img in enumerate(images):
                img_path = out_dir / f"page_{i+1}.png"
                img.save(str(img_path), "PNG")
                extracted_images.append(img_path)
            if extracted_images:
                return extracted_images
        except Exception:
            pass

        return extracted_images
