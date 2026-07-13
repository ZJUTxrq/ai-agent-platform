"""quote-verify capability skill handler.

提供 verify_quote 工具:核验一段引用是否逐字存在于当前项目知识库原文中。
经 handler_loader 按 manifest 声明动态加载,不由 runtime_service 直接 import。
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from runtime_service.services.requirement_review_agent.knowledge_mcp import (
    call_knowledge_mcp_tool,
)

# 归一化后引用短于该长度时拒绝核验:过短的片段在原文中的偶然命中没有证据价值
MIN_QUOTE_CHARS = 8
_WHITESPACE_PATTERN = re.compile(r"\s+")


class VerifyQuoteArgs(BaseModel):
    project_id: str = Field(description="Project id that scopes the knowledge base.")
    quote: str = Field(description="待核验的知识库规则引用(应为逐字原文)。")
    source_document: str | None = Field(
        default=None,
        description="评审中声明的来源文档名,仅用于结果回显与报告展示。",
    )


def _normalize(text: str | None) -> str:
    return _WHITESPACE_PATTERN.sub("", text or "")


def build_verify_quote_result(
    *,
    verified: bool,
    reason: str,
    quote: str,
    source_document: str | None,
    detail: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "verified": verified,
        "reason": reason,
        "quote": quote[:200],
        "source_document": source_document,
    }
    if detail:
        payload["detail"] = detail[:300]
    if not verified:
        payload["hint"] = (
            "该引用未通过原文核验,不得作为硬冲突依据;"
            "请修正引用后重新核验,或降级为待澄清项。"
        )
    return json.dumps(payload, ensure_ascii=False)


def get_tools(service_config: Any) -> list[StructuredTool]:
    if not getattr(service_config, "knowledge_mcp_enabled", False):
        return []
    if not str(getattr(service_config, "knowledge_mcp_url", "") or "").strip():
        return []

    async def verify_quote(
        project_id: str,
        quote: str,
        source_document: str | None = None,
    ) -> str:
        normalized_quote = _normalize(quote)
        if len(normalized_quote) < MIN_QUOTE_CHARS:
            return build_verify_quote_result(
                verified=False,
                reason="quote_too_short",
                quote=quote,
                source_document=source_document,
                detail=f"归一化后不足 {MIN_QUOTE_CHARS} 字符,无法作为核验对象",
            )
        try:
            raw = await call_knowledge_mcp_tool(
                service_config,
                "query_project_knowledge",
                {
                    "project_id": project_id,
                    "query": quote,
                    "only_need_context": True,
                    "top_k": 10,
                },
            )
        except Exception as exc:  # noqa: BLE001 - 核验失败不应中断评审
            return build_verify_quote_result(
                verified=False,
                reason="knowledge_mcp_unavailable",
                quote=quote,
                source_document=source_document,
                detail=f"{type(exc).__name__}: {exc}",
            )
        verified = normalized_quote in _normalize(raw)
        return build_verify_quote_result(
            verified=verified,
            reason=(
                "exact_match_found"
                if verified
                else "quote_not_found_in_project_knowledge"
            ),
            quote=quote,
            source_document=source_document,
        )

    return [
        StructuredTool.from_function(
            coroutine=verify_quote,
            name="verify_quote",
            description=(
                "核验一段引用是否逐字存在于当前项目知识库原文中。"
                "任何作为硬冲突依据的知识库引用,必须先通过本工具核验。"
            ),
            args_schema=VerifyQuoteArgs,
            infer_schema=False,
            response_format="content",
        )
    ]
