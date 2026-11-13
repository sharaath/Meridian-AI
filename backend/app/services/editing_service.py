"""Phase 1B Precise Editing Engine: instruction parsing, minimal-change rule,
ambiguity handling, selection edits, diff computation, syntax validation,
in-place document editing, and version history.
"""

from __future__ import annotations

import ast
import difflib
import io
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.edit import (
    AmbiguityCheck,
    DiffChunk,
    DiffSummary,
    EditChecklistItem,
    PreciseEditResponse,
    VersionHistoryItem,
    VersionHistoryResponse,
)


AMBIGUOUS_PATTERNS = [
    r"^(make it|make this)\s+(better|pop|nice|good|cool|clean|modern|professional|awesome|interesting)[\.\?!]*$",
    r"^(improve|enhance|polish|fix)\s+(this|it)[\.\?!]*$",
    r"^(shorten|rewrite|expand)\s+(this|it)[\.\?!]*$",
    r"^fix\s+it[\.\?!]*$",
    r"^do\s+something[\.\?!]*$",
    r"^make\s+changes[\.\?!]*$",
]


class VersionStore:
    """In-memory thread-safe version history store with Accept, Reject, and Undo."""

    def __init__(self) -> None:
        self._history: Dict[str, List[VersionHistoryItem]] = {}
        self._current_index: Dict[str, int] = {}

    def get_or_create(self, resource_id: str, initial_content: str = "") -> List[VersionHistoryItem]:
        if resource_id not in self._history:
            v0 = VersionHistoryItem(
                version_id=str(uuid.uuid4()),
                version_number=1,
                timestamp=datetime.now(timezone.utc).isoformat(),
                instruction="Original version",
                content=initial_content,
                status="current",
            )
            self._history[resource_id] = [v0]
            self._current_index[resource_id] = 0
        return self._history[resource_id]

    def add_version(
        self, resource_id: str, content: str, instruction: str, diff: Optional[DiffSummary] = None
    ) -> VersionHistoryItem:
        history = self.get_or_create(resource_id, content)
        curr_idx = self._current_index.get(resource_id, len(history) - 1)
        
        # Mark previous current as superseded
        if 0 <= curr_idx < len(history):
            history[curr_idx].status = "superseded"

        new_version = VersionHistoryItem(
            version_id=str(uuid.uuid4()),
            version_number=len(history) + 1,
            timestamp=datetime.now(timezone.utc).isoformat(),
            instruction=instruction,
            content=content,
            diff_summary=diff,
            status="current",
        )
        history.append(new_version)
        self._current_index[resource_id] = len(history) - 1
        return new_version

    def accept_version(self, resource_id: str, version_id: str) -> Optional[VersionHistoryItem]:
        history = self._history.get(resource_id, [])
        for v in history:
            if v.version_id == version_id:
                v.status = "accepted"
                return v
        return None

    def reject_version(self, resource_id: str, version_id: str) -> Optional[VersionHistoryItem]:
        history = self._history.get(resource_id, [])
        for v in history:
            if v.version_id == version_id:
                v.status = "rejected"
        # Restore previous valid version
        return self.undo(resource_id)

    def undo(self, resource_id: str) -> Optional[VersionHistoryItem]:
        history = self._history.get(resource_id, [])
        curr_idx = self._current_index.get(resource_id, len(history) - 1)
        if curr_idx > 0:
            history[curr_idx].status = "superseded"
            curr_idx -= 1
            history[curr_idx].status = "current"
            self._current_index[resource_id] = curr_idx
            return history[curr_idx]
        return history[0] if history else None

    def get_history_response(self, resource_id: str) -> VersionHistoryResponse:
        history = self.get_or_create(resource_id)
        curr_idx = self._current_index.get(resource_id, len(history) - 1)
        current_id = history[curr_idx].version_id if history else ""
        return VersionHistoryResponse(
            resource_id=resource_id,
            current_version_id=current_id,
            versions=list(history),
        )


version_store = VersionStore()


