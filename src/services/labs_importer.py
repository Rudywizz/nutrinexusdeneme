from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
from datetime import datetime
import re

from PyPDF2 import PdfReader

from src.services.labs_parser import LabRow, parse_enabiz_text

def extract_text_from_pdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    parts = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t:
            parts.append(t)
    return "\n".join(parts)

def parse_enabiz_pdf(pdf_path: str) -> List[LabRow]:
    text = extract_text_from_pdf(pdf_path)
    return parse_enabiz_text(text)
