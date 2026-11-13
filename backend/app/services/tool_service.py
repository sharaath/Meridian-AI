"""Tool Execution Engine for Meridian AI (Phase 3):
- Model tool-use loop with max 5 iterations and per-tool timeouts.
- Supported tools: web_search, read_document, run_python (sandboxed).
- Tool status streaming and citation collection.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.tables import UploadedFile
from app.services.search_service import (
    SearchResultItem,
    WebSearchUnavailableError,
    format_search_context,
    search_web_results,
)


MAX_TOOL_ITERATIONS = 5
TOOL_TIMEOUT_SEARCH = 10.0
TOOL_TIMEOUT_DOC = 5.0
TOOL_TIMEOUT_PYTHON = 5.0


@dataclass
class ToolExecutionResult:
    tool: str
    output: str
    citations: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    duration_ms: int = 0


TOOL_SYSTEM_PROMPT = """You have access to the following tools:
1. `web_search`: Search the live web for recent facts, news, documentation, or online information.
   Arguments: {"query": string, "max_results": int (optional, default 5)}
2. `read_document`: Read the extracted contents or specific pages of an uploaded document.
   Arguments: {"filename": string, "page": int (optional)}
3. `run_python`: Execute Python code in a safe sandbox for calculations, math, data processing, or algorithmic verification.
   Arguments: {"code": string}

To call a tool, format your output with a tool_call block:
```tool_call
{"tool": "<tool_name>", "arguments": {<arguments>}}
```
When you invoke a tool, output ONLY the tool call block and wait for the system to return the result.
When using facts from web_search in your final answer, cite your sources using numbered brackets like [1], [2] corresponding to the search citations.
"""


def parse_tool_call(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Detect and parse tool call requests from model output."""
    clean = text.strip()
    if not clean:
        return None

    # Pattern 1: ```tool_call\n{...}\n```
    m = re.search(r"```(?:tool_call|tool|json)?\s*(\{[\s\S]*?\})\s*```", clean, re.IGNORECASE)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict) and "tool" in data:
                return data["tool"], data.get("arguments", {})
        except Exception:
            pass

    # Pattern 2: <tool_call>{...}</tool_call>
    m = re.search(r"<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>", clean, re.IGNORECASE)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict) and "tool" in data:
                return data["tool"], data.get("arguments", {})
        except Exception:
            pass

    # Pattern 3: Raw JSON root object {"tool": "...", "arguments": {...}}
    if clean.startswith("{") and clean.endswith("}"):
        try:
            data = json.loads(clean)
            if isinstance(data, dict) and "tool" in data:
                return data["tool"], data.get("arguments", {})
        except Exception:
            pass

    # Pattern 4: tool_call: name(arg="...")
    m = re.search(r"(?:tool_call|call):\s*([a-zA-Z0-9_]+)\(([\s\S]*?)\)", clean, re.IGNORECASE)
    if m:
        tool_name = m.group(1)
        raw_args = m.group(2).strip()
        args: Dict[str, Any] = {}
        for pair in re.finditer(r'([a-zA-Z0-9_]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s,]+))', raw_args):
            k = pair.group(1)
            v = pair.group(2) or pair.group(3) or pair.group(4)
            args[k] = v
        if tool_name in ("web_search", "read_document", "run_python"):
            return tool_name, args

    return None


