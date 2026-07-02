<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseDialog from '@/components/base/BaseDialog.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import ConfirmDialog from '@/components/base/ConfirmDialog.vue'
import SurfaceCard from '@/components/base/SurfaceCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { usePagination } from '@/composables/usePagination'
import { useVisibleFilterSettings } from '@/composables/useVisibleFilterSettings'
import { useWorkspaceProjectContext } from '@/composables/useWorkspaceProjectContext'
import ActionMenu from '@/components/platform/ActionMenu.vue'
import DataTable from '@/components/platform/DataTable.vue'
import EmptyState from '@/components/platform/EmptyState.vue'
import FilterSettingsMenu from '@/components/platform/FilterSettingsMenu.vue'
import FilterToolbar from '@/components/platform/FilterToolbar.vue'
import PaginationBar from '@/components/platform/PaginationBar.vue'
import RequirementReviewOverviewStrip from '@/components/platform/RequirementReviewOverviewStrip.vue'
import RequirementReviewWorkspaceNav from '@/components/platform/RequirementReviewWorkspaceNav.vue'
import SearchInput from '@/components/platform/SearchInput.vue'
import StateBanner from '@/components/platform/StateBanner.vue'
import StatusPill from '@/components/platform/StatusPill.vue'
import type { ActionMenuItem, DataTableColumn } from '@/components/platform/data-table'
import type { FilterSettingItem } from '@/components/platform/filter-settings'
import { getOperationFailureMessage } from '@/services/operations/operations.service'
import {
  createRequirementReviewResult,
  deleteRequirementReviewResult,
  exportRequirementReviewResultsByOperation,
  getRequirementReviewBatchDetail,
  getRequirementReviewOverview,
  getRequirementReviewResult,
  getRequirementReviewRole,
  listRequirementReviewBatches,
  listRequirementReviewResults,
  updateRequirementReviewResult,
  type UpsertRequirementReviewResultPayload
} from '@/services/requirement-review/requirement-review.service'
import { useUiStore } from '@/stores/ui'
import type {
  RequirementReviewBatchDetail,
  RequirementReviewBatchSummary,
  RequirementReviewOverview,
  RequirementReviewResult,
  RequirementReviewRole
} from '@/types/management'
import { copyText } from '@/utils/clipboard'
import { downloadBlob } from '@/utils/browser-download'
import { formatDateTime, shortId } from '@/utils/format'

type ResultDialogMode = 'detail' | 'create' | 'edit'

type JsonParseResult = {
  value: Record<string, unknown>
  error: string | null
}

type ResultFormState = {
  batch_id: string
  thread_id: string
  requirement_summary: string
  review_score: string
  quality_gate: string
  generation_policy: string
  generation_policy_reason: string
  document_ids_text: string
  key_findings_text: string
  major_risks_text: string
  missing_or_ambiguous_items_text: string
  suggestions_to_improve_text: string
  assumptions_text: string
  dimension_scores_text: string
  raw_result_text: string
}

const QUALITY_GATE_OPTIONS = ['pass', 'conditional', 'fail']
const GENERATION_POLICY_OPTIONS = [
  'allow_generation',
  'allow_generation_with_assumptions',
  'block_generation'
]

function getQualityGateTone(value: string): 'neutral' | 'success' | 'warning' | 'danger' {
  const normalized = value.trim().toLowerCase()
  if (normalized === 'pass') {
    return 'success'
  }
  if (normalized === 'conditional') {
    return 'warning'
  }
  if (normalized === 'fail') {
    return 'danger'
  }
  return 'neutral'
}

function stringifyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function joinLines(value: string[] | undefined) {
  return Array.isArray(value) ? value.join('\n') : ''
}

function formatDimensionLabel(value: string) {
  return value.replace(/_/g, ' ')
}

function parseJsonObjectText(value: string, label: string): JsonParseResult {
  const normalized = value.trim()
  if (!normalized) {
    return { value: {}, error: null }
  }
  try {
    const parsed = JSON.parse(normalized) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { value: {}, error: `${label} 必须是 JSON 对象` }
    }
    return { value: parsed as Record<string, unknown>, error: null }
  } catch (error) {
    return {
      value: {},
      error: error instanceof Error ? `${label} JSON 非法: ${error.message}` : `${label} JSON 非法`
    }
  }
}

function buildFormFromResult(item: RequirementReviewResult): ResultFormState {
  return {
    batch_id: item.batch_id ?? '',
    thread_id: item.thread_id ?? '',
    requirement_summary: item.requirement_summary ?? '',
    review_score: item.review_score == null ? '' : String(item.review_score),
    quality_gate: item.quality_gate ?? 'conditional',
    generation_policy: item.generation_policy ?? 'allow_generation_with_assumptions',
    generation_policy_reason: item.generation_policy_reason ?? '',
    document_ids_text: item.document_ids.join('\n'),
    key_findings_text: joinLines(item.key_findings),
    major_risks_text: joinLines(item.major_risks),
    missing_or_ambiguous_items_text: joinLines(item.missing_or_ambiguous_items),
    suggestions_to_improve_text: joinLines(item.suggestions_to_improve),
    assumptions_text: joinLines(item.assumptions),
    dimension_scores_text: stringifyJson(item.dimension_scores),
    raw_result_text: stringifyJson(item.raw_result)
  }
}

