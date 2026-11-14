"""Export conversations and individual AI responses to TXT, PDF, DOCX, and PPTX."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import List, Sequence, Tuple
from xml.sax.saxutils import escape

from fpdf import FPDF, XPos, YPos

from app.models.tables import Conversation, Message


def export_conversation_txt(conversation: Conversation, messages: Sequence[Message]) -> bytes:
    lines = [
        f"Meridian AI — Conversation Export",
        f"Title: {conversation.title}",
        f"Mode: {conversation.mode}",
        f"Created: {conversation.created_at.isoformat()}",
        "=" * 60,
        "",
    ]
    for msg in messages:
        role_label = "You" if msg.role == "user" else "Meridian"
        lines.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M UTC')}] {role_label}:")
        lines.append(msg.content)
        if msg.citations_json:
            lines.append("Sources:")
            for idx, cite in enumerate(msg.citations_json, start=1):
                lines.append(f"  [{idx}] {cite.get('title', 'Source')} - {cite.get('url', '')}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _latin1_safe(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _safe_multi_cell(pdf: FPDF, height: float, text: str) -> None:
    cleaned = _latin1_safe(text)
    if not cleaned:
        return
    pdf.set_x(pdf.l_margin)
    try:
        pdf.multi_cell(pdf.epw, height, cleaned, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    except Exception:
        # Fallback to character wrapping for unbreakable strings (e.g. long URLs)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, height, cleaned, wrapmode="CHAR", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def export_conversation_pdf(conversation: Conversation, messages: Sequence[Message]) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    _safe_multi_cell(pdf, 8, conversation.title or "Meridian AI Conversation")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(
        0,
        6,
        _latin1_safe(f"Mode: {conversation.mode} | Exported from Meridian AI"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(4)

    for msg in messages:
        role_label = "You" if msg.role == "user" else "Meridian"
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(
            0,
            7,
            _latin1_safe(f"{role_label} ({msg.created_at.strftime('%Y-%m-%d %H:%M UTC')})"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(51, 65, 85)
        _safe_multi_cell(pdf, 5.5, msg.content)
        pdf.ln(3)

    return bytes(pdf.output())


def _strip_inline_md(text: str) -> str:
    return text.replace("**", "").replace("__", "").replace("`", "")


def export_message_pdf(
    content: str,
    title: str = "Meridian Document",
    embedded_logos: Sequence[bytes] | None = None,
) -> bytes:
    """Render a single Markdown AI response (e.g. resume, report, letter) as a clean standalone PDF."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if embedded_logos:
        try:
            logo_stream = io.BytesIO(embedded_logos[0])
            pdf.image(logo_stream, x=15, y=12, h=14)
            pdf.set_y(30)
        except Exception:
            pass

    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            pdf.ln(3)
            i += 1
            continue
        if line in ("---", "***", "___"):
            y = pdf.get_y()
            pdf.set_draw_color(203, 213, 225)
            pdf.line(15, y, 195, y)
            pdf.ln(3)
            i += 1
            continue

        # Markdown table support
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?\s*[-:]+[-|\s:]*$", lines[i + 1]):
            def _parse_row(r: str) -> List[str]:
                return [c.strip() for c in r.strip().strip("|").split("|")]

            headers = _parse_row(line)
            i += 2
            rows: List[List[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_parse_row(lines[i]))
                i += 1
            col_count = max(1, len(headers))
            col_w = pdf.epw / col_count
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_fill_color(241, 245, 249)
            pdf.set_text_color(15, 23, 42)
            pdf.set_x(pdf.l_margin)
            for h in headers:
                pdf.cell(col_w, 7, _latin1_safe(_strip_inline_md(h)[:40]), border=1, fill=True)
            pdf.ln(7)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(51, 65, 85)
            for row in rows:
                pdf.set_x(pdf.l_margin)
                for idx in range(col_count):
                    val = row[idx] if idx < len(row) else ""
                    pdf.cell(col_w, 6.5, _latin1_safe(_strip_inline_md(val)[:42]), border=1)
                pdf.ln(6.5)
            pdf.ln(3)
            continue

        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 16)
            pdf.set_text_color(15, 23, 42)
            _safe_multi_cell(pdf, 8, _strip_inline_md(line[2:].strip()))
            pdf.ln(1)
            i += 1
            continue
        if line.startswith("## "):
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(13, 148, 136)
            _safe_multi_cell(pdf, 7, _strip_inline_md(line[3:].strip()))
            pdf.ln(1)
            i += 1
            continue
        if line.startswith("### "):
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(15, 23, 42)
            _safe_multi_cell(pdf, 6, _strip_inline_md(line[4:].strip()))
            i += 1
            continue
        if line.startswith("- ") or line.startswith("* "):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(51, 65, 85)
            _safe_multi_cell(pdf, 5.5, f"  - {_strip_inline_md(line[2:].strip())}")
            i += 1
            continue

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(51, 65, 85)
        _safe_multi_cell(pdf, 5.5, _strip_inline_md(line))
        i += 1

    if not lines:
        pdf.set_font("Helvetica", "B", 14)
        _safe_multi_cell(pdf, 8, title)

    return bytes(pdf.output())


