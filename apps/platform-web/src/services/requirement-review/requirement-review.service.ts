import { platformHttpClient } from '@/services/http/client'
import {
  downloadOperationArtifact,
  submitOperation,
  waitForOperationTerminalState
} from '@/services/operations/operations.service'
import type { ChatAttachmentBlock } from '@/utils/chat-content'
import type {
  ManagementDownload,
  ManagementOperation,
  RequirementFeatureList,
  RequirementReviewBatchDetail,
  RequirementReviewBatchSummary,
  RequirementReviewDocument,
  RequirementReviewOverview,
  RequirementReviewRole,
  RequirementReviewResult
} from '@/types/management'

type BatchListResponse = {
  items: RequirementReviewBatchSummary[]
  total: number
}

type DocumentListResponse = {
  items: RequirementReviewDocument[]
  total: number
}

type ResultListResponse = {
  items: RequirementReviewResult[]
  total: number
}

export type UpsertRequirementReviewDocumentPayload = {
  batch_id?: string | null
  thread_id?: string | null
  filename?: string
  content_type?: string
  source_kind?: string
  parse_status?: string
  summary_for_model?: string
  parsed_text?: string | null
  structured_data?: Record<string, unknown> | null
  provenance?: Record<string, unknown> | null
  error?: Record<string, unknown> | null
}

export type UpsertRequirementReviewResultPayload = {
  batch_id?: string | null
  thread_id?: string | null
  document_ids?: string[] | null
  requirement_summary?: string
  review_score?: number | null
  quality_gate?: string
  dimension_scores?: Record<string, unknown> | null
  key_findings?: string[] | null
  major_risks?: string[] | null
  missing_or_ambiguous_items?: string[] | null
  suggestions_to_improve?: string[] | null
  generation_policy?: string
  generation_policy_reason?: string
  assumptions?: string[] | null
  raw_result?: Record<string, unknown> | null
}

function buildHeaders(projectId: string) {
  return {
    'x-project-id': projectId
  }
}

function resolveEndpoint(projectId: string, suffix: string) {
  const normalizedSuffix = suffix.startsWith('/') ? suffix : `/${suffix}`
  return {
    client: platformHttpClient,
    path: `/api/projects/${projectId}/requirement-review${normalizedSuffix}`
  }
}

function parseContentDispositionFilename(header: string | null): string | null {
  if (!header) {
    return null
  }
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }
  const plainMatch = header.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1] ?? null
}

async function downloadFrom(
  projectId: string,
  suffix: string,
  params?: Record<string, string | number | undefined>
): Promise<ManagementDownload> {
  const { client, path } = resolveEndpoint(projectId, suffix)
  const response = await client.get(path, {
    headers: buildHeaders(projectId),
    responseType: 'blob',
    params
  })
  return {
    blob: response.data as Blob,
    filename: parseContentDispositionFilename(String(response.headers['content-disposition'] || '')),
    contentType: String(response.headers['content-type'] || '')
  }
}