function createEmptyForm(): ResultFormState {
  return {
    batch_id: '',
    thread_id: '',
    requirement_summary: '',
    review_score: '',
    quality_gate: 'conditional',
    generation_policy: 'allow_generation_with_assumptions',
    generation_policy_reason: '',
    document_ids_text: '',
    key_findings_text: '',
    major_risks_text: '',
    missing_or_ambiguous_items_text: '',
    suggestions_to_improve_text: '',
    assumptions_text: '',
    dimension_scores_text: '{}',
    raw_result_text: '{}'
  }
}

const { activeProjectId, activeProject } = useWorkspaceProjectContext()
const uiStore = useUiStore()

const overview = ref<RequirementReviewOverview | null>(null)
const batches = ref<RequirementReviewBatchSummary[]>([])
const role = ref<RequirementReviewRole | null>(null)
const items = ref<RequirementReviewResult[]>([])
const selectedId = ref('')
const selectedResult = ref<RequirementReviewResult | null>(null)
const batchDetail = ref<RequirementReviewBatchDetail | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const batchDetailLoading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const exporting = ref(false)
const detailDialogOpen = ref(false)
const dialogMode = ref<ResultDialogMode>('detail')
const showDeleteDialog = ref(false)
const error = ref('')
const detailError = ref('')
const batchDetailError = ref('')
const formError = ref('')
const searchInput = ref('')
const batchInput = ref('')
const qualityGateInput = ref('')
const query = ref('')
const batchFilter = ref('')
const qualityGateFilter = ref('')
const form = ref<ResultFormState>(createEmptyForm())

const pagination = usePagination({
  initialPageSize: 20,
  storageKey: 'pw:requirement-review-results:page-size'
})
const filterItems: FilterSettingItem[] = [
  { key: 'batch', label: '批次' },
  { key: 'quality_gate', label: '门禁' }
]
const { visibleFilterKeys, visibleFilterSet, setVisibleFilterKeys } = useVisibleFilterSettings(
  filterItems,
  'pw:requirement-review-results:filters'
)

const resultRows = computed(() => items.value as unknown as Record<string, unknown>[])
const currentResult = computed(
  () => selectedResult.value ?? items.value.find((item) => item.id === selectedId.value) ?? null
)
const canWrite = computed(() => Boolean(role.value?.can_write_requirement_review))
const sameBatchDocuments = computed(() => batchDetail.value?.documents.items ?? [])
const sameBatchResults = computed(() =>
  (batchDetail.value?.results.items ?? []).filter((item) => item.id !== currentResult.value?.id)
)
const gateSummaryEntries = computed(() =>
  Object.entries(batchDetail.value?.batch.quality_gate_summary ?? {}).sort(([left], [right]) =>
    left.localeCompare(right)
  )
)
const dimensionScoresState = computed(() =>
  parseJsonObjectText(form.value.dimension_scores_text, 'dimension_scores')
)
const rawResultState = computed(() => parseJsonObjectText(form.value.raw_result_text, 'raw_result'))
const dialogTitle = computed(() => {
  if (dialogMode.value === 'create') {
    return '新增评审结果'
  }
  if (dialogMode.value === 'edit') {
    return '编辑评审结果'
  }
  return '评审详情'
})

const columns = computed<DataTableColumn[]>(() => [
  {
    key: 'requirement_summary',
    label: '评审摘要',
    sortable: true,
    alwaysVisible: true,
    sortValue: (row) => row.requirement_summary || ''
  },
  {
    key: 'review_score',
    label: '评分',
    sortable: true,
    sortValue: (row) => row.review_score || 0
  },
  {
    key: 'quality_gate',
    label: '门禁',
    sortable: true,
    sortValue: (row) => row.quality_gate || ''
  },
  {
    key: 'generation_policy',
    label: '生成策略',
    sortable: true,
    sortValue: (row) => row.generation_policy || ''
  },
  {
    key: 'batch_id',
    label: '批次',
    sortable: true,
    defaultHidden: true,
    sortValue: (row) => row.batch_id || ''
  },
  {
    key: 'created_at',
    label: '创建时间',
    sortable: true,
    sortValue: (row) => row.created_at || ''
  }
])

function resultFromRow(row: Record<string, unknown>) {
  return row as RequirementReviewResult
}

function pushToast(type: 'success' | 'warning' | 'error', title: string, message: string) {
  uiStore.pushToast({ type, title, message })
}

async function handleCopyResultId(result: RequirementReviewResult) {
  const copied = await copyText(result.id)
  pushToast(
    copied ? 'success' : 'warning',
    copied ? '已复制结果 ID' : '复制失败',
    copied ? result.id : '当前环境不支持自动复制，请手动复制。'
  )
}

async function handleCopyBatchId(batchId: string) {
  const copied = await copyText(batchId)
  pushToast(
    copied ? 'success' : 'warning',
    copied ? '已复制批次 ID' : '复制失败',
    copied ? batchId : '当前环境不支持自动复制，请手动复制。'
  )
}

async function loadMeta(projectId: string) {
  const [overviewPayload, batchPayload, rolePayload] = await Promise.all([
    getRequirementReviewOverview(projectId),
    listRequirementReviewBatches(projectId, { limit: 100, offset: 0 }),
    getRequirementReviewRole(projectId)
  ])
  overview.value = overviewPayload
  batches.value = batchPayload.items
  role.value = rolePayload
}

