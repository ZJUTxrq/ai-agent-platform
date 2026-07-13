# 能力 skill 插件机制:目录即注册单元,manifest.yaml 是唯一契约。
# 本模块保持零框架依赖(仅 stdlib + PyYAML),使 registry/router 可脱离
# langchain/deepagents 环境独立单测;handler 的加载在 handler_loader.py 中。
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

MANIFEST_FILE_NAME = "manifest.yaml"
CAPABILITIES_MOUNT_PREFIX = "/skills/capabilities"
KNOWN_CATEGORIES = {"api", "security", "business-flow", "data-compliance", "general"}
# 与 prompts.py 中的强制阶段顺序保持一致
KNOWN_INJECT_STAGES = {
    "requirement-evidence-analysis",
    "requirement-quality-scoring",
    "requirement-gate-decision",
    "requirement-review-output-formatter",
    "requirement-review-persistence",
}
# 与 schemas.RequirementReviewDimensionScores 字段保持一致
KNOWN_SCORING_DIMENSIONS = {
    "business_objective",
    "scope_boundary",
    "workflow_and_rules",
    "testability",
    "risks_and_dependencies",
}
KNOWN_TOP_LEVEL_FIELDS = {
    "name",
    "version",
    "category",
    "description",
    "enabled",
    "triggers",
    "prompt",
    "scoring",
    "handler",
    "requires_tools",
    "compatibility",
}
DEFAULT_INJECT_STAGE = "requirement-evidence-analysis"
DEFAULT_TRIGGER_PRIORITY = 100
DEFAULT_MAX_FINDINGS = 10
DEFAULT_HANDLER_ENTRYPOINT = "get_tools"
DEFAULT_HANDLER_TIMEOUT_SECONDS = 10
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class CapabilityTriggers:
    keywords: tuple[str, ...] = ()
    requirement_types: tuple[str, ...] = ()
    priority: int = DEFAULT_TRIGGER_PRIORITY
    always: bool = False


@dataclass(frozen=True)
class CapabilityHandlerSpec:
    module: str
    entrypoint: str = DEFAULT_HANDLER_ENTRYPOINT
    tools: tuple[str, ...] = ()
    timeout_seconds: int = DEFAULT_HANDLER_TIMEOUT_SECONDS


@dataclass(frozen=True)
class CapabilitySkillManifest:
    name: str
    version: str
    category: str
    description: str
    enabled: bool
    directory: Path
    triggers: CapabilityTriggers
    prompt_file: str
    inject_stage: str
    scoring_dimension: str
    scoring_max_findings: int
    handler: CapabilityHandlerSpec | None
    requires_tools: tuple[str, ...]
    agents: tuple[str, ...]

    @property
    def prompt_path(self) -> Path:
        return self.directory / self.prompt_file

    @property
    def prompt_virtual_path(self) -> str:
        """agent 虚拟文件系统中的 read_file 路径。"""
        return f"{CAPABILITIES_MOUNT_PREFIX}/{self.directory.name}/{self.prompt_file}"


@dataclass
class CapabilityRegistry:
    skills: list[CapabilitySkillManifest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def get(self, name: str) -> CapabilitySkillManifest | None:
        for manifest in self.skills:
            if manifest.name == name:
                return manifest
        return None

    @property
    def enabled_skills(self) -> list[CapabilitySkillManifest]:
        return [manifest for manifest in self.skills if manifest.enabled]


class ManifestError(ValueError):
    pass


def _as_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ManifestError(f"{field_name} must be a list of strings")
    items: list[str] = []
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text:
            items.append(text)
    return tuple(items)


def _as_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError(f"{field_name} must be a mapping")
    return value


def _parse_triggers(raw: Any) -> CapabilityTriggers:
    data = _as_mapping(raw, "triggers")
    priority = data.get("priority", DEFAULT_TRIGGER_PRIORITY)
    if not isinstance(priority, int) or isinstance(priority, bool):
        raise ManifestError("triggers.priority must be an integer")
    always = data.get("always", False)
    if not isinstance(always, bool):
        raise ManifestError("triggers.always must be a boolean")
    return CapabilityTriggers(
        keywords=_as_string_tuple(data.get("keywords"), "triggers.keywords"),
        requirement_types=_as_string_tuple(
            data.get("requirement_types"), "triggers.requirement_types"
        ),
        priority=priority,
        always=always,
    )


def _parse_handler(raw: Any) -> CapabilityHandlerSpec | None:
    if raw is None:
        return None
    data = _as_mapping(raw, "handler")
    module = str(data.get("module") or "").strip()
    if not module:
        raise ManifestError("handler.module is required when handler is declared")
    entrypoint = str(data.get("entrypoint") or DEFAULT_HANDLER_ENTRYPOINT).strip()
    timeout_seconds = data.get("timeout_seconds", DEFAULT_HANDLER_TIMEOUT_SECONDS)
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool):
        raise ManifestError("handler.timeout_seconds must be an integer")
    return CapabilityHandlerSpec(
        module=module,
        entrypoint=entrypoint,
        tools=_as_string_tuple(data.get("tools"), "handler.tools"),
        timeout_seconds=timeout_seconds,
    )


