"""PDF document builder for v1.7.0 reports."""
from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Iterable, List


def _resolve_font_path() -> str | None:
    """Pick a common Cyrillic-capable TTF font from host system."""
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _chunk_line(line: str, max_chars: int = 110) -> List[str]:
    text = (line or "").rstrip()
    if not text:
        return [""]

    chunks: List[str] = []
    rest = text
    while len(rest) > max_chars:
        split_at = rest.rfind(" ", 0, max_chars)
        if split_at <= 0:
            split_at = max_chars
        chunks.append(rest[:split_at].rstrip())
        rest = rest[split_at:].lstrip()
    chunks.append(rest)
    return chunks


def _normalize_lines(lines: Iterable[str]) -> List[str]:
    out: List[str] = []
    for line in lines:
        out.extend(_chunk_line(line))
    return out


def build_report_pdf_bytes(title: str, subtitle: str, lines: Iterable[str]) -> bytes:
    """Build simple multi-page PDF and return bytes."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "PDF export requires reportlab. Install dependencies from requirements.txt"
        ) from exc

    font_name = "Helvetica"
    font_path = _resolve_font_path()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("ReportSans", font_path))
            font_name = "ReportSans"
        except Exception:
            font_name = "Helvetica"

    prepared_lines = _normalize_lines(lines)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin_left = 40
    margin_top = 52
    line_height = 14
    y = height - margin_top

    def safe_text(value: str) -> str:
        if font_name == "Helvetica":
            return (value or "").encode("latin-1", "replace").decode("latin-1")
        return value or ""

    def new_page() -> None:
        nonlocal y
        c.showPage()
        y = height - margin_top
        c.setFont(font_name, 10)

    c.setFont(font_name, 15)
    c.drawString(margin_left, y, safe_text(title))
    y -= 22

    c.setFont(font_name, 10)
    c.drawString(margin_left, y, safe_text(subtitle))
    y -= 18
    c.drawString(
        margin_left, y, safe_text(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    )
    y -= 18

    for line in prepared_lines:
        if y < 48:
            new_page()
        c.drawString(margin_left, y, safe_text(line))
        y -= line_height

    c.save()
    return buffer.getvalue()