async function loadResults() {
  const projectId = activeProjectId.value
  if (!projectId) {
    overview.value = null
    batches.value = []
    role.value = null
    items.value = []
    selectedId.value = ''
    selectedResult.value = null
    batchDetail.value = null
    pagination.setTotal(0)
    error.value = ''
    return
  }

  loading.value = true
  error.value = ''

  try {
    await loadMeta(projectId)
    const payload = await listRequirementReviewResults(projectId, {
      batch_id: batchFilter.value || undefined,
      quality_gate: qualityGateFilter.value || undefined,
      query: query.value || undefined,
      limit: pagination.pageSize.value,
      offset: pagination.offset.value
    })
    items.value = payload.items
    pagination.setTotal(payload.total)
    if (!selectedId.value || !payload.items.some((item) => item.id === selectedId.value)) {
      selectedId.value = payload.items[0]?.id || ''
    }
  } catch (loadError) {
    items.value = []
    pagination.setTotal(0)
    error.value = loadError instanceof Error ? loadError.message : '评审结果列表加载失败'
  } finally {
    loading.value = false
  }
}

async function loadBatchDetail(batchId: string | null | undefined) {
  const projectId = activeProjectId.value
  if (!projectId || !batchId) {
    batchDetail.value = null
    batchDetailError.value = ''
    return
  }

  batchDetailLoading.value = true
  batchDetailError.value = ''
  try {
    batchDetail.value = await getRequirementReviewBatchDetail(projectId, batchId, {
      document_limit: 100,
      document_offset: 0,
      result_limit: 50,
      result_offset: 0
    })
  } catch (loadError) {
    batchDetail.value = null
    batchDetailError.value = loadError instanceof Error ? loadError.message : '批次上下文加载失败'
  } finally {
    batchDetailLoading.value = false
  }
}

