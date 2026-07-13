# middleware / handler_loader / verify_quote 的测试依赖 langchain 运行环境,
# 在 runtime-service 容器(或 uv 环境)中运行;registry/router 的纯逻辑测试
# 见 capability_skills_test.py。
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("langchain")
pytest.importorskip("deepagents")

from runtime_service.services.requirement_review_agent.capability_skills.handler_loader import (  # noqa: E402
    _import_handler_module,
    load_capability_handler_tools,
)
from runtime_service.services.requirement_review_agent.capability_skills.middleware import (  # noqa: E402
    CapabilitySkillRoutingMiddleware,
    build_selected_capability_note,
)
from runtime_service.services.requirement_review_agent.capability_skills.registry import (  # noqa: E402
    load_capability_registry,
)
from runtime_service.services.requirement_review_agent.schemas import (  # noqa: E402
    RequirementReviewAgentConfig,
)

SHIPPED_CAPABILITIES_ROOT = (
    Path(__file__).resolve().parents[1] / "skills" / "capabilities"
)


def _shipped_registry():
    return load_capability_registry(SHIPPED_CAPABILITIES_ROOT)


def _fake_request(user_text: str | None):
    messages = []
    if user_text is not None:
        messages.append({"type": "human", "content": user_text})
    return SimpleNamespace(messages=messages)


# ---- middleware:路由注入 ----


def test_middleware_builds_note_for_security_requirement():
    middleware = CapabilitySkillRoutingMiddleware(
        _shipped_registry(), RequirementReviewAgentConfig()
    )
    note = middleware._build_note(_fake_request("新增登录鉴权功能,token 有效期 2 小时"))
    assert note is not None
    assert "`security-review`" in note
    assert "/skills/capabilities/security-review/SKILL.md" in note
    assert "`quote-verify`" in note
    assert "api-review" not in note
    assert "business-flow-review" not in note


def test_middleware_note_contains_stage_and_dimension():
    registry = _shipped_registry()
    selected = [registry.get("security-review")]
    note = build_selected_capability_note(selected)
    assert "requirement-evidence-analysis" in note
    assert "workflow_and_rules" in note
    assert "requirement-quality-scoring" in note  # 统一扣分约束


def test_middleware_always_skill_selected_without_keywords():
    middleware = CapabilitySkillRoutingMiddleware(
        _shipped_registry(), RequirementReviewAgentConfig()
    )
    note = middleware._build_note(_fake_request("一段与任何关键词无关的普通需求描述"))
    assert note is not None
    assert "`quote-verify`" in note
    assert "security-review" not in note


def test_middleware_disabled_by_config_returns_none():
    middleware = CapabilitySkillRoutingMiddleware(
        _shipped_registry(),
        RequirementReviewAgentConfig(capability_skills_enabled=False),
    )
    assert middleware._build_note(_fake_request("登录鉴权需求")) is None


def test_middleware_no_user_message_still_selects_always_skills():
    middleware = CapabilitySkillRoutingMiddleware(
        _shipped_registry(), RequirementReviewAgentConfig()
    )
    note = middleware._build_note(_fake_request(None))
    assert note is not None
    assert "`quote-verify`" in note


# ---- handler_loader ----


def test_handler_loader_loads_verify_quote_tool():
    tools = load_capability_handler_tools(
        _shipped_registry(), RequirementReviewAgentConfig()
    )
    assert [tool.name for tool in tools] == ["verify_quote"]


def test_handler_loader_returns_empty_when_knowledge_disabled():
    tools = load_capability_handler_tools(
        _shipped_registry(),
        RequirementReviewAgentConfig(knowledge_mcp_enabled=False),
    )
    assert tools == []


def test_handler_loader_returns_empty_when_capability_disabled():
    tools = load_capability_handler_tools(
        _shipped_registry(),
        RequirementReviewAgentConfig(capability_skills_enabled=False),
    )
    assert tools == []


def test_handler_loader_skips_tool_name_mismatch(tmp_path):
    directory = tmp_path / "bad-tools"
    directory.mkdir()
    (directory / "SKILL.md").write_text("# x\ncontent", encoding="utf-8")
    (directory / "handler.py").write_text(
        "from types import SimpleNamespace\n"
        "def get_tools(config):\n"
        "    return [SimpleNamespace(name='unexpected_tool')]\n",
        encoding="utf-8",
    )
    (directory / "manifest.yaml").write_text(
        "\n".join(
            [
                "name: bad-tools",
                "version: 0.1.0",
                "category: general",
                "description: tool name mismatch",
                "prompt:",
                "  file: SKILL.md",
                "scoring:",
                "  dimension: testability",
                "handler:",
                "  module: handler.py",
                "  tools:",
                "    - verify_quote",
            ]
        ),
        encoding="utf-8",
    )
    registry = load_capability_registry(tmp_path)
    assert registry.errors == []
    tools = load_capability_handler_tools(registry, RequirementReviewAgentConfig())
    assert tools == []


