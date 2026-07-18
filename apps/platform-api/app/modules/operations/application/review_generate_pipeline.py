from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.context.models import ActorContext
from app.core.runtime_contract import normalize_runtime_payload
from app.modules.operations.application.ports import (
    OperationExecutionResult,
    OperationExecutorProtocol,
    StoredOperation,
)
from app.modules.requirement_review.application import (
    ListRequirementReviewResultsQuery,
    RequirementReviewService,
)
from app.modules.requirement_review.domain import RequirementFeatureList
from app.modules.runtime_gateway.application.ports import RuntimeGatewayUpstreamProtocol

REVIEW_AND_GENERATE_KIND = "testcase.review_and_generate"
DEFAULT_REVIEW_GRAPH_ID = "requirement_review_agent"
DEFAULT_GENERATE_GRAPH_ID = "test_case_agent_v2"
GENERATION_POLICY_ALLOW = "allow_generation"
GENERATION_POLICY_WITH_ASSUMPTIONS = "allow_generation_with_assumptions"
GENERATION_POLICY_BLOCK = "block_generation"
FEATURE_LIST_STATUS_CONFIRMED = "confirmed"

_JSON_BLOCK_PATTERN = re.compile(r"```json\s*(.*?)```", re.DOTALL)

_REVIEW_INSTRUCTION = (
    "请对以下需求进行完整的需求质量评审，"
    "并在完成评审后调用 persist_requirement_review_result 正式保存评审结果。"
)

_MAX_ATTACHMENT_COUNT = 6
_MAX_ATTACHMENT_TOTAL_BASE64_CHARS = 20_000_000