async function loadDetail() {
  const projectId = activeProjectId.value
  if (!projectId || !selectedId.value) {
    selectedResult.value = null
    batchDetail.value = null
    detailError.value = ''
    batchDetailError.value = ''
    return
  }

  detailLoading.value = true
  detailError.value = ''
  try {
    const result = await getRequirementReviewResult(projectId, selectedId.value)
    selectedResult.value = result
    if (dialogMode.value === 'edit') {
      form.value = buildFormFromResult(result)
    }
    await loadBatchDetail(result.batch_id)
  } catch (loadError) {
    selectedResult.value = null
    batchDetail.value = null
    detailError.value = loadError instanceof Error ? loadError.message : '评审详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function selectResult(resultId: string) {
  selectedId.value = resultId
}

function openDetailDialog(result: RequirementReviewResult) {
  dialogMode.value = 'detail'
  formError.value = ''
  detailDialogOpen.value = true
  if (selectedId.value !== result.id) {
    selectedId.value = result.id
    return
  }
  if (!selectedResult.value && !detailLoading.value) {
    void loadDetail()
  }
}

async function openEditDialog(result: RequirementReviewResult) {
  dialogMode.value = 'edit'
  formError.value = ''
  detailDialogOpen.value = true
  if (selectedId.value !== result.id) {
    selectedId.value = result.id
    return
  }
  if (!selectedResult.value || selectedResult.value.id !== result.id) {
    await loadDetail()
  }
  if (selectedResult.value) {
    form.value = buildFormFromResult(selectedResult.value)
  }
}

function closeDetailDialog() {
  if (saving.value || deleting.value) {
    return
  }
  detailDialogOpen.value = false
  dialogMode.value = 'detail'
  formError.value = ''
}

function openCreateDialog() {
  dialogMode.value = 'create'
  selectedId.value = ''
  selectedResult.value = null
  batchDetail.value = null
  detailError.value = ''
  batchDetailError.value = ''
  formError.value = ''
  form.value = createEmptyForm()
  detailDialogOpen.value = true
}

function buildMutationPayload(): UpsertRequirementReviewResultPayload {
  const parsedDimensionScores = parseJsonObjectText(form.value.dimension_scores_text, 'dimension_scores')
  if (parsedDimensionScores.error) {
    throw new Error(parsedDimensionScores.error)
  }
  const parsedRawResult = parseJsonObjectText(form.value.raw_result_text, 'raw_result')
  if (parsedRawResult.error) {
    throw new Error(parsedRawResult.error)
  }
  const normalizedReviewScore = form.value.review_score.trim()
  if (!normalizedReviewScore) {
    throw new Error('review_score 不能为空')
  }
  const reviewScore = Number(normalizedReviewScore)
  if (!Number.isFinite(reviewScore)) {
    throw new Error('review_score 必须是数字')
  }
  return {
    batch_id: form.value.batch_id.trim() || null,
    thread_id: form.value.thread_id.trim() || null,
    requirement_summary: form.value.requirement_summary.trim(),
    review_score: reviewScore,
    quality_gate: form.value.quality_gate,
    generation_policy: form.value.generation_policy,
    generation_policy_reason: form.value.generation_policy_reason.trim(),
    document_ids: splitLines(form.value.document_ids_text),
    key_findings: splitLines(form.value.key_findings_text),
    major_risks: splitLines(form.value.major_risks_text),
    missing_or_ambiguous_items: splitLines(form.value.missing_or_ambiguous_items_text),
    suggestions_to_improve: splitLines(form.value.suggestions_to_improve_text),
    assumptions: splitLines(form.value.assumptions_text),
    dimension_scores: parsedDimensionScores.value,
    raw_result: parsedRawResult.value
  }
}

async function handleSave() {
  const projectId = activeProjectId.value
  const resultId = currentResult.value?.id
  if (!projectId) {
    return
  }

  if (!form.value.requirement_summary.trim()) {
    formError.value = '评审摘要不能为空'
    return
  }

  saving.value = true
  formError.value = ''

  try {
    const nextMode = dialogMode.value
    const payload = buildMutationPayload()
    const saved =
      nextMode === 'create'
        ? await createRequirementReviewResult(projectId, {
            ...payload,
            generation_policy: payload.generation_policy || 'allow_generation_with_assumptions'
          })
        : await updateRequirementReviewResult(projectId, resultId || '', payload)
    selectedResult.value = saved
    selectedId.value = saved.id
    form.value = buildFormFromResult(saved)
    dialogMode.value = 'detail'
    pushToast(
      'success',
      nextMode === 'create' ? '创建成功' : '保存成功',
      `评审结果 ${shortId(saved.id)} 已同步`
    )
    await loadResults()
    await loadBatchDetail(saved.batch_id)
  } catch (saveError) {
    formError.value = saveError instanceof Error ? saveError.message : '评审结果保存失败'
  } finally {
    saving.value = false
  }
}

async function handleExport() {
  const projectId = activeProjectId.value
  if (!projectId || exporting.value) {
    return
  }
  exporting.value = true
  try {
    const exportOptions = {
      batch_id: batchFilter.value || undefined,
      quality_gate: qualityGateFilter.value || undefined,
      query: query.value || undefined
    }
    const download = await (async () => {
      const result = await exportRequirementReviewResultsByOperation(projectId, exportOptions)
      if (result.operation.status !== 'succeeded') {
        throw new Error(getOperationFailureMessage(result.operation))
      }
      return result.download
    })()
    downloadBlob(download.blob, download.filename || 'requirement-review-results.xlsx')
    pushToast('success', '导出成功', '评审结果 Excel 已开始下载')
  } catch (exportError) {
    pushToast(
      'error',
      '导出失败',
      exportError instanceof Error ? exportError.message : '评审结果导出失败'
    )
  } finally {
    exporting.value = false
  }
}

async function handleDelete() {
  const projectId = activeProjectId.value
  const resultId = currentResult.value?.id
  if (!projectId || !resultId) {
    return
  }

  deleting.value = true
  try {
    await deleteRequirementReviewResult(projectId, resultId)
    pushToast('success', '删除成功', `评审结果 ${shortId(resultId)} 已删除`)
    showDeleteDialog.value = false
    closeDetailDialog()
    selectedResult.value = null
    batchDetail.value = null
    await loadResults()
  } catch (deleteError) {
    pushToast(
      'error',
      '删除失败',
      deleteError instanceof Error ? deleteError.message : '评审结果删除失败'
    )
  } finally {
    deleting.value = false
  }
}

function resultActions(result: RequirementReviewResult): ActionMenuItem[] {
  const actions: ActionMenuItem[] = [
    {
      key: 'detail',
      label: detailDialogOpen.value && result.id === selectedId.value ? '当前详情' : '查看详情',
      icon: 'eye',
      disabled: detailDialogOpen.value && result.id === selectedId.value && dialogMode.value === 'detail',
      onSelect: () => openDetailDialog(result)
    },
    {
      key: 'copy-result-id',
      label: '复制结果 ID',
      icon: 'copy',
      onSelect: () => void handleCopyResultId(result)
    },
    {
      key: 'copy-batch-id',
      label: result.batch_id ? '复制批次 ID' : '缺少批次 ID',
      icon: 'copy',
      disabled: !result.batch_id,
      onSelect: () => void handleCopyBatchId(result.batch_id || '')
    }
  ]

  if (canWrite.value) {
    actions.push(
      {
        key: 'edit',
        label: '编辑',
        icon: 'edit',
        onSelect: () => void openEditDialog(result)
      },
      {
        key: 'delete',
        label: '删除',
        icon: 'trash',
        danger: true,
        onSelect: () => {
          selectedId.value = result.id
          selectedResult.value = result
          detailDialogOpen.value = true
          dialogMode.value = 'detail'
          showDeleteDialog.value = true
        }
      }
    )
  }

  return actions
}

function applyFilters() {
  query.value = searchInput.value.trim()
  batchFilter.value = batchInput.value
  qualityGateFilter.value = qualityGateInput.value
  if (pagination.page.value === 1) {
    void loadResults()
    return
  }
  pagination.resetPage()
}

function resetFilters() {
  searchInput.value = ''
  batchInput.value = ''
  qualityGateInput.value = ''
  query.value = ''
  batchFilter.value = ''
  qualityGateFilter.value = ''
  if (pagination.page.value === 1) {
    void loadResults()
    return
  }
  pagination.resetPage()
}

function updateVisibleFilters(nextKeys: string[]) {
  const previous = new Set(visibleFilterKeys.value)
  setVisibleFilterKeys(nextKeys)

  let shouldReload = false
  if (previous.has('batch') && !visibleFilterSet.value.has('batch')) {
    batchInput.value = ''
    batchFilter.value = ''
    shouldReload = true
  }
  if (previous.has('quality_gate') && !visibleFilterSet.value.has('quality_gate')) {
    qualityGateInput.value = ''
    qualityGateFilter.value = ''
    shouldReload = true
  }

  if (shouldReload) {
    if (pagination.page.value === 1) {
      void loadResults()
    } else {
      pagination.resetPage()
    }
  }
}

watch(
  [() => activeProjectId.value, () => pagination.page.value, () => pagination.pageSize.value],
  () => {
    void loadResults()
  },
  { immediate: true }
)

watch(
  () => selectedId.value,
  () => {
    if (detailDialogOpen.value) {
      void loadDetail()
    }
  }
)
</script>

<template>
  <section class="pw-page-shell space-y-4">
    <RequirementReviewWorkspaceNav />

    <PageHeader
      eyebrow="Requirement Review"
      title="评审结果列表"
      description="查看当前项目下已持久化的需求评审结果，并支持导出、查看详情、新增、编辑和删除。"
    >
      <template #actions>
        <BaseButton
          variant="secondary"
          :disabled="exporting"
          @click="handleExport"
        >
          {{ exporting ? '导出中...' : '导出 Excel' }}
        </BaseButton>
        <BaseButton
          variant="secondary"
          @click="loadResults"
        >
          刷新
        </BaseButton>
        <BaseButton
          v-if="canWrite"
          :disabled="saving || deleting"
          @click="openCreateDialog"
        >
          新增结果
        </BaseButton>
      </template>
    </PageHeader>

    <RequirementReviewOverviewStrip :overview="overview" />

    <StateBanner
      v-if="error"
      title="评审结果列表加载失败"
      :description="error"
      variant="danger"
    />

    <EmptyState
      v-if="!activeProject"
      icon="project"
      title="请先选择项目"
      description="当前没有项目上下文，无法读取需求评审结果。"
    />

    <div
      v-else
      class="space-y-4"
    >
      <FilterToolbar>
        <div class="flex flex-wrap items-center gap-3">
          <div class="min-w-0 flex-1 basis-full sm:min-w-[260px]">
            <SearchInput
              v-model="searchInput"
              placeholder="按摘要、策略或结果 ID 搜索"
            />
          </div>

          <div
            v-if="visibleFilterSet.has('batch')"
            class="w-full sm:w-[240px]"
          >
            <BaseSelect v-model="batchInput">
              <option value="">
                全部批次
              </option>
              <option
                v-for="item in batches"
                :key="item.batch_id"
                :value="item.batch_id"
              >
                {{ item.batch_id }}
              </option>
            </BaseSelect>
          </div>

          <div
            v-if="visibleFilterSet.has('quality_gate')"
            class="w-full sm:w-[200px]"
          >
            <BaseSelect v-model="qualityGateInput">
              <option value="">
                全部门禁
              </option>
              <option
                v-for="option in QUALITY_GATE_OPTIONS"
                :key="option"
                :value="option"
              >
                {{ option }}
              </option>
            </BaseSelect>
          </div>

          <div class="flex w-full flex-wrap items-center justify-end gap-2 xl:ml-auto xl:w-auto xl:flex-nowrap">
            <FilterSettingsMenu
              :items="filterItems"
              :model-value="visibleFilterKeys"
              @update:model-value="updateVisibleFilters"
            />
            <BaseButton
              variant="secondary"
              @click="resetFilters"
            >
              清空
            </BaseButton>
            <BaseButton @click="applyFilters">
              应用筛选
            </BaseButton>
          </div>
        </div>
      </FilterToolbar>

      <SurfaceCard class="space-y-4 overflow-hidden">
        <DataTable
          :columns="columns"
          :rows="resultRows"
          :loading="loading"
          row-key="id"
          sort-storage-key="pw:requirement-review-results:sort"
          column-storage-key="pw:requirement-review-results:columns"
          empty-title="当前没有评审结果"
          empty-description="当前项目下还没有保存过需求评审结果。"
          empty-icon="testcase"
        >
          <template #cell-requirement_summary="{ row }">
            <button
              type="button"
              class="text-left"
              @click="openDetailDialog(resultFromRow(row))"
            >
              <div class="font-medium text-gray-900 dark:text-white">
                {{ resultFromRow(row).requirement_summary || '--' }}
              </div>
              <div class="mt-1 text-xs text-gray-400 dark:text-dark-400">
                {{ shortId(resultFromRow(row).id) }}
              </div>
            </button>
          </template>

          <template #cell-review_score="{ row }">
            <span class="font-medium text-gray-900 dark:text-white">
              {{ resultFromRow(row).review_score }}
            </span>
          </template>

          <template #cell-quality_gate="{ row }">
            <StatusPill :tone="getQualityGateTone(resultFromRow(row).quality_gate)">
              {{ resultFromRow(row).quality_gate }}
            </StatusPill>
          </template>

          <template #cell-generation_policy="{ row }">
            <span class="text-gray-500 dark:text-dark-300">
              {{ resultFromRow(row).generation_policy }}
            </span>
          </template>

          <template #cell-batch_id="{ row }">
            <span class="text-gray-500 dark:text-dark-300">
              {{ resultFromRow(row).batch_id || '--' }}
            </span>
          </template>

          <template #cell-created_at="{ row }">
            <span class="text-gray-500 dark:text-dark-300">
              {{ formatDateTime(resultFromRow(row).created_at) }}
            </span>
          </template>

          <template #cell-actions="{ row }">
            <ActionMenu :items="resultActions(resultFromRow(row))" />
          </template>
        </DataTable>

        <PaginationBar
          v-if="pagination.total.value > 0"
          :total="pagination.total.value"
          :page="pagination.page.value"
          :page-size="pagination.pageSize.value"
          :disabled="loading || detailLoading || saving || deleting"
          @update:page="pagination.setPage"
          @update:page-size="pagination.setPageSize"
        />
      </SurfaceCard>
    </div>

    <BaseDialog
      :show="detailDialogOpen"
      :title="dialogTitle"
      width="full"
      @close="closeDetailDialog"
    >
      <div class="space-y-4">
        <StateBanner
          v-if="detailError"
          title="评审详情异常"
          :description="detailError"
          variant="danger"
        />

        <StateBanner
          v-if="formError"
          title="表单校验失败"
          :description="formError"
          variant="warning"
        />

        <div
          v-if="detailLoading"
          class="pw-panel-muted px-4 py-6 text-sm text-gray-500 dark:text-dark-300"
        >
          正在加载评审详情...
        </div>

        <template v-else-if="dialogMode !== 'create' && !currentResult">
          <EmptyState
            icon="testcase"
            title="暂无评审详情"
            description="当前没有可展示的评审结果。"
          />
        </template>

        <template v-else-if="dialogMode === 'detail' && currentResult">
          <div class="space-y-3">
            <div class="space-y-1">
              <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                Requirement Review
              </div>
              <div class="break-all text-xl font-semibold text-gray-900 dark:text-white">
                {{ currentResult.requirement_summary || '--' }}
              </div>
            </div>
            <div class="flex flex-wrap gap-2 text-xs text-gray-500 dark:text-dark-300">
              <span class="pw-chip-subtle break-all">{{ currentResult.id }}</span>
              <span
                v-if="currentResult.thread_id"
                class="pw-chip-subtle break-all"
              >
                Thread {{ currentResult.thread_id }}
              </span>
              <span class="pw-chip-subtle break-all">
                {{ activeProject?.name || activeProjectId || '--' }}
              </span>
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div class="pw-panel-muted px-3 py-3 text-sm">
              评分: <span class="font-medium text-gray-900 dark:text-white">{{ currentResult.review_score }}</span>
            </div>
            <div class="pw-panel-muted px-3 py-3 text-sm">
              门禁:
              <StatusPill :tone="getQualityGateTone(currentResult.quality_gate)">
                {{ currentResult.quality_gate }}
              </StatusPill>
            </div>
            <div class="pw-panel-muted px-3 py-3 text-sm">
              生成策略: {{ currentResult.generation_policy }}
            </div>
            <div class="pw-panel-muted break-all px-3 py-3 text-sm">
              批次: {{ currentResult.batch_id || '--' }}
            </div>
          </div>

          <div class="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
            <div class="space-y-4 text-sm">
              <div class="pw-panel-lg">
                <div class="text-sm font-semibold text-gray-900 dark:text-white">
                  生成策略说明
                </div>
                <div class="mt-3 whitespace-pre-wrap leading-7 text-gray-600 dark:text-dark-300">
                  {{ currentResult.generation_policy_reason || '--' }}
                </div>
              </div>

              <div class="grid gap-4 lg:grid-cols-2">
                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    关键发现
                  </div>
                  <ul class="mt-3 list-disc space-y-1 pl-5 text-gray-600 dark:text-dark-300">
                    <li
                      v-for="item in currentResult.key_findings"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                    <li v-if="currentResult.key_findings.length === 0">
                      --
                    </li>
                  </ul>
                </div>

                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    主要风险
                  </div>
                  <ul class="mt-3 list-disc space-y-1 pl-5 text-gray-600 dark:text-dark-300">
                    <li
                      v-for="item in currentResult.major_risks"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                    <li v-if="currentResult.major_risks.length === 0">
                      --
                    </li>
                  </ul>
                </div>
              </div>

              <div class="grid gap-4 lg:grid-cols-2">
                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    缺失/歧义项
                  </div>
                  <ul class="mt-3 list-disc space-y-1 pl-5 text-gray-600 dark:text-dark-300">
                    <li
                      v-for="item in currentResult.missing_or_ambiguous_items"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                    <li v-if="currentResult.missing_or_ambiguous_items.length === 0">
                      --
                    </li>
                  </ul>
                </div>

                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    建议补充
                  </div>
                  <ul class="mt-3 list-disc space-y-1 pl-5 text-gray-600 dark:text-dark-300">
                    <li
                      v-for="item in currentResult.suggestions_to_improve"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                    <li v-if="currentResult.suggestions_to_improve.length === 0">
                      --
                    </li>
                  </ul>
                </div>
              </div>

              <div class="grid gap-4 lg:grid-cols-2">
                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    关联文档 ID
                  </div>
                  <div class="mt-3 space-y-2">
                    <div
                      v-for="documentId in currentResult.document_ids"
                      :key="documentId"
                      class="pw-panel-muted break-all px-3 py-2 text-xs"
                    >
                      {{ documentId }}
                    </div>
                    <div
                      v-if="currentResult.document_ids.length === 0"
                      class="text-xs text-gray-500 dark:text-dark-300"
                    >
                      --
                    </div>
                  </div>
                </div>

                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    前提假设
                  </div>
                  <ul class="mt-3 list-disc space-y-1 pl-5 text-gray-600 dark:text-dark-300">
                    <li
                      v-for="item in currentResult.assumptions"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                    <li v-if="currentResult.assumptions.length === 0">
                      --
                    </li>
                  </ul>
                </div>
              </div>

              <div class="grid gap-4 lg:grid-cols-2">
                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    维度评分
                  </div>
                  <div
                    v-if="Object.keys(currentResult.dimension_scores || {}).length > 0"
                    class="mt-3 grid gap-3 sm:grid-cols-2"
                  >
                    <div
                      v-for="(score, label) in currentResult.dimension_scores"
                      :key="label"
                      class="pw-panel-muted px-3 py-3"
                    >
                      <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                        {{ formatDimensionLabel(label) }}
                      </div>
                      <div class="mt-2 text-lg font-semibold text-gray-900 dark:text-white">
                        {{ score }}
                      </div>
                    </div>
                  </div>
                  <div
                    v-else
                    class="mt-3 text-sm text-gray-500 dark:text-dark-300"
                  >
                    --
                  </div>
                </div>

                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    原始结构化结果
                  </div>
                  <details class="mt-3 group">
                    <summary class="cursor-pointer text-sm font-medium text-gray-600 marker:text-gray-400 dark:text-dark-300">
                      展开原始 JSON
                    </summary>
                    <pre class="pw-code-block mt-3">{{ stringifyJson(currentResult.raw_result) }}</pre>
                  </details>
                </div>
              </div>
            </div>

            <div class="space-y-4">
              <div class="pw-panel-lg">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div class="text-sm font-semibold text-gray-900 dark:text-white">
                      Batch Context
                    </div>
                    <div class="mt-1 text-xs text-gray-400 dark:text-dark-400">
                      {{ currentResult.batch_id || '当前结果未归属批次' }}
                    </div>
                  </div>
                  <BaseButton
                    variant="secondary"
                    :disabled="!currentResult.batch_id || batchDetailLoading"
                    @click="loadBatchDetail(currentResult.batch_id)"
                  >
                    {{ batchDetailLoading ? '加载中...' : '刷新批次上下文' }}
                  </BaseButton>
                </div>

                <StateBanner
                  v-if="batchDetailError"
                  class="mt-4"
                  title="批次上下文加载失败"
                  :description="batchDetailError"
                  variant="warning"
                />

                <div
                  v-else-if="batchDetailLoading"
                  class="mt-4 text-sm text-gray-500 dark:text-dark-300"
                >
                  正在加载批次上下文...
                </div>

                <div
                  v-else-if="batchDetail?.batch"
                  class="mt-4 space-y-4"
                >
                  <div class="grid gap-3 md:grid-cols-3">
                    <div class="pw-panel-muted px-3 py-3 text-sm">
                      结果数: {{ batchDetail.batch.results_count }}
                    </div>
                    <div class="pw-panel-muted px-3 py-3 text-sm">
                      文档数: {{ batchDetail.batch.documents_count }}
                    </div>
                    <div class="pw-panel-muted px-3 py-3 text-sm">
                      最近时间: {{ formatDateTime(batchDetail.batch.latest_created_at) }}
                    </div>
                  </div>

                  <div>
                    <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                      门禁分布
                    </div>
                    <div class="mt-2 flex flex-wrap gap-2">
                      <StatusPill
                        v-for="[status, count] in gateSummaryEntries"
                        :key="status"
                        :tone="getQualityGateTone(status)"
                      >
                        {{ status }} / {{ count }}
                      </StatusPill>
                      <div
                        v-if="gateSummaryEntries.length === 0"
                        class="text-xs text-gray-500 dark:text-dark-300"
                      >
                        当前批次没有门禁聚合数据。
                      </div>
                    </div>
                  </div>

                  <div>
                    <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                      同批次其他评审结果
                    </div>
                    <div class="mt-2 space-y-2">
                      <button
                        v-for="item in sameBatchResults"
                        :key="item.id"
                        type="button"
                        class="pw-panel flex w-full items-start justify-between gap-3 px-3 py-3 text-left"
                        @click="selectResult(item.id)"
                      >
                        <div class="min-w-0">
                          <div class="font-medium text-gray-900 dark:text-white">
                            {{ item.requirement_summary || '--' }}
                          </div>
                          <div class="mt-1 text-xs text-gray-500 dark:text-dark-300">
                            {{ item.review_score }} / {{ item.generation_policy }}
                          </div>
                        </div>
                        <StatusPill :tone="getQualityGateTone(item.quality_gate)">
                          {{ item.quality_gate }}
                        </StatusPill>
                      </button>
                      <div
                        v-if="sameBatchResults.length === 0"
                        class="text-xs text-gray-500 dark:text-dark-300"
                      >
                        当前批次没有其他评审结果。
                      </div>
                    </div>
                  </div>

                  <div>
                    <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                      同批次文档
                    </div>
                    <div class="mt-2 space-y-2">
                      <div
                        v-for="item in sameBatchDocuments"
                        :key="item.id"
                        class="pw-panel px-3 py-3 text-sm"
                      >
                        <div class="font-medium text-gray-900 dark:text-white">
                          {{ item.filename }}
                        </div>
                        <div class="mt-1 text-xs text-gray-500 dark:text-dark-300">
                          {{ item.parse_status }} / {{ shortId(item.id) }}
                        </div>
                      </div>
                      <div
                        v-if="sameBatchDocuments.length === 0"
                        class="text-xs text-gray-500 dark:text-dark-300"
                      >
                        当前批次没有文档记录。
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="grid gap-4 md:grid-cols-2">
            <label class="block">
              <span class="pw-input-label">评审摘要</span>
              <textarea
                v-model="form.requirement_summary"
                rows="4"
                class="pw-input min-h-[120px] resize-y"
                :disabled="saving"
              />
            </label>

            <label class="block">
              <span class="pw-input-label">生成策略说明</span>
              <textarea
                v-model="form.generation_policy_reason"
                rows="4"
                class="pw-input min-h-[120px] resize-y"
                :disabled="saving"
              />
            </label>
          </div>

          <div class="grid gap-4 md:grid-cols-4">
            <label class="block">
              <span class="pw-input-label">评分</span>
              <input
                v-model="form.review_score"
                class="pw-input"
                :disabled="saving"
              >
            </label>

            <label class="block">
              <span class="pw-input-label">门禁</span>
              <BaseSelect
                v-model="form.quality_gate"
                :disabled="saving"
              >
                <option
                  v-for="option in QUALITY_GATE_OPTIONS"
                  :key="option"
                  :value="option"
                >
                  {{ option }}
                </option>
              </BaseSelect>
            </label>

            <label class="block">
              <span class="pw-input-label">生成策略</span>
              <BaseSelect
                v-model="form.generation_policy"
                :disabled="saving"
              >
                <option
                  v-for="option in GENERATION_POLICY_OPTIONS"
                  :key="option"
                  :value="option"
                >
                  {{ option }}
                </option>
              </BaseSelect>
            </label>

            <label class="block">
              <span class="pw-input-label">批次</span>
              <BaseSelect
                v-model="form.batch_id"
                :disabled="saving"
              >
                <option value="">
                  未归属批次
                </option>
                <option
                  v-for="item in batches"
                  :key="item.batch_id"
                  :value="item.batch_id"
                >
                  {{ item.batch_id }}
                </option>
              </BaseSelect>
            </label>
          </div>

          <div class="grid gap-4 md:grid-cols-2">
            <label class="block">
              <span class="pw-input-label">Thread ID</span>
              <input
                v-model="form.thread_id"
                class="pw-input"
                :disabled="saving"
              >
            </label>

            <label class="block">
              <span class="pw-input-label">关联文档 ID（一行一个）</span>
              <textarea
                v-model="form.document_ids_text"
                rows="5"
                class="pw-input min-h-[140px] resize-y"
                :disabled="saving"
              />
            </label>
          </div>

          <div class="grid gap-4 lg:grid-cols-2">
            <label class="block">
              <span class="pw-input-label">关键发现（一行一个）</span>
              <textarea
                v-model="form.key_findings_text"
                rows="7"
                class="pw-input min-h-[180px] resize-y"
                :disabled="saving"
              />
            </label>

            <label class="block">
              <span class="pw-input-label">主要风险（一行一个）</span>
              <textarea
                v-model="form.major_risks_text"
                rows="7"
                class="pw-input min-h-[180px] resize-y"
                :disabled="saving"
              />
            </label>
          </div>

          <div class="grid gap-4 lg:grid-cols-2">
            <label class="block">
              <span class="pw-input-label">缺失/歧义项（一行一个）</span>
              <textarea
                v-model="form.missing_or_ambiguous_items_text"
                rows="7"
                class="pw-input min-h-[180px] resize-y"
                :disabled="saving"
              />
            </label>

            <label class="block">
              <span class="pw-input-label">建议补充（一行一个）</span>
              <textarea
                v-model="form.suggestions_to_improve_text"
                rows="7"
                class="pw-input min-h-[180px] resize-y"
                :disabled="saving"
              />
            </label>
          </div>

          <label class="block">
            <span class="pw-input-label">assumptions（一行一个）</span>
            <textarea
              v-model="form.assumptions_text"
              rows="5"
              class="pw-input min-h-[140px] resize-y"
              :disabled="saving"
            />
          </label>

          <div class="grid gap-4 lg:grid-cols-2">
            <label class="block">
              <span class="pw-input-label">dimension_scores (JSON object)</span>
              <textarea
                v-model="form.dimension_scores_text"
                rows="10"
                class="pw-input min-h-[220px] resize-y font-mono text-xs leading-6"
                :disabled="saving"
              />
              <div
                class="mt-2 text-xs"
                :class="dimensionScoresState.error ? 'text-rose-500' : 'text-gray-400 dark:text-dark-400'"
              >
                {{ dimensionScoresState.error || 'JSON 校验通过' }}
              </div>
            </label>

            <label class="block">
              <span class="pw-input-label">raw_result (JSON object)</span>
              <textarea
                v-model="form.raw_result_text"
                rows="10"
                class="pw-input min-h-[220px] resize-y font-mono text-xs leading-6"
                :disabled="saving"
              />
              <div
                class="mt-2 text-xs"
                :class="rawResultState.error ? 'text-rose-500' : 'text-gray-400 dark:text-dark-400'"
              >
                {{ rawResultState.error || 'JSON 校验通过' }}
              </div>
            </label>
          </div>
        </template>
      </div>

      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <template v-if="dialogMode === 'detail'">
            <BaseButton
              v-if="canWrite && currentResult"
              variant="secondary"
              @click="openEditDialog(currentResult)"
            >
              编辑
            </BaseButton>
            <BaseButton
              v-if="canWrite && currentResult"
              variant="danger"
              @click="showDeleteDialog = true"
            >
              删除
            </BaseButton>
            <BaseButton
              variant="secondary"
              @click="closeDetailDialog"
            >
              关闭
            </BaseButton>
          </template>

          <template v-else>
            <BaseButton
              variant="secondary"
              :disabled="saving"
              @click="dialogMode === 'create' ? closeDetailDialog() : (dialogMode = 'detail')"
            >
              取消
            </BaseButton>
            <BaseButton
              :disabled="saving"
              @click="handleSave"
            >
              {{ saving ? '保存中...' : dialogMode === 'create' ? '创建' : '保存' }}
            </BaseButton>
          </template>
        </div>
      </template>
    </BaseDialog>

    <ConfirmDialog
      :show="showDeleteDialog"
      title="删除评审结果"
      :message="`删除 ${currentResult?.requirement_summary || shortId(currentResult?.id || '')} 后将无法恢复，确认继续吗？`"
      confirm-text="删除"
      danger
      @cancel="showDeleteDialog = false"
      @confirm="handleDelete"
    />
  </section>
</template>
