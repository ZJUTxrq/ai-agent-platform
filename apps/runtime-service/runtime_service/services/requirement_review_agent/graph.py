from __future__ import annotations

from deepagents import create_deep_agent
from langgraph.config import get_config
from runtime_service.middlewares.multimodal import MultimodalMiddleware
from runtime_service.middlewares.runtime_request import RuntimeRequestMiddleware
from runtime_service.runtime.context import RuntimeContext
from runtime_service.runtime.filesystem_backend import build_filesystem_backend
from runtime_service.runtime.modeling import resolve_model_by_id
from runtime_service.runtime.runtime_request_resolver import (
    AgentDefaults,
    ResolvedRuntimeSettings,
)
from runtime_service.services.requirement_review_agent.prompts import (
    build_requirement_review_system_prompt,
)
from runtime_service.services.requirement_review_agent.middleware import (
    RequirementReviewDocumentPersistenceMiddleware,
)
from runtime_service.services.requirement_review_agent.schemas import (
    RequirementReviewAgentConfig,
    build_requirement_review_agent_config,
    get_service_root,
)
from runtime_service.services.requirement_review_agent.tools import (
    build_requirement_review_agent_tools,
)


REQUIREMENT_REVIEW_CONFIG: RequirementReviewAgentConfig = (
    build_requirement_review_agent_config({"configurable": {}})
)
REQUIREMENT_REVIEW_DEFAULTS = AgentDefaults(
    model_id=REQUIREMENT_REVIEW_CONFIG.default_model_id,
    system_prompt="",
    enable_tools=False,
)

BASELINE_MODEL = resolve_model_by_id(REQUIREMENT_REVIEW_DEFAULTS.model_id)
BACKEND = build_filesystem_backend(
    root_dir=get_service_root(),
    virtual_mode=True,
)
SERVICE_TOOLS = build_requirement_review_agent_tools(REQUIREMENT_REVIEW_CONFIG)
REQUIREMENT_REVIEW_MIDDLEWARE = [
    MultimodalMiddleware(
        parser_model_id=REQUIREMENT_REVIEW_CONFIG.multimodal_parser_model_id,
        detail_mode=REQUIREMENT_REVIEW_CONFIG.multimodal_detail_mode,
        detail_text_max_chars=REQUIREMENT_REVIEW_CONFIG.multimodal_detail_text_max_chars,
    ),
    RequirementReviewDocumentPersistenceMiddleware(REQUIREMENT_REVIEW_CONFIG),
]


def _resolve_current_project_id(settings: ResolvedRuntimeSettings) -> str | None:
    project_id = settings.context.project_id
    if project_id:
        return str(project_id).strip() or None
    return None


def _build_system_prompt(settings: ResolvedRuntimeSettings) -> str:
    return build_requirement_review_system_prompt(
        runtime_system_prompt=settings.system_prompt or None,
        current_project_id=_resolve_current_project_id(settings),
    )


def _resolve_service_config_for_run() -> RequirementReviewAgentConfig:
    try:
        config = get_config()
    except RuntimeError:
        return REQUIREMENT_REVIEW_CONFIG

    if isinstance(config, dict):
        return build_requirement_review_agent_config(config)
    return REQUIREMENT_REVIEW_CONFIG


def _resolve_required_tools(
    _settings: ResolvedRuntimeSettings,
) -> list[object]:
    return build_requirement_review_agent_tools(_resolve_service_config_for_run())


async def _aresolve_required_tools(
    _settings: ResolvedRuntimeSettings,
) -> list[object]:
    return build_requirement_review_agent_tools(_resolve_service_config_for_run())


graph = create_deep_agent(
    name="requirement_review_agent",
    model=BASELINE_MODEL,
    tools=SERVICE_TOOLS,
    middleware=[
        RuntimeRequestMiddleware(
            defaults=REQUIREMENT_REVIEW_DEFAULTS,
            required_tools=[],
            public_tools=[],
            required_tool_resolver=_resolve_required_tools,
            arequired_tool_resolver=_aresolve_required_tools,
            system_prompt_resolver=_build_system_prompt,
        ),
        *REQUIREMENT_REVIEW_MIDDLEWARE,
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
    skills=["/skills/"],
    context_schema=RuntimeContext,
)
