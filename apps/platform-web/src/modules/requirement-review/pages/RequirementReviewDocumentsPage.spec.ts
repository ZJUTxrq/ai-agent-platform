import { computed, defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  createRequirementReviewDocumentMock,
  downloadBlobMock,
  exportRequirementReviewDocumentsByOperationMock,
  getRequirementReviewOverviewMock,
  listRequirementReviewBatchesMock,
  getRequirementReviewRoleMock,
  listRequirementReviewDocumentsMock,
  getRequirementReviewDocumentMock,
  getRequirementReviewBatchDetailMock,
  updateRequirementReviewDocumentMock,
  deleteRequirementReviewDocumentMock,
  pushToastMock,
} = vi.hoisted(() => ({
  createRequirementReviewDocumentMock: vi.fn(),
  downloadBlobMock: vi.fn(),
  exportRequirementReviewDocumentsByOperationMock: vi.fn(),
  getRequirementReviewOverviewMock: vi.fn(),
  listRequirementReviewBatchesMock: vi.fn(),
  getRequirementReviewRoleMock: vi.fn(),
  listRequirementReviewDocumentsMock: vi.fn(),
  getRequirementReviewDocumentMock: vi.fn(),
  getRequirementReviewBatchDetailMock: vi.fn(),
  updateRequirementReviewDocumentMock: vi.fn(),
  deleteRequirementReviewDocumentMock: vi.fn(),
  pushToastMock: vi.fn(),
}))

vi.mock('@/composables/useWorkspaceProjectContext', () => ({
  useWorkspaceProjectContext: () => ({
    activeProjectId: ref('project-42'),
    activeProject: computed(() => ({
      id: 'project-42',
      name: 'Project 42',
    })),
  }),
}))

vi.mock('@/stores/ui', () => ({
  useUiStore: () => ({
    pushToast: pushToastMock,
  }),
}))

vi.mock('@/services/requirement-review/requirement-review.service', () => ({
  createRequirementReviewDocument: createRequirementReviewDocumentMock,
  exportRequirementReviewDocumentsByOperation: exportRequirementReviewDocumentsByOperationMock,
  getRequirementReviewOverview: getRequirementReviewOverviewMock,
  listRequirementReviewBatches: listRequirementReviewBatchesMock,
  getRequirementReviewRole: getRequirementReviewRoleMock,
  listRequirementReviewDocuments: listRequirementReviewDocumentsMock,
  getRequirementReviewDocument: getRequirementReviewDocumentMock,
  getRequirementReviewBatchDetail: getRequirementReviewBatchDetailMock,
  updateRequirementReviewDocument: updateRequirementReviewDocumentMock,
  deleteRequirementReviewDocument: deleteRequirementReviewDocumentMock,
}))

vi.mock('@/services/operations/operations.service', () => ({
  getOperationFailureMessage: vi.fn(() => 'operation failed')
}))

vi.mock('@/utils/browser-download', () => ({
  downloadBlob: downloadBlobMock
}))

vi.mock('@/utils/clipboard', () => ({
  copyText: vi.fn().mockResolvedValue(true),
}))

vi.mock('@/utils/format', () => ({
  formatDateTime: (value: string | null | undefined) => value || '--',
  shortId: (value: string | null | undefined) => String(value || '').slice(0, 8),
}))

import RequirementReviewDocumentsPage from './RequirementReviewDocumentsPage.vue'

const ActionMenuStub = defineComponent({
  name: 'ActionMenuStub',
  props: {
    items: {
      type: Array,
      default: () => [],
    },
  },
  template: `
    <div>
      <button
        v-for="item in items"
        :key="item.key"
        :data-test="'action-' + item.key"
        :disabled="item.disabled"
        @click="item.onSelect()"
      >
        {{ item.label }}
      </button>
    </div>
  `,
})

const DataTableStub = defineComponent({
  name: 'DataTableStub',
  props: {
    rows: {
      type: Array,
      default: () => [],
    },
  },
  template: `
    <div data-test="documents-table">
      <div
        v-for="row in rows"
        :key="row.id"
      >
        <slot name="cell-filename" :row="row" />
        <slot name="cell-actions" :row="row" />
      </div>
    </div>
  `,
})

const BaseDialogStub = defineComponent({
  name: 'BaseDialogStub',
  props: {
    show: {
      type: Boolean,
      default: false,
    },
    title: {
      type: String,
      default: '',
    },
  },
  template: `
    <div
      v-if="show"
      data-test="detail-dialog"
    >
      <div data-test="dialog-title">{{ title }}</div>
      <slot />
      <slot name="footer" />
    </div>
  `,
})

