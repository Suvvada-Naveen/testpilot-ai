import type { ApiTestMode, ApiTestStatus, ExecutionBatchResult, InspectionResult, RecentTest, TestExecutionResult, TestPlan, TestSession, TestStatus } from '../types/test'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api').replace(/\/$/, '')

export interface CreateTestSessionInput {
  url: string
  instruction: string
  mode: ApiTestMode
}

export class ApiRequestError extends Error {
  readonly kind: 'network' | 'http'

  constructor(message: string, kind: 'network' | 'http') {
    super(message)
    this.name = 'ApiRequestError'
    this.kind = kind
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, options)
  } catch {
    throw new ApiRequestError(
      'Unable to reach the backend. Check that it is running and try again.',
      'network',
    )
  }

  if (!response.ok) {
    if (response.status >= 500) {
      throw new ApiRequestError('Unable to complete the request. Please try again.', 'http')
    }

    let message = 'The request was rejected. Please check the session details.'
    const body: unknown = await response.json().catch(() => null)
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      if (typeof body.detail === 'string') {
        message = body.detail
      } else if (Array.isArray(body.detail)) {
        const messages = body.detail.flatMap((issue: unknown) => {
          if (typeof issue === 'object' && issue !== null && 'msg' in issue && typeof issue.msg === 'string') {
            return [issue.msg]
          }
          return []
        })
        if (messages.length > 0) message = messages.join(' ')
      }
    }
    throw new ApiRequestError(message, 'http')
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function createTestSession(input: CreateTestSessionInput): Promise<TestSession> {
  return request<TestSession>('/test-sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function getTestSessions(): Promise<TestSession[]> {
  return request<TestSession[]>('/test-sessions')
}

export function getTestSession(id: string): Promise<TestSession> {
  return request<TestSession>(`/test-sessions/${encodeURIComponent(id)}`)
}

export function deleteTestSession(id: string): Promise<void> {
  return request<void>(`/test-sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function inspectTestSession(id: string): Promise<InspectionResult> {
  return request<InspectionResult>(`/test-sessions/${encodeURIComponent(id)}/inspect`, { method: 'POST' })
}

export function getTestSessionInspection(id: string): Promise<InspectionResult> {
  return request<InspectionResult>(`/test-sessions/${encodeURIComponent(id)}/inspection`)
}

export function generateTestPlan(id: string): Promise<TestPlan> {
  return request<TestPlan>(`/test-sessions/${encodeURIComponent(id)}/generate-tests`, { method: 'POST' })
}

export function getTestPlan(id: string): Promise<TestPlan> {
  return request<TestPlan>(`/test-sessions/${encodeURIComponent(id)}/test-plan`)
}

export function executeTestCases(
  sessionId: string,
  testCaseIds: string[],
  confirmDestructive: boolean,
): Promise<ExecutionBatchResult> {
  return request<ExecutionBatchResult>(`/test-sessions/${encodeURIComponent(sessionId)}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ test_case_ids: testCaseIds, confirm_destructive: confirmDestructive }),
  })
}

export function getSessionExecutions(sessionId: string): Promise<TestExecutionResult[]> {
  return request<TestExecutionResult[]>(`/test-sessions/${encodeURIComponent(sessionId)}/executions`)
}

export function getExecution(sessionId: string, executionId: string): Promise<TestExecutionResult> {
  return request<TestExecutionResult>(`/test-sessions/${encodeURIComponent(sessionId)}/executions/${encodeURIComponent(executionId)}`)
}

export function getExecutionScreenshotUrl(sessionId: string, executionId: string): string {
  return `${API_BASE_URL}/test-sessions/${encodeURIComponent(sessionId)}/executions/${encodeURIComponent(executionId)}/screenshot`
}

export function getInspectionScreenshotUrl(id: string): string {
  return `${API_BASE_URL}/test-sessions/${encodeURIComponent(id)}/inspection/screenshot`
}

const modeLabels: Record<ApiTestMode, RecentTest['mode']> = {
  EXPLORE: 'Explore',
  TEST: 'Test',
  FULL_TEST: 'Full Test',
}

const statusLabels: Record<ApiTestStatus, TestStatus> = {
  PENDING: 'Pending',
  RUNNING: 'Running',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
}

export function toRecentTest(session: TestSession): RecentTest {
  const domain = new URL(session.url).hostname.replace(/^www\./, '')

  const createdAt = new Date(session.created_at)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  const sameDay = (left: Date, right: Date) => left.toDateString() === right.toDateString()
  const dateLabel = sameDay(createdAt, today)
    ? 'Today'
    : sameDay(createdAt, yesterday)
      ? 'Yesterday'
      : createdAt.toLocaleDateString('en', { month: 'short', day: 'numeric' })

  return {
    id: session.id,
    domain,
    title: session.instruction,
    mode: modeLabels[session.mode],
    status: statusLabels[session.status],
    dateLabel,
  }
}

export function toModeLabel(mode: ApiTestMode): RecentTest['mode'] {
  return modeLabels[mode]
}

export function toStatusLabel(status: ApiTestStatus): TestStatus {
  return statusLabels[status]
}