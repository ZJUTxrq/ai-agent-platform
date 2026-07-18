<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/platform/EmptyState.vue'
import StateBanner from '@/components/platform/StateBanner.vue'
import StatusPill from '@/components/platform/StatusPill.vue'
import RequirementReviewOverviewStrip from '@/components/platform/RequirementReviewOverviewStrip.vue'
import RequirementReviewWorkspaceNav from '@/components/platform/RequirementReviewWorkspaceNav.vue'
import { useWorkspaceProjectContext } from '@/composables/useWorkspaceProjectContext'
import BaseChatTemplate from '@/modules/chat/components/BaseChatTemplate.vue'
import { resolveChatTarget } from '@/modules/chat/types'
import {
  getRequirementReviewOverview,
  listRequirementReviewResults
} from '@/services/requirement-review/requirement-review.service'
import type { RequirementReviewOverview, RequirementReviewResult } from '@/types/management'
import { writeRecentChatTarget } from '@/utils/chatTarget'
import { formatDateTime } from '@/utils/format'

const LATEST_RESULT_POLL_MS = 15000
const TESTCASE_V2_DRAFT_TARGET_ID = 'test_case_agent_v2'
const CHAT_KICKOFF_STORAGE_PREFIX = 'pw:chat:kickoff'

const route = useRoute()
const router = useRouter()
const { activeProjectId, activeProject } = useWorkspaceProjectContext()

const overview = ref<RequirementReviewOverview | null>(null)
const loading = ref(false)
const error = ref('')
const compactChrome = ref(false)
const latestResult = ref<RequirementReviewResult | null>(null)
let latestResultTimer: number | null = null

const reviewTarget = computed(() =>
  resolveChatTarget({
    targetType: 'graph',
    graphId: 'requirement_review_agent',
    graphName: '需求评审',
    updatedAt: new Date().toISOString()
  })
)

const initialThreadId = computed(() =>
  typeof route.query.threadId === 'string' && route.query.threadId.trim() ? route.query.threadId.trim() : ''
)

const initialBlank = computed(() => !initialThreadId.value && route.query.blank === '1')

watchEffect(() => {
  if (!activeProjectId.value) {
    return
  }

  writeRecentChatTarget(activeProjectId.value, {
    targetType: 'graph',
    graphId: 'requirement_review_agent',
    graphName: '需求评审'
  })
})

async function loadOverview(projectId: string) {
  loading.value = true
  error.value = ''

  try {
    overview.value = await getRequirementReviewOverview(projectId)
  } catch (loadError) {
    overview.value = null
    error.value = loadError instanceof Error ? loadError.message : '需求评审概览加载失败'
  } finally {
    loading.value = false
  }
}

const latestGateTone = computed<'neutral' | 'success' | 'warning' | 'danger'>(() => {
  const gate = (latestResult.value?.quality_gate || '').trim().toLowerCase()
  if (gate === 'pass') {
    return 'success'
  }
  if (gate === 'conditional') {
    return 'warning'
  }
  if (gate === 'blocked' || gate === 'fail') {
    return 'danger'
  }
  return 'neutral'
})

const latestResultAllowsGeneration = computed(() => {
  const policy = (latestResult.value?.generation_policy || '').trim()
  return policy === 'allow_generation' || policy === 'allow_generation_with_assumptions'
})

async function refreshLatestResult(projectId: string) {
  try {
    const page = await listRequirementReviewResults(projectId, { limit: 1 })
    latestResult.value = page.items[0] ?? null
  } catch {
    // 接力提示是增强能力，查询失败时静默保持现状，不打断评审对话。
  }
}

function stopLatestResultPolling() {
  if (latestResultTimer !== null) {
    window.clearInterval(latestResultTimer)
    latestResultTimer = null
  }
}

function startLatestResultPolling(projectId: string) {
  stopLatestResultPolling()
  void refreshLatestResult(projectId)
  latestResultTimer = window.setInterval(() => {
    void refreshLatestResult(projectId)
  }, LATEST_RESULT_POLL_MS)
}

onBeforeUnmount(stopLatestResultPolling)

