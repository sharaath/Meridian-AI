import zipfile
import io
import base64
from app.services.export_service import export_message_pptx


def test_export_pptx_without_images():
    content = """## Slide 1: Introduction
- Overview of meridian
- Core highlights
---
## Slide 2: Next Steps
- Implementation details
- Deployment verification
"""
    pptx_bytes = export_message_pptx(content)
    zf = zipfile.ZipFile(io.BytesIO(pptx_bytes))
    names = zf.namelist()
    assert "ppt/slides/slide1.xml" in names
    assert "ppt/slides/slide2.xml" in names
    slide1 = zf.read("ppt/slides/slide1.xml").decode("utf-8")
    assert "Introduction" in slide1
    assert "Overview of meridian" in slide1
    assert "<p:pic>" not in slide1


def test_export_pptx_with_embedded_images():
    # 1x1 transparent PNG
    raw_png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    images = [("diagram.png", raw_png), ("photo.jpg", raw_png)]

    content = """## Slide 1: Architecture
- System components
- Data flow
---
## Slide 2: Results
- Key metrics
- Performance analysis
"""
    pptx_bytes = export_message_pptx(content, attached_images=images)
    zf = zipfile.ZipFile(io.BytesIO(pptx_bytes))
    names = zf.namelist()

    # Image files embedded in ppt/media/
    assert "ppt/media/image1.png" in names
    assert "ppt/media/image2.jpg" in names

    # Relationships contain image relationship
    rel1 = zf.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
    assert "image1.png" in rel1
    assert "rId2" in rel1

    # Slide 1 XML contains <p:pic> with r:embed="rId2"
    slide1 = zf.read("ppt/slides/slide1.xml").decode("utf-8")
    assert "<p:pic>" in slide1
    assert 'r:embed="rId2"' in slide1

    # Slide 2 XML contains <p:pic>
    slide2 = zf.read("ppt/slides/slide2.xml").decode("utf-8")
    assert "<p:pic>" in slide2


def test_export_pptx_with_markdown_image_tags():
    content = """## Slide 1: Solar Power
![Solar Energy](https://example.com/solar.jpg)
- Clean renewable source
- Photovoltaic cells
---
## Slide 2: Wind Power
- Wind turbines
- Off-shore generation
"""
    # Should not raise exception and should build valid PPTX
    pptx_bytes = export_message_pptx(content)
    zf = zipfile.ZipFile(io.BytesIO(pptx_bytes))
    names = zf.namelist()
    assert "ppt/slides/slide1.xml" in names
    assert "ppt/slides/slide2.xml" in names