def _normalize_attachments(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("attachments must be a list")
    if len(value) > _MAX_ATTACHMENT_COUNT:
        raise ValueError(f"attachments exceed limit of {_MAX_ATTACHMENT_COUNT}")

    normalized: list[dict[str, Any]] = []
    total_chars = 0
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("attachment entries must be objects")
        block_type = str(item.get("type") or "").strip()
        if block_type not in {"image", "file"}:
            raise ValueError("attachment type must be image or file")
        data = item.get("data") or item.get("base64")
        if not isinstance(data, str) or not data.strip():
            raise ValueError("attachment data is required")
        mime_type = item.get("mime_type") or item.get("mimeType")
        if not isinstance(mime_type, str) or not mime_type.strip():
            raise ValueError("attachment mime_type is required")
        total_chars += len(data)
        if total_chars > _MAX_ATTACHMENT_TOTAL_BASE64_CHARS:
            raise ValueError("attachments exceed total size limit")
        block: dict[str, Any] = {
            "type": block_type,
            "mime_type": mime_type.strip(),
            "data": data,
        }
        metadata = item.get("metadata")
        if isinstance(metadata, Mapping):
            block["metadata"] = dict(metadata)
        normalized.append(block)
    return normalized


def _build_message_content(
    *,
    text: str,
    attachments: list[dict[str, Any]],
) -> Any:
    if not attachments:
        return text
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    blocks.extend(attachments)
    return blocks


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if isinstance(item, Mapping):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(part for part in parts if part)


def _is_ai_message(message: Any) -> bool:
    if not isinstance(message, Mapping):
        return False
    message_type = message.get("type")
    role = message.get("role")
    return message_type in {"ai", "assistant"} or role == "assistant"


def _iter_ai_texts_reversed(run_output: Any) -> list[str]:
    messages: Sequence[Any] | None = None
    if isinstance(run_output, Mapping):
        candidate = run_output.get("messages")
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
            messages = candidate
    if messages is None:
        raise ValueError("runtime_run_output_missing_messages")
    texts: list[str] = []
    for message in reversed(list(messages)):
        if not _is_ai_message(message):
            continue
        text = _extract_text_from_content(message.get("content")).strip()
        if text:
            texts.append(text)
    return texts


def extract_final_ai_text(run_output: Any) -> str:
    texts = _iter_ai_texts_reversed(run_output)
    if not texts:
        raise ValueError("runtime_run_output_missing_ai_message")
    return texts[0]


def extract_review_outcome(run_output: Any) -> tuple[str, dict[str, Any]]:
    """返回 (评审报告文本, 结构化结果)。

    agent 通常在输出完整报告后再调用落库工具，最后一条消息只是简短确认，
    因此结构化 JSON 块要按从后往前的顺序在所有 AI 消息里找。
    """
    texts = _iter_ai_texts_reversed(run_output)
    if not texts:
        raise ValueError("runtime_run_output_missing_ai_message")
    for text in texts:
        try:
            return text, extract_structured_review_result(text)
        except ValueError:
            continue
    raise ValueError("review_structured_result_not_found")


def extract_structured_review_result(review_text: str) -> dict[str, Any]:
    matches = _JSON_BLOCK_PATTERN.findall(review_text)
    for raw_block in reversed(matches):
        try:
            parsed = json.loads(raw_block.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("generation_policy"):
            return parsed
    raise ValueError("review_structured_result_not_found")


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text:
            items.append(text)
    return items


def build_feature_list_context(feature_list: RequirementFeatureList) -> str:
    modules_json = json.dumps(feature_list.modules, ensure_ascii=False, indent=2)
    sections = [
        (
            f"以下是已人工确认的需求拆解 featureList"
            f"（id={feature_list.id}，版本 v{feature_list.version}），"
            "仅作为辅助结构使用："
        ),
        (
            "- 评分与缺失/歧义判断必须锚定需求原文；"
            "featureList 中 `inferred: true` 的推断项与 open_questions "
            "不得视为需求原文已覆盖的内容。"
        ),
        f"```json\n{modules_json}\n```",
    ]
    if feature_list.open_questions:
        sections.append(
            "拆解阶段遗留的待澄清项：\n"
            + "\n".join(f"- {item}" for item in feature_list.open_questions)
        )
    if feature_list.assumptions:
        sections.append(
            "拆解阶段的推断假设：\n"
            + "\n".join(f"- {item}" for item in feature_list.assumptions)
        )
    return "\n\n".join(sections)


def feature_list_binding_payload(
    feature_list: RequirementFeatureList,
) -> dict[str, Any]:
    return {
        "id": feature_list.id,
        "version": feature_list.version,
        "status": feature_list.status,
        "confirmed_at": (
            feature_list.confirmed_at.isoformat() if feature_list.confirmed_at else None
        ),
        "confirmed_by": feature_list.confirmed_by,
    }


def build_generation_message(
    *,
    requirement_text: str,
    review_result: Mapping[str, Any],
    feature_list: RequirementFeatureList | None = None,
) -> str:
    quality_gate = str(review_result.get("quality_gate") or "").strip() or "unknown"
    review_score = review_result.get("review_score")
    score_text = f"{review_score}" if review_score is not None else "未知"
    assumptions = _coerce_string_list(review_result.get("assumptions"))

    sections = [
        "请基于以下需求生成正式测试用例。",
        f"该需求已通过需求评审门禁：结论 {quality_gate}（评分 {score_text}）。",
        f"需求内容：\n{requirement_text}",
    ]
    if feature_list is not None:
        modules_json = json.dumps(feature_list.modules, ensure_ascii=False, indent=2)
        sections.append(
            "需求已有人工确认的模块化拆解 featureList"
            f"（id={feature_list.id}，版本 v{feature_list.version}），"
            "测试用例必须按其中的模块与功能点组织，并覆盖各功能点的验收标准：\n"
            f"```json\n{modules_json}\n```"
        )
    if assumptions:
        assumption_lines = "\n".join(f"- {item}" for item in assumptions)
        sections.append(
            "本次评审为条件通过，生成时必须遵循以下评审假设，"
            f"并在输出中显式列出：\n{assumption_lines}"
        )
    return "\n\n".join(sections)


class RequirementReviewAndGenerateExecutor(OperationExecutorProtocol):
    """两 agent 协作流水线：先需求评审，按门禁结论决定是否继续生成测试用例。

    可选接入 featureList：入参携带 feature_list_id 时，要求该拆解已人工确认，
    评审/生成消息都会携带拆解结构，且生成前会复核版本未变。
    """

    kind = REVIEW_AND_GENERATE_KIND

    def __init__(
        self,
        *,
        upstream: RuntimeGatewayUpstreamProtocol,
        review_graph_id: str = DEFAULT_REVIEW_GRAPH_ID,
        generate_graph_id: str = DEFAULT_GENERATE_GRAPH_ID,
        feature_list_service: RequirementReviewService | None = None,
    ) -> None:
        self._upstream = upstream
        self._review_graph_id = review_graph_id
        self._generate_graph_id = generate_graph_id
        self._feature_list_service = feature_list_service

    _PERSISTED_REVIEW_MAX_AGE = timedelta(minutes=15)

    async def _fetch_recent_persisted_review(
        self,
        *,
        actor: ActorContext,
        project_id: str,
    ) -> dict[str, Any] | None:
        """兜底：评审 agent 已通过工具落库、但最终消息缺 JSON 块时，回读最新评审结果。

        只接受近 15 分钟内的记录，避免误用历史评审结论做门禁。
        """
        if self._feature_list_service is None:
            return None
        page = await self._feature_list_service.list_results(
            actor=actor,
            project_id=project_id,
            query=ListRequirementReviewResultsQuery(limit=1, offset=0),
        )
        if not page.items:
            return None
        latest = page.items[0]
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created_at > self._PERSISTED_REVIEW_MAX_AGE:
            return None
        return {
            "requirement_summary": latest.requirement_summary,
            "review_score": latest.review_score,
            "quality_gate": latest.quality_gate,
            "generation_policy": latest.generation_policy,
            "generation_policy_reason": latest.generation_policy_reason,
            "assumptions": latest.assumptions,
            "persisted_result_id": latest.id,
        }

    async def _get_feature_list(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        feature_list_id: str,
    ) -> RequirementFeatureList:
        if self._feature_list_service is None:
            raise ValueError(
                "feature_list_service is not configured for review-and-generate pipeline"
            )
        return await self._feature_list_service.get_feature_list(
            actor=actor,
            project_id=project_id,
            feature_list_id=feature_list_id,
        )

    async def _wait_run(self, *, graph_id: str, project_id: str, content: Any) -> Any:
        payload = normalize_runtime_payload(
            payload={
                "assistant_id": graph_id,
                "input": {"messages": [{"role": "user", "content": content}]},
            },
            project_id=project_id,
        )
        return await self._upstream.wait_global_run(payload)

    async def execute(
        self,
        *,
        operation: StoredOperation,
        actor: ActorContext,
    ) -> OperationExecutionResult:
        project_id = (operation.project_id or "").strip()
        if not project_id:
            raise ValueError("project_id is required for review-and-generate pipeline")
        requirement_text = str(
            operation.input_payload.get("requirement_text") or ""
        ).strip()
        attachments = _normalize_attachments(operation.input_payload.get("attachments"))
        feature_list_id = str(
            operation.input_payload.get("feature_list_id") or ""
        ).strip()
        if not requirement_text and not attachments and not feature_list_id:
            raise ValueError(
                "requirement_text or attachments is required for review-and-generate pipeline"
            )

        feature_list: RequirementFeatureList | None = None
        if feature_list_id:
            feature_list = await self._get_feature_list(
                actor=actor,
                project_id=project_id,
                feature_list_id=feature_list_id,
            )
            if feature_list.status != FEATURE_LIST_STATUS_CONFIRMED:
                # 未确认的拆解不允许进入正式评审，直接短路
                return OperationExecutionResult(
                    result_payload={
                        "project_id": project_id,
                        "feature_list": feature_list_binding_payload(feature_list),
                        "review": {
                            "executed": False,
                            "reason": "feature_list_not_confirmed",
                        },
                        "generation": {
                            "executed": False,
                            "reason": "feature_list_not_confirmed",
                        },
                    },
                    metadata={
                        "feature_list_id": feature_list.id,
                        "feature_list_version": feature_list.version,
                        "feature_list_status": feature_list.status,
                        "generation_executed": False,
                    },
                )
            if not requirement_text:
                requirement_text = feature_list.requirement_text.strip()

        review_text_parts = [_REVIEW_INSTRUCTION]
        if requirement_text:
            review_text_parts.append(f"需求内容：\n{requirement_text}")
        if attachments:
            review_text_parts.append("需求文档见附件，请先解析附件内容再评审。")
        if feature_list is not None:
            review_text_parts.append(build_feature_list_context(feature_list))

        review_run = await self._wait_run(
            graph_id=self._review_graph_id,
            project_id=project_id,
            content=_build_message_content(
                text="\n\n".join(review_text_parts),
                attachments=attachments,
            ),
        )
        try:
            review_text, review_result = extract_review_outcome(review_run)
        except ValueError as exc:
            if str(exc) != "review_structured_result_not_found":
                raise
            review_text = extract_final_ai_text(review_run)
            fallback_result = await self._fetch_recent_persisted_review(
                actor=actor,
                project_id=project_id,
            )
            if fallback_result is None:
                raise
            review_result = fallback_result
        generation_policy = str(review_result.get("generation_policy") or "").strip()
        quality_gate = str(review_result.get("quality_gate") or "").strip()

        review_payload: dict[str, Any] = {
            "quality_gate": quality_gate,
            "generation_policy": generation_policy,
            "review_score": review_result.get("review_score"),
            "report_markdown": review_text,
            "structured_result": review_result,
        }
        base_result_payload: dict[str, Any] = {"project_id": project_id}
        base_metadata: dict[str, Any] = {}
        if feature_list is not None:
            # 评审结论与 featureList 版本绑定，供后续追溯评审时的拆解快照
            base_result_payload["feature_list"] = feature_list_binding_payload(
                feature_list
            )
            base_metadata["feature_list_id"] = feature_list.id
            base_metadata["feature_list_version"] = feature_list.version

        if generation_policy == GENERATION_POLICY_BLOCK:
            return OperationExecutionResult(
                result_payload={
                    **base_result_payload,
                    "review": review_payload,
                    "generation": {
                        "executed": False,
                        "reason": "review_gate_blocked",
                    },
                },
                metadata={
                    **base_metadata,
                    "quality_gate": quality_gate,
                    "generation_policy": generation_policy,
                    "generation_executed": False,
                },
            )

        if feature_list is not None:
            # 评审耗时窗口内拆解可能被编辑：版本或状态变化则终止生成，要求重走确认
            latest_feature_list = await self._get_feature_list(
                actor=actor,
                project_id=project_id,
                feature_list_id=feature_list.id,
            )
            if (
                latest_feature_list.version != feature_list.version
                or latest_feature_list.status != FEATURE_LIST_STATUS_CONFIRMED
            ):
                return OperationExecutionResult(
                    result_payload={
                        **base_result_payload,
                        "feature_list_latest": feature_list_binding_payload(
                            latest_feature_list
                        ),
                        "review": review_payload,
                        "generation": {
                            "executed": False,
                            "reason": "feature_list_changed_during_review",
                        },
                    },
                    metadata={
                        **base_metadata,
                        "quality_gate": quality_gate,
                        "generation_policy": generation_policy,
                        "generation_executed": False,
                        "feature_list_latest_version": latest_feature_list.version,
                        "feature_list_latest_status": latest_feature_list.status,
                    },
                )

        generation_run = await self._wait_run(
            graph_id=self._generate_graph_id,
            project_id=project_id,
            content=build_generation_message(
                requirement_text=requirement_text,
                review_result=review_result,
                feature_list=feature_list,
            ),
        )
        generation_text = extract_final_ai_text(generation_run)

        return OperationExecutionResult(
            result_payload={
                **base_result_payload,
                "review": review_payload,
                "generation": {
                    "executed": True,
                    "output_markdown": generation_text,
                },
            },
            metadata={
                **base_metadata,
                "quality_gate": quality_gate,
                "generation_policy": generation_policy,
                "generation_executed": True,
            },
        )


__all__ = [
    "DEFAULT_GENERATE_GRAPH_ID",
    "DEFAULT_REVIEW_GRAPH_ID",
    "FEATURE_LIST_STATUS_CONFIRMED",
    "REVIEW_AND_GENERATE_KIND",
    "RequirementReviewAndGenerateExecutor",
    "build_feature_list_context",
    "build_generation_message",
    "extract_final_ai_text",
    "extract_review_outcome",
    "extract_structured_review_result",
    "feature_list_binding_payload",
]
