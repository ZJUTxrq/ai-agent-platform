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
import {
  resolveDocumentContentType,
  resolveDocumentStoragePath
} from '@/modules/testcase/document-preview'
import { getOperationFailureMessage } from '@/services/operations/operations.service'
import {
  createRequirementReviewDocument,
  downloadRequirementReviewDocument,
  deleteRequirementReviewDocument,
  exportRequirementReviewDocumentsByOperation,
  getRequirementReviewBatchDetail,
  getRequirementReviewDocument,
  getRequirementReviewOverview,
  getRequirementReviewRole,
  listRequirementReviewBatches,
  listRequirementReviewDocuments,
  previewRequirementReviewDocument,
  updateRequirementReviewDocument,
  type UpsertRequirementReviewDocumentPayload
} from '@/services/requirement-review/requirement-review.service'
import { useUiStore } from '@/stores/ui'
import type {
  RequirementReviewBatchDetail,
  RequirementReviewBatchSummary,
  RequirementReviewDocument,
  RequirementReviewOverview,
  RequirementReviewResult,
  RequirementReviewRole
} from '@/types/management'
import { copyText } from '@/utils/clipboard'
import { downloadBlob } from '@/utils/browser-download'
import { formatDateTime, shortId } from '@/utils/format'

type DocumentDialogMode = 'detail' | 'create' | 'edit'

type JsonParseResult = {
  value: Record<string, unknown>
  error: string | null
}

type DocumentFormState = {
  batch_id: string
  thread_id: string
  filename: string
  content_type: string
  source_kind: string
  parse_status: string
  summary_for_model: string
  parsed_text: string
  structured_data_text: string
  provenance_text: string
  error_text: string
}

const PARSE_STATUS_OPTIONS = ['parsed', 'failed', 'unsupported', 'unprocessed']

