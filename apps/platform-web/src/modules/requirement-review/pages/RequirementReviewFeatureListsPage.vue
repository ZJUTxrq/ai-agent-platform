<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseDialog from '@/components/base/BaseDialog.vue'
import ConfirmDialog from '@/components/base/ConfirmDialog.vue'
import SurfaceCard from '@/components/base/SurfaceCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { usePagination } from '@/composables/usePagination'
import { useWorkspaceProjectContext } from '@/composables/useWorkspaceProjectContext'
import ActionMenu from '@/components/platform/ActionMenu.vue'
import DataTable from '@/components/platform/DataTable.vue'
import EmptyState from '@/components/platform/EmptyState.vue'
import PaginationBar from '@/components/platform/PaginationBar.vue'
import StateBanner from '@/components/platform/StateBanner.vue'
import StatusPill from '@/components/platform/StatusPill.vue'
import type { ActionMenuItem, DataTableColumn } from '@/components/platform/data-table'
import { getOperationFailureMessage } from '@/services/operations/operations.service'
import {
  confirmRequirementFeatureList,
  decomposeRequirementByOperation,
  deleteRequirementFeatureList,
  getRequirementReviewRole,
  listRequirementFeatureLists,
  updateRequirementFeatureList
} from '@/services/requirement-review/requirement-review.service'
import { useUiStore } from '@/stores/ui'
import type {
  RequirementFeatureList,
  RequirementFeatureModule,
  RequirementFeaturePoint,
  RequirementReviewRole
} from '@/types/management'
import {
  CHAT_ATTACHMENT_ACCEPT,
  fileToChatAttachmentBlock,
  type ChatAttachmentBlock
} from '@/utils/chat-content'
import { formatDateTime, shortId } from '@/utils/format'

const MAX_ATTACHMENT_COUNT = 6
const MAX_ATTACHMENT_FILE_BYTES = 10 * 1024 * 1024

function getStatusTone(status: string): 'neutral' | 'success' | 'warning' | 'danger' {
  const normalized = status.trim().toLowerCase()
  if (normalized === 'confirmed') {
    return 'success'
  }
  if (normalized === 'draft') {
    return 'warning'
  }
  return 'neutral'
}

const CHAT_KICKOFF_STORAGE_PREFIX = 'pw:chat:kickoff'
const REVIEW_CHAT_TARGET_ID = 'requirement_review_agent'
const TESTCASE_CHAT_TARGET_ID = 'test_case_agent_v2'

const { activeProjectId, activeProject } = useWorkspaceProjectContext()
const uiStore = useUiStore()
const router = useRouter()

const role = ref<RequirementReviewRole | null>(null)
const items = ref<RequirementFeatureList[]>([])
const loading = ref(false)
const decomposing = ref(false)
const confirming = ref(false)
const deleting = ref(false)
const error = ref('')
const requirementInput = ref('')
const attachmentFiles = ref<File[]>([])
const attachmentInputRef = ref<HTMLInputElement | null>(null)
const detailDialogOpen = ref(false)
const showConfirmDialog = ref(false)
const showDeleteDialog = ref(false)
const currentItem = ref<RequirementFeatureList | null>(null)
const editDialogOpen = ref(false)
const editSaving = ref(false)
const editError = ref('')
const editForm = ref({
  requirement_summary: '',
  requirement_text: '',
  open_questions_text: '',
  assumptions_text: ''
})
const editModules = ref<EditableModule[]>([])

const pagination = usePagination({
  initialPageSize: 20,
  storageKey: 'pw:requirement-feature-lists:page-size'
})

const canWrite = computed(() => role.value?.can_write_requirement_review ?? false)
const rows = computed(() => items.value as unknown as Record<string, unknown>[])

const columns = computed<DataTableColumn[]>(() => [
  {
    key: 'requirement_summary',
    label: '需求摘要',
    sortable: true,
    alwaysVisible: true,
    sortValue: (row) => row.requirement_summary || ''
  },
  {
    key: 'version',
    label: '版本',
    sortable: true,
    sortValue: (row) => row.version || 0
  },
  {
    key: 'status',
    label: '状态',
    sortable: true,
    sortValue: (row) => row.status || ''
  },
  {
    key: 'decomposable',
    label: '可拆解',
    sortable: true,
    sortValue: (row) => (row.decomposable ? 1 : 0)
  },
  {
    key: 'updated_at',
    label: '更新时间',
    sortable: true,
    sortValue: (row) => row.updated_at || ''
  }
])

