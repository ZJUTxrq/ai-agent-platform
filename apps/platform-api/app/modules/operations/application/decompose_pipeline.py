from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from app.core.context.models import ActorContext
from app.core.normalization import clean_str
from app.core.runtime_contract import normalize_runtime_payload
from app.modules.operations.application.ports import (
    OperationExecutionResult,
    OperationExecutorProtocol,
    StoredOperation,
)
from app.modules.operations.application.review_generate_pipeline import (
    _build_message_content,
    _normalize_attachments,
    extract_final_ai_text,
)
from app.modules.requirement_review.application import (
    CreateRequirementFeatureListCommand,
    RequirementReviewService,
)
from app.modules.runtime_gateway.application.ports import RuntimeGatewayUpstreamProtocol

REQUIREMENT_DECOMPOSE_KIND = "requirement.feature_list.decompose"
DEFAULT_DECOMPOSE_GRAPH_ID = "requirement_decompose_agent"

_JSON_BLOCK_PATTERN = re.compile(r"```json\s*(.*?)```", re.DOTALL)

_DECOMPOSE_INSTRUCTION = (
    "请把以下需求忠实拆解为「模块 -> 功能点 -> 验收标准/约束/优先级」的结构化草稿，"
    "拆解结果只作为待人工确认的 featureList，不要评审打分，也不要生成测试用例。"
)


def extract_structured_feature_list(decompose_text: str) -> dict[str, Any]:
    matches = _JSON_BLOCK_PATTERN.findall(decompose_text)
    for raw_block in reversed(matches):
        try:
            parsed = json.loads(raw_block.strip())
        except json.JSONDecodeError:
            continue
        # decomposable 可能为 False，按键存在性识别结构化块
        if isinstance(parsed, dict) and "decomposable" in parsed:
            return parsed
    raise ValueError("decompose_structured_result_not_found")


_MAX_PARSED_ATTACHMENT_TEXT_CHARS = 30_000


def extract_parsed_attachment_text(run_output: Any) -> str:
    """从 run 状态里取多模态中间件的解析全文（确定性产物，非 LLM 复述）。

    纯附件发起拆解时用它回填 requirement_text，保证后续评审能锚定完整原文。
    """
    if not isinstance(run_output, Mapping):
        return ""
    artifacts = run_output.get("multimodal_attachments")
    if not isinstance(artifacts, list):
        return ""
    sections: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        parsed = artifact.get("parsed_text")
        text = parsed.strip() if isinstance(parsed, str) else ""
        if not text:
            summary = artifact.get("summary_for_model")
            text = summary.strip() if isinstance(summary, str) else ""
        if not text:
            continue
        name = artifact.get("name")
        header = f"【附件：{name}】" if isinstance(name, str) and name.strip() else "【附件】"
        sections.append(f"{header}\n{text}")
    combined = "\n\n".join(sections)
    if len(combined) > _MAX_PARSED_ATTACHMENT_TEXT_CHARS:
        combined = (
            combined[:_MAX_PARSED_ATTACHMENT_TEXT_CHARS]
            + "\n\n……（解析文本超长已截断）"
        )
    return combined


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text:
            items.append(text)
    return items


def _coerce_module_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def build_feature_list_command(
    *,
    operation: StoredOperation,
    requirement_text: str,
    structured_result: dict[str, Any],
) -> CreateRequirementFeatureListCommand:
    requirement_summary = str(structured_result.get("requirement_summary") or "").strip()
    if not requirement_summary:
        raise ValueError("decompose_result_missing_requirement_summary")
    return CreateRequirementFeatureListCommand(
        batch_id=clean_str(operation.input_payload.get("batch_id")),
        # 幂等键绑定 operation：worker 重试不会产生重复草稿
        idempotency_key=f"fl:op:{operation.id}",
        decomposable=bool(structured_result.get("decomposable")),
        undecomposable_reason=clean_str(
            structured_result.get("undecomposable_reason")
        ),
        requirement_text=requirement_text,
        requirement_summary=requirement_summary,
        modules=_coerce_module_list(structured_result.get("modules")),
        open_questions=_coerce_string_list(structured_result.get("open_questions")),
        assumptions=_coerce_string_list(structured_result.get("assumptions")),
        raw_result=dict(structured_result),
    )


class RequirementDecomposeExecutor(OperationExecutorProtocol):
    """需求拆解流水线：跑拆解 agent，把结构化 featureList 以草稿状态落库，等待人工确认。"""

    kind = REQUIREMENT_DECOMPOSE_KIND

    def __init__(
        self,
        *,
        upstream: RuntimeGatewayUpstreamProtocol,
        feature_list_service: RequirementReviewService,
        decompose_graph_id: str = DEFAULT_DECOMPOSE_GRAPH_ID,
    ) -> None:
        self._upstream = upstream
        self._feature_list_service = feature_list_service
        self._decompose_graph_id = decompose_graph_id

    async def execute(
        self,
        *,
        operation: StoredOperation,
        actor: ActorContext,
    ) -> OperationExecutionResult:
        project_id = (operation.project_id or "").strip()
        if not project_id:
            raise ValueError("project_id is required for requirement decompose pipeline")
        requirement_text = str(
            operation.input_payload.get("requirement_text") or ""
        ).strip()
        attachments = _normalize_attachments(operation.input_payload.get("attachments"))
        if not requirement_text and not attachments:
            raise ValueError(
                "requirement_text or attachments is required for requirement decompose pipeline"
            )

        text_parts = [_DECOMPOSE_INSTRUCTION]
        if requirement_text:
            text_parts.append(f"需求内容：\n{requirement_text}")
        if attachments:
            text_parts.append("需求文档见附件，请先解析附件内容再拆解。")

        payload = normalize_runtime_payload(
            payload={
                "assistant_id": self._decompose_graph_id,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": _build_message_content(
                                text="\n\n".join(text_parts),
                                attachments=attachments,
                            ),
                        }
                    ]
                },
            },
            project_id=project_id,
        )
        decompose_run = await self._upstream.wait_global_run(payload)
        decompose_text = extract_final_ai_text(decompose_run)
        structured_result = extract_structured_feature_list(decompose_text)

        # 带附件时，落库的需求原文取多模态解析全文：此时输入框文字只是给模型的指令
        # （如"需求拆解"），不是需求内容；纯文字提交时文字本身才是需求原文
        if attachments:
            requirement_text = extract_parsed_attachment_text(decompose_run)

        feature_list = await self._feature_list_service.create_feature_list(
            actor=actor,
            project_id=project_id,
            command=build_feature_list_command(
                operation=operation,
                requirement_text=requirement_text,
                structured_result=structured_result,
            ),
        )

        return OperationExecutionResult(
            result_payload={
                "project_id": project_id,
                "feature_list": feature_list.model_dump(mode="json"),
                "report_markdown": decompose_text,
                "next_step": (
                    "feature_list_confirm_required"
                    if feature_list.decomposable
                    else "requirement_clarification_required"
                ),
            },
            metadata={
                "feature_list_id": feature_list.id,
                "feature_list_version": feature_list.version,
                "feature_list_status": feature_list.status,
                "decomposable": feature_list.decomposable,
            },
        )


__all__ = [
    "DEFAULT_DECOMPOSE_GRAPH_ID",
    "REQUIREMENT_DECOMPOSE_KIND",
    "RequirementDecomposeExecutor",
    "build_feature_list_command",
    "extract_parsed_attachment_text",
    "extract_structured_feature_list",
]
