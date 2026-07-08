from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from runtime_service.services.requirement_review_agent import knowledge_mcp  # noqa: E402
from runtime_service.services.requirement_review_agent.schemas import (  # noqa: E402
    DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_MCP_URL,
    RequirementReviewAgentConfig as ServiceConfig,
    build_requirement_review_agent_config,
)


def test_build_requirement_review_knowledge_mcp_specs_defaults() -> None:
    specs = knowledge_mcp.build_requirement_review_knowledge_mcp_specs(
        ServiceConfig()
    )
    assert specs == {
        knowledge_mcp.REQUIREMENT_REVIEW_KNOWLEDGE_SERVER_NAME: {
            "transport": "sse",
            "url": DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_MCP_URL,
            "timeout": 30,
            "sse_read_timeout": 300,
        }
    }


def test_get_knowledge_tools_disabled_returns_empty() -> None:
    config = ServiceConfig(knowledge_mcp_enabled=False)
    assert knowledge_mcp.get_requirement_review_knowledge_tools(config) == []
    assert (
        asyncio.run(knowledge_mcp.aget_requirement_review_knowledge_tools(config))
        == []
    )


def test_get_knowledge_tools_registers_statically_without_network() -> None:
    """构建工具列表不应触发任何 MCP 连接（惰性连接是本模块的核心约定）。"""
    tools = knowledge_mcp.get_requirement_review_knowledge_tools(
        ServiceConfig(knowledge_mcp_url="http://127.0.0.1:1/sse")
    )
    tool_names = {getattr(tool, "name", "") for tool in tools}
    assert tool_names == knowledge_mcp.REQUIRED_KNOWLEDGE_TOOL_NAMES


def test_tool_invocation_calls_mcp_lazily_and_drops_none_args(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_call(config, tool_name, arguments):
        captured["url"] = config.knowledge_mcp_url
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        return "answer-from-kb"

    monkeypatch.setattr(knowledge_mcp, "call_knowledge_mcp_tool", fake_call)

    tools = knowledge_mcp.get_requirement_review_knowledge_tools(
        ServiceConfig(knowledge_mcp_url="http://127.0.0.1:8765/sse")
    )
    query_tool = next(
        tool for tool in tools if getattr(tool, "name", "") == "query_project_knowledge"
    )

    content = asyncio.run(
        query_tool.ainvoke({"project_id": "project-a", "query": "退款规则"})
    )

    assert content == "answer-from-kb"
    assert captured["url"] == "http://127.0.0.1:8765/sse"
    assert captured["tool_name"] == "query_project_knowledge"
    # 未提供的可选参数不应传给 MCP 服务端
    assert captured["arguments"] == {"project_id": "project-a", "query": "退款规则"}


def test_tool_invocation_failure_returns_error_payload(monkeypatch) -> None:
    async def broken_call(config, tool_name, arguments):
        raise RuntimeError("mcp unavailable")

    monkeypatch.setattr(knowledge_mcp, "call_knowledge_mcp_tool", broken_call)

    tools = knowledge_mcp.get_requirement_review_knowledge_tools(
        ServiceConfig(knowledge_mcp_url="http://127.0.0.1:8765/sse")
    )
    query_tool = next(
        tool for tool in tools if getattr(tool, "name", "") == "query_project_knowledge"
    )

    content = asyncio.run(
        query_tool.ainvoke({"project_id": "project-a", "query": "x"})
    )

    payload = json.loads(content)
    assert payload["error"] == "knowledge_mcp_unavailable"
    assert payload["tool"] == "query_project_knowledge"
    assert "RuntimeError" in payload["detail"]


def test_normalize_call_tool_result_error_flag() -> None:
    class _Text:
        def __init__(self, text: str) -> None:
            self.text = text

    class _Result:
        def __init__(self, texts: list[str], is_error: bool) -> None:
            self.content = [_Text(t) for t in texts]
            self.isError = is_error

    ok = knowledge_mcp._normalize_call_tool_result(
        "query_project_knowledge", _Result(["hello"], False)
    )
    assert ok == "hello"

    err = json.loads(
        knowledge_mcp._normalize_call_tool_result(
            "query_project_knowledge", _Result(["boom"], True)
        )
    )
    assert err["error"] == "knowledge_mcp_tool_error"
    assert err["detail"] == "boom"


def test_build_requirement_review_agent_config_reads_prefixed_keys() -> None:
    config = build_requirement_review_agent_config(
        {
            "configurable": {
                "requirement_review_default_model_id": "gpt-4o-mini",
                "requirement_review_multimodal_detail_mode": True,
                "requirement_review_knowledge_mcp_enabled": False,
                "requirement_review_knowledge_mcp_url": "http://127.0.0.1:9999/sse",
                "requirement_review_knowledge_timeout_seconds": 12,
                "requirement_review_knowledge_sse_read_timeout_seconds": 34,
            }
        }
    )

    assert config.default_model_id == "gpt-4o-mini"
    assert config.multimodal_detail_mode is True
    assert config.knowledge_mcp_enabled is False
    assert config.knowledge_mcp_url == "http://127.0.0.1:9999/sse"
    assert config.knowledge_timeout_seconds == 12
    assert config.knowledge_sse_read_timeout_seconds == 34