function itemFromRow(row: Record<string, unknown>) {
  return row as unknown as RequirementFeatureList
}

function pushToast(type: 'success' | 'warning' | 'error', title: string, message: string) {
  uiStore.pushToast({ type, title, message })
}

function featurePointCount(item: RequirementFeatureList) {
  return item.modules.reduce((total, module) => total + (module.feature_points?.length ?? 0), 0)
}

async function loadFeatureLists() {
  const projectId = activeProjectId.value
  if (!projectId) {
    items.value = []
    pagination.setTotal(0)
    return
  }
  loading.value = true
  error.value = ''
  try {
    const [payload, rolePayload] = await Promise.all([
      listRequirementFeatureLists(projectId, {
        limit: pagination.pageSize.value,
        offset: (pagination.page.value - 1) * pagination.pageSize.value
      }),
      getRequirementReviewRole(projectId)
    ])
    items.value = payload.items
    pagination.setTotal(payload.total)
    role.value = rolePayload
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载 featureList 失败'
  } finally {
    loading.value = false
  }
}

function openAttachmentPicker() {
  attachmentInputRef.value?.click()
}

function onAttachmentSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  for (const file of files) {
    if (attachmentFiles.value.length >= MAX_ATTACHMENT_COUNT) {
      pushToast('warning', '附件数量超限', `最多上传 ${MAX_ATTACHMENT_COUNT} 个附件`)
      break
    }
    if (file.size > MAX_ATTACHMENT_FILE_BYTES) {
      pushToast('warning', '附件过大', `${file.name} 超过 10MB，已跳过`)
      continue
    }
    attachmentFiles.value.push(file)
  }
}

function removeAttachment(index: number) {
  attachmentFiles.value.splice(index, 1)
}

async function handleDecompose() {
  const projectId = activeProjectId.value
  const requirementText = requirementInput.value.trim()
  if (!projectId || (!requirementText && attachmentFiles.value.length === 0)) {
    return
  }
  decomposing.value = true
  try {
    let attachments: ChatAttachmentBlock[] | undefined
    if (attachmentFiles.value.length > 0) {
      attachments = await Promise.all(
        attachmentFiles.value.map((file) => fileToChatAttachmentBlock(file))
      )
    }
    const operation = await decomposeRequirementByOperation(projectId, {
      requirement_text: requirementText || undefined,
      attachments
    })
    if (operation.status === 'succeeded') {
      requirementInput.value = ''
      attachmentFiles.value = []
      const nextStep = String(operation.result_payload?.next_step || '')
      pushToast(
        'success',
        '拆解完成',
        nextStep === 'requirement_clarification_required'
          ? '需求信息不足，agent 判定为不可拆解，请查看原因并澄清需求。'
          : '已生成 featureList 草稿，请人工确认后再发起评审。'
      )
      await loadFeatureLists()
    } else {
      pushToast('error', '拆解失败', getOperationFailureMessage(operation))
    }
  } catch (err) {
    pushToast('error', '拆解失败', err instanceof Error ? err.message : '未知错误')
  } finally {
    decomposing.value = false
  }
}

function openDetailDialog(item: RequirementFeatureList) {
  currentItem.value = item
  detailDialogOpen.value = true
}

function openConfirmDialog(item: RequirementFeatureList) {
  currentItem.value = item
  showConfirmDialog.value = true
}

function openDeleteDialog(item: RequirementFeatureList) {
  currentItem.value = item
  showDeleteDialog.value = true
}

type EditableFeaturePoint = {
  feature_id: string
  title: string
  description: string
  source_excerpt: string
  priority: string
  inferred: boolean
  acceptance_criteria_text: string
  constraints_text: string
  open_questions_text: string
  extras: Record<string, unknown>
}

type EditableModule = {
  name: string
  description: string
  feature_points: EditableFeaturePoint[]
  extras: Record<string, unknown>
}

const PRIORITY_OPTIONS = ['P0', 'P1', 'P2', 'P3']

const _POINT_KNOWN_KEYS = new Set([
  'feature_id',
  'title',
  'description',
  'source_excerpt',
  'priority',
  'inferred',
  'acceptance_criteria',
  'constraints',
  'open_questions'
])
const _MODULE_KNOWN_KEYS = new Set(['name', 'description', 'feature_points'])

function _collectExtras(source: Record<string, unknown>, knownKeys: Set<string>) {
  const extras: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(source)) {
    if (!knownKeys.has(key)) {
      extras[key] = value
    }
  }
  return extras
}