def _docx_inline_runs(text: str, base_bold: bool, color: str, size_half_pts: str) -> str:
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    runs: List[str] = []
    for part in parts:
        if not part:
            continue
        is_bold = base_bold
        clean = part
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            is_bold = True
            clean = part[2:-2]
        clean = clean.replace("`", "")
        bold_tag = "<w:b/>" if is_bold else ""
        runs.append(
            f"<w:r><w:rPr>{bold_tag}<w:color w:val=\"{color}\"/><w:sz w:val=\"{size_half_pts}\"/></w:rPr>"
            f"<w:t xml:space=\"preserve\">{escape(clean)}</w:t></w:r>"
        )
    return "".join(runs)


def _docx_table_xml(headers: List[str], rows: List[List[str]]) -> str:
    col_count = max(1, len(headers))
    tbl_pr = (
        "<w:tblPr><w:tblBorders>"
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        "</w:tblBorders></w:tblPr>"
    )

    def _row_xml(cells: List[str], is_header: bool) -> str:
        shd = '<w:shd w:val="clear" w:color="auto" w:fill="F1F5F9"/>' if is_header else ""
        xml_cells = []
        for idx in range(col_count):
            val = cells[idx] if idx < len(cells) else ""
            runs = _docx_inline_runs(val, is_header, "0F172A" if is_header else "1E293B", "20")
            xml_cells.append(f"<w:tc><w:tcPr>{shd}</w:tcPr><w:p>{runs}</w:p></w:tc>")
        return f"<w:tr>{''.join(xml_cells)}</w:tr>"

    all_rows = [_row_xml(headers, True)] + [_row_xml(r, False) for r in rows]
    return f"<w:tbl>{tbl_pr}{''.join(all_rows)}</w:tbl>"


def _extract_template_assets(template_docx_bytes: bytes) -> tuple[str, str, List[str]]:
    """Extract <w:document ...> open tag, <w:sectPr>...</w:sectPr>, and logo <w:p> drawing blocks."""
    default_doc_open = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    default_sect = "<w:sectPr/>"
    drawing_paragraphs: List[str] = []

    try:
        with zipfile.ZipFile(io.BytesIO(template_docx_bytes)) as zf:
            xml_text = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        doc_open_match = re.search(r"<w:document\b[^>]*>", xml_text)
        doc_open = doc_open_match.group(0) if doc_open_match else default_doc_open
        sect_match = re.search(r"<w:sectPr\b[\s\S]*?</w:sectPr>", xml_text)
        sect_pr = sect_match.group(0) if sect_match else default_sect

        for para_match in re.finditer(r"<w:p\b[\s\S]*?</w:p>", xml_text):
            para_xml = para_match.group(0)
            if "<w:drawing" in para_xml or "<w:pict" in para_xml or "<v:imagedata" in para_xml:
                drawing_paragraphs.append(para_xml)
                if len(drawing_paragraphs) >= 4:
                    break
        return doc_open, sect_pr, drawing_paragraphs
    except Exception:
        return default_doc_open, default_sect, []


