from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from deepagents.middleware._utils import append_to_system_message
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langgraph.config import get_config

from runtime_service.services.requirement_review_agent.capability_skills.registry import (
    CapabilityRegistry,
    CapabilitySkillManifest,
    route_capability_skills,
)
from runtime_service.services.requirement_review_agent.schemas import (
    RequirementReviewAgentConfig,
    build_requirement_review_agent_config,
)


def _get_message_content(message: Any) -> Any:
    if hasattr(message, "content"):
        return getattr(message, "content")
    if isinstance(message, Mapping):
        return message.get("content")
    return None


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return " ".join(content.split()).strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            normalized = " ".join(item.split()).strip()
            if normalized:
                parts.append(normalized)
            continue
        if not isinstance(item, Mapping):
            continue
        text = item.get("text")
        if isinstance(text, str):
            normalized = " ".join(text.split()).strip()
            if normalized:
                parts.append(normalized)
    return " ".join(parts).strip()


def _get_latest_user_message(messages: Sequence[Any]) -> Any | None:
    for message in reversed(messages):
        message_type = getattr(message, "type", None) or (
            message.get("type") if isinstance(message, Mapping) else None
        )
        message_role = getattr(message, "role", None) or (
            message.get("role") if isinstance(message, Mapping) else None
        )
        if message_type in {"human", "user"} or message_role == "user":
            return message
    return None


def build_selected_capability_note(
    selected: Sequence[CapabilitySkillManifest],
) -> str:
    lines = [
        "# 本次启用的能力 Skills",
        "",
        "根据本次需求内容,以下能力 skill 已启用,必须逐项执行:",
        "",
    ]
    for index, manifest in enumerate(selected, start=1):
        lines.extend(
            [
                f"{index}. `{manifest.name}`({manifest.category}):{manifest.description}",
                f"   - SKILL 文件:进入执行阶段时先 `read_file` `{manifest.prompt_virtual_path}`",
                f"   - 执行阶段:`{manifest.inject_stage}`",
                (
                    f"   - 发现项挂靠维度:`{manifest.scoring_dimension}`"
                    f"(单 skill 最多 {manifest.scoring_max_findings} 条)"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "执行约束:",
            "- 进入对应阶段时必须先读取上述 SKILL 文件,再执行其中的检查清单;",
            "- 发现项 = 问题描述 + 证据(需求原文或知识库引用)+ 影响 + 挂靠维度,"
            "由 `requirement-quality-scoring` 阶段统一量化扣分;",
            "- 能力 skill 不直接给出或修改任何维度分数与总分;",
            "- 最终评审报告中必须列出本次启用的能力 skill 名称清单。",
        ]
    )
    return "\n".join(lines)


class CapabilitySkillRoutingMiddleware(AgentMiddleware[Any, Any]):
    """按最新用户消息路由能力 skill,并把启用清单注入 system message。"""

    def __init__(
        self,
        registry: CapabilityRegistry,
        service_config: RequirementReviewAgentConfig,
    ) -> None:
        self._registry = registry
        self._service_config = service_config

    def _resolve_service_config(self) -> RequirementReviewAgentConfig:
        try:
            config = get_config()
        except RuntimeError:
            return self._service_config
        if isinstance(config, dict):
            return build_requirement_review_agent_config(config)
        return self._service_config

    def _build_note(self, request: ModelRequest) -> str | None:
        service_config = self._resolve_service_config()
        if not service_config.capability_skills_enabled:
            return None
        latest_user_message = _get_latest_user_message(list(request.messages or []))
        text = _extract_text_from_content(_get_message_content(latest_user_message))
        selected = route_capability_skills(text, self._registry)
        if not selected:
            return None
        return build_selected_capability_note(selected)

    def _apply(self, request: ModelRequest) -> ModelRequest:
        note = self._build_note(request)
        if not note:
            return request
        return request.override(
            system_message=append_to_system_message(request.system_message, note)
        )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._apply(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._apply(request))


__all__ = [
    "CapabilitySkillRoutingMiddleware",
    "build_selected_capability_note",
]