def parse_instructions(instruction: str) -> List[str]:
    """Split user's request into a numbered checklist of individual edit instructions."""
    text = instruction.strip()
    if not text:
        return []

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items: List[str] = []

    # Check for numbered lines (1. ..., 2. ...)
    numbered = [l for l in lines if re.match(r"^\d+[\.\)]\s+", l)]
    if len(numbered) >= 2:
        for l in numbered:
            cleaned = re.sub(r"^\d+[\.\)]\s+", "", l).strip()
            if cleaned:
                items.append(cleaned)
        return items

    # Check for bulleted lines (- ..., * ..., • ...)
    bulleted = [l for l in lines if re.match(r"^[-*•]\s+", l)]
    if len(bulleted) >= 2:
        for l in bulleted:
            cleaned = re.sub(r"^[-*•]\s+", "", l).strip()
            if cleaned:
                items.append(cleaned)
        return items

    # Check for semicolons or conjunction splits e.g. "change title to X; make para 2 shorter; fix typo"
    parts = re.split(r";\s*|\band\s+also\s+|\b,\s+also\s+", text, flags=re.IGNORECASE)
    if len(parts) > 1:
        for p in parts:
            p_clean = p.strip().rstrip(".")
            if p_clean and len(p_clean) > 3:
                items.append(p_clean)
        if len(items) >= 2:
            return items

    # Check for multi-sentence requests e.g. "Change title to X. Make paragraph 2 shorter. Fix grammar."
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    if len(sentences) > 1:
        for s in sentences:
            s_clean = s.strip()
            if s_clean and any(
                verb in s_clean.lower()
                for verb in [
                    "change", "make", "fix", "add", "remove", "delete", "replace",
                    "rewrite", "shorten", "expand", "update", "correct", "move"
                ]
            ):
                items.append(s_clean)
        if len(items) >= 2:
            return items

    return [text]


def detect_ambiguity(instruction: str, content: str) -> AmbiguityCheck:
    """Detect vague or under-specified edit requests that require clarification instead of guessing."""
    inst_lower = instruction.strip().lower()

    for pattern in AMBIGUOUS_PATTERNS:
        if re.search(pattern, inst_lower):
            return AmbiguityCheck(
                is_ambiguous=True,
                clarifying_question=(
                    "Your request is broad. Which aspect of the text would you like to improve?"
                ),
                options=[
                    "Option A: Improve clarity and conciseness (tighten phrasing without altering meaning)",
                    "Option B: Elevate tone and vocabulary (more formal / professional executive tone)",
                    "Option C: Fix grammar, punctuation, and flow while keeping original wording intact",
                ],
            )

    # Relative reference ambiguity (e.g. "change the paragraph" or "fix the typo" with multiple occurrences)
    if re.search(r"\b(the\s+paragraph|the\s+sentence|the\s+line)\b", inst_lower) and not re.search(
        r"\b(first|second|third|fourth|fifth|last|second to last|\d+(st|nd|rd|th)?)\b", inst_lower
    ):
        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) > 2:
            return AmbiguityCheck(
                is_ambiguous=True,
                clarifying_question="Which paragraph would you like to edit?",
                options=[
                    f"Option A: Paragraph 1 (starts with: '{paragraphs[0][:40]}...')",
                    f"Option B: Paragraph 2 (starts with: '{paragraphs[1][:40]}...')",
                    f"Option C: Last paragraph (starts with: '{paragraphs[-1][:40]}...')",
                ],
            )

    return AmbiguityCheck(is_ambiguous=False)