def _parse_manifest(
    directory: Path,
    data: Any,
    *,
    warnings: list[str],
) -> CapabilitySkillManifest:
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be a mapping")

    unknown_fields = set(data) - KNOWN_TOP_LEVEL_FIELDS
    if unknown_fields:
        warnings.append(
            f"{directory.name}: unknown manifest fields ignored: {sorted(unknown_fields)}"
        )

    name = str(data.get("name") or "").strip()
    if not name:
        raise ManifestError("name is required")
    if name != directory.name:
        raise ManifestError(
            f"name '{name}' must match directory name '{directory.name}'"
        )

    version = str(data.get("version") or "").strip()
    if not _VERSION_PATTERN.match(version):
        raise ManifestError(f"version '{version}' must be semver (X.Y.Z)")

    category = str(data.get("category") or "").strip()
    if category not in KNOWN_CATEGORIES:
        raise ManifestError(
            f"category '{category}' must be one of {sorted(KNOWN_CATEGORIES)}"
        )

    description = str(data.get("description") or "").strip()
    if not description:
        raise ManifestError("description is required")

    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ManifestError("enabled must be a boolean")

    prompt_data = _as_mapping(data.get("prompt"), "prompt")
    prompt_file = str(prompt_data.get("file") or "SKILL.md").strip()
    prompt_path = directory / prompt_file
    if not prompt_path.is_file():
        raise ManifestError(f"prompt file '{prompt_file}' does not exist")
    if not prompt_path.read_text(encoding="utf-8").strip():
        raise ManifestError(f"prompt file '{prompt_file}' is empty")
    inject_stage = str(
        prompt_data.get("inject_stage") or DEFAULT_INJECT_STAGE
    ).strip()
    if inject_stage not in KNOWN_INJECT_STAGES:
        raise ManifestError(
            f"prompt.inject_stage '{inject_stage}' must be one of "
            f"{sorted(KNOWN_INJECT_STAGES)}"
        )

    scoring_data = _as_mapping(data.get("scoring"), "scoring")
    scoring_dimension = str(scoring_data.get("dimension") or "").strip()
    if scoring_dimension not in KNOWN_SCORING_DIMENSIONS:
        raise ManifestError(
            f"scoring.dimension '{scoring_dimension}' must be one of "
            f"{sorted(KNOWN_SCORING_DIMENSIONS)}"
        )
    max_findings = scoring_data.get("max_findings", DEFAULT_MAX_FINDINGS)
    if not isinstance(max_findings, int) or isinstance(max_findings, bool):
        raise ManifestError("scoring.max_findings must be an integer")

    handler = _parse_handler(data.get("handler"))
    if handler is not None and not (directory / handler.module).is_file():
        raise ManifestError(f"handler module '{handler.module}' does not exist")

    compatibility = _as_mapping(data.get("compatibility"), "compatibility")

    return CapabilitySkillManifest(
        name=name,
        version=version,
        category=category,
        description=description,
        enabled=enabled,
        directory=directory,
        triggers=_parse_triggers(data.get("triggers")),
        prompt_file=prompt_file,
        inject_stage=inject_stage,
        scoring_dimension=scoring_dimension,
        scoring_max_findings=max_findings,
        handler=handler,
        requires_tools=_as_string_tuple(data.get("requires_tools"), "requires_tools"),
        agents=_as_string_tuple(compatibility.get("agents"), "compatibility.agents"),
    )