function getParseStatusTone(status: string): 'neutral' | 'success' | 'warning' | 'danger' {
  const normalized = status.trim().toLowerCase()
  if (normalized === 'parsed') {
    return 'success'
  }
  if (normalized === 'failed') {
    return 'danger'
  }
  if (normalized === 'unsupported') {
    return 'warning'
  }
  return 'neutral'
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function openPreviewWindowShell(filename?: string) {
  const previewWindow = window.open('', '_blank')
  if (!previewWindow) {
    throw new Error('浏览器阻止了预览窗口，请允许当前站点打开新窗口后重试。')
  }

  previewWindow.document.write(`<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapeHtml(filename || 'document')}</title>
    <style>
      body {
        margin: 0;
        min-height: 100dvh;
        display: grid;
        place-items: center;
        background: #eef3fa;
        color: #33465f;
        font-family: "Segoe UI", "PingFang SC", sans-serif;
      }
      .preview-loading {
        border-radius: 18px;
        border: 1px solid rgba(118, 145, 178, 0.18);
        background: rgba(255, 255, 255, 0.92);
        padding: 18px 22px;
        box-shadow: 0 18px 40px rgba(67, 93, 126, 0.08);
        font-size: 14px;
      }
    </style>
  </head>
  <body>
    <div class="preview-loading">正在加载预览…</div>
  </body>
</html>`)
  previewWindow.document.close()
  return previewWindow
}

function isTextPreviewContentType(contentType: string): boolean {
  return (
    contentType.startsWith('text/') ||
    contentType === 'application/json' ||
    contentType === 'application/xml' ||
    contentType === 'application/javascript' ||
    contentType === 'text/markdown'
  )
}

function supportsInlinePreview(contentType: string): boolean {
  return (
    contentType.startsWith('application/pdf') ||
    contentType.startsWith('image/') ||
    isTextPreviewContentType(contentType)
  )
}

async function openDocumentPreview(
  blob: Blob,
  options?: { filename?: string; contentType?: string | null; previewWindow?: Window | null }
) {
  const contentType = (options?.contentType || blob.type || 'application/octet-stream').toLowerCase()
  const previewWindow = options?.previewWindow ?? window.open('', '_blank')
  if (!previewWindow) {
    throw new Error('浏览器阻止了预览窗口，请允许当前站点打开新窗口后重试。')
  }

  if (contentType.startsWith('application/pdf')) {
    const objectUrl = URL.createObjectURL(blob)
    previewWindow.location.replace(objectUrl)
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
    return
  }

  if (contentType.startsWith('image/')) {
    const objectUrl = URL.createObjectURL(blob)
    previewWindow.document.write(`<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapeHtml(options?.filename || 'image')}</title>
    <style>
      body {
        margin: 0;
        min-height: 100dvh;
        display: grid;
        place-items: center;
        background: #dfe7f3;
      }
      img {
        display: block;
        max-width: min(92vw, 1440px);
        max-height: 92vh;
        object-fit: contain;
        border-radius: 18px;
        box-shadow: 0 24px 60px rgba(15, 23, 42, 0.16);
        background: rgba(255, 255, 255, 0.82);
      }
    </style>
  </head>
  <body>
    <img src="${objectUrl}" alt="${escapeHtml(options?.filename || 'image')}" />
  </body>
</html>`)
    previewWindow.document.close()
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
    return
  }

  if (isTextPreviewContentType(contentType)) {
    const text = await blob.text()
    previewWindow.document.write(`<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapeHtml(options?.filename || 'document')}</title>
    <style>
      body {
        margin: 0;
        padding: 24px;
        background: #eef3fa;
        color: #142033;
        font-family: "SFMono-Regular", "Consolas", monospace;
      }
      pre {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        line-height: 1.7;
        font-size: 13px;
      }
    </style>
  </head>
  <body>
    <pre>${escapeHtml(text)}</pre>
  </body>
</html>`)
    previewWindow.document.close()
    return
  }

  throw new Error(`当前类型暂不支持在线预览：${contentType}`)
}

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

function buildFormFromDocument(item: RequirementReviewDocument): DocumentFormState {
  return {
    batch_id: item.batch_id ?? '',
    thread_id: item.thread_id ?? '',
    filename: item.filename,
    content_type: item.content_type,
    source_kind: item.source_kind,
    parse_status: item.parse_status,
    summary_for_model: item.summary_for_model ?? '',
    parsed_text: item.parsed_text ?? '',
    structured_data_text: stringifyJson(item.structured_data),
    provenance_text: stringifyJson(item.provenance),
    error_text: item.error ? stringifyJson(item.error) : '{}'
  }
}

function createEmptyForm(): DocumentFormState {
  return {
    batch_id: '',
    thread_id: '',
    filename: '',
    content_type: 'application/pdf',
    source_kind: 'upload',
    parse_status: 'parsed',
    summary_for_model: '',
    parsed_text: '',
    structured_data_text: '{}',
    provenance_text: '{}',
    error_text: '{}'
  }
}

const { activeProjectId, activeProject } = useWorkspaceProjectContext()
const uiStore = useUiStore()

const overview = ref<RequirementReviewOverview | null>(null)
const batches = ref<RequirementReviewBatchSummary[]>([])
const role = ref<RequirementReviewRole | null>(null)
const items = ref<RequirementReviewDocument[]>([])
const selectedId = ref('')
const selectedDocument = ref<RequirementReviewDocument | null>(null)
const batchDetail = ref<RequirementReviewBatchDetail | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const batchDetailLoading = ref(false)
const previewing = ref(false)
const downloading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const exporting = ref(false)
const detailDialogOpen = ref(false)
const dialogMode = ref<DocumentDialogMode>('detail')
const showDeleteDialog = ref(false)
const error = ref('')
const detailError = ref('')
const batchDetailError = ref('')
const formError = ref('')
const searchInput = ref('')
const batchInput = ref('')
const parseStatusInput = ref('')
const query = ref('')
const batchFilter = ref('')
const parseStatusFilter = ref('')
const form = ref<DocumentFormState>(createEmptyForm())

const pagination = usePagination({
  initialPageSize: 20,
  storageKey: 'pw:requirement-review-documents:page-size'
})
const filterItems: FilterSettingItem[] = [
  { key: 'batch', label: '批次' },
  { key: 'parse_status', label: '解析状态' }
]
const { visibleFilterKeys, visibleFilterSet, setVisibleFilterKeys } = useVisibleFilterSettings(
  filterItems,
  'pw:requirement-review-documents:filters'
)

const documentRows = computed(() => items.value as unknown as Record<string, unknown>[])
const selectedListItem = computed(
  () => items.value.find((item) => item.id === selectedId.value) ?? null
)
const currentDocument = computed(
  () => selectedDocument.value ?? items.value.find((item) => item.id === selectedId.value) ?? null
)
const selectedItem = computed(() => selectedDocument.value ?? selectedListItem.value)
const storagePath = computed(() => resolveDocumentStoragePath(selectedItem.value))
const selectedContentType = computed(() => resolveDocumentContentType(selectedItem.value).toLowerCase())
const isPreviewSupported = computed(() => supportsInlinePreview(selectedContentType.value))
const canWrite = computed(() => Boolean(role.value?.can_write_requirement_review))
const sameBatchResults = computed<RequirementReviewResult[]>(() => batchDetail.value?.results.items ?? [])
const sameBatchDocuments = computed(() =>
  (batchDetail.value?.documents.items ?? []).filter((item) => item.id !== currentDocument.value?.id)
)
const selectedBatchSummary = computed(
  () => batchDetail.value?.batch ?? batches.value.find((item) => item.batch_id === (selectedItem.value?.batch_id || '')) ?? null
)
const batchStatusEntries = computed(() =>
  Object.entries(selectedBatchSummary.value?.parse_status_summary ?? {}).sort(([left], [right]) =>
    left.localeCompare(right)
  )
)
const structuredDataState = computed(() => parseJsonObjectText(form.value.structured_data_text, 'structured_data'))
const provenanceState = computed(() => parseJsonObjectText(form.value.provenance_text, 'provenance'))
const errorState = computed(() => parseJsonObjectText(form.value.error_text, 'error'))
const dialogTitle = computed(() => {
  if (dialogMode.value === 'create') {
    return '新增评审文档'
  }
  if (dialogMode.value === 'edit') {
    return '编辑评审文档'
  }
  return '文档详情'
})

const columns = computed<DataTableColumn[]>(() => [
  {
    key: 'filename',
    label: '文件名',
    sortable: true,
    alwaysVisible: true,
    sortValue: (row) => row.filename || ''
  },
  {
    key: 'parse_status',
    label: '状态',
    sortable: true,
    sortValue: (row) => row.parse_status || ''
  },
  {
    key: 'source_kind',
    label: '来源',
    sortable: true,
    sortValue: (row) => row.source_kind || ''
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

function documentFromRow(row: Record<string, unknown>) {
  return row as RequirementReviewDocument
}

function pushToast(type: 'success' | 'warning' | 'error', title: string, message: string) {
  uiStore.pushToast({ type, title, message })
}

async function handleCopyDocumentId(document: RequirementReviewDocument) {
  const copied = await copyText(document.id)
  pushToast(
    copied ? 'success' : 'warning',
    copied ? '已复制文档 ID' : '复制失败',
    copied ? document.id : '当前环境不支持自动复制，请手动复制。'
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

async function loadDocuments() {
  const projectId = activeProjectId.value
  if (!projectId) {
    overview.value = null
    batches.value = []
    role.value = null
    items.value = []
    selectedId.value = ''
    selectedDocument.value = null
    batchDetail.value = null
    pagination.setTotal(0)
    error.value = ''
    return
  }

  loading.value = true
  error.value = ''

  try {
    await loadMeta(projectId)
    const payload = await listRequirementReviewDocuments(projectId, {
      batch_id: batchFilter.value || undefined,
      parse_status: parseStatusFilter.value || undefined,
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
    error.value = loadError instanceof Error ? loadError.message : '文档列表加载失败'
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
    selectedDocument.value = null
    batchDetail.value = null
    detailError.value = ''
    batchDetailError.value = ''
    return
  }

  detailLoading.value = true
  detailError.value = ''
  try {
    const document = await getRequirementReviewDocument(projectId, selectedId.value)
    selectedDocument.value = document
    if (dialogMode.value === 'edit') {
      form.value = buildFormFromDocument(document)
    }
    await loadBatchDetail(document.batch_id)
  } catch (loadError) {
    selectedDocument.value = null
    batchDetail.value = null
    detailError.value = loadError instanceof Error ? loadError.message : '文档详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function selectDocument(documentId: string) {
  selectedId.value = documentId
}

async function openEditDialog(document: RequirementReviewDocument) {
  dialogMode.value = 'edit'
  formError.value = ''
  detailDialogOpen.value = true
  if (selectedId.value !== document.id) {
    selectedId.value = document.id
    return
  }
  if (!selectedDocument.value || selectedDocument.value.id !== document.id) {
    await loadDetail()
  }
  if (selectedDocument.value) {
    form.value = buildFormFromDocument(selectedDocument.value)
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
  selectedDocument.value = null
  batchDetail.value = null
  detailError.value = ''
  batchDetailError.value = ''
  formError.value = ''
  form.value = createEmptyForm()
  detailDialogOpen.value = true
}

function buildMutationPayload(): UpsertRequirementReviewDocumentPayload {
  const parsedStructuredData = parseJsonObjectText(form.value.structured_data_text, 'structured_data')
  if (parsedStructuredData.error) {
    throw new Error(parsedStructuredData.error)
  }
  const parsedProvenance = parseJsonObjectText(form.value.provenance_text, 'provenance')
  if (parsedProvenance.error) {
    throw new Error(parsedProvenance.error)
  }
  const parsedError = parseJsonObjectText(form.value.error_text, 'error')
  if (parsedError.error) {
    throw new Error(parsedError.error)
  }

  return {
    batch_id: form.value.batch_id.trim() || null,
    thread_id: form.value.thread_id.trim() || null,
    filename: form.value.filename.trim(),
    content_type: form.value.content_type.trim(),
    source_kind: form.value.source_kind.trim(),
    parse_status: form.value.parse_status,
    summary_for_model: form.value.summary_for_model,
    parsed_text: form.value.parsed_text,
    structured_data: parsedStructuredData.value,
    provenance: parsedProvenance.value,
    error: parsedError.value
  }
}

async function handleSave() {
  const projectId = activeProjectId.value
  const documentId = currentDocument.value?.id
  if (!projectId) {
    return
  }

  if (!form.value.filename.trim()) {
    formError.value = '文件名不能为空'
    return
  }
  if (!form.value.content_type.trim()) {
    formError.value = 'content_type 不能为空'
    return
  }

  saving.value = true
  formError.value = ''

  try {
    const nextMode = dialogMode.value
    const payload = buildMutationPayload()
    const saved =
      nextMode === 'create'
        ? await createRequirementReviewDocument(projectId, {
            ...payload,
            filename: payload.filename || '',
            content_type: payload.content_type || 'application/pdf'
          })
        : await updateRequirementReviewDocument(projectId, documentId || '', payload)
    selectedDocument.value = saved
    selectedId.value = saved.id
    form.value = buildFormFromDocument(saved)
    dialogMode.value = 'detail'
    pushToast(
      'success',
      nextMode === 'create' ? '创建成功' : '保存成功',
      `评审文档 ${shortId(saved.id)} 已同步`
    )
    await loadDocuments()
    await loadBatchDetail(saved.batch_id)
  } catch (saveError) {
    formError.value = saveError instanceof Error ? saveError.message : '评审文档保存失败'
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
      parse_status: parseStatusFilter.value || undefined,
      query: query.value || undefined
    }
    const download = await (async () => {
      const result = await exportRequirementReviewDocumentsByOperation(projectId, exportOptions)
      if (result.operation.status !== 'succeeded') {
        throw new Error(getOperationFailureMessage(result.operation))
      }
      return result.download
    })()
    downloadBlob(download.blob, download.filename || 'requirement-review-documents.xlsx')
    pushToast('success', '导出成功', '评审文档 Excel 已开始下载')
  } catch (exportError) {
    pushToast(
      'error',
      '导出失败',
      exportError instanceof Error ? exportError.message : '评审文档导出失败'
    )
  } finally {
    exporting.value = false
  }
}

async function handlePreview(targetDocument: RequirementReviewDocument | null = selectedItem.value) {
  const projectId = activeProjectId.value
  if (!projectId || !targetDocument) {
    return
  }
  const targetContentType = resolveDocumentContentType(targetDocument).toLowerCase()
  if (!supportsInlinePreview(targetContentType)) {
    detailError.value = `当前类型暂不支持在线预览：${targetContentType || 'unknown'}`
    return
  }

  previewing.value = true
  let previewWindow: Window | null = null

  try {
    selectDocument(targetDocument.id)
    previewWindow = openPreviewWindowShell(targetDocument.filename)
    const download = await previewRequirementReviewDocument(projectId, targetDocument.id)
    await openDocumentPreview(download.blob, {
      filename: targetDocument.filename,
      contentType: download.contentType || targetContentType,
      previewWindow
    })
  } catch (previewError) {
    previewWindow?.close()
    detailError.value = previewError instanceof Error ? previewError.message : '文档预览失败'
  } finally {
    previewing.value = false
  }
}

async function handleDownload(targetDocument: RequirementReviewDocument | null = selectedItem.value) {
  const projectId = activeProjectId.value
  if (!projectId || !targetDocument) {
    return
  }

  downloading.value = true
  try {
    selectDocument(targetDocument.id)
    const download = await downloadRequirementReviewDocument(projectId, targetDocument.id)
    downloadBlob(download.blob, download.filename || targetDocument.filename)
  } catch (downloadError) {
    detailError.value = downloadError instanceof Error ? downloadError.message : '文档下载失败'
  } finally {
    downloading.value = false
  }
}

async function handleDelete() {
  const projectId = activeProjectId.value
  const documentId = currentDocument.value?.id
  if (!projectId || !documentId) {
    return
  }

  deleting.value = true
  try {
    await deleteRequirementReviewDocument(projectId, documentId)
    pushToast('success', '删除成功', `评审文档 ${shortId(documentId)} 已删除`)
    showDeleteDialog.value = false
    closeDetailDialog()
    selectedDocument.value = null
    batchDetail.value = null
    await loadDocuments()
  } catch (deleteError) {
    pushToast(
      'error',
      '删除失败',
      deleteError instanceof Error ? deleteError.message : '评审文档删除失败'
    )
  } finally {
    deleting.value = false
  }
}

function documentActions(document: RequirementReviewDocument): ActionMenuItem[] {
  const path = resolveDocumentStoragePath(document)
  const previewSupported = supportsInlinePreview(resolveDocumentContentType(document).toLowerCase())
  const actions: ActionMenuItem[] = [
    {
      key: 'detail',
      label: document.id === selectedId.value ? '当前详情' : '查看详情',
      icon: 'eye',
      disabled: document.id === selectedId.value,
      onSelect: () => selectDocument(document.id)
    },
    {
      key: 'preview',
      label: '在线预览',
      icon: 'eye',
      disabled: !path || !previewSupported,
      onSelect: () => void handlePreview(document)
    },
    {
      key: 'download',
      label: '下载原始文件',
      icon: 'download',
      disabled: !path,
      onSelect: () => void handleDownload(document)
    },
    {
      key: 'copy-document-id',
      label: '复制文档 ID',
      icon: 'copy',
      onSelect: () => void handleCopyDocumentId(document)
    },
    {
      key: 'copy-batch-id',
      label: document.batch_id ? '复制批次 ID' : '缺少批次 ID',
      icon: 'copy',
      disabled: !document.batch_id,
      onSelect: () => void handleCopyBatchId(document.batch_id || '')
    }
  ]

  if (canWrite.value) {
    actions.push(
      {
        key: 'edit',
        label: '编辑',
        icon: 'edit',
        onSelect: () => void openEditDialog(document)
      },
      {
        key: 'delete',
        label: '删除',
        icon: 'trash',
        danger: true,
        onSelect: () => {
          selectedId.value = document.id
          selectedDocument.value = document
          dialogMode.value = 'detail'
          showDeleteDialog.value = true
        }
      }
    )
  }

  return actions
}

function documentRowClass(row: Record<string, unknown>) {
  return documentFromRow(row).id === selectedId.value ? 'bg-primary-50/80 dark:bg-primary-950/20' : ''
}

function applyFilters() {
  query.value = searchInput.value.trim()
  batchFilter.value = batchInput.value
  parseStatusFilter.value = parseStatusInput.value
  if (pagination.page.value === 1) {
    void loadDocuments()
    return
  }
  pagination.resetPage()
}

function resetFilters() {
  searchInput.value = ''
  batchInput.value = ''
  parseStatusInput.value = ''
  query.value = ''
  batchFilter.value = ''
  parseStatusFilter.value = ''
  if (pagination.page.value === 1) {
    void loadDocuments()
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
  if (previous.has('parse_status') && !visibleFilterSet.value.has('parse_status')) {
    parseStatusInput.value = ''
    parseStatusFilter.value = ''
    shouldReload = true
  }

  if (shouldReload) {
    if (pagination.page.value === 1) {
      void loadDocuments()
    } else {
      pagination.resetPage()
    }
  }
}

watch(
  [() => activeProjectId.value, () => pagination.page.value, () => pagination.pageSize.value],
  () => {
    void loadDocuments()
  },
  { immediate: true }
)

watch(
  () => selectedId.value,
  () => {
    void loadDetail()
  }
)
</script>

<template>
  <section class="pw-page-shell space-y-4">
    <RequirementReviewWorkspaceNav />

    <PageHeader
      eyebrow="Requirement Review"
      title="文档列表"
      description="查看当前项目下已持久化的需求评审原始文档与解析结果，并支持导出、查看详情、新增、编辑和删除。"
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
          @click="loadDocuments"
        >
          刷新
        </BaseButton>
        <BaseButton
          v-if="canWrite"
          :disabled="saving || deleting"
          @click="openCreateDialog"
        >
          新增文档
        </BaseButton>
      </template>
    </PageHeader>

    <RequirementReviewOverviewStrip :overview="overview" />

    <StateBanner
      v-if="error"
      title="文档列表加载失败"
      :description="error"
      variant="danger"
    />

    <EmptyState
      v-if="!activeProject"
      icon="project"
      title="请先选择项目"
      description="当前没有项目上下文，无法读取需求评审文档。"
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
              placeholder="按文件名、摘要或文档 ID 搜索"
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
            v-if="visibleFilterSet.has('parse_status')"
            class="w-full sm:w-[200px]"
          >
            <BaseSelect v-model="parseStatusInput">
              <option value="">
                全部状态
              </option>
              <option
                v-for="option in PARSE_STATUS_OPTIONS"
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

      <div class="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
      <SurfaceCard class="space-y-4 overflow-hidden">
        <DataTable
          :columns="columns"
          :rows="documentRows"
          :loading="loading"
          :row-class="documentRowClass"
          row-key="id"
          sort-storage-key="pw:requirement-review-documents:sort"
          column-storage-key="pw:requirement-review-documents:columns"
          empty-title="当前没有文档记录"
          empty-description="当前项目下还没有保存过需求评审文档。"
          empty-icon="folder"
        >
          <template #cell-filename="{ row }">
            <button
              type="button"
              class="text-left"
              @click="selectDocument(documentFromRow(row).id)"
            >
              <div class="font-medium text-gray-900 dark:text-white">
                {{ documentFromRow(row).filename }}
              </div>
              <div class="mt-1 text-xs text-gray-400 dark:text-dark-400">
                {{ documentFromRow(row).content_type }} / {{ shortId(documentFromRow(row).id) }}
              </div>
              <div
                v-if="documentFromRow(row).id === selectedId"
                class="mt-1 text-xs uppercase tracking-[0.14em] text-primary-600 dark:text-primary-300"
              >
                当前查看
              </div>
            </button>
          </template>

          <template #cell-parse_status="{ row }">
            <StatusPill :tone="getParseStatusTone(documentFromRow(row).parse_status)">
              {{ documentFromRow(row).parse_status }}
            </StatusPill>
          </template>

          <template #cell-source_kind="{ row }">
            <span class="text-gray-500 dark:text-dark-300">
              {{ documentFromRow(row).source_kind }}
            </span>
          </template>

          <template #cell-batch_id="{ row }">
            <span class="text-gray-500 dark:text-dark-300">
              {{ documentFromRow(row).batch_id || '--' }}
            </span>
          </template>

          <template #cell-created_at="{ row }">
            <span class="text-gray-500 dark:text-dark-300">
              {{ formatDateTime(documentFromRow(row).created_at) }}
            </span>
          </template>

          <template #cell-actions="{ row }">
            <ActionMenu :items="documentActions(documentFromRow(row))" />
          </template>
        </DataTable>

        <PaginationBar
          v-if="pagination.total.value > 0"
          :total="pagination.total.value"
          :page="pagination.page.value"
          :page-size="pagination.pageSize.value"
          :disabled="loading || detailLoading || previewing || downloading || saving || deleting"
          @update:page="pagination.setPage"
          @update:page-size="pagination.setPageSize"
        />
      </SurfaceCard>
        <SurfaceCard class="space-y-4">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div class="text-base font-semibold text-gray-900 dark:text-white">
              解析详情
            </div>
            <div class="flex flex-wrap gap-2">
              <BaseButton
                variant="secondary"
                :disabled="!selectedItem || !storagePath || !isPreviewSupported || previewing"
                @click="handlePreview()"
              >
                {{ previewing ? '预览中...' : '在线预览' }}
              </BaseButton>
              <BaseButton
                variant="secondary"
                :disabled="!selectedItem || !storagePath || downloading"
                @click="handleDownload()"
              >
                {{ downloading ? '下载中...' : '下载原始文件' }}
              </BaseButton>
            </div>
          </div>

          <StateBanner
            v-if="detailError"
            title="文档详情异常"
            :description="detailError"
            variant="danger"
          />

          <div
            v-if="detailLoading"
            class="text-sm text-gray-500 dark:text-dark-300"
          >
            正在加载文档详情...
          </div>

          <EmptyState
            v-else-if="!selectedItem"
            icon="folder"
            title="先选择一个文档"
            description="选中左侧文档后，这里会展示解析详情，并支持在线预览和原始文件下载。"
          />

          <template v-else>
            <div class="space-y-1">
              <div class="text-lg font-semibold break-all tracking-tight text-gray-900 dark:text-white">
                {{ selectedItem.filename }}
              </div>
              <div class="text-xs text-gray-400 dark:text-dark-400">
                {{ selectedItem.id }}
              </div>
            </div>

            <div class="grid gap-3 text-sm">
              <div>
                <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                  解析状态
                </div>
                <div class="mt-1 text-gray-900 dark:text-white">
                  {{ selectedItem.parse_status }}
                </div>
              </div>
              <div>
                <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                  原始文件路径
                </div>
                <div class="mt-1 break-all text-gray-500 dark:text-dark-300">
                  {{ storagePath || '当前记录未保存原始文件路径，仅保留了解析结果。' }}
                </div>
              </div>
              <div>
                <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                  预览能力
                </div>
                <div class="mt-1 text-gray-500 dark:text-dark-300">
                  {{
                    isPreviewSupported
                      ? `当前支持在线预览，类型为 ${selectedItem.content_type || 'unknown'}。`
                      : `当前仅支持下载，暂不支持在线预览 ${selectedItem.content_type || 'unknown'}。`
                  }}
                </div>
              </div>
              <div>
                <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                  摘要
                </div>
                <div class="mt-1 whitespace-pre-wrap text-gray-500 dark:text-dark-300">
                  {{ selectedItem.summary_for_model || '--' }}
                </div>
              </div>
              <div>
                <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                  parsed_text
                </div>
                <pre class="pw-code-block mt-2 max-h-[220px]">{{ selectedItem.parsed_text || '--' }}</pre>
              </div>
              <div>
                <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                  structured_data
                </div>
                <pre class="pw-code-block max-h-[220px]">{{ stringifyJson(selectedItem.structured_data) }}</pre>
              </div>
              <div>
                <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                  provenance
                </div>
                <pre class="pw-code-block mt-2 max-h-[220px]">{{ stringifyJson(selectedItem.provenance) }}</pre>
              </div>
              <div v-if="selectedItem.error">
                <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                  error
                </div>
                <pre class="mt-2 max-h-[180px] overflow-auto whitespace-pre-wrap break-words rounded-2xl bg-rose-50 p-3 text-xs text-rose-700 dark:bg-rose-950/20 dark:text-rose-200">{{ stringifyJson(selectedItem.error) }}</pre>
              </div>

              <div class="pw-panel-muted">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div class="text-sm font-semibold text-gray-900 dark:text-white">
                      Batch Context
                    </div>
                    <div class="mt-1 text-xs text-gray-400 dark:text-dark-400">
                      {{ selectedItem.batch_id || '当前文档未归属批次' }}
                    </div>
                  </div>
                  <div class="flex flex-wrap gap-2">
                    <BaseButton
                      variant="secondary"
                      :disabled="!selectedItem.batch_id || batchDetailLoading"
                      @click="loadBatchDetail(selectedItem.batch_id)"
                    >
                      {{ batchDetailLoading ? '加载中...' : '刷新批次上下文' }}
                    </BaseButton>
                    <BaseButton
                      v-if="selectedItem.batch_id"
                      variant="secondary"
                      @click="handleCopyBatchId(selectedItem.batch_id)"
                    >
                      复制批次 ID
                    </BaseButton>
                  </div>
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
                  v-else-if="selectedBatchSummary"
                  class="mt-4 space-y-4"
                >
                  <div class="grid gap-3 md:grid-cols-3">
                    <div class="pw-panel-muted px-3 py-3 text-sm">
                      结果数: {{ selectedBatchSummary.results_count }}
                    </div>
                    <div class="pw-panel-muted px-3 py-3 text-sm">
                      文档数: {{ selectedBatchSummary.documents_count }}
                    </div>
                    <div class="pw-panel-muted px-3 py-3 text-sm">
                      最近时间: {{ formatDateTime(selectedBatchSummary.latest_created_at) }}
                    </div>
                  </div>

                  <div>
                    <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                      解析状态分布
                    </div>
                    <div class="mt-2 flex flex-wrap gap-2">
                      <StatusPill
                        v-for="[status, count] in batchStatusEntries"
                        :key="status"
                        :tone="getParseStatusTone(status)"
                      >
                        {{ status }} / {{ count }}
                      </StatusPill>
                      <div
                        v-if="batchStatusEntries.length === 0"
                        class="text-xs text-gray-500 dark:text-dark-300"
                      >
                        当前批次没有状态聚合数据。
                      </div>
                    </div>
                  </div>

                  <div>
                    <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                      同批次其他评审结果
                    </div>
                    <div class="mt-2 space-y-2">
                      <div
                        v-for="item in sameBatchResults"
                        :key="item.id"
                        class="pw-panel px-3 py-3 text-sm"
                      >
                        <div class="flex items-start justify-between gap-3">
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
                        </div>
                      </div>
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
                      <button
                        v-for="document in sameBatchDocuments"
                        :key="document.id"
                        type="button"
                        class="pw-panel flex w-full items-start justify-between gap-3 px-3 py-3 text-left transition hover:border-primary-200 dark:hover:border-primary-700"
                        @click="selectDocument(document.id)"
                      >
                        <div class="min-w-0">
                          <div class="font-medium text-gray-900 dark:text-white">
                            {{ document.filename }}
                          </div>
                          <div class="mt-1 break-all text-xs text-gray-500 dark:text-dark-300">
                            {{ document.id }}
                          </div>
                        </div>
                        <StatusPill :tone="getParseStatusTone(document.parse_status)">
                          {{ document.parse_status }}
                        </StatusPill>
                      </button>
                      <div
                        v-if="sameBatchDocuments.length === 0"
                        class="text-xs text-gray-500 dark:text-dark-300"
                      >
                        当前批次没有其他文档。
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </SurfaceCard>
      </div>
    </div>

    <BaseDialog
      :show="detailDialogOpen && dialogMode !== 'detail'"
      :title="dialogTitle"
      width="full"
      @close="closeDetailDialog"
    >
      <div class="space-y-4">
        <StateBanner
          v-if="detailError"
          title="文档详情异常"
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
          正在加载文档详情...
        </div>

        <template v-else-if="dialogMode !== 'create' && !currentDocument">
          <EmptyState
            icon="folder"
            title="暂无文档详情"
            description="当前没有可展示的文档记录。"
          />
        </template>

        <template v-else-if="dialogMode === 'detail' && currentDocument">
          <div class="space-y-3">
            <div class="space-y-1">
              <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                Requirement Review Document
              </div>
              <div class="break-all text-xl font-semibold text-gray-900 dark:text-white">
                {{ currentDocument.filename }}
              </div>
            </div>
            <div class="flex flex-wrap gap-2 text-xs text-gray-500 dark:text-dark-300">
              <span class="pw-chip-subtle break-all">{{ currentDocument.id }}</span>
              <span
                v-if="currentDocument.thread_id"
                class="pw-chip-subtle break-all"
              >
                Thread {{ currentDocument.thread_id }}
              </span>
              <span class="pw-chip-subtle break-all">
                {{ activeProject?.name || activeProjectId || '--' }}
              </span>
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div class="pw-panel-muted px-3 py-3 text-sm">
              状态:
              <StatusPill :tone="getParseStatusTone(currentDocument.parse_status)">
                {{ currentDocument.parse_status }}
              </StatusPill>
            </div>
            <div class="pw-panel-muted px-3 py-3 text-sm">
              来源: {{ currentDocument.source_kind }}
            </div>
            <div class="pw-panel-muted break-all px-3 py-3 text-sm">
              批次: {{ currentDocument.batch_id || '--' }}
            </div>
            <div class="pw-panel-muted px-3 py-3 text-sm">
              时间: {{ formatDateTime(currentDocument.created_at) }}
            </div>
          </div>

          <div class="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
            <div class="space-y-4 text-sm">
              <div class="pw-panel-lg">
                <div class="text-sm font-semibold text-gray-900 dark:text-white">
                  摘要
                </div>
                <div class="mt-3 whitespace-pre-wrap leading-7 text-gray-600 dark:text-dark-300">
                  {{ currentDocument.summary_for_model || '--' }}
                </div>
              </div>

              <div class="pw-panel-lg">
                <div class="text-sm font-semibold text-gray-900 dark:text-white">
                  解析文本
                </div>
                <pre class="pw-code-block mt-3 max-h-[260px]">{{ currentDocument.parsed_text || '--' }}</pre>
              </div>

              <div class="grid gap-4 lg:grid-cols-2">
                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    结构化数据
                  </div>
                  <div class="mt-3 text-xs text-gray-500 dark:text-dark-300">
                    共 {{ Object.keys(currentDocument.structured_data || {}).length }} 个字段
                  </div>
                  <details class="mt-3 group">
                    <summary class="cursor-pointer text-sm font-medium text-gray-600 marker:text-gray-400 dark:text-dark-300">
                      展开 JSON
                    </summary>
                    <pre class="pw-code-block mt-3 max-h-[260px]">{{ stringifyJson(currentDocument.structured_data) }}</pre>
                  </details>
                </div>

                <div class="pw-panel-lg">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">
                    来源信息
                  </div>
                  <div class="mt-3 text-xs text-gray-500 dark:text-dark-300">
                    共 {{ Object.keys(currentDocument.provenance || {}).length }} 个字段
                  </div>
                  <details class="mt-3 group">
                    <summary class="cursor-pointer text-sm font-medium text-gray-600 marker:text-gray-400 dark:text-dark-300">
                      展开 JSON
                    </summary>
                    <pre class="pw-code-block mt-3 max-h-[260px]">{{ stringifyJson(currentDocument.provenance) }}</pre>
                  </details>
                </div>
              </div>

              <div
                v-if="currentDocument.error"
                class="pw-panel-lg"
              >
                <div class="text-sm font-semibold text-gray-900 dark:text-white">
                  解析错误
                </div>
                <pre class="mt-3 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-2xl bg-rose-50 p-3 text-xs text-rose-700 dark:bg-rose-950/20 dark:text-rose-200">{{ stringifyJson(currentDocument.error) }}</pre>
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
                      {{ currentDocument.batch_id || '当前文档未归属批次' }}
                    </div>
                  </div>
                  <BaseButton
                    variant="secondary"
                    :disabled="!currentDocument.batch_id || batchDetailLoading"
                    @click="loadBatchDetail(currentDocument.batch_id)"
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
                      文档数: {{ batchDetail.batch.documents_count }}
                    </div>
                    <div class="pw-panel-muted px-3 py-3 text-sm">
                      结果数: {{ batchDetail.batch.results_count }}
                    </div>
                    <div class="pw-panel-muted px-3 py-3 text-sm">
                      最近时间: {{ formatDateTime(batchDetail.batch.latest_created_at) }}
                    </div>
                  </div>

                  <div>
                    <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                      同批次其他文档
                    </div>
                    <div class="mt-2 space-y-2">
                      <button
                        v-for="item in sameBatchDocuments"
                        :key="item.id"
                        type="button"
                        class="pw-panel flex w-full items-start justify-between gap-3 px-3 py-3 text-left"
                        @click="selectDocument(item.id)"
                      >
                        <div class="min-w-0">
                          <div class="font-medium text-gray-900 dark:text-white">
                            {{ item.filename }}
                          </div>
                          <div class="mt-1 text-xs text-gray-500 dark:text-dark-300">
                            {{ shortId(item.id) }}
                          </div>
                        </div>
                        <StatusPill :tone="getParseStatusTone(item.parse_status)">
                          {{ item.parse_status }}
                        </StatusPill>
                      </button>
                      <div
                        v-if="sameBatchDocuments.length === 0"
                        class="text-xs text-gray-500 dark:text-dark-300"
                      >
                        当前批次没有其他文档。
                      </div>
                    </div>
                  </div>

                  <div>
                    <div class="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-dark-400">
                      同批次评审结果
                    </div>
                    <div class="mt-2 space-y-2">
                      <div
                        v-for="item in sameBatchResults"
                        :key="item.id"
                        class="pw-panel px-3 py-3 text-sm"
                      >
                        <div class="flex items-start justify-between gap-3">
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
                        </div>
                      </div>
                      <div
                        v-if="sameBatchResults.length === 0"
                        class="text-xs text-gray-500 dark:text-dark-300"
                      >
                        当前批次没有评审结果。
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
              <span class="pw-input-label">文件名</span>
              <input
                v-model="form.filename"
                class="pw-input"
                :disabled="saving"
              >
            </label>

            <label class="block">
              <span class="pw-input-label">content_type</span>
              <input
                v-model="form.content_type"
                class="pw-input"
                :disabled="saving"
              >
            </label>
          </div>

          <div class="grid gap-4 md:grid-cols-4">
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

            <label class="block">
              <span class="pw-input-label">Thread ID</span>
              <input
                v-model="form.thread_id"
                class="pw-input"
                :disabled="saving"
              >
            </label>

            <label class="block">
              <span class="pw-input-label">source_kind</span>
              <input
                v-model="form.source_kind"
                class="pw-input"
                :disabled="saving"
              >
            </label>

            <label class="block">
              <span class="pw-input-label">parse_status</span>
              <BaseSelect
                v-model="form.parse_status"
                :disabled="saving"
              >
                <option
                  v-for="option in PARSE_STATUS_OPTIONS"
                  :key="option"
                  :value="option"
                >
                  {{ option }}
                </option>
              </BaseSelect>
            </label>
          </div>

          <label class="block">
            <span class="pw-input-label">摘要</span>
            <textarea
              v-model="form.summary_for_model"
              rows="4"
              class="pw-input min-h-[120px] resize-y"
              :disabled="saving"
            />
          </label>

          <label class="block">
            <span class="pw-input-label">parsed_text</span>
            <textarea
              v-model="form.parsed_text"
              rows="8"
              class="pw-input min-h-[220px] resize-y"
              :disabled="saving"
            />
          </label>

          <div class="grid gap-4 lg:grid-cols-3">
            <label class="block">
              <span class="pw-input-label">structured_data (JSON object)</span>
              <textarea
                v-model="form.structured_data_text"
                rows="10"
                class="pw-input min-h-[220px] resize-y font-mono text-xs leading-6"
                :disabled="saving"
              />
              <div
                class="mt-2 text-xs"
                :class="structuredDataState.error ? 'text-rose-500' : 'text-gray-400 dark:text-dark-400'"
              >
                {{ structuredDataState.error || 'JSON 校验通过' }}
              </div>
            </label>

            <label class="block">
              <span class="pw-input-label">provenance (JSON object)</span>
              <textarea
                v-model="form.provenance_text"
                rows="10"
                class="pw-input min-h-[220px] resize-y font-mono text-xs leading-6"
                :disabled="saving"
              />
              <div
                class="mt-2 text-xs"
                :class="provenanceState.error ? 'text-rose-500' : 'text-gray-400 dark:text-dark-400'"
              >
                {{ provenanceState.error || 'JSON 校验通过' }}
              </div>
            </label>

            <label class="block">
              <span class="pw-input-label">error (JSON object)</span>
              <textarea
                v-model="form.error_text"
                rows="10"
                class="pw-input min-h-[220px] resize-y font-mono text-xs leading-6"
                :disabled="saving"
              />
              <div
                class="mt-2 text-xs"
                :class="errorState.error ? 'text-rose-500' : 'text-gray-400 dark:text-dark-400'"
              >
                {{ errorState.error || 'JSON 校验通过' }}
              </div>
            </label>
          </div>
        </template>
      </div>

      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <template v-if="dialogMode === 'detail'">
            <BaseButton
              v-if="currentDocument?.id"
              variant="secondary"
              @click="handleCopyDocumentId(currentDocument)"
            >
              复制文档 ID
            </BaseButton>
            <BaseButton
              v-if="currentDocument?.batch_id"
              variant="secondary"
              @click="handleCopyBatchId(currentDocument.batch_id)"
            >
              复制批次 ID
            </BaseButton>
            <BaseButton
              v-if="canWrite && currentDocument"
              variant="secondary"
              @click="openEditDialog(currentDocument)"
            >
              编辑
            </BaseButton>
            <BaseButton
              v-if="canWrite && currentDocument"
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
              @click="closeDetailDialog"
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
      title="删除评审文档"
      :message="`删除 ${currentDocument?.filename || shortId(currentDocument?.id || '')} 后将无法恢复，确认继续吗？`"
      confirm-text="删除"
      danger
      @cancel="showDeleteDialog = false"
      @confirm="handleDelete"
    />
  </section>
</template>
