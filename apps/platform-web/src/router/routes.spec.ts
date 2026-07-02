import type { RouteRecordRaw } from 'vue-router'
import { describe, expect, it } from 'vitest'

import { routes } from './routes'

function getWorkspaceChildren(): RouteRecordRaw[] {
  const workspaceRoute = routes.find((route) => route.path === '/workspace')
  return (workspaceRoute?.children ?? []) as RouteRecordRaw[]
}

function getKnowledgeChildren(): RouteRecordRaw[] {
  const knowledgeRoute = getWorkspaceChildren().find(
    (route) => route.path === 'projects/:projectId/knowledge'
  )
  return (knowledgeRoute?.children ?? []) as RouteRecordRaw[]
}

describe('workspace knowledge routes', () => {
  it('redirects the base knowledge route to the documents tab for the active project', () => {
    const knowledgeIndexRoute = getKnowledgeChildren().find((route) => route.name === 'workspace-project-knowledge')

    expect(knowledgeIndexRoute).toBeDefined()
    expect(knowledgeIndexRoute?.path).toBe('')
    expect(knowledgeIndexRoute?.meta).toMatchObject({
      title: '知识库',
      eyebrow: 'Knowledge',
      requiredPermissions: ['project.knowledge.read'],
      permissionProjectSource: 'route'
    })

    const redirect = knowledgeIndexRoute?.redirect as ((to: { params: Record<string, unknown> }) => string)
    expect(redirect({ params: { projectId: '  project-42  ' } })).toBe(
      '/workspace/projects/project-42/knowledge/documents'
    )
  })

  it('registers the expected knowledge child tabs with route-scoped read permission metadata', () => {
    const knowledgeRoutes = getKnowledgeChildren().filter((route) => route.path !== '')

    expect(
      knowledgeRoutes.map((route) => ({
        path: route.path,
        name: route.name,
        title: route.meta?.title
      }))
    ).toEqual([
      {
        path: 'documents',
        name: 'workspace-project-knowledge-documents',
        title: '知识文档'
      },
      {
        path: 'retrieval',
        name: 'workspace-project-knowledge-retrieval',
        title: '知识检索'
      },
      {
        path: 'graph',
        name: 'workspace-project-knowledge-graph',
        title: '知识图谱'
      },
      {
        path: 'settings',
        name: 'workspace-project-knowledge-settings',
        title: '知识设置'
      }
    ])

    for (const route of knowledgeRoutes) {
      expect(route.meta).toMatchObject({
        eyebrow: 'Knowledge',
        requiredPermissions: ['project.knowledge.read'],
        permissionProjectSource: 'route'
      })
    }
  })
})

describe('workspace agent routes', () => {
  it('registers the requirement review entry as a project-scoped runtime graph page', () => {
    const reviewRoute = getWorkspaceChildren().find((route) => route.name === 'workspace-requirement-review')

    expect(reviewRoute).toBeDefined()
    expect(reviewRoute?.path).toBe('requirement-review')
    expect(reviewRoute?.component).toBeDefined()
    expect(reviewRoute?.meta).toMatchObject({
      title: '需求评审',
      eyebrow: 'Requirement Review',
      requiredPermissions: ['project.runtime.read'],
      permissionProjectSource: 'workspace',
      allowWithoutProject: true
    })
  })

  it('registers requirement review result and document pages with project-scoped runtime read permission', () => {
    const children = getWorkspaceChildren()
    const resultsRoute = children.find((route) => route.name === 'workspace-requirement-review-results')
    const documentsRoute = children.find((route) => route.name === 'workspace-requirement-review-documents')

    expect(resultsRoute).toBeDefined()
    expect(resultsRoute?.path).toBe('requirement-review-results')
    expect(resultsRoute?.meta).toMatchObject({
      title: '评审结果',
      eyebrow: 'Requirement Review',
      requiredPermissions: ['project.runtime.read'],
      permissionProjectSource: 'workspace',
      allowWithoutProject: true
    })

    expect(documentsRoute).toBeDefined()
    expect(documentsRoute?.path).toBe('requirement-review-documents')
    expect(documentsRoute?.meta).toMatchObject({
      title: '文档列表',
      eyebrow: 'Requirement Review',
      requiredPermissions: ['project.runtime.read'],
      permissionProjectSource: 'workspace',
      allowWithoutProject: true
    })
  })
})