function buildGenerationKickoffMessage(result: RequirementReviewResult) {
  const summary = (result.requirement_summary || '').trim()
  const scoreText = result.review_score !== null && result.review_score !== undefined ? `${result.review_score}` : '未知'
  const lines = [
    '请基于最近一次已通过需求评审的需求，生成正式测试用例并保存。',
    '',
    `评审结论：${result.quality_gate}（评分 ${scoreText}）。`
  ]
  if (summary) {
    lines.push('', `需求摘要（来自评审记录）：${summary}`)
  }
  lines.push('', '生成前请先查询项目知识库补充业务上下文；如评审为条件通过，必须遵循评审假设并在输出中列出。')
  return lines.join('\n')
}

function continueToGeneration() {
  const projectId = activeProjectId.value?.trim()
  const result = latestResult.value
  if (!projectId || !result) {
    return
  }

  const kickoffKey = `${CHAT_KICKOFF_STORAGE_PREFIX}:${projectId}:${TESTCASE_V2_DRAFT_TARGET_ID}`
  window.localStorage.setItem(kickoffKey, buildGenerationKickoffMessage(result))
  void router.push({
    path: '/workspace/testcase-v2/generate',
    query: { ts: String(Date.now()) }
  })
}

watch(
  () => activeProjectId.value,
  (projectId) => {
    if (!projectId) {
      overview.value = null
      error.value = ''
      latestResult.value = null
      stopLatestResultPolling()
      return
    }

    void loadOverview(projectId)
    startLatestResultPolling(projectId)
  },
  { immediate: true }
)
</script>

<template>
  <section class="pw-page-shell pw-chat-page-shell">
    <RequirementReviewWorkspaceNav :compact="compactChrome" />

    <StateBanner
      v-if="error"
      title="需求评审概览加载失败"
      :description="error"
      variant="warning"
    />

    <RequirementReviewOverviewStrip
      v-if="!compactChrome"
      :overview="overview"
      :compact="false"
    />

    <div
      v-if="!compactChrome && activeProject && latestResult"
      class="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--pw-border,#e5e7eb)] bg-[var(--pw-surface,#fff)] px-4 py-3"
    >
      <span class="text-sm font-medium">最近一次评审</span>
      <StatusPill
        :label="latestResult.quality_gate || 'unknown'"
        :tone="latestGateTone"
      />
      <span
        v-if="latestResult.review_score !== null && latestResult.review_score !== undefined"
        class="text-sm text-[var(--pw-text-secondary,#6b7280)]"
      >
        评分 {{ latestResult.review_score }}
      </span>
      <span class="text-xs text-[var(--pw-text-secondary,#6b7280)]">
        {{ formatDateTime(latestResult.created_at) }}
      </span>
      <template v-if="latestResultAllowsGeneration">
        <BaseButton @click="continueToGeneration">
          生成测试用例 →
        </BaseButton>
        <span class="text-xs text-[var(--pw-text-secondary,#6b7280)]">
          将跳转到 Testcase V2 并预填生成指令，发送即开始生成。
        </span>
      </template>
      <span
        v-else
        class="text-xs text-[var(--pw-text-secondary,#6b7280)]"
      >
        评审未通过，请按报告澄清需求后重新提交评审；用例生成入口已按门禁策略关闭。
      </span>
    </div>

    <EmptyState
      v-if="!activeProject"
      icon="project"
      title="请先选择项目"
      description="需求评审也是项目级入口。没有项目上下文时，评审结果和文档都无法稳定归档。"
    />

    <BaseChatTemplate
      v-else
      :target="reviewTarget"
      :initial-thread-id="initialThreadId"
      :initial-blank="initialBlank"
      context-notice="当前页面固定接入 graph: requirement_review_agent，只做需求质量评分、门禁判断和评审结果沉淀。"
      source-note="建议上传真实 PRD/PDF。评审通过后，再进入后续测试用例生成流程。"
      :display="{
        title: '需求评审 · AI 对话生成',
        description: '上传 PRD 或粘贴需求内容，先完成评分、门禁结论、风险项和补充建议。',
        emptyTitle: '上传 PRD 开始评审',
        emptyDescription: '第一条消息建议直接说明评审目标，例如：请从测试角度评审这份 PRD，输出评分、门禁结论、主要缺口和修改建议。'
      }"
      :features="{
        allowRunOptions: true,
        showHistory: true,
        showArtifacts: true,
        showContextBar: true
      }"
      @compact-mode-change="compactChrome = $event"
    />
  </section>
</template>