function toEditableModules(modules: RequirementFeatureList['modules']): EditableModule[] {
  return modules.map((module) => ({
    name: module.name ?? '',
    description: module.description ?? '',
    feature_points: (module.feature_points ?? []).map((point) => ({
      feature_id: point.feature_id ?? '',
      title: point.title ?? '',
      description: point.description ?? '',
      source_excerpt: point.source_excerpt ?? '',
      priority: point.priority ?? 'P1',
      inferred: point.inferred ?? false,
      acceptance_criteria_text: (point.acceptance_criteria ?? []).join('\n'),
      constraints_text: (point.constraints ?? []).join('\n'),
      open_questions_text: (point.open_questions ?? []).join('\n'),
      extras: _collectExtras(point as Record<string, unknown>, _POINT_KNOWN_KEYS)
    })),
    extras: _collectExtras(module as Record<string, unknown>, _MODULE_KNOWN_KEYS)
  }))
}

function serializeEditableModules(list: EditableModule[]): Record<string, unknown>[] {
  return list.map((module) => ({
    ...module.extras,
    name: module.name.trim(),
    description: module.description.trim(),
    feature_points: module.feature_points.map((point) => ({
      ...point.extras,
      feature_id: point.feature_id,
      title: point.title.trim(),
      description: point.description.trim(),
      source_excerpt: point.source_excerpt,
      priority: point.priority,
      inferred: point.inferred,
      acceptance_criteria: parseLines(point.acceptance_criteria_text),
      constraints: parseLines(point.constraints_text),
      open_questions: parseLines(point.open_questions_text)
    }))
  }))
}

let manualPointCounter = 0

function addModule() {
  editModules.value.push({
    name: '',
    description: '',
    feature_points: [],
    extras: {}
  })
}

function removeModule(index: number) {
  editModules.value.splice(index, 1)
}

function addFeaturePoint(module: EditableModule) {
  manualPointCounter += 1
  module.feature_points.push({
    // 人工新增的点：inferred 固定为 true 且无来源摘录——原文没有的内容不允许伪装成原文提取
    feature_id: `manual-${Date.now().toString(36)}-${manualPointCounter}`,
    title: '',
    description: '',
    source_excerpt: '',
    priority: 'P1',
    inferred: true,
    acceptance_criteria_text: '',
    constraints_text: '',
    open_questions_text: '',
    extras: { source: 'manual' }
  })
}

function removeFeaturePoint(module: EditableModule, index: number) {
  module.feature_points.splice(index, 1)
}

function openEditDialog(item: RequirementFeatureList) {
  currentItem.value = item
  editError.value = ''
  editForm.value = {
    requirement_summary: item.requirement_summary,
    requirement_text: item.requirement_text,
    open_questions_text: item.open_questions.join('\n'),
    assumptions_text: item.assumptions.join('\n')
  }
  editModules.value = toEditableModules(item.modules)
  editDialogOpen.value = true
}

function parseLines(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
}

async function handleSaveEdit() {
  const projectId = activeProjectId.value
  const item = currentItem.value
  if (!projectId || !item) {
    return
  }
  for (const [moduleIndex, module] of editModules.value.entries()) {
    if (!module.name.trim()) {
      editError.value = `第 ${moduleIndex + 1} 个模块缺少名称`
      return
    }
    for (const [pointIndex, point] of module.feature_points.entries()) {
      if (!point.title.trim()) {
        editError.value = `模块「${module.name}」第 ${pointIndex + 1} 个功能点缺少标题`
        return
      }
    }
  }
  const modules = serializeEditableModules(editModules.value)
  editSaving.value = true
  editError.value = ''
  try {
    const updated = await updateRequirementFeatureList(projectId, item.id, {
      requirement_summary: editForm.value.requirement_summary.trim(),
      requirement_text: editForm.value.requirement_text,
      modules,
      open_questions: parseLines(editForm.value.open_questions_text),
      assumptions: parseLines(editForm.value.assumptions_text)
    })
    editDialogOpen.value = false
    if (updated.version !== item.version) {
      pushToast(
        'success',
        '已保存新版本',
        `featureList 升级为 v${updated.version} 并回到 draft 状态，请重新人工确认。`
      )
    } else {
      pushToast('success', '已保存', '内容无变化，版本保持不变。')
    }
    await loadFeatureLists()
  } catch (err) {
    editError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    editSaving.value = false
  }
}

