<script setup lang="ts">
import { computed, ref, watch, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import EmptyState from '@/components/platform/EmptyState.vue'
import StateBanner from '@/components/platform/StateBanner.vue'
import RequirementReviewOverviewStrip from '@/components/platform/RequirementReviewOverviewStrip.vue'
import RequirementReviewWorkspaceNav from '@/components/platform/RequirementReviewWorkspaceNav.vue'
import { useWorkspaceProjectContext } from '@/composables/useWorkspaceProjectContext'
import BaseChatTemplate from '@/modules/chat/components/BaseChatTemplate.vue'
import { resolveChatTarget } from '@/modules/chat/types'
import { getRequirementReviewOverview } from '@/services/requirement-review/requirement-review.service'
import type { RequirementReviewOverview } from '@/types/management'
import { writeRecentChatTarget } from '@/utils/chatTarget'

const route = useRoute()
const { activeProjectId, activeProject } = useWorkspaceProjectContext()

const overview = ref<RequirementReviewOverview | null>(null)
const loading = ref(false)
const error = ref('')
const compactChrome = ref(false)

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

watch(
  () => activeProjectId.value,
  (projectId) => {
    if (!projectId) {
      overview.value = null
      error.value = ''
      return
    }

    void loadOverview(projectId)
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