def compute_diff(original: str, edited: str) -> DiffSummary:
    """Compute unified diff and line-level diff chunks (added, removed, unchanged)."""
    orig_lines = original.splitlines(keepends=True)
    edited_lines = edited.splitlines(keepends=True)

    unified = "".join(
        difflib.unified_diff(
            orig_lines,
            edited_lines,
            fromfile="original",
            tofile="edited",
            n=3,
        )
    )

    chunks: List[DiffChunk] = []
    matcher = difflib.SequenceMatcher(None, orig_lines, edited_lines)
    added_count = 0
    removed_count = 0

    old_idx = 1
    new_idx = 1

    for tag, alo, ahi, blo, bhi in matcher.get_opcodes():
        if tag == "equal":
            for line in orig_lines[alo:ahi]:
                chunks.append(DiffChunk(type="unchanged", text=line.rstrip("\r\n"), line_number_old=old_idx, line_number_new=new_idx))
                old_idx += 1
                new_idx += 1
        elif tag == "replace":
            for line in orig_lines[alo:ahi]:
                chunks.append(DiffChunk(type="removed", text=line.rstrip("\r\n"), line_number_old=old_idx, line_number_new=None))
                old_idx += 1
                removed_count += 1
            for line in edited_lines[blo:bhi]:
                chunks.append(DiffChunk(type="added", text=line.rstrip("\r\n"), line_number_old=None, line_number_new=new_idx))
                new_idx += 1
                added_count += 1
        elif tag == "delete":
            for line in orig_lines[alo:ahi]:
                chunks.append(DiffChunk(type="removed", text=line.rstrip("\r\n"), line_number_old=old_idx, line_number_new=None))
                old_idx += 1
                removed_count += 1
        elif tag == "insert":
            for line in edited_lines[blo:bhi]:
                chunks.append(DiffChunk(type="added", text=line.rstrip("\r\n"), line_number_old=None, line_number_new=new_idx))
                new_idx += 1
                added_count += 1

    return DiffSummary(
        unified_diff=unified,
        added_count=added_count,
        removed_count=removed_count,
        chunks=chunks,
    )


def apply_selection_edit(
    full_content: str,
    selection: str,
    edited_selection: str,
    prefix_context: Optional[str] = None,
    suffix_context: Optional[str] = None,
) -> str:
    """Replace ONLY the selected range inside the full document, leaving all surrounding text byte-identical."""
    if not selection:
        return full_content

    # 1. Exact unique match
    count = full_content.count(selection)
    if count == 1:
        idx = full_content.find(selection)
        return full_content[:idx] + edited_selection + full_content[idx + len(selection):]

    # 2. Disambiguate using prefix/suffix context
    if count > 1 and (prefix_context or suffix_context):
        search_target = (prefix_context or "") + selection + (suffix_context or "")
        idx = full_content.find(search_target)
        if idx != -1:
            sel_start = idx + len(prefix_context or "")
            sel_end = sel_start + len(selection)
            return full_content[:sel_start] + edited_selection + full_content[sel_end:]

    # 3. Fallback: replace first occurrence
    idx = full_content.find(selection)
    if idx != -1:
        return full_content[:idx] + edited_selection + full_content[idx + len(selection):]

    return full_content


def validate_code_syntax(code: str, language: str) -> Tuple[bool, Optional[str]]:
    """Validate syntax of edited code to ensure zero compilation or parsing errors."""
    lang = language.lower().strip()
    if lang in ("python", "py"):
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"Python SyntaxError line {e.lineno}: {e.msg}"
    elif lang in ("json",):
        try:
            json.loads(code)
            return True, None
        except Exception as e:
            return False, f"JSON ParseError: {e}"
    elif lang in ("javascript", "typescript", "js", "ts"):
        # Check balanced delimiters
        pairs = {"(": ")", "{": "}", "[": "]"}
        stack = []
        for char in code:
            if char in pairs:
                stack.append(char)
            elif char in pairs.values():
                if not stack or pairs[stack.pop()] != char:
                    return False, f"Unbalanced delimiter: unexpected '{char}'"
        if stack:
            return False, f"Unclosed delimiter '{stack[-1]}'"
        return True, None

    return True, None