async function handleConfirm() {
  const projectId = activeProjectId.value
  const item = currentItem.value
  showConfirmDialog.value = false
  if (!projectId || !item) {
    return
  }
  confirming.value = true
  try {
    // 携带 expected_version：拆解内容被并发编辑时确认会被 409 拒绝
    await confirmRequirementFeatureList(projectId, item.id, {
      expected_version: item.version
    })
    pushToast('success', '已确认', `featureList v${item.version} 已确认，可发起评审与用例生成。`)
    await loadFeatureLists()
  } catch (err) {
    pushToast('error', '确认失败', err instanceof Error ? err.message : '未知错误')
  } finally {
    confirming.value = false
  }
}

async function handleDelete() {
  const projectId = activeProjectId.value
  const item = currentItem.value
  showDeleteDialog.value = false
  if (!projectId || !item) {
    return
  }
  deleting.value = true
  try {
    await deleteRequirementFeatureList(projectId, item.id)
    pushToast('success', '已删除', shortId(item.id))
    await loadFeatureLists()
  } catch (err) {
    pushToast('error', '删除失败', err instanceof Error ? err.message : '未知错误')
  } finally {
    deleting.value = false
  }
}

function buildReviewKickoffMessage(item: RequirementFeatureList) {
  const sections = [
    '请对以下需求进行完整的需求质量评审，并在完成评审后调用 persist_requirement_review_result 正式保存评审结果。'
  ]
  const requirementText = item.requirement_text.trim()
  if (requirementText) {
    sections.push(`需求内容：\n${requirementText}`)
  }
  sections.push(
    `以下是已人工确认的需求拆解 featureList（id=${item.id}，版本 v${item.version}），仅作为辅助结构：\n` +
      '- 评分与缺失/歧义判断必须锚定需求原文；featureList 中 `inferred: true` 的推断项与 open_questions 不得视为需求原文已覆盖的内容。\n' +
      '```json\n' +
      JSON.stringify(item.modules, null, 2) +
      '\n```'
  )
  if (item.open_questions.length) {
    sections.push(
      '拆解阶段遗留的待澄清项：\n' + item.open_questions.map((q) => `- ${q}`).join('\n')
    )
  }
  if (item.assumptions.length) {
    sections.push(
      '拆解阶段的推断假设：\n' + item.assumptions.map((a) => `- ${a}`).join('\n')
    )
  }
  sections.push(`评审报告中请注明本次评审基于 featureList id=${item.id} v${item.version}。`)
  return sections.join('\n\n')
}

function startReviewConversation(item: RequirementFeatureList) {
  const projectId = activeProjectId.value?.trim()
  if (!projectId) {
    return
  }
  const kickoffKey = `${CHAT_KICKOFF_STORAGE_PREFIX}:${projectId}:${REVIEW_CHAT_TARGET_ID}`
  window.localStorage.setItem(kickoffKey, buildReviewKickoffMessage(item))
  // blank=1：强制落在空白新对话上，避免 kickoff 草稿填进历史线程
  void router.push({
    path: '/workspace/requirement-review',
    query: { ts: String(Date.now()), blank: '1' }
  })
}

function buildPointGenerationKickoffMessage(
  item: RequirementFeatureList,
  module: RequirementFeatureModule,
  point: RequirementFeaturePoint
) {
  const sections = [
    `请只针对以下单个功能点生成正式测试用例，逐条覆盖其验收标准，不要扩展到其它功能点。`,
    `该功能点来自已人工确认的需求拆解 featureList（id=${item.id}，版本 v${item.version}），所属模块：${module.name}。`
  ]
  if (item.requirement_summary.trim()) {
    sections.push(`需求背景摘要：${item.requirement_summary.trim()}`)
  }
  sections.push(
    '功能点定义：\n```json\n' + JSON.stringify(point, null, 2) + '\n```'
  )
  const lines = [
    '生成要求：',
    '- 用例按该功能点组织，每条验收标准至少对应一条用例；',
    '- 约束条件必须体现为用例的前置条件或校验点；',
    '- 功能点的 open_questions 未澄清项不要臆测，作为用例备注标出；'
  ]
  if (point.inferred) {
    lines.push('- 该功能点为推断/人工补充项（非需求原文提取），输出中必须显式注明。')
  }
  lines.push('- 如需补充业务上下文，先查询项目知识库。')
  sections.push(lines.join('\n'))
  return sections.join('\n\n')
}

