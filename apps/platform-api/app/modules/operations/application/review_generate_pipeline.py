from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.core.context.models import ActorContext
from app.core.runtime_contract import normalize_runtime_payload
from app.modules.operations.application.ports import (
    OperationExecutionResult,
    OperationExecutorProtocol,
    StoredOperation,
)
from app.modules.runtime_gateway.application.ports import RuntimeGatewayUpstreamProtocol

REVIEW_AND_GENERATE_KIND = "testcase.review_and_generate"
DEFAULT_REVIEW_GRAPH_ID = "requirement_review_agent"
DEFAULT_GENERATE_GRAPH_ID = "test_case_agent_v2"
GENERATION_POLICY_ALLOW = "allow_generation"
GENERATION_POLICY_WITH_ASSUMPTIONS = "allow_generation_with_assumptions"
GENERATION_POLICY_BLOCK = "block_generation"

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


def extract_final_ai_text(run_output: Any) -> str:
    messages: Sequence[Any] | None = None
    if isinstance(run_output, Mapping):
        candidate = run_output.get("messages")
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
            messages = candidate
    if messages is None:
        raise ValueError("runtime_run_output_missing_messages")
    for message in reversed(list(messages)):
        if not _is_ai_message(message):
            continue
        text = _extract_text_from_content(message.get("content")).strip()
        if text:
            return text
    raise ValueError("runtime_run_output_missing_ai_message")


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


def build_generation_message(
    *,
    requirement_text: str,
    review_result: Mapping[str, Any],
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
    if assumptions:
        assumption_lines = "\n".join(f"- {item}" for item in assumptions)
        sections.append(
            "本次评审为条件通过，生成时必须遵循以下评审假设，"
            f"并在输出中显式列出：\n{assumption_lines}"
        )
    return "\n\n".join(sections)


class RequirementReviewAndGenerateExecutor(OperationExecutorProtocol):
    """两 agent 协作流水线：先需求评审，按门禁结论决定是否继续生成测试用例。"""

    kind = REVIEW_AND_GENERATE_KIND

    def __init__(
        self,
        *,
        upstream: RuntimeGatewayUpstreamProtocol,
        review_graph_id: str = DEFAULT_REVIEW_GRAPH_ID,
        generate_graph_id: str = DEFAULT_GENERATE_GRAPH_ID,
    ) -> None:
        self._upstream = upstream
        self._review_graph_id = review_graph_id
        self._generate_graph_id = generate_graph_id

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
        if not requirement_text and not attachments:
            raise ValueError(
                "requirement_text or attachments is required for review-and-generate pipeline"
            )

        review_text_parts = [_REVIEW_INSTRUCTION]
        if requirement_text:
            review_text_parts.append(f"需求内容：\n{requirement_text}")
        if attachments:
            review_text_parts.append("需求文档见附件，请先解析附件内容再评审。")

        review_run = await self._wait_run(
            graph_id=self._review_graph_id,
            project_id=project_id,
            content=_build_message_content(
                text="\n\n".join(review_text_parts),
                attachments=attachments,
            ),
        )
        review_text = extract_final_ai_text(review_run)
        review_result = extract_structured_review_result(review_text)
        generation_policy = str(review_result.get("generation_policy") or "").strip()
        quality_gate = str(review_result.get("quality_gate") or "").strip()

        review_payload: dict[str, Any] = {
            "quality_gate": quality_gate,
            "generation_policy": generation_policy,
            "review_score": review_result.get("review_score"),
            "report_markdown": review_text,
            "structured_result": review_result,
        }

        if generation_policy == GENERATION_POLICY_BLOCK:
            return OperationExecutionResult(
                result_payload={
                    "project_id": project_id,
                    "review": review_payload,
                    "generation": {
                        "executed": False,
                        "reason": "review_gate_blocked",
                    },
                },
                metadata={
                    "quality_gate": quality_gate,
                    "generation_policy": generation_policy,
                    "generation_executed": False,
                },
            )

        generation_run = await self._wait_run(
            graph_id=self._generate_graph_id,
            project_id=project_id,
            message=build_generation_message(
                requirement_text=requirement_text,
                review_result=review_result,
            ),
        )
        generation_text = extract_final_ai_text(generation_run)

        return OperationExecutionResult(
            result_payload={
                "project_id": project_id,
                "review": review_payload,
                "generation": {
                    "executed": True,
                    "output_markdown": generation_text,
                },
            },
            metadata={
                "quality_gate": quality_gate,
                "generation_policy": generation_policy,
                "generation_executed": True,
            },
        )


__all__ = [
    "DEFAULT_GENERATE_GRAPH_ID",
    "DEFAULT_REVIEW_GRAPH_ID",
    "REVIEW_AND_GENERATE_KIND",
    "RequirementReviewAndGenerateExecutor",
    "build_generation_message",
    "extract_final_ai_text",
    "extract_structured_review_result",
]
