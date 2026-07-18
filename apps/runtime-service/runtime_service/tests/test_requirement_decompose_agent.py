from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from runtime_service.runtime.context import RuntimeContext  # noqa: E402
from runtime_service.runtime.runtime_request_resolver import (  # noqa: E402
    ResolvedRuntimeSettings,
)

requirement_decompose_graph = importlib.import_module(
    "runtime_service.services.requirement_decompose_agent.graph"
)
requirement_decompose_schemas = importlib.import_module(
    "runtime_service.services.requirement_decompose_agent.schemas"
)
requirement_decompose_prompts = importlib.import_module(
    "runtime_service.services.requirement_decompose_agent.prompts"
)


def _valid_payload() -> dict:
    return {
        "requirement_summary": "优惠券活动需求：领取、核销与库存扣减。",
        "decomposable": True,
        "modules": [
            {
                "name": "优惠券",
                "description": "领取与核销",
                "feature_points": [
                    {
                        "feature_id": "coupon-claim",
                        "title": "用户领取优惠券",
                        "source_excerpt": "用户可在活动页领取优惠券，每人限领一张。",
                        "acceptance_criteria": ["每人限领一张"],
                        "constraints": ["库存扣减需幂等"],
                        "priority": "P0",
                        "inferred": False,
                        "open_questions": ["库存耗尽后的文案未定义"],
                    }
                ],
            }
        ],
        "open_questions": ["活动时间范围未说明"],
        "assumptions": [],
    }


def test_requirement_decompose_agent_exports_static_graph_symbol() -> None:
    assert hasattr(requirement_decompose_graph, "graph")
    assert hasattr(requirement_decompose_graph.graph, "invoke")


def test_feature_list_result_schema_validates_structured_output() -> None:
    result = requirement_decompose_schemas.RequirementFeatureListResult.model_validate(
        _valid_payload()
    )
    assert result.decomposable is True
    assert result.modules[0].feature_points[0].feature_id == "coupon-claim"
    assert result.modules[0].feature_points[0].priority == "P0"


def test_non_inferred_feature_point_requires_source_excerpt() -> None:
    payload = _valid_payload()
    payload["modules"][0]["feature_points"][0]["source_excerpt"] = ""
    with pytest.raises(ValidationError, match="source_excerpt"):
        requirement_decompose_schemas.RequirementFeatureListResult.model_validate(
            payload
        )


def test_inferred_feature_point_allows_empty_source_excerpt() -> None:
    payload = _valid_payload()
    feature_point = payload["modules"][0]["feature_points"][0]
    feature_point["source_excerpt"] = ""
    feature_point["inferred"] = True
    result = requirement_decompose_schemas.RequirementFeatureListResult.model_validate(
        payload
    )
    assert result.modules[0].feature_points[0].inferred is True


def test_decomposable_result_requires_feature_points() -> None:
    payload = _valid_payload()
    payload["modules"] = []
    with pytest.raises(ValidationError, match="at least one module"):
        requirement_decompose_schemas.RequirementFeatureListResult.model_validate(
            payload
        )


def test_undecomposable_result_requires_reason_and_forbids_modules() -> None:
    payload = _valid_payload()
    payload["decomposable"] = False
    with pytest.raises(ValidationError, match="undecomposable_reason"):
        requirement_decompose_schemas.RequirementFeatureListResult.model_validate(
            payload
        )

    payload["undecomposable_reason"] = "需求原文过于模糊"
    with pytest.raises(ValidationError, match="must not contain modules"):
        requirement_decompose_schemas.RequirementFeatureListResult.model_validate(
            payload
        )

    payload["modules"] = []
    result = requirement_decompose_schemas.RequirementFeatureListResult.model_validate(
        payload
    )
    assert result.decomposable is False


def test_requirement_decompose_prompt_includes_output_contract() -> None:
    prompt = requirement_decompose_prompts.build_requirement_decompose_system_prompt(
        current_project_id="project-123"
    )

    assert "忠实提取" in prompt
    assert "结构化结果（供入库接口使用）" in prompt
    assert "source_excerpt" in prompt
    assert "decomposable" in prompt
    assert "project-123" in prompt
    assert "不评审、不打分、不生成测试用例" in prompt


def test_requirement_decompose_build_system_prompt_uses_runtime_project_id() -> None:
    settings = ResolvedRuntimeSettings(
        context=RuntimeContext(project_id="project-abc"),
        model="runtime-model",
        system_prompt="runtime prompt",
        enable_tools=False,
        requested_public_tool_names=[],
    )
    prompt = requirement_decompose_graph._build_system_prompt(settings)

    assert prompt.startswith("runtime prompt")
    assert "project-abc" in prompt