def export_message_docx(
    content: str,
    title: str = "Meridian Document",
    template_docx_bytes: bytes | None = None,
) -> bytes:
    """Build a valid Microsoft Word (.docx) package, preserving uploaded template styles, headers, and logos when supplied."""
    body_blocks_xml: List[str] = []
    lines = content.splitlines() or [title]
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            body_blocks_xml.append("<w:p/>")
            i += 1
            continue

        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?\s*[-:]+[-|\s:]*$", lines[i + 1]):
            def _parse_row(r: str) -> List[str]:
                return [c.strip() for c in r.strip().strip("|").split("|")]

            headers = _parse_row(line)
            i += 2
            rows: List[List[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_parse_row(lines[i]))
                i += 1
            body_blocks_xml.append(_docx_table_xml(headers, rows))
            continue

        is_bold = False
        size_half_pts = "22"
        color = "1E293B"
        text = line

        if line.startswith("# "):
            is_bold = True
            size_half_pts = "34"
            color = "0F172A"
            text = line[2:].strip()
        elif line.startswith("## "):
            is_bold = True
            size_half_pts = "28"
            color = "0D9488"
            text = line[3:].strip()
        elif line.startswith("### "):
            is_bold = True
            size_half_pts = "24"
            color = "0F172A"
            text = line[4:].strip()
        elif line.startswith("- ") or line.startswith("* "):
            text = f"•  {line[2:].strip()}"

        runs_xml = _docx_inline_runs(text, is_bold, color, size_half_pts)
        body_blocks_xml.append(f'<w:p><w:pPr><w:spacing w:after="120"/></w:pPr>{runs_xml}</w:p>')
        i += 1

    if template_docx_bytes:
        doc_open, sect_pr, logo_paras = _extract_template_assets(template_docx_bytes)
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f"{doc_open}<w:body>{''.join(logo_paras)}{''.join(body_blocks_xml)}{sect_pr}</w:body></w:document>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(template_docx_bytes), "r") as src_zf, zipfile.ZipFile(
            buf, "w", zipfile.ZIP_DEFLATED
        ) as dst_zf:
            for item in src_zf.infolist():
                if item.filename == "word/document.xml":
                    dst_zf.writestr("word/document.xml", document_xml.encode("utf-8"))
                else:
                    dst_zf.writestr(item, src_zf.read(item.filename))
        return buf.getvalue()

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body_blocks_xml)}<w:sectPr/></w:body>"
        "</w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def _split_slides(content: str, fallback_title: str) -> List[Tuple[str, List[str], Optional[str]]]:
    slides: List[Tuple[str, List[str], Optional[str]]] = []
    current_title = ""
    current_body: List[str] = []
    current_img_url: Optional[str] = None

    for raw in content.splitlines():
        line = raw.strip()
        if line in ("---", "***", "___"):
            if current_title or current_body:
                slides.append((current_title or f"Slide {len(slides) + 1}", current_body, current_img_url))
                current_title = ""
                current_body = []
                current_img_url = None
            continue

        heading_match = re.match(r"^#{1,3}\s+(.*)$", line)
        slide_prefix_match = re.match(r"^(?:\*\*)?Slide\s+\d+\s*[:\-–]\s*(.*?)(?:\*\*)?$", line, re.IGNORECASE)

        if heading_match or slide_prefix_match:
            if current_title or current_body:
                slides.append((current_title or f"Slide {len(slides) + 1}", current_body, current_img_url))
            current_title = _strip_inline_md(
                (slide_prefix_match.group(1) if slide_prefix_match else heading_match.group(1)).strip()
            )
            current_body = []
            current_img_url = None
            continue

        img_match = re.search(r"!\[(.*?)\]\((https?://[^\s)]+|/[^\s)]+)\)", line)
        if img_match:
            current_img_url = img_match.group(2)
            continue

        if line:
            cleaned = _strip_inline_md(re.sub(r"^[-*]\s+", "• ", line))
            current_body.append(cleaned)

    if current_title or current_body:
        slides.append((current_title or fallback_title, current_body, current_img_url))

    if not slides:
        slides.append((fallback_title, [content.strip() or "Generated by Meridian AI"], None))
    return slides


