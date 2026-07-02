from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from typing import Any

from deepagents.backends import FilesystemBackend
from deepagents.middleware.skills import _alist_skills

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from runtime_service.runtime.context import RuntimeContext  # noqa: E402
from runtime_service.runtime.runtime_request_resolver import (  # noqa: E402
    ResolvedRuntimeSettings,
)

os.environ["REQUIREMENT_REVIEW_KNOWLEDGE_MCP_ENABLED"] = "false"

requirement_review_graph = importlib.import_module(
    "runtime_service.services.requirement_review_agent.graph"
)
requirement_review_schemas = importlib.import_module(
    "runtime_service.services.requirement_review_agent.schemas"
)
requirement_review_prompts = importlib.import_module(
    "runtime_service.services.requirement_review_agent.prompts"
)


def _settings(
    *, project_id: str | None = None, system_prompt: str = ""
) -> ResolvedRuntimeSettings:
    return ResolvedRuntimeSettings(
        context=RuntimeContext(project_id=project_id),
        model="runtime-model",
        system_prompt=system_prompt,
        enable_tools=False,
        requested_public_tool_names=[],
    )


def test_requirement_review_agent_exports_static_graph_symbol() -> None:
    assert hasattr(requirement_review_graph, "graph")
    assert not hasattr(requirement_review_graph, "make_graph")
    assert hasattr(requirement_review_graph.graph, "invoke")


def test_requirement_review_agent_skills_are_enumerable() -> None:
    backend = FilesystemBackend(
        root_dir=str(requirement_review_schemas.get_service_root()),
        virtual_mode=True,
    )
    skills = asyncio.run(_alist_skills(backend, "/skills/"))

    skill_names = {skill["name"] for skill in skills}

    assert skill_names == {
        "requirement-evidence-analysis",
        "requirement-quality-scoring",
        "requirement-gate-decision",
        "requirement-review-output-formatter",
        "requirement-review-persistence",
    }


def test_requirement_review_agent_build_system_prompt_uses_runtime_project_id(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    def fake_build_requirement_review_system_prompt(
        *,
        runtime_system_prompt: str | None = None,
        current_project_id: str | None = None,
    ) -> str:
        captured["runtime_system_prompt"] = runtime_system_prompt
        captured["current_project_id"] = current_project_id
        return "resolved prompt"

    monkeypatch.setattr(
        requirement_review_graph,
        "build_requirement_review_system_prompt",
        fake_build_requirement_review_system_prompt,
    )

    prompt = requirement_review_graph._build_system_prompt(
        _settings(project_id="project-123", system_prompt="runtime prompt")
    )

    assert prompt == "resolved prompt"
    assert captured == {
        "runtime_system_prompt": "runtime prompt",
        "current_project_id": "project-123",
    }


def test_requirement_review_agent_required_tools_include_knowledge_and_service_tools(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        requirement_review_graph,
        "_resolve_service_config_for_run",
        lambda: "service-config",
    )
    monkeypatch.setattr(
        requirement_review_graph,
        "get_requirement_review_knowledge_tools",
        lambda service_config: ["knowledge_tool"],
    )
    monkeypatch.setattr(
        requirement_review_graph,
        "build_requirement_review_agent_tools",
        lambda service_config: ["service_tool"],
    )

    resolved_tools = requirement_review_graph._resolve_required_tools(_settings())

    assert resolved_tools == ["knowledge_tool", "service_tool"]


def test_requirement_review_agent_aresolve_required_tools_include_knowledge_and_service_tools(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        requirement_review_graph,
        "_resolve_service_config_for_run",
        lambda: "service-config",
    )

    async def fake_knowledge_tools(service_config: Any) -> list[str]:
        del service_config
        return ["knowledge_tool"]

    monkeypatch.setattr(
        requirement_review_graph,
        "aget_requirement_review_knowledge_tools",
        fake_knowledge_tools,
    )
    monkeypatch.setattr(
        requirement_review_graph,
        "build_requirement_review_agent_tools",
        lambda service_config: ["service_tool"],
    )

    resolved_tools = asyncio.run(
        requirement_review_graph._aresolve_required_tools(_settings())
    )

    assert resolved_tools == ["knowledge_tool", "service_tool"]


def test_requirement_review_result_schema_validates_structured_output() -> None:
    result = requirement_review_schemas.RequirementReviewResult.model_validate(
        {
            "requirement_summary": "白银用户优惠券需求覆盖领取、发放、展示、核销与退款影响。",
            "review_score": 82,
            "quality_gate": "conditional",
            "dimension_scores": {
                "business_objective": 18,
                "scope_boundary": 16,
                "workflow_and_rules": 17,
                "testability": 16,
                "risks_and_dependencies": 15,
            },
            "key_findings": ["主流程较完整", "优惠券规则已有基础描述"],
            "major_risks": ["退款后券状态未定义"],
            "missing_or_ambiguous_items": ["部分退款是否退券未说明"],
            "suggestions_to_improve": ["补充退款、过期和叠加规则"],
            "assumptions": ["默认同一订单仅能使用一张优惠券"],
            "generation_policy": "allow_generation_with_assumptions",
            "generation_policy_reason": "主体流程可测，但需带假设处理缺失规则。",
        }
    )

    assert result.review_score == 82
    assert result.quality_gate == "conditional"
    assert result.major_risks == ["退款后券状态未定义"]
    assert result.generation_policy == "allow_generation_with_assumptions"


def test_requirement_review_output_schema_exposes_expected_fields() -> None:
    schema = requirement_review_schemas.get_requirement_review_output_schema()
    properties = set(schema["properties"])

    assert {
        "requirement_summary",
        "review_score",
        "quality_gate",
        "dimension_scores",
        "key_findings",
        "major_risks",
        "missing_or_ambiguous_items",
        "suggestions_to_improve",
        "assumptions",
        "generation_policy",
        "generation_policy_reason",
    } <= properties


def test_requirement_review_prompt_includes_structured_output_contract() -> None:
    prompt = requirement_review_prompts.build_requirement_review_system_prompt()

    assert "最终回答必须先输出面向用户阅读的 Markdown 评审报告" in prompt
    assert "结构化结果（供入库接口使用）" in prompt
    assert "persist_requirement_review_result" in prompt
    assert "query_project_knowledge" in prompt
    assert "major_risks" in prompt
    assert "generation_policy_reason" in prompt
