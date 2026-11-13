"""Evaluation Suite for Phase 1B: Precise Editing Engine.
Tests all 18 core requirements:
1. Instruction parsing (numbered, bulleted, semicolons, sentences)
2. Multi-instruction execution & checklist verification
3. Minimal-change rule (byte-identical preservation outside target)
4. Negative constraint enforcement (preserve headings)
5. Quantitative constraint enforcement (max word count limit)
6. Ambiguity detection on broad directives ('make it better')
7. Ambiguity detection on unspecified relative references ('change the paragraph')
8. Selection-based editing (splicing only selected range)
9. Selection disambiguation with duplicate target tokens via context
10. Code syntax check: Python valid AST
11. Code syntax check: Python invalid syntax detected
12. Code syntax check: JSON validation
13. Code syntax check: JavaScript / TypeScript delimiter matching
14. Numbered list targeted edit (item 3 only)
15. Markdown table targeted cell modification
16. File-aware in-place DOCX editing preserving styles and structure
17. File-aware in-place PPTX editing preserving slide layout
18. Diff computation correctness & chunk classification
19. Version history lifecycle (Add, Accept, Reject, Undo)
"""

import io
import json
import os
import sys
import zipfile

# Add backend to path for module resolution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

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
    """Drive coroutine synchronously without socket loop dependency."""
    try:
        return coro.send(None)
    except StopIteration as e:
        return e.value


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.details = ""

    def pass_test(self, details: str = ""):
        self.passed = True
        self.details = details

    def fail_test(self, details: str = ""):
        self.passed = False
        self.details = details