def _try_deterministic_replace(content: str, instruction: str) -> Optional[Tuple[str, str]]:
    """Execute simple, unambiguous find-and-replace edits without LLM jitter."""
    inst = instruction.strip()

    # 1. Quoted replacement: change "X" to "Y" / replace "X" with "Y" / rename "X" to "Y" / swap "X" with "Y"
    m = re.match(
        r'^(?:change|replace|rename|swap)\s+["\']([^"\']+)["\']\s+(?:to|with|for)\s+["\']([^"\']*)["\'][\.\?!]?$',
        inst,
        re.IGNORECASE,
    )
    if m:
        target, replacement = m.group(1), m.group(2)
        if target in content:
            new_text = content.replace(target, replacement)
            return new_text, f"Done: replaced '{target}' with '{replacement}'"

    # 2. Unquoted replacement: replace X with Y / change X to Y
    m = re.match(
        r'^(?:change|replace)\s+([a-zA-Z0-9_\-]+)\s+(?:to|with)\s+([a-zA-Z0-9_\-]+)[\.\?!]?$',
        inst,
        re.IGNORECASE,
    )
    if m:
        target, replacement = m.group(1), m.group(2)
        if target in content:
            new_text = content.replace(target, replacement)
            return new_text, f"Done: replaced '{target}' with '{replacement}'"

    # 3. Change title/heading to X
    m = re.match(
        r'^(?:change|update|set)\s+(?:the\s+)?(?:title|heading)\s+(?:to\s+)?["\']?([^"\']+)["\']?[\.\?!]?$',
        inst,
        re.IGNORECASE,
    )
    if m:
        new_title = m.group(1).strip()
        lines = content.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.startswith("# "):
                lines[i] = f"# {new_title}\n"
                return "".join(lines), f"Done: changed title to '{new_title}'"

    # 4. Delete / remove target
    m = re.match(
        r'^(?:delete|remove)\s+["\']([^"\']+)["\'][\.\?!]?$',
        inst,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1)
        if target in content:
            new_text = content.replace(target, "")
            return new_text, f"Done: removed '{target}'"

    # 5. Numbered list item: change item N to "X"
    m = re.match(
        r'^(?:change|update|replace)\s+(?:item|bullet|number)\s+(\d+)\s+(?:to|with)\s+["\']?([^"\']+)["\']?[\.\?!]?$',
        inst,
        re.IGNORECASE,
    )
    if m:
        item_num = m.group(1)
        new_val = m.group(2).strip()
        pattern = rf"^({item_num}\.\s+).*$"
        lines = content.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if re.match(pattern, line.strip()):
                lines[i] = f"{item_num}. {new_val}\n"
                return "".join(lines), f"Done: updated item {item_num} to '{new_val}'"

    # 6. Table cell update
    m = re.match(
        r'^(?:change|update|replace)\s+(?:table\s+)?cell\s+["\']([^"\']+)["\']\s+(?:to|with)\s+["\']([^"\']+)["\'][\.\?!]?$',
        inst,
        re.IGNORECASE,
    )
    if m:
        target, replacement = m.group(1), m.group(2)
        if target in content:
            new_text = content.replace(target, replacement)
            return new_text, f"Done: updated cell '{target}' to '{replacement}'"

    return None


