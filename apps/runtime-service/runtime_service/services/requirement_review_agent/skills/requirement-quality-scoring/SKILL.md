---
name: requirement-quality-scoring
description: 基于需求证据从五个测试质量维度进行 0-100 分评分。
---

# 需求质量评分

使用本 skill 对需求质量进行维度化评分。

## 前置条件

必须先完成 `requirement-evidence-analysis`。

## 评分维度

每个维度 0-20 分，总分 100 分：

- `business_objective`：业务目标和用户价值是否清楚
- `scope_boundary`：做什么、不做什么是否明确
- `workflow_and_rules`：主流程、分支、异常、业务规则是否完整
- `testability`：输入、输出、状态、验收标准是否可观察、可验证
- `risks_and_dependencies`：接口、数据、权限、边界条件、假设是否可识别

## 评分原则

- 只根据当前证据评分，不要脑补缺失业务规则。
- 需求越能直接支撑测试设计，分数越高。
- 关键规则缺失、状态不明、验收标准不可观察时要明显扣分。
- `review_score` 必须等于五个维度分之和。

## 输出要求

输出中间评分结果，不要给最终 JSON。

必须包含：

- `dimension_scores`
- `review_score`
- 主要扣分依据
- 可以支撑高分的明确证据

本 skill 不生成正式测试用例。
