from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
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
from app.modules.requirement_review.domain import (
    RequirementFeatureList,
    RequirementReviewResult,
    RequirementReviewResultPage,
)

PROJECT_ID = "00000000-0000-0000-0000-000000000001"
FEATURE_LIST_ID = "00000000-0000-0000-0000-0000000000fl"


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


def _make_feature_list(**overrides: Any) -> RequirementFeatureList:
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "id": FEATURE_LIST_ID,
        "project_id": PROJECT_ID,
        "version": 1,
        "status": "confirmed",
        "decomposable": True,
        "requirement_text": "优惠券活动需求原文",
        "requirement_summary": "优惠券领取需求",
        "modules": [
            {
                "name": "优惠券",
                "feature_points": [
                    {
                        "feature_id": "coupon-claim",
                        "title": "用户领取优惠券",
                        "source_excerpt": "用户可在活动页领取优惠券",
                        "acceptance_criteria": ["每人限领一张"],
                        "inferred": False,
                    }
                ],
            }
        ],
        "open_questions": ["过期券是否可退"],
        "assumptions": [],
        "confirmed_at": now,
        "confirmed_by": "user-1",
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return RequirementFeatureList(**values)


class _FakeFeatureListService:
    """按调用顺序弹出 feature list；最后一个响应保持复用。"""

    def __init__(
        self,
        responses: list[RequirementFeatureList] | None = None,
        *,
        persisted_results: list[RequirementReviewResult] | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._persisted_results = list(persisted_results or [])
        self.calls: list[str] = []

    async def get_feature_list(
        self, *, actor: Any, project_id: str, feature_list_id: str
    ) -> RequirementFeatureList:
        self.calls.append(feature_list_id)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]

    async def list_results(
        self, *, actor: Any, project_id: str, query: Any
    ) -> RequirementReviewResultPage:
        return RequirementReviewResultPage(
            items=self._persisted_results,
            total=len(self._persisted_results),
        )


def _make_persisted_result(**overrides: Any) -> RequirementReviewResult:
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "id": "persisted-result-1",
        "project_id": PROJECT_ID,
        "requirement_summary": "闪购需求评审摘要",
        "review_score": 54,
        "quality_gate": "blocked",
        "generation_policy": "block_generation",
        "generation_policy_reason": "需求关键规则缺失",
        "assumptions": [],
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return RequirementReviewResult(**values)


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