const ConfirmDialogStub = defineComponent({
  name: 'ConfirmDialogStub',
  props: {
    show: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['cancel', 'confirm'],
  template: `
    <div
      v-if="show"
      data-test="confirm-dialog"
    >
      <button
        data-test="confirm-delete"
        @click="$emit('confirm')"
      >
        confirm
      </button>
    </div>
  `,
})

function createDocument(overrides: Record<string, unknown> = {}) {
  return {
    id: 'doc-1',
    project_id: 'project-42',
    batch_id: 'batch-1',
    thread_id: 'thread-1',
    filename: 'prd.pdf',
    content_type: 'application/pdf',
    source_kind: 'upload',
    parse_status: 'parsed',
    summary_for_model: 'document summary',
    parsed_text: 'document body',
    structured_data: { feature: 'coupon' },
    provenance: { source: 'upload' },
    error: null,
    created_at: '2026-06-20T00:00:00Z',
    updated_at: '2026-06-20T00:00:00Z',
    ...overrides,
  }
}

function createBatchDetail() {
  return {
    batch: {
      batch_id: 'batch-1',
      documents_count: 1,
      results_count: 1,
      latest_created_at: '2026-06-20T00:00:00Z',
      parse_status_summary: { parsed: 1 },
      quality_gate_summary: { conditional: 1 },
    },
    documents: {
      items: [createDocument()],
      total: 1,
    },
    results: {
      items: [
        {
          id: 'result-1',
          project_id: 'project-42',
          batch_id: 'batch-1',
          thread_id: 'thread-1',
          document_ids: ['doc-1'],
          requirement_summary: 'Requirement summary A',
          review_score: 81,
          quality_gate: 'conditional',
          dimension_scores: {},
          key_findings: [],
          major_risks: [],
          missing_or_ambiguous_items: [],
          suggestions_to_improve: [],
          generation_policy: 'allow_generation_with_assumptions',
          generation_policy_reason: '',
          assumptions: [],
          raw_result: {},
          created_at: '2026-06-20T00:00:00Z',
          updated_at: '2026-06-20T00:00:00Z',
        },
      ],
      total: 1,
    },
  }
}

function mountPage() {
  return mount(RequirementReviewDocumentsPage, {
    global: {
      stubs: {
        BaseButton: { template: '<button @click="$emit(\'click\')"><slot /></button>' },
        BaseDialog: BaseDialogStub,
        BaseSelect: {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template:
            '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
        },
        ConfirmDialog: ConfirmDialogStub,
        SurfaceCard: { template: '<section><slot /></section>' },
        PageHeader: {
          props: ['eyebrow', 'title', 'description'],
          template: '<header><h1>{{ title }}</h1><slot name="actions" /></header>',
        },
        ActionMenu: ActionMenuStub,
        DataTable: DataTableStub,
        EmptyState: { template: '<div data-test="empty-state" />' },
        FilterSettingsMenu: { template: '<div />' },
        FilterToolbar: { template: '<div><slot /></div>' },
        PaginationBar: { template: '<div data-test="pagination" />' },
        RequirementReviewOverviewStrip: { template: '<div data-test="overview" />' },
        RequirementReviewWorkspaceNav: { template: '<nav />' },
        SearchInput: { template: '<input />' },
        StateBanner: { props: ['title', 'description'], template: '<div>{{ title }}{{ description }}</div>' },
        StatusPill: { template: '<span><slot /></span>' },
      },
    },
  })
}

describe('RequirementReviewDocumentsPage', () => {
  beforeEach(() => {
    pushToastMock.mockReset()
    createRequirementReviewDocumentMock.mockReset()
    exportRequirementReviewDocumentsByOperationMock.mockReset()
    getRequirementReviewOverviewMock.mockReset()
    listRequirementReviewBatchesMock.mockReset()
    getRequirementReviewRoleMock.mockReset()
    listRequirementReviewDocumentsMock.mockReset()
    getRequirementReviewDocumentMock.mockReset()
    getRequirementReviewBatchDetailMock.mockReset()
    updateRequirementReviewDocumentMock.mockReset()
    deleteRequirementReviewDocumentMock.mockReset()

    getRequirementReviewOverviewMock.mockResolvedValue({
      project_id: 'project-42',
      documents_total: 1,
      parsed_documents_total: 1,
      failed_documents_total: 0,
      results_total: 1,
      pass_results_total: 0,
      conditional_results_total: 1,
      fail_results_total: 0,
      latest_batch_id: 'batch-1',
      latest_activity_at: '2026-06-20T00:00:00Z',
    })
    listRequirementReviewBatchesMock.mockResolvedValue({
      items: [
        {
          batch_id: 'batch-1',
          documents_count: 1,
          results_count: 1,
          latest_created_at: '2026-06-20T00:00:00Z',
          parse_status_summary: { parsed: 1 },
          quality_gate_summary: { conditional: 1 },
        },
      ],
      total: 1,
    })
    getRequirementReviewRoleMock.mockResolvedValue({
      project_id: 'project-42',
      role: 'editor',
      can_write_requirement_review: true,
    })
    listRequirementReviewDocumentsMock.mockResolvedValue({
      items: [createDocument()],
      total: 1,
    })
    getRequirementReviewDocumentMock.mockResolvedValue(createDocument())
    getRequirementReviewBatchDetailMock.mockResolvedValue(createBatchDetail())
    updateRequirementReviewDocumentMock.mockResolvedValue(
      createDocument({
        filename: 'prd-updated.pdf',
      }),
    )
    createRequirementReviewDocumentMock.mockResolvedValue(
      createDocument({
        id: 'doc-2',
        filename: 'new-prd.pdf'
      })
    )
    exportRequirementReviewDocumentsByOperationMock.mockResolvedValue({
      operation: {
        id: 'op-1',
        status: 'succeeded'
      },
      download: {
        blob: new Blob(['xlsx']),
        filename: 'requirement-review-documents.xlsx',
        contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      }
    })
    deleteRequirementReviewDocumentMock.mockResolvedValue(undefined)
  })

  it('supports document detail, edit and delete actions', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(listRequirementReviewDocumentsMock).toHaveBeenCalledWith(
      'project-42',
      expect.objectContaining({
        limit: 20,
        offset: 0,
      }),
    )

    await wrapper.get('[data-test="action-detail"]').trigger('click')
    await flushPromises()

    expect(getRequirementReviewDocumentMock).toHaveBeenCalledWith('project-42', 'doc-1')
    expect(wrapper.get('[data-test="detail-dialog"]').text()).toContain('prd.pdf')

    await wrapper.get('[data-test="action-edit"]').trigger('click')
    await flushPromises()

    const inputs = wrapper.get('[data-test="detail-dialog"]').findAll('input')
    expect(inputs.length).toBeGreaterThan(0)
    await inputs[0]!.setValue('prd-updated.pdf')

    const dialogButtons = wrapper.get('[data-test="detail-dialog"]').findAll('button')
    await dialogButtons[dialogButtons.length - 1]!.trigger('click')
    await flushPromises()

    expect(updateRequirementReviewDocumentMock).toHaveBeenCalledWith(
      'project-42',
      'doc-1',
      expect.objectContaining({
        filename: 'prd-updated.pdf',
      }),
    )

    await wrapper.get('[data-test="action-delete"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="confirm-dialog"]').exists()).toBe(true)
    await wrapper.get('[data-test="confirm-delete"]').trigger('click')
    await flushPromises()

    expect(deleteRequirementReviewDocumentMock).toHaveBeenCalledWith('project-42', 'doc-1')
  })

  it('supports document create and export actions', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const createButton = wrapper
      .findAll('button')
      .find((button) => button.text() === '新增文档')
    expect(createButton).toBeTruthy()
    await createButton!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="detail-dialog"]').exists()).toBe(true)

    const dialog = wrapper.get('[data-test="detail-dialog"]')
    const inputs = dialog.findAll('input')
    await inputs[0]!.setValue('new-prd.pdf')
    await inputs[1]!.setValue('application/pdf')

    const saveButton = dialog.findAll('button').find((button) => button.text() === '创建')
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(createRequirementReviewDocumentMock).toHaveBeenCalledWith(
      'project-42',
      expect.objectContaining({
        filename: 'new-prd.pdf',
        content_type: 'application/pdf'
      })
    )

    const exportButton = wrapper
      .findAll('button')
      .find((button) => button.text() === '导出 Excel')
    expect(exportButton).toBeTruthy()
    await exportButton!.trigger('click')
    await flushPromises()

    expect(exportRequirementReviewDocumentsByOperationMock).toHaveBeenCalledWith(
      'project-42',
      expect.objectContaining({
        batch_id: undefined,
        parse_status: undefined,
        query: undefined
      })
    )
    expect(downloadBlobMock).toHaveBeenCalled()
  })
})