def test_handler_loader_skips_broken_handler(tmp_path):
    directory = tmp_path / "broken-handler"
    directory.mkdir()
    (directory / "SKILL.md").write_text("# x\ncontent", encoding="utf-8")
    (directory / "handler.py").write_text("raise RuntimeError('boom')", encoding="utf-8")
    (directory / "manifest.yaml").write_text(
        "\n".join(
            [
                "name: broken-handler",
                "version: 0.1.0",
                "category: general",
                "description: broken handler",
                "prompt:",
                "  file: SKILL.md",
                "scoring:",
                "  dimension: testability",
                "handler:",
                "  module: handler.py",
            ]
        ),
        encoding="utf-8",
    )
    registry = load_capability_registry(tmp_path)
    tools = load_capability_handler_tools(registry, RequirementReviewAgentConfig())
    assert tools == []


# ---- verify_quote 行为 ----


def _load_quote_verify_module():
    registry = _shipped_registry()
    return _import_handler_module(registry.get("quote-verify"))


def _invoke_verify_quote(module, monkeypatch, kb_response, **kwargs):
    if isinstance(kb_response, Exception):

        async def fake_call(config, tool_name, arguments):
            raise kb_response

    else:

        async def fake_call(config, tool_name, arguments):
            fake_call.captured_arguments = arguments
            return kb_response

    monkeypatch.setattr(module, "call_knowledge_mcp_tool", fake_call)
    tools = module.get_tools(RequirementReviewAgentConfig())
    assert [tool.name for tool in tools] == ["verify_quote"]
    arguments = {
        "project_id": "proj-1",
        "quote": "订单取消后不允许再次支付",
        "source_document": "支付业务规则.md",
    }
    arguments.update(kwargs)
    result = asyncio.run(tools[0].ainvoke(arguments))
    return json.loads(result)


def test_verify_quote_exact_match_ignores_whitespace(monkeypatch):
    module = _load_quote_verify_module()
    payload = _invoke_verify_quote(
        module,
        monkeypatch,
        "……规则 3:订单取消后 不允许\n再次支付。来源:支付业务规则.md",
    )
    assert payload["verified"] is True
    assert payload["reason"] == "exact_match_found"


def test_verify_quote_not_found(monkeypatch):
    module = _load_quote_verify_module()
    payload = _invoke_verify_quote(
        module, monkeypatch, "知识库里是完全不同的内容"
    )
    assert payload["verified"] is False
    assert payload["reason"] == "quote_not_found_in_project_knowledge"
    assert "不得作为硬冲突依据" in payload["hint"]


def test_verify_quote_kb_unavailable(monkeypatch):
    module = _load_quote_verify_module()
    payload = _invoke_verify_quote(
        module, monkeypatch, ConnectionError("kb down")
    )
    assert payload["verified"] is False
    assert payload["reason"] == "knowledge_mcp_unavailable"


def test_verify_quote_too_short_rejected(monkeypatch):
    module = _load_quote_verify_module()
    payload = _invoke_verify_quote(
        module, monkeypatch, "任何内容", quote="短引用"
    )
    assert payload["verified"] is False
    assert payload["reason"] == "quote_too_short"


def test_verify_quote_uses_only_need_context(monkeypatch):
    module = _load_quote_verify_module()

    captured = {}

    async def fake_call(config, tool_name, arguments):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        return "订单取消后不允许再次支付"

    monkeypatch.setattr(module, "call_knowledge_mcp_tool", fake_call)
    tools = module.get_tools(RequirementReviewAgentConfig())
    asyncio.run(
        tools[0].ainvoke(
            {"project_id": "proj-1", "quote": "订单取消后不允许再次支付"}
        )
    )
    assert captured["tool_name"] == "query_project_knowledge"
    assert captured["arguments"]["only_need_context"] is True
    assert captured["arguments"]["project_id"] == "proj-1"


# ---- graph 装配 ----


def test_graph_module_exposes_capability_registry():
    import importlib

    # 包 __init__ 将 `graph` 名绑定到编译后的图对象,须经 importlib 取模块本身
    graph_module = importlib.import_module(
        "runtime_service.services.requirement_review_agent.graph"
    )

    registry = graph_module.CAPABILITY_REGISTRY
    names = {manifest.name for manifest in registry.skills}
    assert {"api-review", "security-review", "business-flow-review"} <= names

    # quote-verify 依赖 query_project_knowledge;其他测试模块可能以
    # 知识库禁用的环境先导入 graph,此时 quote-verify 应被拒载而非报错
    service_tool_names = {
        getattr(tool, "name", "") for tool in graph_module.SERVICE_TOOLS
    }
    if "query_project_knowledge" in service_tool_names:
        assert registry.errors == []
        assert "quote-verify" in names
        assert "verify_quote" in service_tool_names
    else:
        assert all("quote-verify" in error for error in registry.errors)