export async function getRequirementReviewOverview(
  projectId: string
): Promise<RequirementReviewOverview> {
  const { client, path } = resolveEndpoint(projectId, '/overview')
  const response = await client.get(path, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementReviewOverview
}

export async function getRequirementReviewRole(
  projectId: string
): Promise<RequirementReviewRole> {
  const { client, path } = resolveEndpoint(projectId, '/role')
  const response = await client.get(path, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementReviewRole
}

export async function listRequirementReviewBatches(
  projectId: string,
  options?: { limit?: number; offset?: number }
): Promise<BatchListResponse> {
  const { client, path } = resolveEndpoint(projectId, '/batches')
  const response = await client.get(path, {
    headers: buildHeaders(projectId),
    params: {
      limit: options?.limit ?? 50,
      offset: options?.offset ?? 0
    }
  })
  return response.data as BatchListResponse
}

export async function getRequirementReviewBatchDetail(
  projectId: string,
  batchId: string,
  options?: {
    document_limit?: number
    document_offset?: number
    result_limit?: number
    result_offset?: number
  }
): Promise<RequirementReviewBatchDetail> {
  const { client, path } = resolveEndpoint(projectId, `/batches/${batchId}`)
  const response = await client.get(path, {
    headers: buildHeaders(projectId),
    params: {
      document_limit: options?.document_limit ?? 100,
      document_offset: options?.document_offset ?? 0,
      result_limit: options?.result_limit ?? 50,
      result_offset: options?.result_offset ?? 0
    }
  })
  return response.data as RequirementReviewBatchDetail
}

export async function listRequirementReviewDocuments(
  projectId: string,
  options?: {
    batch_id?: string
    parse_status?: string
    query?: string
    limit?: number
    offset?: number
  }
): Promise<DocumentListResponse> {
  const { client, path } = resolveEndpoint(projectId, '/documents')
  const response = await client.get(path, {
    headers: buildHeaders(projectId),
    params: {
      limit: options?.limit ?? 20,
      offset: options?.offset ?? 0,
      batch_id: options?.batch_id?.trim() || undefined,
      parse_status: options?.parse_status?.trim() || undefined,
      query: options?.query?.trim() || undefined
    }
  })
  return response.data as DocumentListResponse
}

export async function getRequirementReviewDocument(
  projectId: string,
  documentId: string
): Promise<RequirementReviewDocument> {
  const { client, path } = resolveEndpoint(projectId, `/documents/${documentId}`)
  const response = await client.get(path, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementReviewDocument
}

export async function previewRequirementReviewDocument(
  projectId: string,
  documentId: string
): Promise<ManagementDownload> {
  return downloadFrom(projectId, `/documents/${documentId}/preview`)
}

export async function downloadRequirementReviewDocument(
  projectId: string,
  documentId: string
): Promise<ManagementDownload> {
  return downloadFrom(projectId, `/documents/${documentId}/download`)
}

export async function exportRequirementReviewDocuments(
  projectId: string,
  options?: {
    batch_id?: string
    parse_status?: string
    query?: string
  }
): Promise<ManagementDownload> {
  return downloadFrom(projectId, '/documents/export', {
    batch_id: options?.batch_id?.trim() || undefined,
    parse_status: options?.parse_status?.trim() || undefined,
    query: options?.query?.trim() || undefined
  })
}

export async function exportRequirementReviewDocumentsByOperation(
  projectId: string,
  options?: {
    batch_id?: string
    parse_status?: string
    query?: string
    idempotencyKey?: string
  }
): Promise<{
  operation: ManagementOperation
  download: ManagementDownload
}> {
  const submitted = await submitOperation({
    kind: 'requirement-review.documents.export',
    project_id: projectId,
    idempotency_key: options?.idempotencyKey,
    input_payload: {
      batch_id: options?.batch_id?.trim() || undefined,
      parse_status: options?.parse_status?.trim() || undefined,
      query: options?.query?.trim() || undefined
    }
  })
  const operation = await waitForOperationTerminalState(submitted.id, {
    pollMs: 1000,
    timeoutMs: 120000
  })
  const download = await downloadOperationArtifact(operation.id)
  return {
    operation,
    download
  }
}

export async function createRequirementReviewDocument(
  projectId: string,
  payload: Required<Pick<UpsertRequirementReviewDocumentPayload, 'filename' | 'content_type'>> &
    UpsertRequirementReviewDocumentPayload
): Promise<RequirementReviewDocument> {
  const { client, path } = resolveEndpoint(projectId, '/documents')
  const response = await client.post(path, payload, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementReviewDocument
}

export async function updateRequirementReviewDocument(
  projectId: string,
  documentId: string,
  payload: UpsertRequirementReviewDocumentPayload
): Promise<RequirementReviewDocument> {
  const { client, path } = resolveEndpoint(projectId, `/documents/${documentId}`)
  const response = await client.patch(path, payload, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementReviewDocument
}

export async function deleteRequirementReviewDocument(
  projectId: string,
  documentId: string
): Promise<void> {
  const { client, path } = resolveEndpoint(projectId, `/documents/${documentId}`)
  await client.delete(path, {
    headers: buildHeaders(projectId)
  })
}

export async function listRequirementReviewResults(
  projectId: string,
  options?: {
    batch_id?: string
    quality_gate?: string
    generation_policy?: string
    query?: string
    limit?: number
    offset?: number
  }
): Promise<ResultListResponse> {
  const { client, path } = resolveEndpoint(projectId, '/results')
  const response = await client.get(path, {
    headers: buildHeaders(projectId),
    params: {
      limit: options?.limit ?? 20,
      offset: options?.offset ?? 0,
      batch_id: options?.batch_id?.trim() || undefined,
      quality_gate: options?.quality_gate?.trim() || undefined,
      generation_policy: options?.generation_policy?.trim() || undefined,
      query: options?.query?.trim() || undefined
    }
  })
  return response.data as ResultListResponse
}

export async function getRequirementReviewResult(
  projectId: string,
  resultId: string
): Promise<RequirementReviewResult> {
  const { client, path } = resolveEndpoint(projectId, `/results/${resultId}`)
  const response = await client.get(path, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementReviewResult
}

export async function exportRequirementReviewResults(
  projectId: string,
  options?: {
    batch_id?: string
    quality_gate?: string
    generation_policy?: string
    query?: string
  }
): Promise<ManagementDownload> {
  return downloadFrom(projectId, '/results/export', {
    batch_id: options?.batch_id?.trim() || undefined,
    quality_gate: options?.quality_gate?.trim() || undefined,
    generation_policy: options?.generation_policy?.trim() || undefined,
    query: options?.query?.trim() || undefined
  })
}

export async function exportRequirementReviewResultsByOperation(
  projectId: string,
  options?: {
    batch_id?: string
    quality_gate?: string
    generation_policy?: string
    query?: string
    idempotencyKey?: string
  }
): Promise<{
  operation: ManagementOperation
  download: ManagementDownload
}> {
  const submitted = await submitOperation({
    kind: 'requirement-review.results.export',
    project_id: projectId,
    idempotency_key: options?.idempotencyKey,
    input_payload: {
      batch_id: options?.batch_id?.trim() || undefined,
      quality_gate: options?.quality_gate?.trim() || undefined,
      generation_policy: options?.generation_policy?.trim() || undefined,
      query: options?.query?.trim() || undefined
    }
  })
  const operation = await waitForOperationTerminalState(submitted.id, {
    pollMs: 1000,
    timeoutMs: 120000
  })
  const download = await downloadOperationArtifact(operation.id)
  return {
    operation,
    download
  }
}

export async function createRequirementReviewResult(
  projectId: string,
  payload: Required<Pick<UpsertRequirementReviewResultPayload, 'generation_policy'>> &
    UpsertRequirementReviewResultPayload
): Promise<RequirementReviewResult> {
  const { client, path } = resolveEndpoint(projectId, '/results')
  const response = await client.post(path, payload, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementReviewResult
}

export async function updateRequirementReviewResult(
  projectId: string,
  resultId: string,
  payload: UpsertRequirementReviewResultPayload
): Promise<RequirementReviewResult> {
  const { client, path } = resolveEndpoint(projectId, `/results/${resultId}`)
  const response = await client.patch(path, payload, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementReviewResult
}

export async function deleteRequirementReviewResult(
  projectId: string,
  resultId: string
): Promise<void> {
  const { client, path } = resolveEndpoint(projectId, `/results/${resultId}`)
  await client.delete(path, {
    headers: buildHeaders(projectId)
  })
}

type FeatureListListResponse = {
  items: RequirementFeatureList[]
  total: number
}

export async function listRequirementFeatureLists(
  projectId: string,
  options?: {
    batch_id?: string
    status?: string
    query?: string
    limit?: number
    offset?: number
  }
): Promise<FeatureListListResponse> {
  const { client, path } = resolveEndpoint(projectId, '/feature-lists')
  const response = await client.get(path, {
    headers: buildHeaders(projectId),
    params: {
      limit: options?.limit ?? 20,
      offset: options?.offset ?? 0,
      batch_id: options?.batch_id?.trim() || undefined,
      status: options?.status?.trim() || undefined,
      query: options?.query?.trim() || undefined
    }
  })
  return response.data as FeatureListListResponse
}

export async function getRequirementFeatureList(
  projectId: string,
  featureListId: string
): Promise<RequirementFeatureList> {
  const { client, path } = resolveEndpoint(projectId, `/feature-lists/${featureListId}`)
  const response = await client.get(path, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementFeatureList
}

export type UpdateRequirementFeatureListPayload = {
  requirement_text?: string
  requirement_summary?: string
  modules?: Record<string, unknown>[]
  open_questions?: string[]
  assumptions?: string[]
}

export async function updateRequirementFeatureList(
  projectId: string,
  featureListId: string,
  payload: UpdateRequirementFeatureListPayload
): Promise<RequirementFeatureList> {
  const { client, path } = resolveEndpoint(projectId, `/feature-lists/${featureListId}`)
  const response = await client.patch(path, payload, {
    headers: buildHeaders(projectId)
  })
  return response.data as RequirementFeatureList
}

export async function confirmRequirementFeatureList(
  projectId: string,
  featureListId: string,
  options?: { expected_version?: number }
): Promise<RequirementFeatureList> {
  const { client, path } = resolveEndpoint(
    projectId,
    `/feature-lists/${featureListId}/confirm`
  )
  const response = await client.post(
    path,
    { expected_version: options?.expected_version },
    { headers: buildHeaders(projectId) }
  )
  return response.data as RequirementFeatureList
}

export async function deleteRequirementFeatureList(
  projectId: string,
  featureListId: string
): Promise<void> {
  const { client, path } = resolveEndpoint(projectId, `/feature-lists/${featureListId}`)
  await client.delete(path, {
    headers: buildHeaders(projectId)
  })
}

export async function decomposeRequirementByOperation(
  projectId: string,
  options: {
    requirement_text?: string
    attachments?: ChatAttachmentBlock[]
    batch_id?: string
    idempotencyKey?: string
  }
): Promise<ManagementOperation> {
  const submitted = await submitOperation({
    kind: 'requirement.feature_list.decompose',
    project_id: projectId,
    idempotency_key: options.idempotencyKey,
    input_payload: {
      requirement_text: options.requirement_text?.trim() || undefined,
      attachments: options.attachments?.length ? options.attachments : undefined,
      batch_id: options.batch_id?.trim() || undefined
    }
  })
  return waitForOperationTerminalState(submitted.id, {
    pollMs: 2000,
    timeoutMs: 300000
  })
}

export async function reviewAndGenerateByOperation(
  projectId: string,
  options: {
    feature_list_id?: string
    requirement_text?: string
    idempotencyKey?: string
  }
): Promise<ManagementOperation> {
  const submitted = await submitOperation({
    kind: 'testcase.review_and_generate',
    project_id: projectId,
    idempotency_key: options.idempotencyKey,
    input_payload: {
      feature_list_id: options.feature_list_id || undefined,
      requirement_text: options.requirement_text?.trim() || undefined
    }
  })
  return waitForOperationTerminalState(submitted.id, {
    pollMs: 2000,
    timeoutMs: 600000
  })
}