def load_capability_registry(
    capabilities_root: Path,
    *,
    available_tool_names: set[str] | None = None,
    agent_name: str | None = None,
) -> CapabilityRegistry:
    """扫描 capabilities 目录并加载全部 manifest。

    单个 skill 校验失败只记入 errors 并跳过,不影响其他 skill,也不阻断启动。
    - available_tool_names:传入时,requires_tools 不满足的 skill 拒载;
    - agent_name:传入时,compatibility.agents 声明了且不含该 agent 的 skill 拒载。
    """
    registry = CapabilityRegistry()
    if not capabilities_root.is_dir():
        return registry

    for directory in sorted(capabilities_root.iterdir()):
        if not directory.is_dir():
            continue
        manifest_path = directory / MANIFEST_FILE_NAME
        if not manifest_path.is_file():
            registry.errors.append(f"{directory.name}: missing {MANIFEST_FILE_NAME}")
            continue
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = _parse_manifest(directory, data, warnings=registry.warnings)
        except ManifestError as exc:
            registry.errors.append(f"{directory.name}: {exc}")
            continue
        except yaml.YAMLError as exc:
            registry.errors.append(f"{directory.name}: invalid yaml: {exc}")
            continue

        if available_tool_names is not None:
            missing_tools = [
                tool
                for tool in manifest.requires_tools
                if tool not in available_tool_names
            ]
            if missing_tools:
                registry.errors.append(
                    f"{directory.name}: required tools unavailable: {missing_tools}"
                )
                continue

        if agent_name and manifest.agents and agent_name not in manifest.agents:
            registry.errors.append(
                f"{directory.name}: not compatible with agent '{agent_name}'"
            )
            continue

        registry.skills.append(manifest)

    for message in registry.errors:
        logger.warning("capability skill rejected: %s", message)
    for message in registry.warnings:
        logger.warning("capability skill warning: %s", message)
    return registry


def route_capability_skills(
    requirement_text: str | None,
    registry: CapabilityRegistry,
) -> list[CapabilitySkillManifest]:
    """按需求文本选择本次评审启用的能力 skill。

    - triggers.always 的 skill 恒选中(如 quote-verify 这类审计型能力);
    - 其余按 keywords 大小写不敏感的包含匹配;
    - 结果按 (priority, name) 排序,priority 小者先注入。
    """
    text = (requirement_text or "").lower()
    selected: list[CapabilitySkillManifest] = []
    for manifest in registry.enabled_skills:
        if manifest.triggers.always:
            selected.append(manifest)
            continue
        if not text:
            continue
        if any(keyword.lower() in text for keyword in manifest.triggers.keywords):
            selected.append(manifest)
    return sorted(selected, key=lambda item: (item.triggers.priority, item.name))


def build_capability_skills_prompt(registry: CapabilityRegistry) -> str:
    """由 registry 动态生成 system prompt 中的能力 skill 清单段。

    这段清单取代硬编码:新增能力 skill 只需提交目录,重启后自动进入清单。
    """
    enabled = registry.enabled_skills
    if not enabled:
        return ""
    lines = [
        "# 能力评审 Skills(按场景启用)",
        "",
        "平台已注册以下能力评审 skill。每次评审开始时,系统会根据需求内容注入"
        "《本次启用的能力 Skills》清单;只需执行清单中列出的项,未列出的不要主动读取:",
        "",
    ]
    for manifest in enabled:
        lines.append(
            f"- `{manifest.name}`({manifest.category}):{manifest.description}"
        )
    lines.extend(
        [
            "",
            "能力 skill 的统一约束:",
            "- 检查结果以“发现项”形式并入评审:问题描述 + 证据(需求原文或知识库引用)+ 影响说明;",
            "- 每个发现项挂靠该 skill 声明的评分维度,由 `requirement-quality-scoring` 阶段统一量化扣分;",
            "- 能力 skill 不直接给出或修改任何维度分数与总分。",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "CAPABILITIES_MOUNT_PREFIX",
    "CapabilityHandlerSpec",
    "CapabilityRegistry",
    "CapabilitySkillManifest",
    "CapabilityTriggers",
    "KNOWN_CATEGORIES",
    "KNOWN_INJECT_STAGES",
    "KNOWN_SCORING_DIMENSIONS",
    "MANIFEST_FILE_NAME",
    "ManifestError",
    "build_capability_skills_prompt",
    "load_capability_registry",
    "route_capability_skills",
]
