from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from deepagents.middleware._utils import append_to_system_message
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.messages import AIMessage
from langgraph.config import get_config
from runtime_service.integrations import (
    InteractionDataServiceClient,
    build_interaction_data_service_config,
)
from runtime_service.services.test_case_service_v2.knowledge_query_guard_middleware import (
    _TEST_CASE_GENERATION_PATTERN,
    _extract_text_from_content,
    _get_latest_user_message,
    _get_message_content,
    _resolve_project_id,
)
from runtime_service.services.test_case_service_v2.schemas import (
    TestCaseServiceConfig,
    build_test_case_service_config,
)

REQUIREMENT_REVIEW_RESULTS_PATH = "/api/requirement-review-service/results"
GENERATION_POLICY_ALLOW = "allow_generation"
GENERATION_POLICY_WITH_ASSUMPTIONS = "allow_generation_with_assumptions"
GENERATION_POLICY_BLOCK = "block_generation"
GATE_ACTION_PASS = "pass"
GATE_ACTION_BLOCK = "block"
GATE_ACTION_INJECT = "inject"
_REVIEW_RESULT_CACHE_TTL_SECONDS = 30.0
_MAX_LISTED_ITEMS = 5

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequirementGateDecision:
    action: str
    block_message: str | None = None
    system_note: str | None = None
    review_result: Mapping[str, Any] | None = None


@dataclass
class _CachedReviewResult:
    fetched_at: float
    payload: Mapping[str, Any] | None = None
    available: bool = field(default=False)


def _build_interaction_client() -> InteractionDataServiceClient | None:
    try:
        config = get_config()
    except RuntimeError:
        config = None
    client = InteractionDataServiceClient(build_interaction_data_service_config(config))
    if not client.is_configured:
        return None
    return client


def fetch_latest_review_result(
    project_id: str,
    *,
    client: InteractionDataServiceClient | None = None,
) -> tuple[Mapping[str, Any] | None, bool]:
    """返回 (最新评审结果, 服务是否可用)。查询失败按服务不可用处理。"""
    resolved_client = client or _build_interaction_client()
    if resolved_client is None:
        return None, False
    try:
        payload = resolved_client.get_json(
            REQUIREMENT_REVIEW_RESULTS_PATH,
            params={"project_id": project_id, "limit": 1, "offset": 0},
        )
    except Exception:
        logger.warning(
            "test_case_service_v2 requirement gate query failed, fallback to pass-through",
            extra={"project_id": project_id},
            exc_info=True,
        )
        return None, False

    items = payload.get("items") if isinstance(payload, Mapping) else None
    if not isinstance(items, list) or not items:
        return None, True
    first = items[0]
    if not isinstance(first, Mapping):
        return None, True
    return first, True


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text:
            items.append(text)
    return items


def _format_listed_items(items: list[str]) -> str:
    limited = items[:_MAX_LISTED_ITEMS]
    lines = [f"- {item}" for item in limited]
    if len(items) > _MAX_LISTED_ITEMS:
        lines.append(f"- ……（另有 {len(items) - _MAX_LISTED_ITEMS} 项，见评审报告）")
    return "\n".join(lines)


def _build_block_message(result: Mapping[str, Any]) -> str:
    review_score = result.get("review_score")
    score_text = f"{review_score}" if review_score is not None else "未知"
    reason = str(result.get("generation_policy_reason") or "").strip()
    missing_items = _coerce_string_list(result.get("missing_or_ambiguous_items"))
    suggestions = _coerce_string_list(result.get("suggestions_to_improve"))

    sections = [
        "⛔ 需求评审门禁未通过，本次不生成正式测试用例。",
        f"最近一次需求评审结论为 blocked（评分 {score_text}）。",
    ]
    if reason:
        sections.append(f"门禁原因：{reason}")
    if missing_items:
        sections.append("主要缺失或歧义项：\n" + _format_listed_items(missing_items))
    if suggestions:
        sections.append("改进建议：\n" + _format_listed_items(suggestions))
    sections.append("请先按建议澄清需求并重新执行需求评审，评审通过后再发起用例生成。")
    return "\n\n".join(sections)


def _build_assumptions_note(result: Mapping[str, Any]) -> str:
    assumptions = _coerce_string_list(result.get("assumptions"))
    reason = str(result.get("generation_policy_reason") or "").strip()
    summary = str(result.get("requirement_summary") or "").strip()

    lines = [
        "# 需求评审门禁（conditional）",
        "最近一次需求评审结论为 conditional：允许生成，但必须基于以下评审假设。",
    ]
    if summary:
        lines.append(f"评审需求摘要：{summary}")
    if reason:
        lines.append(f"门禁说明：{reason}")
    if assumptions:
        lines.append("生成时必须显式遵循并在输出中列出以下假设：")
        lines.append(_format_listed_items(assumptions))
    else:
        lines.append("评审未提供具体假设，生成时需在输出中注明“需求评审为条件通过”。")
    return "\n".join(lines)


