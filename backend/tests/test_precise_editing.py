"""Pytest test suite for Phase 1B: Precise Editing Engine."""

import io
import json
import zipfile
import pytest

from app.schemas.edit import (
    AmbiguityCheck,
    CodeEditRequest,
    DiffSummary,
    PreciseEditRequest,
    SelectionEditRequest,
)
from app.services.editing_service import (
    VersionStore,
    apply_selection_edit,
    compute_diff,
    detect_ambiguity,
    edit_docx_inplace,
    edit_pptx_inplace,
    execute_precise_edit,
    parse_instructions,
    validate_code_syntax,
    version_store,
)


def run_coro(coro):
    try:
        return coro.send(None)
    except StopIteration as e:
        return e.value


def test_instruction_parsing_numbered_and_bullets():
    inst = "1. change title to Meridian\n2. replace 'old' with 'new'\n3. fix typo"
    items = parse_instructions(inst)
    assert len(items) == 3
    assert items[0] == "change title to Meridian"

    bullets = "- first item\n- second item\n- third item"
    b_items = parse_instructions(bullets)
    assert len(b_items) == 3


def test_multi_instruction_deterministic_edit():
    doc = "# Draft Title\n\nSystem is flawed with teh latency."
    inst = "1. change title to 'Optimal Architecture'\n2. replace 'flawed' with 'performant'\n3. replace 'teh' with 'the'"
    res = run_coro(execute_precise_edit(doc, inst))

    assert res.success is True
    assert len(res.checklist) == 3
    assert all(item.status == "done" for item in res.checklist)
    assert "# Optimal Architecture" in res.edited_text
    assert "performant with the latency" in res.edited_text


def test_minimal_change_rule_byte_identical_outside_target():
    p1 = "Paragraph 1: Background intro.\n\n"
    p2 = "Paragraph 2: Methodology details.\n\n"
    p3 = "Paragraph 3: Results showed initial errors.\n\n"
    p4 = "Paragraph 4: Discussion of results.\n\n"
    p5 = "Paragraph 5: Final conclusions."
    full_doc = p1 + p2 + p3 + p4 + p5

    inst = "replace 'initial errors' with 'improved benchmarks'"
    res = run_coro(execute_precise_edit(full_doc, inst))

    assert res.success is True
    edited = res.edited_text
    prefix = p1 + p2 + "Paragraph 3: Results showed "
    suffix = ".\n\n" + p4 + p5
    assert edited.startswith(prefix)
    assert edited.endswith(suffix)


def test_negative_constraint_preserve_headings():
    doc = "# Header 1\n## Subheader 2\nBody content."
    inst = "replace 'Body content' with 'Refined body content'"
    res = run_coro(execute_precise_edit(doc, inst, constraints={"preserve_headings": True}))

    assert res.success is True
    assert "# Header 1" in res.edited_text
    assert "## Subheader 2" in res.edited_text


def test_quantitative_constraint_word_count():
    doc = "Word " * 60
    inst = "replace 'Word' with 'Term'"
    res = run_coro(execute_precise_edit(doc, inst, constraints={"max_words": 12}))

    assert res.success is True
    assert len(res.edited_text.split()) <= 12


def test_ambiguity_detection_broad_requests():
    amb = detect_ambiguity("make it better", "Some document text.")
    assert amb.is_ambiguous is True
    assert amb.clarifying_question is not None
    assert len(amb.options) >= 3


def test_ambiguity_detection_unspecified_paragraph():
    doc = "Para 1.\n\nPara 2.\n\nPara 3.\n\nPara 4."
    amb = detect_ambiguity("change the paragraph", doc)
    assert amb.is_ambiguous is True
    assert "Which paragraph" in amb.clarifying_question


def test_selection_based_editing_splicing():
    full = "Start block.\n[SELECT_THIS]\nEnd block."
    spliced = apply_selection_edit(full, "[SELECT_THIS]", "[REPLACED]")
    assert spliced == "Start block.\n[REPLACED]\nEnd block."


def test_code_syntax_python_ast():
    valid_code = "def add(x: int, y: int) -> int:\n    return x + y\n"
    valid, err = validate_code_syntax(valid_code, "python")
    assert valid is True
    assert err is None

    bad_code = "def add(x, y\n    return x + y"
    bad, err = validate_code_syntax(bad_code, "python")
    assert bad is False
    assert err is not None


def test_code_syntax_json():
    valid, _ = validate_code_syntax('{"valid": true}', "json")
    assert valid is True

    bad, _ = validate_code_syntax('{invalid: true}', "json")
    assert bad is False


def test_numbered_list_item_edit():
    doc = "1. Item one\n2. Item two\n3. Item three\n4. Item four"
    inst = 'change item 2 to "Item two updated"'
    res = run_coro(execute_precise_edit(doc, inst))
    assert res.success is True
    lines = res.edited_text.splitlines()
    assert lines[1] == "2. Item two updated"
    assert lines[0] == "1. Item one"
    assert lines[2] == "3. Item three"


def test_markdown_table_cell_edit():
    doc = "| ID | Name | Role |\n|---|---|---|\n| 1 | Alice | Member |\n| 2 | Bob | Viewer |"
    inst = 'update cell "Member" to "Admin"'
    res = run_coro(execute_precise_edit(doc, inst))
    assert res.success is True
    assert "| 1 | Alice | Admin |" in res.edited_text
    assert "| 2 | Bob | Viewer |" in res.edited_text


def test_docx_inplace_editing():
    in_buf = io.BytesIO()
    doc_xml = '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Project Genesis</w:t></w:r></w:p></w:body></w:document>'
    with zipfile.ZipFile(in_buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", doc_xml.encode("utf-8"))

    edited = edit_docx_inplace(in_buf.getvalue(), {"Project Genesis": "Project Meridian"})
    with zipfile.ZipFile(io.BytesIO(edited), "r") as z:
        out_xml = z.read("word/document.xml").decode("utf-8")
    assert "Project Meridian" in out_xml
    assert "Project Genesis" not in out_xml


def test_diff_computation():
    orig = "Line 1\nLine 2\nLine 3\n"
    edited = "Line 1\nLine 2 modified\nLine 3\n"
    diff = compute_diff(orig, edited)
    assert diff.added_count == 1
    assert diff.removed_count == 1
    assert len(diff.chunks) > 0


def test_version_store_undo_lifecycle():
    store = VersionStore()
    doc_id = "pytest-doc-1"
    store.get_or_create(doc_id, "v1 text")
    v2 = store.add_version(doc_id, "v2 text", "edit 1")
    v3 = store.add_version(doc_id, "v3 text", "edit 2")

    restored = store.undo(doc_id)
    assert restored.content == "v2 text"

    restored_v1 = store.undo(doc_id)
    assert restored_v1.content == "v1 text"
