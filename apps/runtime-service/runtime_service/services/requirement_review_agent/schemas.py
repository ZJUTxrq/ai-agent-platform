from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from runtime_service.middlewares.multimodal.types import get_default_multimodal_model_id
from runtime_service.runtime.config_utils import read_configurable

DEFAULT_REQUIREMENT_REVIEW_MODEL_ID = "deepseek_chat"
DEFAULT_MULTIMODAL_DETAIL_MODE = False
DEFAULT_MULTIMODAL_DETAIL_TEXT_MAX_CHARS = 2000
DEFAULT_REQUIREMENT_REVIEW_PERSISTENCE_ENABLED = True
DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_MCP_ENABLED = True
DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_MCP_URL = "http://127.0.0.1:8621/sse"
DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_TIMEOUT_SECONDS = 30
DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_SSE_READ_TIMEOUT_SECONDS = 300
DEFAULT_REQUIREMENT_REVIEW_CAPABILITY_SKILLS_ENABLED = True
CONFIG_KEY_PREFIX = "requirement_review"
CONFIG_ENV_PREFIX = CONFIG_KEY_PREFIX.upper()
RequirementQualityGate = Literal["pass", "conditional", "blocked"]
RequirementGenerationPolicy = Literal[
    "allow_generation",
    "allow_generation_with_assumptions",
    "block_generation",
]


@dataclass(frozen=True)
class RequirementReviewAgentConfig:
    multimodal_parser_model_id: str = field(
        default_factory=get_default_multimodal_model_id
    )
    multimodal_detail_mode: bool = DEFAULT_MULTIMODAL_DETAIL_MODE
    multimodal_detail_text_max_chars: int = DEFAULT_MULTIMODAL_DETAIL_TEXT_MAX_CHARS
    default_model_id: str = DEFAULT_REQUIREMENT_REVIEW_MODEL_ID
    persistence_enabled: bool = DEFAULT_REQUIREMENT_REVIEW_PERSISTENCE_ENABLED
    knowledge_mcp_enabled: bool = DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_MCP_ENABLED
    knowledge_mcp_url: str = DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_MCP_URL
    knowledge_timeout_seconds: int = DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_TIMEOUT_SECONDS
    knowledge_sse_read_timeout_seconds: int = (
        DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_SSE_READ_TIMEOUT_SECONDS
    )
    capability_skills_enabled: bool = (
        DEFAULT_REQUIREMENT_REVIEW_CAPABILITY_SKILLS_ENABLED
    )


class RequirementReviewDimensionScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_objective: int = Field(ge=0, le=20)
    scope_boundary: int = Field(ge=0, le=20)
    workflow_and_rules: int = Field(ge=0, le=20)
    testability: int = Field(ge=0, le=20)
    risks_and_dependencies: int = Field(ge=0, le=20)


class RequirementReviewResult(BaseModel):
    """Structured output contract for requirement quality review."""

    model_config = ConfigDict(extra="forbid")

    requirement_summary: str = Field(min_length=1)
    review_score: int = Field(ge=0, le=100)
    quality_gate: RequirementQualityGate
    dimension_scores: RequirementReviewDimensionScores
    key_findings: list[str] = Field(default_factory=list)
    major_risks: list[str] = Field(default_factory=list)
    missing_or_ambiguous_items: list[str] = Field(default_factory=list)
    suggestions_to_improve: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    generation_policy: RequirementGenerationPolicy
    generation_policy_reason: str = Field(min_length=1)

    @field_validator(
        "key_findings",
        "major_risks",
        "missing_or_ambiguous_items",
        "suggestions_to_improve",
        "assumptions",
    )
    @classmethod
    def _strip_list_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]

    @model_validator(mode="after")
    def _validate_score_and_policy(self) -> RequirementReviewResult:
        score_total = (
            self.dimension_scores.business_objective
            + self.dimension_scores.scope_boundary
            + self.dimension_scores.workflow_and_rules
            + self.dimension_scores.testability
            + self.dimension_scores.risks_and_dependencies
        )
        if self.review_score != score_total:
            raise ValueError("review_score must equal sum of dimension_scores")

        expected_gate = (
            "pass"
            if self.review_score >= 85
            else "conditional"
            if self.review_score >= 70
            else "blocked"
        )
        if self.quality_gate != expected_gate:
            raise ValueError("quality_gate must match review_score thresholds")

        expected_policy = {
            "pass": "allow_generation",
            "conditional": "allow_generation_with_assumptions",
            "blocked": "block_generation",
        }[self.quality_gate]
        if self.generation_policy != expected_policy:
            raise ValueError("generation_policy must match quality_gate")

        return self


def get_requirement_review_output_schema() -> dict[str, Any]:
    return RequirementReviewResult.model_json_schema()


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


def _read_env_default(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def build_requirement_review_agent_config(
    config: RunnableConfig,
) -> RequirementReviewAgentConfig:
    private_config = dict(read_configurable(config))
    default_multimodal_parser_model_id = get_default_multimodal_model_id()

    def read_private_config(name: str) -> Any:
        return private_config.get(f"{CONFIG_KEY_PREFIX}_{name}")

    return RequirementReviewAgentConfig(
        multimodal_parser_model_id=str(
            read_private_config("multimodal_parser_model_id")
            or default_multimodal_parser_model_id
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
            or DEFAULT_REQUIREMENT_REVIEW_MODEL_ID
        ),
        persistence_enabled=_parse_bool(
            read_private_config("persistence_enabled"),
            DEFAULT_REQUIREMENT_REVIEW_PERSISTENCE_ENABLED,
        ),
        knowledge_mcp_enabled=_parse_bool(
            read_private_config("knowledge_mcp_enabled"),
            _parse_bool(
                _read_env_default(f"{CONFIG_ENV_PREFIX}_KNOWLEDGE_MCP_ENABLED"),
                DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_MCP_ENABLED,
            ),
        ),
        knowledge_mcp_url=str(
            read_private_config("knowledge_mcp_url")
            or _read_env_default(f"{CONFIG_ENV_PREFIX}_KNOWLEDGE_MCP_URL")
            or DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_MCP_URL
        ),
        knowledge_timeout_seconds=_parse_int(
            read_private_config("knowledge_timeout_seconds"),
            _parse_int(
                _read_env_default(f"{CONFIG_ENV_PREFIX}_KNOWLEDGE_TIMEOUT_SECONDS"),
                DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_TIMEOUT_SECONDS,
            ),
        ),
        knowledge_sse_read_timeout_seconds=_parse_int(
            read_private_config("knowledge_sse_read_timeout_seconds"),
            _parse_int(
                _read_env_default(
                    f"{CONFIG_ENV_PREFIX}_KNOWLEDGE_SSE_READ_TIMEOUT_SECONDS"
                ),
                DEFAULT_REQUIREMENT_REVIEW_KNOWLEDGE_SSE_READ_TIMEOUT_SECONDS,
            ),
        ),
        capability_skills_enabled=_parse_bool(
            read_private_config("capability_skills_enabled"),
            _parse_bool(
                _read_env_default(f"{CONFIG_ENV_PREFIX}_CAPABILITY_SKILLS_ENABLED"),
                DEFAULT_REQUIREMENT_REVIEW_CAPABILITY_SKILLS_ENABLED,
            ),
        ),
    )


def get_service_root() -> Path:
    return Path(__file__).resolve().parent


def get_skills_root() -> Path:
    return get_service_root() / "skills"