function startPointGeneration(
  module: RequirementFeatureModule,
  point: RequirementFeaturePoint
) {
  const projectId = activeProjectId.value?.trim()
  const item = currentItem.value
  if (!projectId || !item) {
    return
  }
  const kickoffKey = `${CHAT_KICKOFF_STORAGE_PREFIX}:${projectId}:${TESTCASE_CHAT_TARGET_ID}`
  window.localStorage.setItem(
    kickoffKey,
    buildPointGenerationKickoffMessage(item, module, point)
  )
  detailDialogOpen.value = false
  void router.push({
    path: '/workspace/testcase-v2/generate',
    query: { ts: String(Date.now()), blank: '1' }
  })
}

function rowActions(item: RequirementFeatureList): ActionMenuItem[] {
  const actions: ActionMenuItem[] = [
    {
      key: 'detail',
      label: '查看详情',
      onSelect: () => openDetailDialog(item)
    }
  ]
  if (canWrite.value) {
    actions.push({
      key: 'edit',
      label: '编辑拆解',
      disabled: editSaving.value,
      onSelect: () => openEditDialog(item)
    })
  }
  if (canWrite.value && item.status === 'draft' && item.decomposable) {
    actions.push({
      key: 'confirm',
      label: '确认拆解',
      disabled: confirming.value,
      onSelect: () => openConfirmDialog(item)
    })
  }
  if (canWrite.value && item.status === 'confirmed') {
    actions.push({
      key: 'review-chat',
      label: '发起评审对话',
      onSelect: () => startReviewConversation(item)
    })
  }
  if (canWrite.value) {
    actions.push({
      key: 'delete',
      label: '删除',
      danger: true,
      disabled: deleting.value,
      onSelect: () => openDeleteDialog(item)
    })
  }
  return actions
}

watch(
  [activeProjectId, () => pagination.page.value, () => pagination.pageSize.value],
  () => {
    void loadFeatureLists()
  },
  { immediate: true }
)
</script>