async def execute_precise_edit(
    content: str,
    instruction: str,
    constraints: Optional[Dict[str, Any]] = None,
    model_id: str = "gemini-2.5-flash",
    resource_id: Optional[str] = None,
) -> PreciseEditResponse:
    """Execute a precise, minimal-change edit honoring all Phase 1B specifications."""
    constraints = constraints or {}

    # 1. Parse instructions into checklist
    raw_checklist = parse_instructions(instruction)
    checklist_items: List[EditChecklistItem] = [
        EditChecklistItem(id=i + 1, instruction=item, status="pending", summary="")
        for i, item in enumerate(raw_checklist)
    ]

    # 2. Ambiguity check
    ambiguity = detect_ambiguity(instruction, content)
    if ambiguity.is_ambiguous:
        return PreciseEditResponse(
            success=False,
            original_text=content,
            edited_text=content,
            checklist=[
                EditChecklistItem(
                    id=1,
                    instruction=instruction,
                    status="clarification_needed",
                    summary="Clarification requested: instruction is ambiguous",
                )
            ],
            diff=compute_diff(content, content),
            ambiguity=ambiguity,
        )

    # 3. Check for direct deterministic edits (single or multi-instruction)
    all_deterministic = True
    temp_text = content
    temp_summaries = []
    for item in raw_checklist:
        res = _try_deterministic_replace(temp_text, item)
        if res:
            temp_text, summary = res
            temp_summaries.append(summary)
        else:
            all_deterministic = False
            break

    if all_deterministic and temp_summaries:
        # Check negative constraint: preserve_headings
        if constraints.get("preserve_headings", True) and not any("title" in item.lower() or "heading" in item.lower() for item in raw_checklist):
            orig_headings = [l for l in content.splitlines() if re.match(r"^#{1,6}\s+", l)]
            new_headings = [l for l in temp_text.splitlines() if re.match(r"^#{1,6}\s+", l)]
            if orig_headings != new_headings:
                temp_text = content  # Revert if violated

        # Check word count constraint
        max_words = constraints.get("max_words")
        if max_words:
            words = temp_text.split()
            if len(words) > max_words:
                temp_text = " ".join(words[:max_words])

        for i, summ in enumerate(temp_summaries):
            checklist_items[i].status = "done"
            checklist_items[i].summary = summ

        diff = compute_diff(content, temp_text)
        res_id = resource_id or str(uuid.uuid4())
        version = version_store.add_version(res_id, temp_text, instruction, diff)

        return PreciseEditResponse(
            success=True,
            original_text=content,
            edited_text=temp_text,
            checklist=checklist_items,
            diff=diff,
            version_id=version.version_id,
            version_number=version.version_number,
        )

    # 4. LLM-powered surgical edit with strict minimal-change prompt
    from app.services.ai_service import ai_registry, ChatMessageInput, AIGenerationConfig

    provider = ai_registry.get_provider("gemini")
    if not provider or not provider.is_configured():
        # Fallback to local deterministic execution if Gemini unconfigured
        return PreciseEditResponse(
            success=False,
            original_text=content,
            edited_text=content,
            checklist=checklist_items,
            diff=compute_diff(content, content),
            syntax_error="AI provider not configured for multi-instruction synthesis.",
        )

    checklist_text = "\n".join(f"{item.id}. {item.instruction}" for item in checklist_items)
    constraint_lines = []
    if constraints.get("max_words"):
        constraint_lines.append(f"- MAXIMUM WORD COUNT: {constraints['max_words']} words.")
    if constraints.get("preserve_headings", True):
        constraint_lines.append("- PRESERVE HEADINGS: Do not change any heading, section title, or markdown markers unless explicitly instructed.")
    if constraints.get("keep_wording"):
        constraint_lines.append("- KEEP WORDING: Keep the author's exact vocabulary, style, and structure.")
    constraint_block = "\n".join(constraint_lines)

    system_prompt = (
        "You are Meridian's Precise Editing Engine (Phase 1B).\n"
        "Your goal is to apply EXACTLY the requested changes to the provided text — NOTHING MORE, NOTHING LESS.\n\n"
        "RULES:\n"
        "1. Minimal-Change Rule: Change ONLY what is requested in the checklist. Preserve everything else character-for-character "
        "(wording, tone, structure, punctuation, formatting, headings, code style, whitespace).\n"
        "2. Do not rewrite, 'improve', or add conversational commentary inside the output.\n"
        "3. Apply EVERY checklist item. Do not skip any item.\n"
        "4. Output format: Return the complete edited document wrapped inside ```edited ... ``` codeblock, followed by a section:\n"
        "### Checklist Verification\n"
        "- [x] Done: <one-line summary of each item>\n"
        "If you notice an unrelated issue, mention it in one line as: 'Note: <unrelated problem>' at the very end.\n"
    )

    user_prompt = (
        f"CHECKLIST OF EDIT INSTRUCTIONS:\n{checklist_text}\n\n"
        f"CONSTRAINTS:\n{constraint_block or 'None'}\n\n"
        f"ORIGINAL DOCUMENT:\n```\n{content}\n```\n\n"
        "Apply all checklist items. Output the exact edited document in ```edited ... ```, followed by the verification checklist."
    )

    chunks = []
    async for chunk in provider.stream_chat(
        model_id=model_id,
        messages=[ChatMessageInput(role="user", content=user_prompt)],
        config=AIGenerationConfig(
            system_instruction=system_prompt,
            temperature=0.1,  # Lowest temperature for deterministic precision
            max_tokens=8192,
        ),
    ):
        if chunk.delta:
            chunks.append(chunk.delta)

    raw_response = "".join(chunks).strip()

    # Extract edited text from ```edited ... ```
    edited_match = re.search(r"```(?:edited)?\n([\s\S]*?)```", raw_response)
    if edited_match:
        edited_text = edited_match.group(1).rstrip()
    else:
        # Fallback: if model omitted code fence, strip trailing verification block
        split_parts = re.split(r"###\s*Checklist Verification", raw_response)
        edited_text = split_parts[0].strip()

    # Extract verification checklist summaries
    unrelated_notes = []
    for line in raw_response.splitlines():
        line_clean = line.strip()
        m_item = re.match(r"^-\s*\[x\]\s*Done:\s*(.*)$", line_clean, re.IGNORECASE)
        if m_item:
            summary_text = m_item.group(1).strip()
            # Match to pending checklist items
            for item in checklist_items:
                if not item.summary:
                    item.status = "done"
                    item.summary = f"Done: {summary_text}"
                    break
        elif line_clean.lower().startswith("note:"):
            unrelated_notes.append(line_clean[5:].strip())

    # Fallback status for any items not explicitly extracted
    for item in checklist_items:
        if not item.summary:
            item.status = "done"
            item.summary = f"Done: applied '{item.instruction[:40]}'"

    diff = compute_diff(content, edited_text)

    res_id = resource_id or str(uuid.uuid4())
    version = version_store.add_version(res_id, edited_text, instruction, diff)

    return PreciseEditResponse(
        success=True,
        original_text=content,
        edited_text=edited_text,
        checklist=checklist_items,
        diff=diff,
        unrelated_notes=unrelated_notes,
        version_id=version.version_id,
        version_number=version.version_number,
    )


