"""Document intelligence service: extracts structured text & page references from PDF, DOCX, TXT."""

from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class ExtractedDocument:
    text: str
    page_count: int
    pages: List[Dict[str, object]]


@dataclass
class ExtractedImage:
    filename: str
    mime_type: str
    data: bytes


_EXT_MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _normalize_image_bytes(raw: bytes, filename: str) -> ExtractedImage | None:
    ext = Path(filename).suffix.lower()
    if ext in _EXT_MIME_MAP:
        return ExtractedImage(filename=Path(filename).name, mime_type=_EXT_MIME_MAP[ext], data=raw)
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as img:
            out = io.BytesIO()
            img.convert("RGBA").save(out, format="PNG")
            return ExtractedImage(
                filename=f"{Path(filename).stem}.png",
                mime_type="image/png",
                data=out.getvalue(),
            )
    except Exception:
        return None


def extract_embedded_images(data: bytes, extension: str, max_images: int = 8) -> List[ExtractedImage]:
    """Extract embedded logos, diagrams, and photos from DOCX or PDF files for multimodal AI inspection."""
    ext = extension.lower().lstrip(".")
    images: List[ExtractedImage] = []

    if ext == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for member in sorted(zf.namelist()):
                    if not member.lower().startswith("word/media/"):
                        continue
                    raw = zf.read(member)
                    if not raw or len(raw) > 5 * 1024 * 1024:
                        continue
                    normalized = _normalize_image_bytes(raw, member)
                    if normalized:
                        images.append(normalized)
                    if len(images) >= max_images:
                        break
        except Exception:
            return images
    elif ext == "pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            for page_idx, page in enumerate(reader.pages, start=1):
                for img_file in getattr(page, "images", []) or []:
                    raw = getattr(img_file, "data", b"")
                    name = getattr(img_file, "name", f"page{page_idx}_img.png")
                    if not raw or len(raw) > 5 * 1024 * 1024:
                        continue
                    normalized = _normalize_image_bytes(raw, f"page{page_idx}_{name}")
                    if normalized:
                        images.append(normalized)
                    if len(images) >= max_images:
                        return images
        except Exception:
            return images

    return images


def extract_pdf_text(data: bytes) -> ExtractedDocument:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages: List[Dict[str, object]] = []
    combined_parts: List[str] = []

    for idx, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        pages.append({"page": idx, "text": page_text})
        if page_text:
            combined_parts.append(f"--- Page {idx} ---\n{page_text}")

    return ExtractedDocument(
        text="\n\n".join(combined_parts),
        page_count=len(reader.pages),
        pages=pages,
    )


def extract_docx_text(data: bytes) -> ExtractedDocument:
    try:
        import docx  # type: ignore

        document = docx.Document(io.BytesIO(data))
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    paragraphs.append(" | ".join(cells))
        full_text = "\n".join(paragraphs)
    except ImportError:
        # Pure stdlib fallback for DOCX (OOXML zip with word/document.xml)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for para in root.findall(".//w:p", ns):
            texts = [t.text for t in para.findall(".//w:t", ns) if t.text]
            line = "".join(texts).strip()
            if line:
                paragraphs.append(line)
        full_text = "\n".join(paragraphs)

    return ExtractedDocument(
        text=full_text,
        page_count=max(1, (len(full_text) // 3000) + 1) if full_text else 0,
        pages=[{"page": 1, "text": full_text}] if full_text else [],
    )


def extract_plain_text(data: bytes) -> ExtractedDocument:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    text = text.strip()
    return ExtractedDocument(
        text=text,
        page_count=max(1, (len(text) // 3000) + 1) if text else 0,
        pages=[{"page": 1, "text": text}] if text else [],
    )


def extract_document_content(data: bytes, extension: str) -> ExtractedDocument:
    """Extract text and page references based on normalized file extension."""
    ext = extension.lower().lstrip(".")
    if ext == "pdf":
        return extract_pdf_text(data)
    if ext == "docx":
        return extract_docx_text(data)
    if ext in ("txt", "md", "csv"):
        return extract_plain_text(data)
    raise ValueError(f"Unsupported document extension: {ext}")