class ReviewOutcomeExtractionTest(unittest.IsolatedAsyncioTestCase):
    """评审 agent 落库后最后一条消息常是简短确认，JSON 块在更早的消息里。"""

    @staticmethod
    def _run_with_tool_ack(structured: dict[str, Any] | None) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"type": "human", "content": "评审请求"}]
        if structured is not None:
            report = (
                "# 评审报告\n\n```json\n"
                + json.dumps(structured, ensure_ascii=False)
                + "\n```"
            )
            messages.append({"type": "ai", "content": report})
        messages.append({"type": "tool", "content": "{\"status\": \"persisted\"}"})
        messages.append({"type": "ai", "content": "评审结果已正式保存。"})
        return {"messages": messages}

    async def test_structured_block_in_earlier_ai_message_is_used(self) -> None:
        upstream = _FakeUpstream(
            {DEFAULT_REVIEW_GRAPH_ID: self._run_with_tool_ack(_blocked_structured())}
        )
        executor = RequirementReviewAndGenerateExecutor(upstream=upstream)

        result = await executor.execute(operation=_make_operation(), actor=_actor())

        self.assertEqual(
            result.result_payload["generation"],
            {"executed": False, "reason": "review_gate_blocked"},
        )
        self.assertIn("评审报告", result.result_payload["review"]["report_markdown"])

    async def test_missing_block_falls_back_to_persisted_result(self) -> None:
        upstream = _FakeUpstream(
            {DEFAULT_REVIEW_GRAPH_ID: self._run_with_tool_ack(None)}
        )
        service = _FakeFeatureListService(
            persisted_results=[_make_persisted_result()]
        )
        executor = RequirementReviewAndGenerateExecutor(
            upstream=upstream,
            feature_list_service=service,
        )

        result = await executor.execute(operation=_make_operation(), actor=_actor())

        self.assertEqual(result.metadata["generation_policy"], "block_generation")
        self.assertFalse(result.metadata["generation_executed"])

    async def test_missing_block_without_fallback_raises(self) -> None:
        upstream = _FakeUpstream(
            {DEFAULT_REVIEW_GRAPH_ID: self._run_with_tool_ack(None)}
        )
        executor = RequirementReviewAndGenerateExecutor(upstream=upstream)

        with self.assertRaisesRegex(ValueError, "review_structured_result_not_found"):
            await executor.execute(operation=_make_operation(), actor=_actor())

    async def test_stale_persisted_result_is_not_used_as_fallback(self) -> None:
        upstream = _FakeUpstream(
            {DEFAULT_REVIEW_GRAPH_ID: self._run_with_tool_ack(None)}
        )
        stale = _make_persisted_result(
            created_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        service = _FakeFeatureListService(persisted_results=[stale])
        executor = RequirementReviewAndGenerateExecutor(
            upstream=upstream,
            feature_list_service=service,
        )

        with self.assertRaisesRegex(ValueError, "review_structured_result_not_found"):
            await executor.execute(operation=_make_operation(), actor=_actor())


class FeatureListGatedPipelineTest(unittest.IsolatedAsyncioTestCase):
    def _operation_with_feature_list(self) -> StoredOperation:
        return _make_operation(
            input_payload={"feature_list_id": FEATURE_LIST_ID}
        )

    async def test_unconfirmed_feature_list_short_circuits_pipeline(self) -> None:
        upstream = _FakeUpstream({})
        service = _FakeFeatureListService([_make_feature_list(status="draft")])
        executor = RequirementReviewAndGenerateExecutor(
            upstream=upstream,
            feature_list_service=service,
        )

        result = await executor.execute(
            operation=self._operation_with_feature_list(), actor=_actor()
        )

        self.assertEqual(len(upstream.calls), 0)
        self.assertEqual(
            result.result_payload["review"],
            {"executed": False, "reason": "feature_list_not_confirmed"},
        )
        self.assertEqual(
            result.result_payload["generation"],
            {"executed": False, "reason": "feature_list_not_confirmed"},
        )
        self.assertEqual(result.metadata["feature_list_status"], "draft")

    async def test_confirmed_feature_list_flows_into_review_and_generation(self) -> None:
        upstream = _FakeUpstream(
            {
                DEFAULT_REVIEW_GRAPH_ID: _review_run_output(_conditional_structured()),
                DEFAULT_GENERATE_GRAPH_ID: {
                    "messages": [{"type": "ai", "content": "## 测试用例\n用例内容"}]
                },
            }
        )
        service = _FakeFeatureListService([_make_feature_list()])
        executor = RequirementReviewAndGenerateExecutor(
            upstream=upstream,
            feature_list_service=service,
        )

        result = await executor.execute(
            operation=self._operation_with_feature_list(), actor=_actor()
        )

        review_message = upstream.calls[0]["input"]["messages"][0]["content"]
        # 评审消息带原文与拆解结构，且要求锚定原文评分
        self.assertIn("优惠券活动需求原文", review_message)
        self.assertIn("coupon-claim", review_message)
        self.assertIn("锚定需求原文", review_message)

        generation_message = upstream.calls[1]["input"]["messages"][0]["content"]
        self.assertIn("coupon-claim", generation_message)
        self.assertIn("按其中的模块与功能点组织", generation_message)

        self.assertTrue(result.result_payload["generation"]["executed"])
        binding = result.result_payload["feature_list"]
        self.assertEqual(binding["id"], FEATURE_LIST_ID)
        self.assertEqual(binding["version"], 1)
        self.assertEqual(result.metadata["feature_list_version"], 1)

    async def test_feature_list_changed_during_review_skips_generation(self) -> None:
        upstream = _FakeUpstream(
            {DEFAULT_REVIEW_GRAPH_ID: _review_run_output(_conditional_structured())}
        )
        service = _FakeFeatureListService(
            [
                _make_feature_list(),
                _make_feature_list(version=2, status="draft"),
            ]
        )
        executor = RequirementReviewAndGenerateExecutor(
            upstream=upstream,
            feature_list_service=service,
        )

        result = await executor.execute(
            operation=self._operation_with_feature_list(), actor=_actor()
        )

        self.assertEqual(len(upstream.calls), 1)
        self.assertEqual(
            result.result_payload["generation"],
            {"executed": False, "reason": "feature_list_changed_during_review"},
        )
        self.assertEqual(result.metadata["feature_list_latest_version"], 2)
        self.assertFalse(result.metadata["generation_executed"])

    async def test_feature_list_requires_configured_service(self) -> None:
        executor = RequirementReviewAndGenerateExecutor(upstream=_FakeUpstream({}))
        with self.assertRaisesRegex(ValueError, "feature_list_service"):
            await executor.execute(
                operation=self._operation_with_feature_list(),
                actor=_actor(),
            )


if __name__ == "__main__":
    unittest.main()