def decide_requirement_gate(
    result: Mapping[str, Any] | None,
    *,
    service_available: bool,
) -> RequirementGateDecision:
    if not service_available:
        return RequirementGateDecision(action=GATE_ACTION_PASS)
    if result is None:
        return RequirementGateDecision(
            action=GATE_ACTION_INJECT,
            system_note=(
                "# 需求评审门禁\n"
                "当前项目没有需求评审记录，本次生成未经过需求门禁。"
                "必须在最终输出开头注明：“⚠️ 本需求未经过需求评审门禁”。"
            ),
        )

    policy = str(result.get("generation_policy") or "").strip()
    if policy == GENERATION_POLICY_BLOCK:
        return RequirementGateDecision(
            action=GATE_ACTION_BLOCK,
            block_message=_build_block_message(result),
            review_result=result,
        )
    if policy == GENERATION_POLICY_WITH_ASSUMPTIONS:
        return RequirementGateDecision(
            action=GATE_ACTION_INJECT,
            system_note=_build_assumptions_note(result),
            review_result=result,
        )

    review_score = result.get("review_score")
    score_text = f"{review_score}" if review_score is not None else "未知"
    return RequirementGateDecision(
        action=GATE_ACTION_INJECT,
        system_note=(
            "# 需求评审门禁\n"
            f"最近一次需求评审结论为 pass（评分 {score_text}），允许生成正式测试用例。"
        ),
        review_result=result,
    )


class TestCaseRequirementGateMiddleware(AgentMiddleware[Any, Any]):
    """按项目最新需求评审结论对用例生成请求施加门禁。"""

    def __init__(self, service_config: TestCaseServiceConfig) -> None:
        self._service_config = service_config
        self._cache: dict[str, _CachedReviewResult] = {}

    def _resolve_service_config(self) -> TestCaseServiceConfig:
        try:
            config = get_config()
        except RuntimeError:
            return self._service_config
        if isinstance(config, dict):
            return build_test_case_service_config(config)
        return self._service_config

    @staticmethod
    def _is_generation_request(request: ModelRequest) -> bool:
        # 只按最新用户消息的文本意图判定；附件本身不代表生成请求，
        # 否则“传文件让 agent 总结”也会被门禁误拦。
        latest_user_message = _get_latest_user_message(list(request.messages or []))
        if latest_user_message is None:
            return False
        latest_user_text = _extract_text_from_content(
            _get_message_content(latest_user_message)
        )
        if not latest_user_text:
            return False
        return bool(_TEST_CASE_GENERATION_PATTERN.search(latest_user_text))

    def _fetch_with_cache(self, project_id: str) -> tuple[Mapping[str, Any] | None, bool]:
        cached = self._cache.get(project_id)
        now = time.monotonic()
        if cached is not None and now - cached.fetched_at < _REVIEW_RESULT_CACHE_TTL_SECONDS:
            return cached.payload, cached.available
        payload, available = fetch_latest_review_result(project_id)
        self._cache[project_id] = _CachedReviewResult(
            fetched_at=now,
            payload=payload,
            available=available,
        )
        return payload, available

    def _resolve_decision(self, request: ModelRequest) -> RequirementGateDecision | None:
        service_config = self._resolve_service_config()
        if not service_config.requirement_gate_enabled:
            return None
        if not self._is_generation_request(request):
            return None
        project_id = _resolve_project_id(request)
        if not project_id:
            return None
        result, available = self._fetch_with_cache(project_id)
        return decide_requirement_gate(result, service_available=available)

    @staticmethod
    def _apply_decision(
        request: ModelRequest,
        decision: RequirementGateDecision,
    ) -> tuple[ModelRequest, ModelResponse | None]:
        if decision.action == GATE_ACTION_BLOCK:
            return request, ModelResponse(
                result=[AIMessage(content=decision.block_message or "")]
            )
        if decision.action == GATE_ACTION_INJECT and decision.system_note:
            return (
                request.override(
                    system_message=append_to_system_message(
                        request.system_message, decision.system_note
                    )
                ),
                None,
            )
        return request, None

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        decision = self._resolve_decision(request)
        if decision is None:
            return handler(request)
        updated_request, blocked_response = self._apply_decision(request, decision)
        if blocked_response is not None:
            return blocked_response
        return handler(updated_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        service_config = self._resolve_service_config()
        if not service_config.requirement_gate_enabled:
            return await handler(request)
        if not self._is_generation_request(request):
            return await handler(request)
        project_id = _resolve_project_id(request)
        if not project_id:
            return await handler(request)
        result, available = await asyncio.to_thread(self._fetch_with_cache, project_id)
        decision = decide_requirement_gate(result, service_available=available)
        updated_request, blocked_response = self._apply_decision(request, decision)
        if blocked_response is not None:
            return blocked_response
        return await handler(updated_request)


__all__ = [
    "GATE_ACTION_BLOCK",
    "GATE_ACTION_INJECT",
    "GATE_ACTION_PASS",
    "GENERATION_POLICY_ALLOW",
    "GENERATION_POLICY_BLOCK",
    "GENERATION_POLICY_WITH_ASSUMPTIONS",
    "REQUIREMENT_REVIEW_RESULTS_PATH",
    "RequirementGateDecision",
    "TestCaseRequirementGateMiddleware",
    "decide_requirement_gate",
    "fetch_latest_review_result",
]
