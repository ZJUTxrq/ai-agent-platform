from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from runtime_service.middlewares.multimodal.types import get_default_multimodal_model_id
from runtime_service.runtime.config_utils import read_configurable

DEFAULT_REQUIREMENT_DECOMPOSE_MODEL_ID = "deepseek_chat"
DEFAULT_MULTIMODAL_DETAIL_MODE = False
DEFAULT_MULTIMODAL_DETAIL_TEXT_MAX_CHARS = 2000
CONFIG_KEY_PREFIX = "requirement_decompose"

FeaturePriority = Literal["P0", "P1", "P2", "P3"]


@dataclass(frozen=True)
class RequirementDecomposeAgentConfig:
    multimodal_parser_model_id: str = field(
        default_factory=get_default_multimodal_model_id
    )
    multimodal_detail_mode: bool = DEFAULT_MULTIMODAL_DETAIL_MODE
    multimodal_detail_text_max_chars: int = DEFAULT_MULTIMODAL_DETAIL_TEXT_MAX_CHARS
    default_model_id: str = DEFAULT_REQUIREMENT_DECOMPOSE_MODEL_ID


class FeaturePoint(BaseModel):
    """单个功能点。拆解是忠实提取：非推断项必须能回指需求原文。"""

    model_config = ConfigDict(extra="forbid")

    feature_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    source_excerpt: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    priority: FeaturePriority = "P1"
    inferred: bool = False
    open_questions: list[str] = Field(default_factory=list)

    @field_validator("acceptance_criteria", "constraints", "open_questions")
    @classmethod
    def _strip_list_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]

    @model_validator(mode="after")
    def _validate_provenance(self) -> FeaturePoint:
        if not self.inferred and not self.source_excerpt.strip():
            raise ValueError(
                "non-inferred feature point must carry a source_excerpt from the requirement"
            )
        return self


class FeatureModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    feature_points: list[FeaturePoint] = Field(default_factory=list)


class RequirementFeatureListResult(BaseModel):
    """Structured output contract for requirement decomposition."""

    model_config = ConfigDict(extra="forbid")

    requirement_summary: str = Field(min_length=1)
    decomposable: bool
    undecomposable_reason: str = ""
    modules: list[FeatureModule] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("open_questions", "assumptions")
    @classmethod
    def _strip_list_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]

    @model_validator(mode="after")
    def _validate_decomposability(self) -> RequirementFeatureListResult:
        if self.decomposable:
            total_feature_points = sum(
                len(module.feature_points) for module in self.modules
            )
            if not self.modules or total_feature_points == 0:
                raise ValueError(
                    "decomposable result must contain at least one module with feature points"
                )
        else:
            if not self.undecomposable_reason.strip():
                raise ValueError(
                    "undecomposable result must explain undecomposable_reason"
                )
            if self.modules:
                raise ValueError("undecomposable result must not contain modules")
        return self


def get_requirement_decompose_output_schema() -> dict[str, Any]:
    return RequirementFeatureListResult.model_json_schema()


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_requirement_decompose_agent_config(
    config: RunnableConfig,
) -> RequirementDecomposeAgentConfig:
    private_config = dict(read_configurable(config))

    def read_private_config(name: str) -> Any:
        return private_config.get(f"{CONFIG_KEY_PREFIX}_{name}")

    return RequirementDecomposeAgentConfig(
        multimodal_parser_model_id=str(
            read_private_config("multimodal_parser_model_id")
            or get_default_multimodal_model_id()
        ),
        multimodal_detail_mode=_parse_bool(
            read_private_config("multimodal_detail_mode"),
            DEFAULT_MULTIMODAL_DETAIL_MODE,
        ),
        multimodal_detail_text_max_chars=_parse_int(
            read_private_config("multimodal_detail_text_max_chars"),
            DEFAULT_MULTIMODAL_DETAIL_TEXT_MAX_CHARS,
        ),
        default_model_id=str(
            read_private_config("default_model_id")
            or DEFAULT_REQUIREMENT_DECOMPOSE_MODEL_ID
        ),
    )


def get_service_root() -> Path:
    return Path(__file__).resolve().parent
