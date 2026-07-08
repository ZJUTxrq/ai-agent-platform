from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.sse import sse_client
from pydantic import BaseModel, Field

from runtime_service.services.test_case_service_v2.schemas import TestCaseServiceConfig

TEST_CASE_KNOWLEDGE_SERVER_NAME = "test_case_knowledge"
REQUIRED_KNOWLEDGE_TOOL_NAMES = {
    "query_project_knowledge",
    "list_project_knowledge_documents",
    "get_project_knowledge_document_status",
}
logger = logging.getLogger(__name__)


def build_test_case_knowledge_mcp_specs(
    service_config: TestCaseServiceConfig,
) -> dict[str, dict[str, object]]:
    url = service_config.knowledge_mcp_url.strip()
    if not url:
        return {}

    return {
        TEST_CASE_KNOWLEDGE_SERVER_NAME: {
            "transport": "sse",
            "url": url,
            "timeout": service_config.knowledge_timeout_seconds,
            "sse_read_timeout": service_config.knowledge_sse_read_timeout_seconds,
        }
    }


class _QueryProjectKnowledgeArgs(BaseModel):
    project_id: str = Field(description="Project id that scopes the knowledge base.")
    query: str = Field(description="Natural language query for project knowledge.")
    mode: str | None = None
    top_k: int | None = None
    metadata_filters: dict[str, Any] | None = None
    metadata_boost: dict[str, Any] | None = None
    strict_scope: bool | None = None
    only_need_context: bool | None = Field(
        default=None,
        description=(
            "Set true to skip answer synthesis and return verbatim source chunks "
            "with citations (faster, better for rule-level referencing)."
        ),
    )


class _ListProjectKnowledgeDocumentsArgs(BaseModel):
    project_id: str = Field(description="Project id that scopes the knowledge base.")
    status: str | None = None
    limit: int | None = None


class _GetProjectKnowledgeDocumentStatusArgs(BaseModel):
    project_id: str = Field(description="Project id that scopes the knowledge base.")
    document_id: str = Field(description="Knowledge document id to inspect.")


# 与 lightrag/mcp/server.py 中的工具定义保持一致；名称和参数 schema 是稳定契约，
# 因此可以在启动时静态注册，把 MCP 连接推迟到每次工具调用时建立。
_KNOWLEDGE_TOOL_DEFINITIONS: tuple[tuple[str, str, type[BaseModel]], ...] = (
    (
        "query_project_knowledge",
        "Query project-scoped knowledge and return an answer with citations.",
        _QueryProjectKnowledgeArgs,
    ),
    (
        "list_project_knowledge_documents",
        "List project-scoped indexed documents and their overall status.",
        _ListProjectKnowledgeDocumentsArgs,
    ),
    (
        "get_project_knowledge_document_status",
        "Get the status of a single project-scoped knowledge document.",
        _GetProjectKnowledgeDocumentStatusArgs,
    ),
)


async def call_knowledge_mcp_tool(
    service_config: TestCaseServiceConfig,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """建立一次性 MCP 会话并调用指定工具，返回文本化结果。"""
    url = service_config.knowledge_mcp_url.strip()
    async with sse_client(
        url,
        timeout=service_config.knowledge_timeout_seconds,
        sse_read_timeout=service_config.knowledge_sse_read_timeout_seconds,
    ) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
    return _normalize_call_tool_result(tool_name, result)


def _build_lazy_knowledge_tool(
    service_config: TestCaseServiceConfig,
    name: str,
    description: str,
    args_schema: type[BaseModel],
) -> StructuredTool:
    async def call_tool(**kwargs: Any) -> str:
        arguments = {key: value for key, value in kwargs.items() if value is not None}
        try:
            return await call_knowledge_mcp_tool(service_config, name, arguments)
        except Exception as exc:  # noqa: BLE001 - 连接失败不应中断用例生成流程
            logger.warning(
                "test_case_service_v2 knowledge MCP call failed",
                extra={
                    "knowledge_mcp_url": service_config.knowledge_mcp_url,
                    "tool_name": name,
                },
                exc_info=True,
            )
            return json.dumps(
                {
                    "error": "knowledge_mcp_unavailable",
                    "tool": name,
                    "detail": f"{type(exc).__name__}: {exc}"[:300],
                    "hint": (
                        "知识库当前不可用。请如实声明本次结论未使用项目知识库，"
                        "不要虚构查询结果。"
                    ),
                },
                ensure_ascii=False,
            )

    return StructuredTool.from_function(
        coroutine=call_tool,
        name=name,
        description=description,
        args_schema=args_schema,
        infer_schema=False,
        response_format="content",
    )


def get_test_case_knowledge_tools(
    service_config: TestCaseServiceConfig,
) -> list[Any]:
    if not service_config.knowledge_mcp_enabled:
        return []
    if not service_config.knowledge_mcp_url.strip():
        return []

    return [
        _build_lazy_knowledge_tool(service_config, name, description, args_schema)
        for name, description, args_schema in _KNOWLEDGE_TOOL_DEFINITIONS
    ]


async def aget_test_case_knowledge_tools(
    service_config: TestCaseServiceConfig,
) -> list[Any]:
    return get_test_case_knowledge_tools(service_config)


def _normalize_call_tool_result(tool_name: str, result: Any) -> str:
    texts: list[str] = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text:
            texts.append(text)
    body = "\n".join(texts)

    if getattr(result, "isError", False):
        return json.dumps(
            {
                "error": "knowledge_mcp_tool_error",
                "tool": tool_name,
                "detail": body[:500],
                "hint": (
                    "知识库工具执行失败。请如实声明本次结论未使用项目知识库，"
                    "不要虚构查询结果。"
                ),
            },
            ensure_ascii=False,
        )
    return body


__all__ = [
    "REQUIRED_KNOWLEDGE_TOOL_NAMES",
    "TEST_CASE_KNOWLEDGE_SERVER_NAME",
    "aget_test_case_knowledge_tools",
    "build_test_case_knowledge_mcp_specs",
    "call_knowledge_mcp_tool",
    "get_test_case_knowledge_tools",
]
