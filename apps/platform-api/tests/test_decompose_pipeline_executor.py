from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from typing import Any

from app.core.context.models import ActorContext
from app.modules.operations.application.decompose_pipeline import (
    DEFAULT_DECOMPOSE_GRAPH_ID,
    RequirementDecomposeExecutor,
    build_feature_list_command,
    extract_parsed_attachment_text,
    extract_structured_feature_list,
)
from app.modules.operations.application.ports import StoredOperation
from app.modules.operations.domain import OperationStatus
from app.modules.requirement_review.domain import RequirementFeatureList

PROJECT_ID = "00000000-0000-0000-0000-000000000001"


class _FakeUpstream:
    def __init__(self, run_output: Any) -> None:
        self._run_output = run_output
        self.calls: list[dict[str, Any]] = []

    async def wait_global_run(self, payload: dict[str, Any] | None = None) -> Any:
        self.calls.append(payload or {})
        return self._run_output


class _FakeFeatureListService:
    def __init__(self) -> None:
        self.created_commands: list[Any] = []

    async def create_feature_list(
        self, *, actor: Any, project_id: str, command: Any
    ) -> RequirementFeatureList:
        self.created_commands.append(command)
        now = datetime.now(timezone.utc)
        return RequirementFeatureList(
            id="feature-list-1",
            project_id=project_id,
            batch_id=command.batch_id,
            idempotency_key=command.idempotency_key,
            version=1,
            status="draft",
            decomposable=command.decomposable,
            undecomposable_reason=command.undecomposable_reason,
            requirement_text=command.requirement_text,
            requirement_summary=command.requirement_summary,
            modules=command.modules,
            open_questions=command.open_questions,
            assumptions=command.assumptions,
            raw_result=command.raw_result,
            created_at=now,
            updated_at=now,
        )


def _make_operation(**overrides: Any) -> StoredOperation:
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "id": "op-1",
        "kind": "requirement.feature_list.decompose",
        "status": OperationStatus.RUNNING,
        "requested_by": "user-1",
        "tenant_id": None,
        "project_id": PROJECT_ID,
        "idempotency_key": None,
        "input_payload": {"requirement_text": "优惠券活动需求原文"},
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


def _structured_result(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "requirement_summary": "优惠券领取需求",
        "decomposable": True,
        "modules": [
            {
                "name": "优惠券",
                "feature_points": [
                    {
                        "feature_id": "coupon-claim",
                        "title": "用户领取优惠券",
                        "source_excerpt": "用户可在活动页领取优惠券",
                        "inferred": False,
                    }
                ],
            }
        ],
        "open_questions": ["活动时间未说明"],
        "assumptions": [],
    }
    values.update(overrides)
    return values


def _run_output(structured: dict[str, Any]) -> dict[str, Any]:
    report = (
        "# 拆解报告\n\n拆解内容……\n\n"
        "## 结构化结果（供入库接口使用）\n\n"
        "```json\n" + json.dumps(structured, ensure_ascii=False) + "\n```\n"
    )
    return {"messages": [
        {"type": "human", "content": "拆解请求"},
        {"type": "ai", "content": report},
    ]}


class ExtractStructuredFeatureListTest(unittest.TestCase):
    def test_extracts_block_by_decomposable_key_even_when_false(self) -> None:
        structured = _structured_result(decomposable=False, modules=[])
        structured["undecomposable_reason"] = "需求过于模糊"
        text = "```json\n" + json.dumps(structured, ensure_ascii=False) + "\n```"
        result = extract_structured_feature_list(text)
        self.assertFalse(result["decomposable"])

    def test_missing_block_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "decompose_structured_result_not_found"):
            extract_structured_feature_list("没有 JSON 的报告")

    def test_command_requires_requirement_summary(self) -> None:
        with self.assertRaisesRegex(ValueError, "requirement_summary"):
            build_feature_list_command(
                operation=_make_operation(),
                requirement_text="原文",
                structured_result={"decomposable": True},
            )


class ExtractParsedAttachmentTextTest(unittest.TestCase):
    def test_prefers_parsed_text_and_falls_back_to_summary(self) -> None:
        run_output = {
            "messages": [],
            "multimodal_attachments": [
                {
                    "name": "需求文档.pdf",
                    "parsed_text": "第一章 优惠券领取规则……",
                    "summary_for_model": "摘要不应被使用",
                },
                {
                    "name": "原型图.png",
                    "parsed_text": None,
                    "summary_for_model": "登录页原型：手机号+验证码",
                },
            ],
        }
        text = extract_parsed_attachment_text(run_output)
        self.assertIn("【附件：需求文档.pdf】", text)
        self.assertIn("第一章 优惠券领取规则", text)
        self.assertIn("登录页原型：手机号+验证码", text)
        self.assertNotIn("摘要不应被使用", text)

    def test_missing_state_key_returns_empty(self) -> None:
        self.assertEqual(extract_parsed_attachment_text({"messages": []}), "")


class RequirementDecomposePipelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_decompose_persists_draft_feature_list(self) -> None:
        upstream = _FakeUpstream(_run_output(_structured_result()))
        service = _FakeFeatureListService()
        executor = RequirementDecomposeExecutor(
            upstream=upstream,
            feature_list_service=service,
        )

        result = await executor.execute(operation=_make_operation(), actor=_actor())

        run_call = upstream.calls[0]
        self.assertEqual(run_call["assistant_id"], DEFAULT_DECOMPOSE_GRAPH_ID)
        self.assertIn(
            "优惠券活动需求原文", run_call["input"]["messages"][0]["content"]
        )

        command = service.created_commands[0]
        self.assertEqual(command.idempotency_key, "fl:op:op-1")
        self.assertEqual(command.requirement_text, "优惠券活动需求原文")
        self.assertTrue(command.decomposable)

        feature_list = result.result_payload["feature_list"]
        self.assertEqual(feature_list["status"], "draft")
        self.assertEqual(
            result.result_payload["next_step"], "feature_list_confirm_required"
        )
        self.assertEqual(result.metadata["feature_list_id"], "feature-list-1")
        self.assertTrue(result.metadata["decomposable"])

    async def test_attachment_only_backfills_requirement_text_from_parsed(self) -> None:
        run_output = _run_output(_structured_result())
        run_output["multimodal_attachments"] = [
            {
                "name": "需求文档.pdf",
                "parsed_text": "第一章 优惠券领取规则：每人限领一张。",
                "summary_for_model": "",
            }
        ]
        upstream = _FakeUpstream(run_output)
        service = _FakeFeatureListService()
        executor = RequirementDecomposeExecutor(
            upstream=upstream,
            feature_list_service=service,
        )

        await executor.execute(
            operation=_make_operation(
                input_payload={
                    "attachments": [
                        {
                            "type": "file",
                            "mime_type": "application/pdf",
                            "data": "ZmFrZQ==",
                        }
                    ]
                }
            ),
            actor=_actor(),
        )

        command = service.created_commands[0]
        self.assertIn("每人限领一张", command.requirement_text)
        self.assertIn("【附件：需求文档.pdf】", command.requirement_text)

    async def test_attachment_with_instruction_text_persists_parsed_text_only(self) -> None:
        run_output = _run_output(_structured_result())
        run_output["multimodal_attachments"] = [
            {
                "name": "需求文档.pdf",
                "parsed_text": "第一章 优惠券领取规则：每人限领一张。",
                "summary_for_model": "",
            }
        ]
        upstream = _FakeUpstream(run_output)
        service = _FakeFeatureListService()
        executor = RequirementDecomposeExecutor(
            upstream=upstream,
            feature_list_service=service,
        )

        await executor.execute(
            operation=_make_operation(
                input_payload={
                    "requirement_text": "需求拆解",
                    "attachments": [
                        {
                            "type": "file",
                            "mime_type": "application/pdf",
                            "data": "ZmFrZQ==",
                        }
                    ],
                }
            ),
            actor=_actor(),
        )

        command = service.created_commands[0]
        # 带附件时输入框文字只是模型指令，不应作为需求原文落库
        self.assertNotIn("需求拆解", command.requirement_text)
        self.assertIn("每人限领一张", command.requirement_text)

    async def test_undecomposable_result_requires_clarification(self) -> None:
        structured = _structured_result(decomposable=False, modules=[])
        structured["undecomposable_reason"] = "需求过于模糊"
        upstream = _FakeUpstream(_run_output(structured))
        service = _FakeFeatureListService()
        executor = RequirementDecomposeExecutor(
            upstream=upstream,
            feature_list_service=service,
        )

        result = await executor.execute(operation=_make_operation(), actor=_actor())

        self.assertEqual(
            result.result_payload["next_step"], "requirement_clarification_required"
        )
        self.assertFalse(result.metadata["decomposable"])

    async def test_requires_project_id(self) -> None:
        executor = RequirementDecomposeExecutor(
            upstream=_FakeUpstream({}),
            feature_list_service=_FakeFeatureListService(),
        )
        with self.assertRaisesRegex(ValueError, "project_id"):
            await executor.execute(
                operation=_make_operation(project_id=None),
                actor=_actor(),
            )

    async def test_requires_requirement_text_or_attachments(self) -> None:
        executor = RequirementDecomposeExecutor(
            upstream=_FakeUpstream({}),
            feature_list_service=_FakeFeatureListService(),
        )
        with self.assertRaisesRegex(ValueError, "requirement_text"):
            await executor.execute(
                operation=_make_operation(input_payload={}),
                actor=_actor(),
            )


if __name__ == "__main__":
    unittest.main()
