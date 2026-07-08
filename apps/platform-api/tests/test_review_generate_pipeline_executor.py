from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from typing import Any

from app.core.context.models import ActorContext
from app.modules.operations.application.ports import StoredOperation
from app.modules.operations.application.review_generate_pipeline import (
    DEFAULT_GENERATE_GRAPH_ID,
    DEFAULT_REVIEW_GRAPH_ID,
    RequirementReviewAndGenerateExecutor,
    build_generation_message,
    extract_final_ai_text,
    extract_structured_review_result,
)
from app.modules.operations.domain import OperationStatus

PROJECT_ID = "00000000-0000-0000-0000-000000000001"


class _FakeUpstream:
    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    async def wait_global_run(self, payload: dict[str, Any] | None = None) -> Any:
        payload = payload or {}
        self.calls.append(payload)
        return self._responses[str(payload.get("assistant_id"))]


def _make_operation(**overrides: Any) -> StoredOperation:
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "id": "op-1",
        "kind": "testcase.review_and_generate",
        "status": OperationStatus.RUNNING,
        "requested_by": "user-1",
        "tenant_id": None,
        "project_id": PROJECT_ID,
        "idempotency_key": None,
        "input_payload": {"requirement_text": "新增闪购特惠房需求"},
        "result_payload": {},
        "error_payload": {},
        "metadata": {},
        "cancel_requested_at": None,
        "started_at": now,
        "finished_at": None,
        "archived_at": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return StoredOperation(**values)


def _actor() -> ActorContext:
    return ActorContext(subject="user-1")


def _review_run_output(structured: dict[str, Any]) -> dict[str, Any]:
    report = (
        "# 评审报告\n\n评审内容……\n\n"
        "## 结构化结果（供入库接口使用）\n\n"
        "```json\n" + json.dumps(structured, ensure_ascii=False) + "\n```\n"
    )
    return {"messages": [
        {"type": "human", "content": "评审请求"},
        {"type": "ai", "content": report},
    ]}


def _blocked_structured() -> dict[str, Any]:
    return {
        "quality_gate": "blocked",
        "review_score": 62,
        "generation_policy": "block_generation",
        "generation_policy_reason": "与知识库约束冲突",
        "assumptions": [],
    }


def _conditional_structured() -> dict[str, Any]:
    return {
        "quality_gate": "conditional",
        "review_score": 78,
        "generation_policy": "allow_generation_with_assumptions",
        "generation_policy_reason": "边界条件需补充",
        "assumptions": ["退款仍走原路退回"],
    }


class ExtractHelpersTest(unittest.TestCase):
    def test_extract_final_ai_text_picks_last_ai_message(self) -> None:
        output = {"messages": [
            {"type": "ai", "content": "第一轮"},
            {"type": "tool", "content": "tool output"},
            {"type": "ai", "content": [{"type": "text", "text": "最终回答"}]},
        ]}
        self.assertEqual(extract_final_ai_text(output), "最终回答")

    def test_extract_final_ai_text_rejects_missing_messages(self) -> None:
        with self.assertRaisesRegex(ValueError, "runtime_run_output_missing_messages"):
            extract_final_ai_text({"values": {}})

    def test_extract_structured_review_result_takes_last_valid_block(self) -> None:
        text = (
            "```json\n{\"other\": 1}\n```\n"
            "```json\n{\"generation_policy\": \"allow_generation\","
            " \"quality_gate\": \"pass\"}\n```"
        )
        result = extract_structured_review_result(text)
        self.assertEqual(result["generation_policy"], "allow_generation")

    def test_extract_structured_review_result_missing_block_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "review_structured_result_not_found"):
            extract_structured_review_result("没有 JSON 的报告")

    def test_build_generation_message_includes_assumptions(self) -> None:
        message = build_generation_message(
            requirement_text="需求正文",
            review_result=_conditional_structured(),
        )
        self.assertIn("需求正文", message)
        self.assertIn("conditional", message)
        self.assertIn("退款仍走原路退回", message)


class ReviewAndGeneratePipelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_review_skips_generation(self) -> None:
        upstream = _FakeUpstream(
            {DEFAULT_REVIEW_GRAPH_ID: _review_run_output(_blocked_structured())}
        )
        executor = RequirementReviewAndGenerateExecutor(upstream=upstream)

        result = await executor.execute(operation=_make_operation(), actor=_actor())

        self.assertEqual(len(upstream.calls), 1)
        self.assertEqual(
            result.result_payload["generation"],
            {"executed": False, "reason": "review_gate_blocked"},
        )
        self.assertFalse(result.metadata["generation_executed"])
        self.assertEqual(result.metadata["generation_policy"], "block_generation")

    async def test_conditional_review_runs_generation_with_assumptions(self) -> None:
        upstream = _FakeUpstream(
            {
                DEFAULT_REVIEW_GRAPH_ID: _review_run_output(_conditional_structured()),
                DEFAULT_GENERATE_GRAPH_ID: {
                    "messages": [{"type": "ai", "content": "## 测试用例\n用例内容"}]
                },
            }
        )
        executor = RequirementReviewAndGenerateExecutor(upstream=upstream)

        result = await executor.execute(operation=_make_operation(), actor=_actor())

        self.assertEqual(len(upstream.calls), 2)
        generation_call = upstream.calls[1]
        self.assertEqual(generation_call["assistant_id"], DEFAULT_GENERATE_GRAPH_ID)
        generation_message = generation_call["input"]["messages"][0]["content"]
        self.assertIn("退款仍走原路退回", generation_message)
        self.assertTrue(result.result_payload["generation"]["executed"])
        self.assertIn("测试用例", result.result_payload["generation"]["output_markdown"])
        self.assertTrue(result.metadata["generation_executed"])

    async def test_project_scope_injected_into_run_payloads(self) -> None:
        upstream = _FakeUpstream(
            {DEFAULT_REVIEW_GRAPH_ID: _review_run_output(_blocked_structured())}
        )
        executor = RequirementReviewAndGenerateExecutor(upstream=upstream)

        await executor.execute(operation=_make_operation(), actor=_actor())

        review_call = upstream.calls[0]
        context = review_call.get("context") or {}
        self.assertEqual(context.get("project_id"), PROJECT_ID)

    async def test_requires_project_id(self) -> None:
        executor = RequirementReviewAndGenerateExecutor(upstream=_FakeUpstream({}))
        with self.assertRaisesRegex(ValueError, "project_id"):
            await executor.execute(
                operation=_make_operation(project_id=None),
                actor=_actor(),
            )

    async def test_requires_requirement_text(self) -> None:
        executor = RequirementReviewAndGenerateExecutor(upstream=_FakeUpstream({}))
        with self.assertRaisesRegex(ValueError, "requirement_text"):
            await executor.execute(
                operation=_make_operation(input_payload={}),
                actor=_actor(),
            )


if __name__ == "__main__":
    unittest.main()