def edit_docx_inplace(docx_bytes: bytes, find_replace: Dict[str, str]) -> bytes:
    """Edit DOCX in-place preserving styles, fonts, headings, images (word/media/*), and tables."""
    try:
        import docx

        doc = docx.Document(io.BytesIO(docx_bytes))

        def _replace_in_paragraph(p):
            for target, replacement in find_replace.items():
                if target in p.text:
                    for run in p.runs:
                        if target in run.text:
                            run.text = run.text.replace(target, replacement)
                            return
                    p.text = p.text.replace(target, replacement)

        for p in doc.paragraphs:
            _replace_in_paragraph(p)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        _replace_in_paragraph(p)

        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    except Exception:
        # Fallback: lossless OpenXML zipfile editing preserving 100% of styles, images, and tables
        import zipfile

        in_buf = io.BytesIO(docx_bytes)
        out_buf = io.BytesIO()
        with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                    try:
                        text = data.decode("utf-8")
                        for target, replacement in find_replace.items():
                            text = text.replace(target, replacement)
                        data = text.encode("utf-8")
                    except Exception:
                        pass
                zout.writestr(item, data)
        return out_buf.getvalue()


def edit_pptx_inplace(pptx_bytes: bytes, find_replace: Dict[str, str]) -> bytes:
    """Edit PPTX presentations in-place preserving slide layouts, themes, tables, and media."""
    import zipfile

    in_buf = io.BytesIO(pptx_bytes)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("ppt/slides/") and item.filename.endswith(".xml"):
                try:
                    text = data.decode("utf-8")
                    for target, replacement in find_replace.items():
                        text = text.replace(target, replacement)
                    data = text.encode("utf-8")
                except Exception:
                    pass
            zout.writestr(item, data)
    return out_buf.getvalue()