<template>
  <section class="pw-page-shell space-y-4">
    <PageHeader
      eyebrow="Requirement Review"
      title="需求拆解"
      description="把需求拆解为模块 / 功能点 / 验收标准草稿，人工确认后进入需求评审与测试用例生成。内容修改会生成新版本并要求重新确认。"
    >
      <template #actions>
        <BaseButton
          variant="secondary"
          :disabled="loading"
          @click="loadFeatureLists"
        >
          刷新
        </BaseButton>
      </template>
    </PageHeader>

    <StateBanner
      v-if="error"
      title="featureList 加载失败"
      :description="error"
      variant="danger"
    />

    <EmptyState
      v-if="!activeProject"
      icon="project"
      title="请先选择项目"
      description="当前没有项目上下文，无法读取需求拆解数据。"
    />

    <div
      v-else
      class="space-y-4"
    >
      <SurfaceCard v-if="canWrite">
        <div class="space-y-3">
          <div class="text-sm font-medium text-gray-900 dark:text-white">
            发起需求拆解
          </div>
          <textarea
            v-model="requirementInput"
            rows="5"
            class="pw-input w-full resize-y"
            placeholder="粘贴需求原文，或上传 PDF / 图片需求文档（可两者同时提供），agent 将忠实拆解为模块 / 功能点 / 验收标准草稿；无法拆解时会给出原因。"
          />
          <input
            ref="attachmentInputRef"
            type="file"
            class="hidden"
            multiple
            :accept="CHAT_ATTACHMENT_ACCEPT"
            @change="onAttachmentSelected"
          >
          <div
            v-if="attachmentFiles.length"
            class="flex flex-wrap gap-2"
          >
            <span
              v-for="(file, index) in attachmentFiles"
              :key="`${file.name}-${index}`"
              class="inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700 dark:bg-dark-700 dark:text-dark-100"
            >
              {{ file.name }}
              <button
                type="button"
                class="text-gray-400 hover:text-gray-600 dark:hover:text-dark-50"
                aria-label="移除附件"
                @click="removeAttachment(index)"
              >
                ✕
              </button>
            </span>
          </div>
          <div class="flex items-center justify-between gap-3">
            <BaseButton
              variant="secondary"
              :disabled="decomposing || attachmentFiles.length >= MAX_ATTACHMENT_COUNT"
              @click="openAttachmentPicker"
            >
              上传 PDF / 图片
            </BaseButton>
            <BaseButton
              :disabled="decomposing || (!requirementInput.trim() && attachmentFiles.length === 0)"
              @click="handleDecompose"
            >
              {{ decomposing ? '拆解中...' : '提交拆解' }}
            </BaseButton>
          </div>
        </div>
      </SurfaceCard>

      <SurfaceCard>
        <DataTable
          :columns="columns"
          :rows="rows"
          :loading="loading"
          row-key="id"
          sort-storage-key="pw:requirement-feature-lists:sort"
          column-storage-key="pw:requirement-feature-lists:columns"
          empty-title="当前没有需求拆解记录"
          empty-description="提交一段需求原文即可生成待确认的 featureList 草稿。"
          empty-icon="testcase"
        >
          <template #cell-requirement_summary="{ row }">
            <button
              type="button"
              class="text-left"
              @click="openDetailDialog(itemFromRow(row))"
            >
              <div class="font-medium text-gray-900 dark:text-white">
                {{ itemFromRow(row).requirement_summary || '--' }}
              </div>
              <div class="mt-1 text-xs text-gray-400 dark:text-dark-400">
                {{ shortId(itemFromRow(row).id) }} · {{ featurePointCount(itemFromRow(row)) }} 个功能点
              </div>
            </button>
          </template>

          <template #cell-version="{ row }">
            <span class="font-medium text-gray-900 dark:text-white">
              v{{ itemFromRow(row).version }}
            </span>
          </template>

          <template #cell-status="{ row }">
            <StatusPill :tone="getStatusTone(itemFromRow(row).status)">
              {{ itemFromRow(row).status }}
            </StatusPill>
          </template>

          <template #cell-decomposable="{ row }">
            <StatusPill :tone="itemFromRow(row).decomposable ? 'success' : 'danger'">
              {{ itemFromRow(row).decomposable ? '可拆解' : '不可拆解' }}
            </StatusPill>
          </template>

          <template #cell-updated_at="{ row }">
            <span class="text-gray-500 dark:text-dark-300">
              {{ formatDateTime(itemFromRow(row).updated_at) }}
            </span>
          </template>

          <template #cell-actions="{ row }">
            <ActionMenu :items="rowActions(itemFromRow(row))" />
          </template>
        </DataTable>

        <PaginationBar
          v-if="pagination.total.value > 0"
          :total="pagination.total.value"
          :page="pagination.page.value"
          :page-size="pagination.pageSize.value"
          :disabled="loading || confirming || deleting"
          @update:page="pagination.setPage"
          @update:page-size="pagination.setPageSize"
        />
      </SurfaceCard>
    </div>

    <BaseDialog
      :show="detailDialogOpen"
      :title="`拆解详情 · v${currentItem?.version ?? ''} · ${currentItem?.status ?? ''}`"
      width="full"
      @close="detailDialogOpen = false"
    >
      <div
        v-if="currentItem"
        class="space-y-4 text-sm"
      >
        <StateBanner
          v-if="!currentItem.decomposable"
          title="agent 判定该需求不可拆解"
          :description="currentItem.undecomposable_reason || '未提供原因'"
          variant="danger"
        />

        <div>
          <div class="font-medium text-gray-900 dark:text-white">
            需求摘要
          </div>
          <p class="mt-1 text-gray-600 dark:text-dark-200">
            {{ currentItem.requirement_summary }}
          </p>
        </div>

        <div v-if="currentItem.requirement_text">
          <div class="font-medium text-gray-900 dark:text-white">
            需求原文
          </div>
          <pre class="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-xs text-gray-600 dark:bg-dark-800 dark:text-dark-200">{{ currentItem.requirement_text }}</pre>
        </div>

        <div
          v-for="module in currentItem.modules"
          :key="module.name"
          class="rounded-lg border border-gray-200 p-3 dark:border-dark-600"
        >
          <div class="font-medium text-gray-900 dark:text-white">
            模块：{{ module.name }}
          </div>
          <p
            v-if="module.description"
            class="mt-1 text-xs text-gray-500 dark:text-dark-300"
          >
            {{ module.description }}
          </p>
          <div
            v-for="point in module.feature_points ?? []"
            :key="point.feature_id"
            class="mt-3 rounded-md bg-gray-50 p-3 dark:bg-dark-800"
          >
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-medium text-gray-900 dark:text-white">{{ point.title }}</span>
              <StatusPill tone="neutral">
                {{ point.priority || 'P1' }}
              </StatusPill>
              <StatusPill
                v-if="point.inferred"
                tone="warning"
              >
                推断项
              </StatusPill>
              <button
                v-if="canWrite && currentItem.status === 'confirmed'"
                type="button"
                class="pw-table-tool-button ml-auto h-7 px-2.5 text-xs"
                @click="startPointGeneration(module, point)"
              >
                生成用例 →
              </button>
            </div>
            <p
              v-if="point.description"
              class="mt-1 text-xs text-gray-600 dark:text-dark-200"
            >
              {{ point.description }}
            </p>
            <p
              v-if="point.source_excerpt"
              class="mt-1 text-xs text-gray-400 dark:text-dark-400"
            >
              来源：「{{ point.source_excerpt }}」
            </p>
            <ul
              v-if="point.acceptance_criteria?.length"
              class="mt-2 list-disc pl-5 text-xs text-gray-600 dark:text-dark-200"
            >
              <li
                v-for="criteria in point.acceptance_criteria"
                :key="criteria"
              >
                {{ criteria }}
              </li>
            </ul>
            <p
              v-if="point.constraints?.length"
              class="mt-1 text-xs text-gray-500 dark:text-dark-300"
            >
              约束：{{ point.constraints.join('；') }}
            </p>
            <p
              v-if="point.open_questions?.length"
              class="mt-1 text-xs text-amber-600 dark:text-amber-400"
            >
              待澄清：{{ point.open_questions.join('；') }}
            </p>
          </div>
        </div>

        <div v-if="currentItem.open_questions.length">
          <div class="font-medium text-gray-900 dark:text-white">
            全局待澄清项
          </div>
          <ul class="mt-1 list-disc pl-5 text-xs text-amber-600 dark:text-amber-400">
            <li
              v-for="question in currentItem.open_questions"
              :key="question"
            >
              {{ question }}
            </li>
          </ul>
        </div>

        <div v-if="currentItem.assumptions.length">
          <div class="font-medium text-gray-900 dark:text-white">
            推断假设
          </div>
          <ul class="mt-1 list-disc pl-5 text-xs text-gray-600 dark:text-dark-200">
            <li
              v-for="assumption in currentItem.assumptions"
              :key="assumption"
            >
              {{ assumption }}
            </li>
          </ul>
        </div>

        <div
          v-if="currentItem.confirmed_at"
          class="text-xs text-gray-400 dark:text-dark-400"
        >
          由 {{ currentItem.confirmed_by || '未知用户' }} 于
          {{ formatDateTime(currentItem.confirmed_at) }} 确认
        </div>
      </div>
    </BaseDialog>

    <BaseDialog
      :show="editDialogOpen"
      :title="`编辑拆解 · v${currentItem?.version ?? ''}${currentItem?.status === 'confirmed' ? '（已确认，保存修改后将生成新版本并需重新确认）' : ''}`"
      width="full"
      @close="editDialogOpen = false"
    >
      <div class="space-y-4 text-sm">
        <StateBanner
          v-if="editError"
          title="保存失败"
          :description="editError"
          variant="danger"
        />

        <label class="block">
          <span class="pw-input-label">需求摘要</span>
          <input
            v-model="editForm.requirement_summary"
            type="text"
            class="pw-input mt-1 w-full"
          >
        </label>

        <label class="block">
          <span class="pw-input-label">需求原文</span>
          <textarea
            v-model="editForm.requirement_text"
            rows="6"
            class="pw-input mt-1 w-full resize-y"
          />
        </label>

        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span class="pw-input-label">模块与功能点</span>
            <BaseButton
              variant="secondary"
              @click="addModule"
            >
              + 新增模块
            </BaseButton>
          </div>

          <div
            v-for="(module, moduleIndex) in editModules"
            :key="moduleIndex"
            class="space-y-3 rounded-lg border border-gray-200 p-3 dark:border-dark-600"
          >
            <div class="flex flex-wrap items-end gap-3">
              <label class="min-w-[200px] flex-1">
                <span class="pw-input-label">模块名称</span>
                <input
                  v-model="module.name"
                  type="text"
                  class="pw-input mt-1 w-full"
                >
              </label>
              <label class="min-w-[200px] flex-[2]">
                <span class="pw-input-label">模块描述</span>
                <input
                  v-model="module.description"
                  type="text"
                  class="pw-input mt-1 w-full"
                >
              </label>
              <BaseButton
                variant="secondary"
                @click="removeModule(moduleIndex)"
              >
                删除模块
              </BaseButton>
            </div>

            <div
              v-for="(point, pointIndex) in module.feature_points"
              :key="`${moduleIndex}-${pointIndex}`"
              class="space-y-2 rounded-md bg-gray-50 p-3 dark:bg-dark-800"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-xs text-gray-400 dark:text-dark-400">
                  {{ point.feature_id }}
                </span>
                <StatusPill :tone="point.inferred ? 'warning' : 'success'">
                  {{ point.inferred ? '推断/人工补充' : '原文提取' }}
                </StatusPill>
                <button
                  type="button"
                  class="ml-auto text-xs text-red-500 hover:text-red-600"
                  @click="removeFeaturePoint(module, pointIndex)"
                >
                  删除功能点
                </button>
              </div>

              <div class="flex flex-wrap gap-3">
                <label class="min-w-[240px] flex-[3]">
                  <span class="pw-input-label">标题</span>
                  <input
                    v-model="point.title"
                    type="text"
                    class="pw-input mt-1 w-full"
                  >
                </label>
                <label class="min-w-[100px] flex-1">
                  <span class="pw-input-label">优先级</span>
                  <select
                    v-model="point.priority"
                    class="pw-input mt-1 w-full"
                  >
                    <option
                      v-for="option in PRIORITY_OPTIONS"
                      :key="option"
                      :value="option"
                    >
                      {{ option }}
                    </option>
                  </select>
                </label>
              </div>

              <label class="block">
                <span class="pw-input-label">描述</span>
                <textarea
                  v-model="point.description"
                  rows="2"
                  class="pw-input mt-1 w-full resize-y"
                />
              </label>

              <p
                v-if="point.source_excerpt"
                class="text-xs text-gray-400 dark:text-dark-400"
              >
                来源摘录（只读）：「{{ point.source_excerpt }}」
              </p>

              <div class="grid gap-3 sm:grid-cols-3">
                <label class="block">
                  <span class="pw-input-label">验收标准（每行一条）</span>
                  <textarea
                    v-model="point.acceptance_criteria_text"
                    rows="3"
                    class="pw-input mt-1 w-full resize-y"
                  />
                </label>
                <label class="block">
                  <span class="pw-input-label">约束（每行一条）</span>
                  <textarea
                    v-model="point.constraints_text"
                    rows="3"
                    class="pw-input mt-1 w-full resize-y"
                  />
                </label>
                <label class="block">
                  <span class="pw-input-label">待澄清项（每行一条）</span>
                  <textarea
                    v-model="point.open_questions_text"
                    rows="3"
                    class="pw-input mt-1 w-full resize-y"
                  />
                </label>
              </div>
            </div>

            <BaseButton
              variant="secondary"
              @click="addFeaturePoint(module)"
            >
              + 新增功能点
            </BaseButton>
          </div>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block">
            <span class="pw-input-label">全局待澄清项（每行一条）</span>
            <textarea
              v-model="editForm.open_questions_text"
              rows="4"
              class="pw-input mt-1 w-full resize-y"
            />
          </label>
          <label class="block">
            <span class="pw-input-label">推断假设（每行一条）</span>
            <textarea
              v-model="editForm.assumptions_text"
              rows="4"
              class="pw-input mt-1 w-full resize-y"
            />
          </label>
        </div>

        <div class="flex justify-end gap-2">
          <BaseButton
            variant="secondary"
            :disabled="editSaving"
            @click="editDialogOpen = false"
          >
            取消
          </BaseButton>
          <BaseButton
            :disabled="editSaving || !editForm.requirement_summary.trim()"
            @click="handleSaveEdit"
          >
            {{ editSaving ? '保存中...' : '保存' }}
          </BaseButton>
        </div>
      </div>
    </BaseDialog>

    <ConfirmDialog
      :show="showConfirmDialog"
      title="确认需求拆解"
      :message="`确认 featureList v${currentItem?.version ?? ''}（${currentItem?.requirement_summary || ''}）后，即可基于该拆解发起需求评审与用例生成。确认继续吗？`"
      confirm-text="确认"
      @cancel="showConfirmDialog = false"
      @confirm="handleConfirm"
    />

    <ConfirmDialog
      :show="showDeleteDialog"
      title="删除需求拆解"
      :message="`删除 ${currentItem?.requirement_summary || shortId(currentItem?.id || '')} 后将无法恢复，确认继续吗？`"
      confirm-text="删除"
      danger
      @cancel="showDeleteDialog = false"
      @confirm="handleDelete"
    />
  </section>
</template>