def export_message_pptx(
    content: str,
    title: str = "Meridian Presentation",
    attached_images: Optional[List[Tuple[str, bytes]]] = None,
) -> bytes:
    """Build a valid editable PowerPoint (.pptx) OOXML presentation from Markdown slides with optional embedded images."""
    slides = _split_slides(content, title)

    slide_overrides = []
    slide_rels_entries = []
    sld_id_entries = []
    images = list(attached_images or [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, (s_title, s_bullets, s_img_url) in enumerate(slides, start=1):
            slide_overrides.append(
                f'<Override PartName="/ppt/slides/slide{idx}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            )
            slide_rels_entries.append(
                f'<Relationship Id="rId{idx + 1}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
                f'Target="slides/slide{idx}.xml"/>'
            )
            sld_id_entries.append(f'<p:sldId id="{255 + idx}" r:id="rId{idx + 1}"/>')

            # Optional slide image embedding from URL or attached images
            img_bytes = None
            ext = "jpg"
            if s_img_url and s_img_url.startswith(("http://", "https://")):
                try:
                    import urllib.request
                    req = urllib.request.Request(s_img_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=8) as r:
                        img_bytes = r.read()
                        ctype = r.headers.get("Content-Type", "")
                        if "png" in ctype:
                            ext = "png"
                        elif "jpeg" in ctype or "jpg" in ctype:
                            ext = "jpg"
                except Exception:
                    img_bytes = None
            elif images and (idx - 1) < len(images):
                img_filename, raw_b = images[idx - 1]
                img_bytes = raw_b
                ext = Path(img_filename).suffix.lstrip(".").lower() or "png"
                if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
                    ext = "png"

            slide_img_rel = ""
            pic_xml = ""
            if img_bytes:
                img_path = f"ppt/media/image{idx}.{ext}"
                zf.writestr(img_path, img_bytes)
                slide_img_rel = (
                    f'<Relationship Id="rId2" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    f'Target="../media/image{idx}.{ext}"/>'
                )
                pic_xml = (
                    f'<p:pic><p:nvPicPr><p:cNvPr id="{10 + idx}" name="SlidePicture{idx}"/>'
                    '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
                    '<p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
                    '<p:spPr><a:xfrm><a:off x="6400000" y="1650000"/><a:ext cx="5100000" cy="4500000"/></a:xfrm>'
                    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
                )

            # Two-column layout if image present, full width if text only
            content_cx = "5300000" if pic_xml else "10820400"

            body_paragraphs = "".join(
                "<a:p><a:pPr marL=\"0\" indent=\"0\"><a:spcAft><a:spcPts val=\"800\"/></a:spcAft></a:pPr>"
                f"<a:r><a:rPr lang=\"en-US\" sz=\"1800\" dirty=\"0\"><a:solidFill><a:srgbClr val=\"1E293B\"/></a:solidFill></a:rPr>"
                f"<a:t>{escape(b)}</a:t></a:r></a:p>"
                for b in (s_bullets[:14] or [""])
            )

            slide_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
                "<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val=\"FAF9F6\"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>"
                "<p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
                "<p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/>"
                "<a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>"
                # Top accent bar
                "<p:sp><p:nvSpPr><p:cNvPr id=\"2\" name=\"AccentBar\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
                "<p:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"12192000\" cy=\"140000\"/></a:xfrm>"
                "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom>"
                "<a:solidFill><a:srgbClr val=\"0D9488\"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr></p:sp>"
                # Title box
                "<p:sp><p:nvSpPr><p:cNvPr id=\"3\" name=\"Title\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr>"
                "<p:nvPr><p:ph type=\"title\"/></p:nvPr></p:nvSpPr>"
                "<p:spPr><a:xfrm><a:off x=\"685800\" y=\"420000\"/><a:ext cx=\"10820400\" cy=\"1100000\"/></a:xfrm>"
                "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr>"
                "<p:txBody><a:bodyPr/><a:lstStyle/>"
                "<a:p><a:r><a:rPr lang=\"en-US\" sz=\"3200\" b=\"1\" dirty=\"0\">"
                "<a:solidFill><a:srgbClr val=\"0F172A\"/></a:solidFill></a:rPr>"
                f"<a:t>{escape(s_title)}</a:t></a:r></a:p></p:txBody></p:sp>"
                # Body box
                "<p:sp><p:nvSpPr><p:cNvPr id=\"4\" name=\"Content\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr>"
                "<p:nvPr><p:ph idx=\"1\"/></p:nvPr></p:nvSpPr>"
                f"<p:spPr><a:xfrm><a:off x=\"685800\" y=\"1650000\"/><a:ext cx=\"{content_cx}\" cy=\"4650000\"/></a:xfrm>"
                "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr>"
                f"<p:txBody><a:bodyPr wrap=\"square\"/><a:lstStyle/>{body_paragraphs}</p:txBody></p:sp>"
                f"{pic_xml}"
                "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
            )
            zf.writestr(f"ppt/slides/slide{idx}.xml", slide_xml)
            zf.writestr(
                f"ppt/slides/_rels/slide{idx}.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" '
                'Target="../slideLayouts/slideLayout1.xml"/>'
                f"{slide_img_rel}"
                "</Relationships>",
            )

        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Default Extension="jpg" ContentType="image/jpeg"/>'
            '<Default Extension="jpeg" ContentType="image/jpeg"/>'
            '<Default Extension="webp" ContentType="image/webp"/>'
            '<Default Extension="gif" ContentType="image/gif"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
            '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            f"{''.join(slide_overrides)}</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="ppt/presentation.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "ppt/presentation.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
            f'<p:sldIdLst>{"".join(sld_id_entries)}</p:sldIdLst>'
            '<p:sldSz cx="12192000" cy="6858000"/>'
            '<p:notesSz cx="6858000" cy="9144000"/>'
            "</p:presentation>",
        )
        zf.writestr(
            "ppt/_rels/presentation.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" '
            'Target="slideMasters/slideMaster1.xml"/>'
            f"{''.join(slide_rels_entries)}</Relationships>",
        )
        zf.writestr(
            "ppt/slideMasters/slideMaster1.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            "<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
            "<p:grpSpPr/></p:spTree></p:cSld>"
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
            'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
            "</p:sldMaster>",
        )
        zf.writestr(
            "ppt/slideMasters/_rels/slideMaster1.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" '
            'Target="../slideLayouts/slideLayout1.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" '
            'Target="../theme/theme1.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "ppt/slideLayouts/slideLayout1.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="obj">'
            "<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
            "<p:grpSpPr/></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>",
        )
        zf.writestr(
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" '
            'Target="../slideMasters/slideMaster1.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "ppt/theme/theme1.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Meridian">'
            '<a:themeElements><a:clrScheme name="Meridian">'
            '<a:dk1><a:srgbClr val="0F172A"/></a:dk1><a:lt1><a:srgbClr val="FAF9F6"/></a:lt1>'
            '<a:dk2><a:srgbClr val="1E293B"/></a:dk2><a:lt2><a:srgbClr val="F4F2ED"/></a:lt2>'
            '<a:accent1><a:srgbClr val="0D9488"/></a:accent1><a:accent2><a:srgbClr val="14B8A6"/></a:accent2>'
            '<a:accent3><a:srgbClr val="38BDF8"/></a:accent3><a:accent4><a:srgbClr val="FBBF24"/></a:accent4>'
            '<a:accent5><a:srgbClr val="34D399"/></a:accent5><a:accent6><a:srgbClr val="64748B"/></a:accent6>'
            '<a:hlink><a:srgbClr val="0D9488"/></a:hlink><a:folHlink><a:srgbClr val="0F766E"/></a:folHlink>'
            '</a:clrScheme><a:fontScheme name="Meridian"><a:majorFont><a:latin typeface="Calibri"/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Calibri"/></a:minorFont></a:fontScheme>'
            '<a:fmtScheme name="Meridian"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
            '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
            '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
            '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
            '</a:fmtScheme></a:themeElements></a:theme>',
        )
    return buf.getvalue()