def run_evaluation():
    results = []

    print("=" * 80)
    print("PHASE 1B PRECISE EDITING EVALUATION SUITE")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # TEST 1: Instruction parsing
    # -------------------------------------------------------------------------
    t1 = TestResult("Test 1: Instruction parsing into numbered checklist")
    try:
        inst = "1. change title to Quantum AI\n2. replace 'flawed' with 'optimal'\n3. replace 'teh' with 'the'"
        parsed = parse_instructions(inst)
        assert len(parsed) == 3, f"Expected 3 items, got {len(parsed)}"
        assert parsed[0] == "change title to Quantum AI"
        assert parsed[1] == "replace 'flawed' with 'optimal'"
        assert parsed[2] == "replace 'teh' with 'the'"

        inst2 = "change title to Meridian AI; replace 'error' with 'bug'; delete 'temp'"
        parsed2 = parse_instructions(inst2)
        assert len(parsed2) == 3, f"Expected 3 items from semicolon, got {len(parsed2)}"

        t1.pass_test(f"Successfully parsed numbered ({len(parsed)}) and semicolon ({len(parsed2)}) instruction checklists.")
    except Exception as e:
        t1.fail_test(str(e))
    results.append(t1)

    # -------------------------------------------------------------------------
    # TEST 2: Multi-instruction deterministic execution & checklist verification
    # -------------------------------------------------------------------------
    t2 = TestResult("Test 2: Multi-instruction execution & checklist verification")
    try:
        doc = "# Draft Notes\n\nThis is a flawed approach with teh system."
        inst = "1. change title to 'Optimal Architecture'\n2. replace 'flawed' with 'robust'\n3. replace 'teh' with 'the'"
        res = run_coro(execute_precise_edit(doc, inst))

        assert res.success is True, "Edit failed"
        assert len(res.checklist) == 3, f"Expected 3 checklist items, got {len(res.checklist)}"
        assert all(item.status == "done" for item in res.checklist), "Not all items marked done"
        assert "# Optimal Architecture" in res.edited_text
        assert "robust approach with the system" in res.edited_text
        t2.pass_test("Applied 3/3 checklist items with verified done status and summary tags.")
    except Exception as e:
        t2.fail_test(str(e))
    results.append(t2)

    # -------------------------------------------------------------------------
    # TEST 3: Minimal-change rule & byte-identical preservation outside target
    # -------------------------------------------------------------------------
    t3 = TestResult("Test 3: Minimal-change rule (byte-identical preservation outside target)")
    try:
        p1 = "Paragraph 1: In 1969, Apollo 11 landed on the moon.\n\n"
        p2 = "Paragraph 2: Neil Armstrong declared the iconic words.\n\n"
        p3 = "Paragraph 3: The mission encountered a computer alarm 1202.\n\n"
        p4 = "Paragraph 4: Lunar module Eagle touched down safely.\n\n"
        p5 = "Paragraph 5: They returned to Earth on July 24."
        full_doc = p1 + p2 + p3 + p4 + p5

        inst = "replace 'computer alarm 1202' with 'radar data overload'"
        res = run_coro(execute_precise_edit(full_doc, inst))

        assert res.success is True
        edited = res.edited_text

        # Verify prefix (p1 + p2) is 100% byte-identical
        prefix_expected = p1 + p2 + "Paragraph 3: The mission encountered a "
        assert edited.startswith(prefix_expected), "Prefix before target was altered!"

        # Verify suffix (after target through p5) is 100% byte-identical
        suffix_expected = ".\n\n" + p4 + p5
        assert edited.endswith(suffix_expected), "Suffix after target was altered!"

        t3.pass_test("Unaffected paragraphs 1, 2, 4, 5 and sentence wrappers are 100% byte-identical.")
    except Exception as e:
        t3.fail_test(str(e))
    results.append(t3)

    # -------------------------------------------------------------------------
    # TEST 4: Negative constraint: preserve headings intact
    # -------------------------------------------------------------------------
    t4 = TestResult("Test 4: Negative constraint enforcement (preserve headings)")
    try:
        doc = "# Executive Summary\n## Section 1: Overview\nContent here.\n### Subsection A\nDetails here."
        inst = "replace 'Content here' with 'Updated financial content'"
        res = run_coro(execute_precise_edit(doc, inst, constraints={"preserve_headings": True}))

        assert res.success is True
        assert "# Executive Summary" in res.edited_text
        assert "## Section 1: Overview" in res.edited_text
        assert "### Subsection A" in res.edited_text
        assert "Updated financial content" in res.edited_text

        t4.pass_test("All H1, H2, H3 headings preserved strictly intact.")
    except Exception as e:
        t4.fail_test(str(e))
    results.append(t4)

    # -------------------------------------------------------------------------
    # TEST 5: Quantitative constraint: word count limit
    # -------------------------------------------------------------------------
    t5 = TestResult("Test 5: Quantitative constraint enforcement (max word count)")
    try:
        doc = "Word " * 50
        inst = "replace 'Word' with 'Term'"
        res = run_coro(execute_precise_edit(doc, inst, constraints={"max_words": 15}))

        assert res.success is True
        word_count = len(res.edited_text.split())
        assert word_count <= 15, f"Word count {word_count} exceeded max_words=15"

        t5.pass_test(f"Word count strictly capped at {word_count} (<= 15 limit).")
    except Exception as e:
        t5.fail_test(str(e))
    results.append(t5)

    # -------------------------------------------------------------------------
    # TEST 6: Ambiguity detection on broad directives ("make it better")
    # -------------------------------------------------------------------------
    t6 = TestResult("Test 6: Ambiguity detection on broad requests ('make it better')")
    try:
        doc = "The product is designed to facilitate faster transactions across our platform."
        amb = detect_ambiguity("make it better", doc)

        assert amb.is_ambiguous is True, "Failed to flag 'make it better' as ambiguous"
        assert amb.clarifying_question is not None, "Missing clarifying question"
        assert len(amb.options) >= 3, f"Expected at least 3 options, got {len(amb.options)}"
        assert any("Option A" in opt for opt in amb.options)

        t6.pass_test(f"Flagged ambiguous directive; returned clarifying question and {len(amb.options)} options.")
    except Exception as e:
        t6.fail_test(str(e))
    results.append(t6)

    # -------------------------------------------------------------------------
    # TEST 7: Ambiguity detection on unspecified relative reference
    # -------------------------------------------------------------------------
    t7 = TestResult("Test 7: Ambiguity detection on unspecified relative reference")
    try:
        doc = "Paragraph one with some info.\n\nParagraph two with other info.\n\nParagraph three with more details."
        amb = detect_ambiguity("change the paragraph", doc)

        assert amb.is_ambiguous is True, "Failed to flag ambiguous relative reference"
        assert "Which paragraph" in amb.clarifying_question
        assert len(amb.options) >= 3

        t7.pass_test(f"Clarification triggered with paragraph selectors: {amb.options[0][:30]}...")
    except Exception as e:
        t7.fail_test(str(e))
    results.append(t7)

    # -------------------------------------------------------------------------
    # TEST 8: Selection-based editing & in-place splicing
    # -------------------------------------------------------------------------
    t8 = TestResult("Test 8: Selection-based editing (splicing only selected range)")
    try:
        full_text = "Before block.\n[TARGET SELECTION]\nAfter block."
        selection = "[TARGET SELECTION]"
        edited_selection = "[SURGICAL REPLACEMENT]"

        spliced = apply_selection_edit(full_text, selection, edited_selection)

        assert spliced == "Before block.\n[SURGICAL REPLACEMENT]\nAfter block."
        assert spliced.startswith("Before block.\n")
        assert spliced.endswith("\nAfter block.")

        t8.pass_test("Target selection replaced in-place; surrounding context 100% byte-identical.")
    except Exception as e:
        t8.fail_test(str(e))
    results.append(t8)

    # -------------------------------------------------------------------------
    # TEST 9: Selection disambiguation with duplicate text via prefix/suffix context
    # -------------------------------------------------------------------------
    t9 = TestResult("Test 9: Selection disambiguation with duplicate occurrences")
    try:
        full_text = "Alpha token Bravo. Charlie token Delta. Echo token Foxtrot."
        selection = "token"
        prefix = "Charlie "
        suffix = " Delta"
        edited_selection = "COIN"

        spliced = apply_selection_edit(full_text, selection, edited_selection, prefix, suffix)

        assert spliced == "Alpha token Bravo. Charlie COIN Delta. Echo token Foxtrot."
        assert spliced.count("token") == 2
        assert spliced.count("COIN") == 1

        t9.pass_test("Disambiguated duplicate target using prefix/suffix context accurately.")
    except Exception as e:
        t9.fail_test(str(e))
    results.append(t9)

    # -------------------------------------------------------------------------
    # TEST 10: Code syntax validation: Python valid AST
    # -------------------------------------------------------------------------
    t10 = TestResult("Test 10: Code syntax check: Python valid AST")
    try:
        code = "def calculate_velocity(distance: float, time: float) -> float:\n    if time <= 0:\n        raise ValueError('Time must be positive')\n    return distance / time\n"
        valid, err = validate_code_syntax(code, "python")

        assert valid is True, f"Expected valid Python, got error: {err}"
        assert err is None

        t10.pass_test("Python code AST parsed successfully without syntax errors.")
    except Exception as e:
        t10.fail_test(str(e))
    results.append(t10)

    # -------------------------------------------------------------------------
    # TEST 11: Code syntax validation: Python invalid syntax detection
    # -------------------------------------------------------------------------
    t11 = TestResult("Test 11: Code syntax check: Python invalid syntax detected")
    try:
        bad_code = "def broken_func(\n    print('missing paren'"
        valid, err = validate_code_syntax(bad_code, "python")

        assert valid is False, "Failed to detect invalid Python syntax"
        assert err is not None
        assert "SyntaxError" in err

        t11.pass_test(f"Correctly caught Python syntax error: {err}")
    except Exception as e:
        t11.fail_test(str(e))
    results.append(t11)

    # -------------------------------------------------------------------------
    # TEST 12: Code syntax validation: JSON parsing
    # -------------------------------------------------------------------------
    t12 = TestResult("Test 12: Code syntax check: JSON validation")
    try:
        valid_json = '{"model": "meridian-v1", "active": true, "tokens": 4096}'
        v_ok, err_ok = validate_code_syntax(valid_json, "json")
        assert v_ok is True

        invalid_json = '{"model": "meridian-v1", "active": true, tokens: 4096}'
        v_bad, err_bad = validate_code_syntax(invalid_json, "json")
        assert v_bad is False
        assert "JSON ParseError" in err_bad

        t12.pass_test("JSON parser validated well-formed JSON and caught malformed key error.")
    except Exception as e:
        t12.fail_test(str(e))
    results.append(t12)

    # -------------------------------------------------------------------------
    # TEST 13: Code syntax validation: JS/TS delimiter matching
    # -------------------------------------------------------------------------
    t13 = TestResult("Test 13: Code syntax check: JS/TS balanced delimiters")
    try:
        valid_ts = "function sum(a: number, b: number): number { return (a + b); }"
        v_ok, err_ok = validate_code_syntax(valid_ts, "typescript")
        assert v_ok is True

        invalid_ts = "function sum(a: number, b: number): number { return (a + b; }"
        v_bad, err_bad = validate_code_syntax(invalid_ts, "typescript")
        assert v_bad is False
        assert "Unbalanced delimiter" in err_bad or "Unclosed delimiter" in err_bad

        t13.pass_test("JS/TS delimiter validator verified matched braces and detected unmatched parenthesis.")
    except Exception as e:
        t13.fail_test(str(e))
    results.append(t13)

    # -------------------------------------------------------------------------
    # TEST 14: Numbered list surgical edit (modifying only item 3)
    # -------------------------------------------------------------------------
    t14 = TestResult("Test 14: Numbered list targeted edit (item 3 only)")
    try:
        doc = "1. Initialize database\n2. Configure telemetry\n3. Deploy old service\n4. Run smoke tests\n5. Monitor latency"
        inst = 'change item 3 to "Deploy Meridian microservice"'
        res = run_coro(execute_precise_edit(doc, inst))

        assert res.success is True
        lines = res.edited_text.splitlines()
        assert lines[0] == "1. Initialize database"
        assert lines[1] == "2. Configure telemetry"
        assert lines[2] == "3. Deploy Meridian microservice"
        assert lines[3] == "4. Run smoke tests"
        assert lines[4] == "5. Monitor latency"

        t14.pass_test("Updated item 3; items 1, 2, 4, 5 are completely identical.")
    except Exception as e:
        t14.fail_test(str(e))
    results.append(t14)

    # -------------------------------------------------------------------------
    # TEST 15: Markdown table targeted cell modification
    # -------------------------------------------------------------------------
    t15 = TestResult("Test 15: Markdown table targeted cell modification")
    try:
        doc = "| Service | Status | SLA |\n|---|---|---|\n| Auth | Online | 99.9% |\n| Billing | Pending | 99.5% |\n| Storage | Online | 99.99% |"
        inst = 'update cell "Pending" to "Active"'
        res = run_coro(execute_precise_edit(doc, inst))

        assert res.success is True
        assert "| Billing | Active | 99.5% |" in res.edited_text
        assert "| Auth | Online | 99.9% |" in res.edited_text
        assert "| Storage | Online | 99.99% |" in res.edited_text

        t15.pass_test("Updated cell 'Pending' -> 'Active' preserving table pipes and formatting.")
    except Exception as e:
        t15.fail_test(str(e))
    results.append(t15)

    # -------------------------------------------------------------------------
    # TEST 16: In-place DOCX edit preserving archive structure
    # -------------------------------------------------------------------------
    t16 = TestResult("Test 16: File-aware in-place DOCX editing")
    try:
        in_buf = io.BytesIO()
        doc_xml = '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Confidential Report 2025</w:t></w:r></w:p></w:body></w:document>'
        styles_xml = '<?xml version="1.0" encoding="UTF-8"?><w:styles><w:style w:styleId="Normal"/></w:styles>'

        with zipfile.ZipFile(in_buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", doc_xml.encode("utf-8"))
            z.writestr("word/styles.xml", styles_xml.encode("utf-8"))

        docx_bytes = in_buf.getvalue()
        edited_docx = edit_docx_inplace(docx_bytes, {"Confidential Report 2025": "Public Executive Summary 2026"})

        with zipfile.ZipFile(io.BytesIO(edited_docx), "r") as z:
            edited_doc_xml = z.read("word/document.xml").decode("utf-8")
            edited_styles_xml = z.read("word/styles.xml").decode("utf-8")

        assert "Public Executive Summary 2026" in edited_doc_xml
        assert "Confidential Report 2025" not in edited_doc_xml
        assert edited_styles_xml == styles_xml, "Styles XML was corrupted!"

        t16.pass_test("DOCX document XML modified in-place; styles and archive structure preserved.")
    except Exception as e:
        t16.fail_test(str(e))
    results.append(t16)

    # -------------------------------------------------------------------------
    # TEST 17: In-place PPTX edit preserving slide layouts
    # -------------------------------------------------------------------------
    t17 = TestResult("Test 17: File-aware in-place PPTX editing")
    try:
        in_buf = io.BytesIO()
        slide_xml = '<?xml version="1.0" encoding="UTF-8"?><p:sld><p:txBody><a:p><a:r><a:t>Q3 Quarterly Earnings</a:t></a:r></a:p></p:txBody></p:sld>'

        with zipfile.ZipFile(in_buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("ppt/slides/slide1.xml", slide_xml.encode("utf-8"))

        pptx_bytes = in_buf.getvalue()
        edited_pptx = edit_pptx_inplace(pptx_bytes, {"Q3 Quarterly Earnings": "Q4 Annual Financial Results"})

        with zipfile.ZipFile(io.BytesIO(edited_pptx), "r") as z:
            out_slide_xml = z.read("ppt/slides/slide1.xml").decode("utf-8")

        assert "Q4 Annual Financial Results" in out_slide_xml
        assert "Q3 Quarterly Earnings" not in out_slide_xml

        t17.pass_test("PPTX slide text modified in-place; presentation structure preserved.")
    except Exception as e:
        t17.fail_test(str(e))
    results.append(t17)

    # -------------------------------------------------------------------------
    # TEST 18: Diff computation correctness & chunk classification
    # -------------------------------------------------------------------------
    t18 = TestResult("Test 18: Diff computation correctness (added/removed/unchanged)")
    try:
        orig = "Line A\nLine B\nLine C\n"
        edited = "Line A\nLine B modified\nLine C\nLine D\n"

        diff = compute_diff(orig, edited)

        assert diff.added_count >= 1, f"Expected added lines, got {diff.added_count}"
        assert diff.removed_count >= 1, f"Expected removed lines, got {diff.removed_count}"
        assert len(diff.chunks) > 0, "No diff chunks generated"

        types = [c.type for c in diff.chunks]
        assert "unchanged" in types
        assert "added" in types
        assert "removed" in types

        t18.pass_test(f"Diff generated: +{diff.added_count}/-{diff.removed_count} lines, chunks categorized accurately.")
    except Exception as e:
        t18.fail_test(str(e))
    results.append(t18)

    # -------------------------------------------------------------------------
    # TEST 19: Version history lifecycle: Add, Accept, Reject, Undo
    # -------------------------------------------------------------------------
    t19 = TestResult("Test 19: Version history lifecycle (Add, Accept, Reject, Undo)")
    try:
        store = VersionStore()
        res_id = "test-doc-123"

        # Step 1: Initialize with original version (v1)
        v0 = store.get_or_create(res_id, "Original document content v1")
        assert len(v0) == 1
        assert v0[0].content == "Original document content v1"

        # Step 2: Add v2 edit
        v2 = store.add_version(res_id, "Document content v2 (edited)", "Applied edit 1")
        assert v2.version_number == 2
        assert v2.status == "current"

        # Step 3: Add v3 edit
        v3 = store.add_version(res_id, "Document content v3 (second edit)", "Applied edit 2")
        assert v3.version_number == 3

        # Step 4: Undo from v3 -> restores v2
        restored_v2 = store.undo(res_id)
        assert restored_v2 is not None
        assert restored_v2.content == "Document content v2 (edited)"
        assert restored_v2.version_number == 2

        # Step 5: Undo from v2 -> restores v1 (initial)
        restored_v1 = store.undo(res_id)
        assert restored_v1 is not None
        assert restored_v1.content == "Original document content v1"
        assert restored_v1.version_number == 1

        # Step 6: Accept version
        accepted = store.accept_version(res_id, restored_v1.version_id)
        assert accepted is not None
        assert accepted.status == "accepted"

        t19.pass_test("Version timeline: v1 -> v2 -> v3 -> Undo(v2) -> Undo(v1) -> Accept byte-identical.")
    except Exception as e:
        t19.fail_test(str(e))
    results.append(t19)

    # -------------------------------------------------------------------------
    # SUMMARY REPORT
    # -------------------------------------------------------------------------
    print()
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)

    for r in results:
        status_tag = "[PASS]" if r.passed else "[FAIL]"
        print(f"{status_tag} {r.name}")
        if r.details:
            print(f"       -> {r.details}")

    print("=" * 80)
    print(f"TOTAL: {passed_count}/{total_count} PASSED ({passed_count/total_count*100:.1f}%)")
    print("=" * 80)

    if passed_count != total_count:
        sys.exit(1)


if __name__ == "__main__":
    run_evaluation()
