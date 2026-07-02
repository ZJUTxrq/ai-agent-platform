import { computed, defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  createRequirementReviewResultMock,
  downloadBlobMock,
  exportRequirementReviewResultsByOperationMock,
  getRequirementReviewOverviewMock,
  listRequirementReviewBatchesMock,
  getRequirementReviewRoleMock,
  listRequirementReviewResultsMock,
  getRequirementReviewResultMock,
  getRequirementReviewBatchDetailMock,
  updateRequirementReviewResultMock,
  deleteRequirementReviewResultMock,
  pushToastMock,
} = vi.hoisted(() => ({
  createRequirementReviewResultMock: vi.fn(),
  downloadBlobMock: vi.fn(),
  exportRequirementReviewResultsByOperationMock: vi.fn(),
  getRequirementReviewOverviewMock: vi.fn(),
  listRequirementReviewBatchesMock: vi.fn(),
  getRequirementReviewRoleMock: vi.fn(),
  listRequirementReviewResultsMock: vi.fn(),
  getRequirementReviewResultMock: vi.fn(),
  getRequirementReviewBatchDetailMock: vi.fn(),
  updateRequirementReviewResultMock: vi.fn(),
  deleteRequirementReviewResultMock: vi.fn(),
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
  createRequirementReviewResult: createRequirementReviewResultMock,
  exportRequirementReviewResultsByOperation: exportRequirementReviewResultsByOperationMock,
  getRequirementReviewOverview: getRequirementReviewOverviewMock,
  listRequirementReviewBatches: listRequirementReviewBatchesMock,
  getRequirementReviewRole: getRequirementReviewRoleMock,
  listRequirementReviewResults: listRequirementReviewResultsMock,
  getRequirementReviewResult: getRequirementReviewResultMock,
  getRequirementReviewBatchDetail: getRequirementReviewBatchDetailMock,
  updateRequirementReviewResult: updateRequirementReviewResultMock,
  deleteRequirementReviewResult: deleteRequirementReviewResultMock,
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

import RequirementReviewResultsPage from './RequirementReviewResultsPage.vue'

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
    <div data-test="results-table">
      <div
        v-for="row in rows"
        :key="row.id"
      >
        <slot name="cell-requirement_summary" :row="row" />
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

function createResult(overrides: Record<string, unknown> = {}) {
  return {
    id: 'result-1',
    project_id: 'project-42',
    batch_id: 'batch-1',
    thread_id: 'thread-1',
    idempotency_key: null,
    document_ids: ['doc-1'],
    requirement_summary: 'Requirement summary A',
    review_score: 81,
    quality_gate: 'conditional',
    dimension_scores: { business_objective: 18, testability: 17 },
    key_findings: ['finding 1'],
    major_risks: ['risk 1'],
    missing_or_ambiguous_items: ['gap 1'],
    suggestions_to_improve: ['suggestion 1'],
    generation_policy: 'allow_generation_with_assumptions',
    generation_policy_reason: 'fill the boundary conditions first',
    assumptions: ['assumption 1'],
    raw_result: { ok: true },
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
      items: [
        {
          id: 'doc-1',
          project_id: 'project-42',
          batch_id: 'batch-1',
          thread_id: 'thread-1',
          filename: 'prd.pdf',
          content_type: 'application/pdf',
          source_kind: 'upload',
          parse_status: 'parsed',
          summary_for_model: 'summary',
          parsed_text: 'body',
          structured_data: {},
          provenance: {},
          error: null,
          created_at: '2026-06-20T00:00:00Z',
          updated_at: '2026-06-20T00:00:00Z',
        },
      ],
      total: 1,
    },
    results: {
      items: [createResult()],
      total: 1,
    },
  }
}

function mountPage() {
  return mount(RequirementReviewResultsPage, {
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

describe('RequirementReviewResultsPage', () => {
  beforeEach(() => {
    pushToastMock.mockReset()
    createRequirementReviewResultMock.mockReset()
    exportRequirementReviewResultsByOperationMock.mockReset()
    getRequirementReviewOverviewMock.mockReset()
    listRequirementReviewBatchesMock.mockReset()
    getRequirementReviewRoleMock.mockReset()
    listRequirementReviewResultsMock.mockReset()
    getRequirementReviewResultMock.mockReset()
    getRequirementReviewBatchDetailMock.mockReset()
    updateRequirementReviewResultMock.mockReset()
    deleteRequirementReviewResultMock.mockReset()

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
    listRequirementReviewResultsMock.mockResolvedValue({
      items: [createResult()],
      total: 1,
    })
    getRequirementReviewResultMock.mockResolvedValue(createResult())
    getRequirementReviewBatchDetailMock.mockResolvedValue(createBatchDetail())
    updateRequirementReviewResultMock.mockResolvedValue(
      createResult({
        requirement_summary: 'Updated requirement summary',
      }),
    )
    createRequirementReviewResultMock.mockResolvedValue(
      createResult({
        id: 'result-2',
        requirement_summary: 'Created requirement summary'
      })
    )
    exportRequirementReviewResultsByOperationMock.mockResolvedValue({
      operation: {
        id: 'op-1',
        status: 'succeeded'
      },
      download: {
        blob: new Blob(['xlsx']),
        filename: 'requirement-review-results.xlsx',
        contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      }
    })
    deleteRequirementReviewResultMock.mockResolvedValue(undefined)
  })

  it('supports detail, edit and delete actions', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(listRequirementReviewResultsMock).toHaveBeenCalledWith(
      'project-42',
      expect.objectContaining({
        limit: 20,
        offset: 0,
      }),
    )

    await wrapper.get('[data-test="action-detail"]').trigger('click')
    await flushPromises()

    expect(getRequirementReviewResultMock).toHaveBeenCalledWith('project-42', 'result-1')
    expect(wrapper.get('[data-test="detail-dialog"]').text()).toContain('Requirement summary A')

    await wrapper.get('[data-test="action-edit"]').trigger('click')
    await flushPromises()

    const textareas = wrapper.findAll('textarea')
    expect(textareas.length).toBeGreaterThan(0)
    await textareas[0]!.setValue('Updated requirement summary')

    const dialogButtons = wrapper.get('[data-test="detail-dialog"]').findAll('button')
    await dialogButtons[dialogButtons.length - 1]!.trigger('click')
    await flushPromises()

    expect(updateRequirementReviewResultMock).toHaveBeenCalledWith(
      'project-42',
      'result-1',
      expect.objectContaining({
        requirement_summary: 'Updated requirement summary',
      }),
    )

    await wrapper.get('[data-test="action-delete"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="confirm-dialog"]').exists()).toBe(true)
    await wrapper.get('[data-test="confirm-delete"]').trigger('click')
    await flushPromises()

    expect(deleteRequirementReviewResultMock).toHaveBeenCalledWith('project-42', 'result-1')
  })

  it('supports create and export actions', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const createButton = wrapper
      .findAll('button')
      .find((button) => button.text() === '新增结果')
    expect(createButton).toBeTruthy()
    await createButton!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="detail-dialog"]').exists()).toBe(true)

    const dialog = wrapper.get('[data-test="detail-dialog"]')
    const textareas = dialog.findAll('textarea')
    await textareas[0]!.setValue('Created requirement summary')
    const inputs = dialog.findAll('input')
    await inputs[0]!.setValue('82')

    const saveButton = dialog.findAll('button').find((button) => button.text() === '创建')
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(createRequirementReviewResultMock).toHaveBeenCalledWith(
      'project-42',
      expect.objectContaining({
        requirement_summary: 'Created requirement summary',
        review_score: 82
      })
    )

    const exportButton = wrapper
      .findAll('button')
      .find((button) => button.text() === '导出 Excel')
    expect(exportButton).toBeTruthy()
    await exportButton!.trigger('click')
    await flushPromises()

    expect(exportRequirementReviewResultsByOperationMock).toHaveBeenCalledWith(
      'project-42',
      expect.objectContaining({
        batch_id: undefined,
        quality_gate: undefined,
        query: undefined
      })
    )
    expect(downloadBlobMock).toHaveBeenCalled()
  })
})
