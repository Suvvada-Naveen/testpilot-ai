export type TestMode = 'Explore' | 'Test' | 'Full Test'

export type TestStatus = 'Completed' | 'Running' | 'Failed' | 'Pending'

export type ApiTestMode = 'EXPLORE' | 'TEST' | 'FULL_TEST'

export type ApiTestStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'

export interface RecentTest {
  id: string
  domain: string
  title: string
  mode: TestMode
  status: TestStatus
  dateLabel: string
}

export interface TestSession {
  id: string
  url: string
  instruction: string
  mode: ApiTestMode
  status: ApiTestStatus
  created_at: string
  updated_at: string
}

export interface InspectedButton {
  text: string
  aria_label: string
  disabled: boolean
}

export interface InspectedInput {
  type: string
  name: string
  id: string
  placeholder: string
  required: boolean
  aria_label: string
}

export interface InspectedLink {
  text: string
  href: string
}

export interface InspectionResult {
  session_id: string
  status: ApiTestStatus
  page: {
    requested_url: string
    final_url: string
    status_code: number | null
    title: string
  }
  elements: {
    headings: string[]
    buttons: InspectedButton[]
    inputs: InspectedInput[]
    links: InspectedLink[]
    forms: { name: string; action: string; method: string }[]
    checkboxes: { name: string; id: string; checked: boolean; required: boolean }[]
    radio_buttons: { name: string; value: string; checked: boolean }[]
    selects: { name: string; id: string; options: { text: string; value: string }[] }[]
  }
  visible_text: string
  screenshot_id: string
  console_errors: { type: string; text: string }[]
  console_messages: { type: string; text: string }[]
  network_errors: { url: string; method: string; failure: string }[]
  error?: string | null
}

export type TestCaseType = 'positive' | 'negative' | 'validation' | 'boundary' | 'navigation' | 'ui' | 'security' | 'other'
export type TestPriority = 'critical' | 'high' | 'medium' | 'low'

export interface PlannedTestCase {
  id: string
  title: string
  type: TestCaseType
  priority: TestPriority
  description: string
  preconditions: string[]
  steps: string[]
  expected_result: string
  target_elements: string[]
  requires_credentials: boolean
}

export interface TestPlan {
  summary: string
  test_cases: PlannedTestCase[]
  warnings: string[]
}

export type ExecutionStatus = 'PENDING' | 'RUNNING' | 'PASSED' | 'FAILED' | 'BLOCKED'
export type ActionExecutionStatus = 'SUCCESS' | 'FAILED'

export interface ExecutedAction {
  step: number
  action: 'navigate' | 'click' | 'fill' | 'select' | 'check' | 'uncheck' | 'press' | 'scroll' | 'wait' | 'read_page' | 'take_screenshot'
  target: string | null
  status: ActionExecutionStatus
  duration_ms: number
  error: string | null
}

export interface TestExecutionResult {
  id: string
  session_id: string
  test_case_id: string
  status: ExecutionStatus
  started_at: string | null
  completed_at: string | null
  duration: number
  actions: ExecutedAction[]
  expected_result: string
  actual_result: string
  failure_reason: string | null
  screenshot_id: string | null
  console_errors: { type: string; text: string }[]
  network_errors: { url: string; method: string; failure: string }[]
}

export interface ExecutionBatchResult {
  session_id: string
  status: string
  total: number
  execution_ids: string[]
  executions: TestExecutionResult[]
}

export interface ValidationErrors {
  url?: string
  instruction?: string
  submit?: string
}