from __future__ import annotations

from deepagents import create_deep_agent
from runtime_service.middlewares.multimodal import MultimodalMiddleware
from runtime_service.middlewares.runtime_request import RuntimeRequestMiddleware
from runtime_service.runtime.context import RuntimeContext
from runtime_service.runtime.filesystem_backend import build_filesystem_backend
from runtime_service.runtime.modeling import resolve_model_by_id
from runtime_service.runtime.runtime_request_resolver import (
    AgentDefaults,
    ResolvedRuntimeSettings,
)
from runtime_service.services.requirement_decompose_agent.prompts import (
    build_requirement_decompose_system_prompt,
)
from runtime_service.services.requirement_decompose_agent.schemas import (
    RequirementDecomposeAgentConfig,
    build_requirement_decompose_agent_config,
    get_service_root,
)
from runtime_service.tools.multimodal import read_multimodal_attachments

REQUIREMENT_DECOMPOSE_CONFIG: RequirementDecomposeAgentConfig = (
    build_requirement_decompose_agent_config({"configurable": {}})
)
REQUIREMENT_DECOMPOSE_DEFAULTS = AgentDefaults(
    model_id=REQUIREMENT_DECOMPOSE_CONFIG.default_model_id,
    system_prompt="",
    enable_tools=False,
)

BASELINE_MODEL = resolve_model_by_id(REQUIREMENT_DECOMPOSE_DEFAULTS.model_id)
BACKEND = build_filesystem_backend(
    root_dir=get_service_root(),
    virtual_mode=True,
)
# 拆解只做忠实提取：不接知识库、不落库，结构化结果由 platform-api 流水线负责持久化
SERVICE_TOOLS = [read_multimodal_attachments]


def _resolve_current_project_id(settings: ResolvedRuntimeSettings) -> str | None:
    project_id = settings.context.project_id
    if project_id:
        return str(project_id).strip() or None
    return None


def _build_system_prompt(settings: ResolvedRuntimeSettings) -> str:
    return build_requirement_decompose_system_prompt(
        runtime_system_prompt=settings.system_prompt or None,
        current_project_id=_resolve_current_project_id(settings),
    )


def _resolve_required_tools(_settings: ResolvedRuntimeSettings) -> list[object]:
    return list(SERVICE_TOOLS)


graph = create_deep_agent(
    name="requirement_decompose_agent",
    model=BASELINE_MODEL,
    tools=SERVICE_TOOLS,
    middleware=[
        RuntimeRequestMiddleware(
            defaults=REQUIREMENT_DECOMPOSE_DEFAULTS,
            required_tools=[],
            public_tools=[],
            required_tool_resolver=_resolve_required_tools,
            system_prompt_resolver=_build_system_prompt,
        ),
        MultimodalMiddleware(
            parser_model_id=REQUIREMENT_DECOMPOSE_CONFIG.multimodal_parser_model_id,
            detail_mode=REQUIREMENT_DECOMPOSE_CONFIG.multimodal_detail_mode,
            detail_text_max_chars=REQUIREMENT_DECOMPOSE_CONFIG.multimodal_detail_text_max_chars,
        ),
    ],
    system_prompt=_build_system_prompt(
        ResolvedRuntimeSettings(
            context=RuntimeContext(),
            model=BASELINE_MODEL,
            system_prompt="",
            enable_tools=False,
            requested_public_tool_names=[],
        )
    ),
    backend=BACKEND,
    context_schema=RuntimeContext,
)
