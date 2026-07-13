from __future__ import annotations

import importlib.util
import logging
from typing import Any

from runtime_service.services.requirement_review_agent.capability_skills.registry import (
    CapabilityRegistry,
    CapabilitySkillManifest,
)
from runtime_service.services.requirement_review_agent.schemas import (
    RequirementReviewAgentConfig,
)

logger = logging.getLogger(__name__)


def _import_handler_module(manifest: CapabilitySkillManifest) -> Any:
    module_path = manifest.directory / manifest.handler.module
    module_name = f"capability_skill_handler__{manifest.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load handler module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_capability_handler_tools(
    registry: CapabilityRegistry,
    service_config: RequirementReviewAgentConfig,
) -> list[Any]:
    """加载所有启用 skill 的 handler 工具。

    单个 handler 失败只告警跳过,不阻断其他 skill 与启动;
    实际返回的工具名必须与 manifest 中 handler.tools 声明一致,否则拒载。
    """
    tools: list[Any] = []
    if not service_config.capability_skills_enabled:
        return tools
    for manifest in registry.enabled_skills:
        if manifest.handler is None:
            continue
        try:
            module = _import_handler_module(manifest)
            entrypoint = getattr(module, manifest.handler.entrypoint)
            skill_tools = list(entrypoint(service_config))
        except Exception:  # noqa: BLE001 - 插件失败不应拖垮 agent 启动
            logger.warning(
                "capability skill handler failed to load, skipped",
                extra={"skill": manifest.name},
                exc_info=True,
            )
            continue
        if not skill_tools:
            # handler 可依据配置(如知识库未启用)自行返回空,静默跳过
            continue
        actual_names = {getattr(tool, "name", None) for tool in skill_tools}
        declared_names = set(manifest.handler.tools)
        if declared_names and actual_names != declared_names:
            logger.warning(
                "capability skill handler tool names mismatch manifest, skipped",
                extra={
                    "skill": manifest.name,
                    "declared": sorted(declared_names),
                    "actual": sorted(str(name) for name in actual_names),
                },
            )
            continue
        tools.extend(skill_tools)
    return tools


__all__ = ["load_capability_handler_tools"]
