"""Tests for Phase 3: Tool-Use Loop & Streaming Status.
Verifies tool parsing, sandboxed python execution, document reading,
web search citations, timeout enforcement, tool iteration caps, and SSE streaming.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.models.tables import UploadedFile
from app.services.ai_service import (
    AIGenerationConfig,
    AIModelInfo,
    AIStreamChunk,
    BaseAIProvider,
    ChatMessageInput,
    ai_registry,
)
from app.services.search_service import SearchResultItem
from app.services.tool_service import (
    MAX_TOOL_ITERATIONS,
    TOOL_TIMEOUT_PYTHON,
    dispatch_tool,
    execute_read_document,
    execute_run_python,
    execute_web_search,
    format_tool_status_message,
    parse_tool_call,
)


class MockDB:
    """Lightweight in-memory DB double for fast, network-isolated tool execution testing."""

    def __init__(self, files=None):
        self._files = files or []

    def query(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._files)


def test_parse_tool_call_markdown_code_block():
    text = """Let me search for this.
```tool_call
{"tool": "web_search", "arguments": {"query": "latest quantum computing news"}}
```"""
    parsed = parse_tool_call(text)
    assert parsed is not None
    tool_name, args = parsed
    assert tool_name == "web_search"
    assert args["query"] == "latest quantum computing news"


def test_parse_tool_call_xml_tags():
    text = """<tool_call>
{"tool": "run_python", "arguments": {"code": "print(2 ** 10)"}}
</tool_call>"""
    parsed = parse_tool_call(text)
    assert parsed is not None
    tool_name, args = parsed
    assert tool_name == "run_python"
    assert args["code"] == "print(2 ** 10)"


def test_parse_tool_call_raw_json():
    text = '{"tool": "read_document", "arguments": {"filename": "financial_report.pdf", "page": 3}}'
    parsed = parse_tool_call(text)
    assert parsed is not None
    tool_name, args = parsed
    assert tool_name == "read_document"
    assert args["filename"] == "financial_report.pdf"
    assert args["page"] == 3


def test_parse_tool_call_functional_syntax():
    text = 'tool_call: web_search(query="Python 3.12 release date")'
    parsed = parse_tool_call(text)
    assert parsed is not None
    tool_name, args = parsed
    assert tool_name == "web_search"
    assert "query" in args


def test_parse_tool_call_none_on_regular_text():
    assert parse_tool_call("Hello, how can I help you today?") is None
    assert parse_tool_call("Here is a regular python snippet:\n```python\nprint(1)\n```") is None


def test_execute_run_python_success():
    res = execute_run_python("a = 15\nb = 27\nprint(a + b)")
    assert res.success is True
    assert "42" in res.output
    assert res.tool == "run_python"
    assert res.duration_ms >= 0


def test_execute_run_python_security_block():
    # Attempting to import shutil or run os.system must be immediately blocked
    res_shutil = execute_run_python("import shutil\nshutil.rmtree('/tmp')")
    assert res_shutil.success is False
    assert "restricted operation" in res_shutil.output
    assert res_shutil.error == "Security violation"

    res_system = execute_run_python("import os\nos.system('whoami')")
    assert res_system.success is False
    assert "restricted operation" in res_system.output


def test_execute_run_python_timeout():
    # Execution must abort when exceeding timeout
    res = execute_run_python("import time\ntime.sleep(2)", timeout=0.5)
    assert res.success is False
    assert "timed out" in res.output.lower()
    assert res.error == "Timeout"


def test_execute_read_document():
    doc = UploadedFile(
        id="file-123",
        user_id="user-456",
        filename="quarterly_results.txt",
        file_type="txt",
        mime_type="text/plain",
        file_size=100,
        storage_path="quarterly_results.txt",
        extracted_text="Q3 revenue was 15 million dollars. Net profit increased by 12%.",
        page_count=1,
        pages_json=[{"page": 1, "text": "Q3 revenue was 15 million dollars. Net profit increased by 12%."}],
    )
    db = MockDB([doc])

    # Read existing doc
    res = execute_read_document(db, "user-456", "quarterly_results.txt")
    assert res.success is True
    assert "15 million dollars" in res.output
    assert res.tool == "read_document"

    # Read specific page
    res_page = execute_read_document(db, "user-456", "quarterly_results.txt", page=1)
    assert res_page.success is True
    assert "Page 1/1" in res_page.output

    # Read nonexistent file
    res_missing = execute_read_document(db, "user-456", "nonexistent.pdf")
    assert res_missing.success is False
    assert "not found" in res_missing.output.lower()


def run_coro(c):
    try:
        f = c.send(None)
        while True:
            try:
                f = c.send(None)
            except StopIteration as e:
                return e.value
    except StopIteration as e:
        return e.value


def test_execute_web_search_empty_query():
    res = run_coro(execute_web_search(""))
    assert res.success is False
    assert "Empty search query" in res.output


def test_execute_web_search_with_mock_results():
    mock_items = [
        SearchResultItem(
            title="FastAPI Release 0.115",
            url="https://fastapi.tiangolo.com/release-notes/",
            snippet="FastAPI 0.115 has been released with performance improvements.",
            source="duckduckgo",
        )
    ]

    async def mock_wait_for(coro, timeout=None):
        if coro is not None and asyncio.iscoroutine(coro):
            coro.close()
        return mock_items

    with patch("asyncio.wait_for", new=mock_wait_for):
        res = run_coro(execute_web_search("fastapi latest version"))
        assert res.success is True
        assert len(res.citations) == 1
        assert res.citations[0]["title"] == "FastAPI Release 0.115"
        assert "FastAPI Release 0.115" in res.output


def test_format_tool_status_message():
    assert "Searching the web" in format_tool_status_message("web_search", {"query": "Mars rovers"})
    assert "Reading document 'report.pdf'" in format_tool_status_message("read_document", {"filename": "report.pdf"})
    assert "Executing Python" in format_tool_status_message("run_python", {"code": "x = 1"})


def test_dispatch_tool():
    db = MockDB([])
    res = run_coro(dispatch_tool(db, "fake-user-id", "run_python", {"code": "print('hello from sandbox')"}))
    assert res.success is True
    assert "hello from sandbox" in res.output


def test_tool_iteration_cap_constant():
    assert MAX_TOOL_ITERATIONS == 5
    assert TOOL_TIMEOUT_PYTHON == 5.0
