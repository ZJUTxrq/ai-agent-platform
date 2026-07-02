from pathlib import Path

import pythoncom
import win32com.client


OUT_PATH = Path(r"E:\project\bug-record-cn.docx")

LINES = [
    "Bug Record - 中文版",
    "",
    "日期：2026-06-16",
    "Bug 1：新增需求评审门禁 Skill 后，PDF 上传流程失败",
    "现象",
    "在 Testcase Agent V2 中加入 requirement-review-gate skill 后，用户携带 PDF 附件发起请求时，智能体流程会失败。",
    "后端 / 模型侧典型报错为：openai.BadRequestError 400，messages[n]: unknown variant file, expected text。",
    "原因",
    "新增的 requirement-review-gate 阶段在正式生成测试用例前，多了一次模型调用。历史聊天消息里仍然保留了 runtime-web 上传时的 PDF 文件内容块。",
    "主模型所使用的 OpenAI 兼容接口在普通对话消息中不接受 file block，只接受 text block。旧版多模态改写逻辑只保护当前附件路径，没有处理历史残留的 file / image block，因此在后续模型调用时这些旧块又被带了出去。",
    "修复",
    "保留多模态解析行为，但在真正发送给主模型前，对消息做一次模型侧清洗：把所有残留的 file / image block 都改写成文本摘要。",
    "修改文件：apps/runtime-service/runtime_service/middlewares/multimodal/prompting.py。",
    "关键函数：_sanitize_attachment_blocks_for_model、_fallback_attachment_block_text、_rewrite_latest_human_message_for_model。",
    "",
    "Bug 2：PDF 元数据落库了，但原始 PDF 文件没有保存成功",
    "现象",
    "runtime-web 可以成功上传 PDF，Testcase Agent V2 也能完成生成和持久化，但通过 runtime-web 上传的原始 PDF 文件不会出现在 Testcase V2 的文档管理下载链路里。",
    "文档元数据可能已经创建，但原始 PDF 资产可能缺失；持久化过程中可能出现 raw_attachment_payload_missing，或者生成空的 storage_path。",
    "原因",
    "Bug 1 的修复把模型侧看到的 file block 改写成了文本，但 document_persistence.py 仍然需要原始 PDF block / base64 内容，才能把原始文件上传到 interaction-data-service。",
    "持久化逻辑会优先读取 attachment.source_payload_base64，读不到时再回退到 source messages。由于消息已经被模型侧清洗，回退来源里的原始 block 已经不存在了。如果 state 中的附件原始 payload 缺失或已经被剥离，原始 PDF 字节就无法再上传。",
    "修复",
    "把“给模型看的文本化清洗”和“给持久化使用的原始附件缓存”分离开。主模型仍然只接收文本摘要，但 runtime-service 内部额外保留一份私有的原始附件 source blocks，专门供持久化使用。",
    "新增 state key：MULTIMODAL_SOURCE_BLOCKS_KEY = multimodal_source_blocks。",
    "修改文件：apps/runtime-service/runtime_service/middlewares/multimodal/types.py；apps/runtime-service/runtime_service/middlewares/multimodal/__init__.py；apps/runtime-service/runtime_service/middlewares/multimodal/middleware.py；apps/runtime-service/runtime_service/services/test_case_service_v2/document_persistence.py。",
    "新增回归测试：apps/runtime-service/runtime_service/tests/test_test_case_service_v2_document_persistence.py。",
    "验证",
    "在 Docker test profile 下运行 runtime-service 单测通过：177 passed，1 warning。剩余 warning 为第三方 langchain-community 的弃用告警。",
    "",
    "日期：2026-06-21",
    "Bug 3：Excel 导出一直停留在导出中，或者在平台页面返回 404",
    "现象",
    "在平台管理页面中，Testcase V2 和需求评审的导出都可能出现异常：界面一直停留在“导出中”，下载产物接口返回 404，或者 worker 端看似执行完成，但前端拿不到可下载文件。",
    "具体表现包括：requirement-review 的导出任务在 platform-api-worker 内部校验失败；部分导出任务长期停留在 submitted / exporting 状态；以及 platform-api 无法读取 worker 已生成的导出文件。",
    "原因",
    "这个导出问题不是单一前端问题，而是由三个后端链路问题叠加导致的。",
    "1）需求评审导出使用的分页大小是 500，但交互数据查询 schema 只允许 limit <= 200，因此 requirement-review 的导出会在 platform-api-worker 内部直接校验失败，Excel 文件根本没有生成出来。",
    "2）operation 任务在数据库事务提交前就被派发到了 Redis。在并发情况下，platform-api-worker 可能先消费到 operation id，但此时数据库里的 operation 记录还不可见，导致这次任务实际丢失，前端就一直显示导出中或 submitted。",
    "3）即使 worker 成功生成了 Excel 文件，platform-api 和 platform-api-worker 之前也没有共享同一个 operation artifact 目录。worker 把文件写在自己的本地目录里，platform-api 后续读取不到，因此下载产物接口返回 404。",
    "另外还有一个关联问题：路由访问过程中的 audit 日志 target_id 过长，可能超过 audit_logs.target_id（varchar(64)）长度限制，从而干扰这类管理页请求。",
    "修复",
    "将需求评审导出的分页大小从 500 调整为 200，与正式查询约束保持一致。",
    "将 operation 派发时机调整到数据库事务提交之后，确保 platform-api-worker 消费任务时一定能查到对应的 operation 记录。",
    "增加共享 Docker volume，让 platform-api-worker 写入、platform-api 读取同一个 /app/.runtime/operations-artifacts 目录。",
    "规范 audit target_id 的生成方式，优先使用稳定的路由模板，必要时压缩动态标识，确保始终不超过数据库字段长度限制。",
    "修改文件：apps/platform-api/app/modules/requirement_review/application/service.py；apps/platform-api/app/modules/operations/application/service.py；apps/platform-api/app/modules/audit/application/http_resolution.py；apps/platform-api/app/entrypoints/http/middleware/audit_log.py；deploy/docker-compose.stack.yml。",
    "新增回归测试：apps/platform-api/tests/test_operations_artifact_flow.py；apps/platform-api/tests/test_audit_http_resolution.py。",
    "验证",
    "worker 日志确认了 requirement-review 最初的导出失败原因，就是 ListRequirementReviewResultsQuery / ListRequirementReviewDocumentsQuery 拒绝了 limit=500。",
    "修复后，新创建的导出任务可以正常完成，platform-api 可以读取导出产物，需求评审结果记录也能在数据库里通过 batch_id 和 project_id 查询验证。",
]


def main() -> None:
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Add()
        sel = word.Selection
        sel.Font.Name = "Microsoft YaHei"
        sel.Font.Size = 11
        first = True
        for line in LINES:
            if not first:
                sel.TypeParagraph()
            first = False
            if line:
                sel.TypeText(line)
        doc.SaveAs(str(OUT_PATH), FileFormat=12)
        doc.Close(False)
    finally:
        word.Quit()
        pythoncom.CoUninitialize()

    print(OUT_PATH)


if __name__ == "__main__":
    main()