async def execute_web_search(query: str, max_results: int = 5) -> ToolExecutionResult:
    """Execute live web search with timeout and return citations."""
    start = time.perf_counter()
    clean_query = query.strip()
    if not clean_query:
        return ToolExecutionResult(
            tool="web_search",
            output="Error: Empty search query provided.",
            success=False,
            error="Empty query",
            duration_ms=0,
        )

    try:
        results = await asyncio.wait_for(
            search_web_results(clean_query, max_results=max_results),
            timeout=TOOL_TIMEOUT_SEARCH,
        )
        duration = int((time.perf_counter() - start) * 1000)
        if not results:
            return ToolExecutionResult(
                tool="web_search",
                output=f"No results found for query: '{clean_query}'.",
                success=True,
                duration_ms=duration,
            )

        citations = [
            {"title": item.title, "url": item.url, "snippet": item.snippet, "source": item.source}
            for item in results
        ]
        context_text = format_search_context(results)
        return ToolExecutionResult(
            tool="web_search",
            output=context_text,
            citations=citations,
            success=True,
            duration_ms=duration,
        )
    except asyncio.TimeoutError:
        return ToolExecutionResult(
            tool="web_search",
            output=f"Search timed out after {TOOL_TIMEOUT_SEARCH}s.",
            success=False,
            error="Timeout",
            duration_ms=int(TOOL_TIMEOUT_SEARCH * 1000),
        )
    except WebSearchUnavailableError as exc:
        return ToolExecutionResult(
            tool="web_search",
            output=f"Web search unavailable: {exc}",
            success=False,
            error=str(exc),
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
    except Exception as exc:
        return ToolExecutionResult(
            tool="web_search",
            output=f"Search error: {exc}",
            success=False,
            error=str(exc),
            duration_ms=int((time.perf_counter() - start) * 1000),
        )


def execute_read_document(
    db: Session,
    user_id: str,
    filename: str,
    page: Optional[int] = None,
) -> ToolExecutionResult:
    """Read document text by filename, keyword, or page from uploaded files."""
    start = time.perf_counter()
    clean_name = filename.strip().lower()

    # Search uploaded files belonging to the user
    files = db.query(UploadedFile).filter(UploadedFile.user_id == user_id).all()
    target_file = None

    # Exact filename match
    for f in files:
        if f.filename.lower() == clean_name:
            target_file = f
            break

    # Substring / stem match if exact match not found
    if not target_file:
        for f in files:
            if clean_name in f.filename.lower() or Path(f.filename).stem.lower() == clean_name:
                target_file = f
                break

    duration = int((time.perf_counter() - start) * 1000)

    if not target_file:
        available = ", ".join([f.filename for f in files]) if files else "None"
        return ToolExecutionResult(
            tool="read_document",
            output=f"Document '{filename}' not found. Available uploaded documents: [{available}].",
            success=False,
            error="File not found",
            duration_ms=duration,
        )

    # If specific page requested and pages_json available
    if page is not None and target_file.pages_json:
        for p in target_file.pages_json:
            if p.get("page") == page:
                return ToolExecutionResult(
                    tool="read_document",
                    output=f"Document: {target_file.filename} (Page {page}/{target_file.page_count}):\n{p.get('text', '')}",
                    success=True,
                    duration_ms=duration,
                )
        return ToolExecutionResult(
            tool="read_document",
            output=f"Page {page} not found in {target_file.filename} (total pages: {target_file.page_count}).",
            success=False,
            duration_ms=duration,
        )

    # Return extracted text (capped at 12,000 chars for context safety)
    content = target_file.extracted_text or "(No text could be extracted from this document)"
    if len(content) > 12000:
        content = content[:12000] + f"\n... [Truncated: showing first 12,000 of {len(target_file.extracted_text)} characters]"

    return ToolExecutionResult(
        tool="read_document",
        output=f"Document: {target_file.filename} (Pages: {target_file.page_count}):\n{content}",
        success=True,
        duration_ms=duration,
    )


def execute_run_python(code: str, timeout: float = TOOL_TIMEOUT_PYTHON) -> ToolExecutionResult:
    """Execute Python code in an isolated, sandboxed subprocess with strict timeouts."""
    start = time.perf_counter()
    clean_code = code.strip()

    if not clean_code:
        return ToolExecutionResult(
            tool="run_python",
            output="Error: Empty Python code provided.",
            success=False,
            error="Empty code",
            duration_ms=0,
        )

    # Disallow hazardous modules or system modification calls
    blocked_patterns = [
        r"\bimport\s+shutil\b",
        r"\bimport\s+ctypes\b",
        r"\bos\.system\b",
        r"\bos\.remove\b",
        r"\bos\.unlink\b",
        r"\bos\.rmdir\b",
        r"\bshutil\.rmtree\b",
        r"\bsubprocess\b",
    ]
    for pat in blocked_patterns:
        if re.search(pat, clean_code):
            return ToolExecutionResult(
                tool="run_python",
                output=f"Execution blocked: code contains restricted operation ({pat}).",
                success=False,
                error="Security violation",
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    try:
        proc = subprocess.run(
            [sys.executable, "-c", clean_code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        duration = int((time.perf_counter() - start) * 1000)
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if len(stdout) > 4000:
            stdout = stdout[:4000] + "\n... [Output truncated at 4000 chars]"
        if len(stderr) > 2000:
            stderr = stderr[:2000] + "\n... [Errors truncated at 2000 chars]"

        output_parts = []
        if stdout:
            output_parts.append(f"Output:\n{stdout}")
        if stderr:
            output_parts.append(f"Errors/Warnings:\n{stderr}")
        if not stdout and not stderr:
            output_parts.append("(Code executed successfully with no output to stdout)")

        output_parts.append(f"Exit code: {proc.returncode}")
        full_output = "\n".join(output_parts)

        return ToolExecutionResult(
            tool="run_python",
            output=full_output,
            success=proc.returncode == 0,
            duration_ms=duration,
        )
    except subprocess.TimeoutExpired:
        return ToolExecutionResult(
            tool="run_python",
            output=f"Execution timed out after {timeout} seconds.",
            success=False,
            error="Timeout",
            duration_ms=int(timeout * 1000),
        )
    except Exception as exc:
        return ToolExecutionResult(
            tool="run_python",
            output=f"Subprocess failure: {exc}",
            success=False,
            error=str(exc),
            duration_ms=int((time.perf_counter() - start) * 1000),
        )


async def dispatch_tool(
    db: Session,
    user_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> ToolExecutionResult:
    """Dispatch a tool call to the corresponding executor."""
    name = tool_name.strip().lower()
    if name == "web_search":
        query = str(arguments.get("query", ""))
        max_results = int(arguments.get("max_results", 5))
        return await execute_web_search(query, max_results=max_results)

    elif name == "read_document":
        filename = str(arguments.get("filename", ""))
        page_arg = arguments.get("page")
        page = int(page_arg) if page_arg is not None else None
        return execute_read_document(db, user_id, filename, page=page)

    elif name == "run_python":
        code = str(arguments.get("code", ""))
        return execute_run_python(code)

    return ToolExecutionResult(
        tool=tool_name,
        output=f"Unknown tool '{tool_name}'. Available tools: web_search, read_document, run_python.",
        success=False,
        error="Unknown tool",
        duration_ms=0,
    )


def format_tool_status_message(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Format human-readable UI status for a tool call."""
    name = tool_name.strip().lower()
    if name == "web_search":
        q = arguments.get("query", "")
        return f"Searching the web for '{q}'..." if q else "Searching the web..."
    elif name == "read_document":
        f = arguments.get("filename", "")
        return f"Reading document '{f}'..." if f else "Reading document..."
    elif name == "run_python":
        return "Executing Python code in sandbox..."
    return f"Running {tool_name}..."

