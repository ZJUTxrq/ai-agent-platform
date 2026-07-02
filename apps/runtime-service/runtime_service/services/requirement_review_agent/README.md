# Requirement Review Agent

独立的需求质量评审智能体，用于在测试用例生成前先做测试视角的需求评分与门禁判断。

这个 agent 与 `test_case_service_v2` 解耦，职责聚焦在：

- 阅读 PRD / 图片 / PDF 等需求输入
- 从测试视角评估需求是否清晰、完整、可验证
- 输出 `pass` / `conditional` / `blocked`
- 在需要时把评审结果与附件解析结果持久化到 `interaction-data-service`

它不生成正式测试用例，也不调用测试用例落库工具。

## Graph

- graph id: `requirement_review_agent`
- implementation: `runtime_service/services/requirement_review_agent/graph.py`
- runtime context: `RuntimeContext`
- multimodal input: `MultimodalMiddleware`
- skills root: `/skills/`

## Skills 流程

`requirement-evidence-analysis`
-> `requirement-quality-scoring`
-> `requirement-gate-decision`
-> `requirement-review-output-formatter`
-> `requirement-review-persistence`（仅在需要正式保存时）

说明：

- `requirement-evidence-analysis`：整理需求事实、证据边界、缺失信息
- `requirement-quality-scoring`：按五个维度评分并计算总分
- `requirement-gate-decision`：给出门禁结论和生成策略
- `requirement-review-output-formatter`：输出 Markdown 评审报告和结构化 JSON
- `requirement-review-persistence`：调用 `persist_requirement_review_result` 写入 `interaction-data-service`

## 输出结构

最终输出分两层：

1. 用户可直接阅读的 Markdown 评审报告
2. `结构化结果（供入库接口使用）` 小节中的 JSON 代码块

结构化 JSON 对齐
`runtime_service.services.requirement_review_agent.schemas.RequirementReviewResult`

核心字段：

- `requirement_summary`
- `review_score`
- `quality_gate`
- `dimension_scores`
- `key_findings`
- `major_risks`
- `missing_or_ambiguous_items`
- `suggestions_to_improve`
- `assumptions`
- `generation_policy`
- `generation_policy_reason`

约束：

- `review_score` 必须等于五个 `dimension_scores` 之和
- `quality_gate` 必须与评分阈值一致
- `generation_policy` 必须与 `quality_gate` 一致

## 持久化

当前持久化通过服务私有工具完成：

- `persist_requirement_review_result`

写入目标：

- `/api/requirement-review-service/documents`
- `/api/requirement-review-service/results`

行为说明：

- 先把当前附件解析结果写成 requirement review document 记录
- 再把最终评审结果写成 requirement review result 记录
- 若没有合法 `project_id`，不会向远端发请求
- 若远端未配置，返回结构化跳过结果，而不是直接打崩链路

## 常用配置

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `requirement_review_default_model_id` | `deepseek_chat` | 服务默认主模型 |
| `requirement_review_multimodal_parser_model_id` | `.env` 默认 parser model | 多模态解析模型 |
| `requirement_review_multimodal_detail_mode` | `False` | 是否启用详细解析 |
| `requirement_review_multimodal_detail_text_max_chars` | `2000` | 详细解析字符上限 |
| `requirement_review_persistence_enabled` | `True` | 是否允许正式持久化 |

## 运行上下文

常用 context 字段：

- `project_id`
- `model_id`
- `multimodal_parser_model_id`

Example:

```json
{
  "project_id": "00000000-0000-0000-0000-000000000001",
  "model_id": "deepseek_chat",
  "multimodal_parser_model_id": "openai_vision"
}
```
