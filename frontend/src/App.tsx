import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import Dashboard from './pages/Dashboard'
import { ApiRequestError, createTestSession, executeTestCases, generateTestPlan, getSessionExecutions, getTestSessions, inspectTestSession, toRecentTest } from './services/testSessionApi'
import type { ApiTestMode, InspectionResult, RecentTest, TestExecutionResult, TestMode, TestPlan, TestSession, ValidationErrors } from './types/test'

const modeValues: Record<TestMode, ApiTestMode> = {
  Explore: 'EXPLORE',
  Test: 'TEST',
  'Full Test': 'FULL_TEST',
}
const executionBatchSize = 10

function App() {
  const [url, setUrl] = useState('')
  const [instruction, setInstruction] = useState('')
  const [testMode, setTestMode] = useState<TestMode>('Explore')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [validationErrors, setValidationErrors] = useState<ValidationErrors>({})
  const [sessionCreated, setSessionCreated] = useState<TestSession | null>(null)
  const [inspectionResult, setInspectionResult] = useState<InspectionResult | null>(null)
  const [isInspecting, setIsInspecting] = useState(false)
  const [inspectionStage, setInspectionStage] = useState<string | null>(null)
  const [inspectionError, setInspectionError] = useState<string | null>(null)
  const [testPlan, setTestPlan] = useState<TestPlan | null>(null)
  const [isGeneratingTestPlan, setIsGeneratingTestPlan] = useState(false)
  const [testPlanStage, setTestPlanStage] = useState<string | null>(null)
  const [testPlanError, setTestPlanError] = useState<string | null>(null)
  const [executionResults, setExecutionResults] = useState<TestExecutionResult[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
  const [executionStage, setExecutionStage] = useState<string | null>(null)
  const [executionError, setExecutionError] = useState<string | null>(null)
  const [recentTests, setRecentTests] = useState<RecentTest[]>([])
  const [isLoadingRecentTests, setIsLoadingRecentTests] = useState(true)
  const [recentTestsError, setRecentTestsError] = useState<string | null>(null)

  useEffect(() => {
    let isActive = true

    getTestSessions()
      .then((sessions) => {
        if (isActive) setRecentTests(sessions.map(toRecentTest))
      })
      .catch(() => {
        if (isActive) setRecentTestsError('Unable to load recent sessions. Check that the backend is running and try again.')
      })
      .finally(() => {
        if (isActive) setIsLoadingRecentTests(false)
      })

    return () => { isActive = false }
  }, [])

  async function refreshRecentTests() {
    setIsLoadingRecentTests(true)
    setRecentTestsError(null)
    try {
      const sessions = await getTestSessions()
      setRecentTests(sessions.map(toRecentTest))
    } catch {
      setRecentTestsError('Unable to load recent sessions. Check that the backend is running and try again.')
    } finally {
      setIsLoadingRecentTests(false)
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isInspecting || isGeneratingTestPlan || isExecuting) return

    const nextErrors: ValidationErrors = {}
    const trimmedUrl = url.trim()
    const trimmedInstruction = instruction.trim()

    try {
      const parsedUrl = new URL(trimmedUrl)
      if (!/^https?:$/.test(parsedUrl.protocol) || !parsedUrl.hostname) {
        nextErrors.url = 'Please enter a valid website URL.'
      }
    } catch {
      nextErrors.url = 'Please enter a valid website URL.'
    }

    if (!trimmedInstruction) {
      nextErrors.instruction = 'Please describe what you would like to test.'
    }

    setValidationErrors(nextErrors)
    setSessionCreated(null)
    setInspectionResult(null)
    setInspectionError(null)
    setTestPlan(null)
    setTestPlanStage(null)
    setTestPlanError(null)
    setExecutionResults([])
    setExecutionStage(null)
    setExecutionError(null)
    if (Object.keys(nextErrors).length > 0) return

    setIsSubmitting(true)
    setValidationErrors({})
    try {
      const session = await createTestSession({
        url: trimmedUrl,
        instruction: trimmedInstruction,
        mode: modeValues[testMode],
      })
      setSessionCreated(session)
      setRecentTests((tests) => [toRecentTest(session), ...tests.filter((test) => test.id !== session.id)])

      try {
        const sessions = await getTestSessions()
        setRecentTests(sessions.map(toRecentTest))
        setRecentTestsError(null)
      } catch {
        setRecentTestsError('Session created, but recent sessions could not be refreshed.')
      }
    } catch (error) {
      const message = error instanceof ApiRequestError
        ? error.message
        : 'Unable to create testing session. Please try again.'
      setValidationErrors({ submit: message })
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleInspectWebsite() {
    if (!sessionCreated || isInspecting || isGeneratingTestPlan || isExecuting) return

    const session = sessionCreated
    const stageTimers: number[] = []
    setIsInspecting(true)
    setInspectionResult(null)
    setInspectionError(null)
    setTestPlan(null)
    setTestPlanStage(null)
    setTestPlanError(null)
    setExecutionResults([])
    setExecutionStage(null)
    setExecutionError(null)
    setInspectionStage('Opening website...')
    stageTimers.push(window.setTimeout(() => setInspectionStage('Reading page...'), 800))
    stageTimers.push(window.setTimeout(() => setInspectionStage('Analyzing page structure...'), 1600))

    try {
      const result = await inspectTestSession(session.id)
      setInspectionResult(result)
      if (result.status === 'FAILED') {
        setInspectionError(result.error || 'Unable to inspect this website.')
      }
      const updatedSession = { ...session, status: result.status }
      setSessionCreated(updatedSession)
      setRecentTests((tests) => [toRecentTest(updatedSession), ...tests.filter((test) => test.id !== session.id)])
      setInspectionStage(result.status === 'COMPLETED' ? 'Completed' : 'Failed')
    } catch (error) {
      setInspectionError(error instanceof ApiRequestError ? error.message : 'Unable to inspect this website.')
      setInspectionStage('Failed')
      setSessionCreated({ ...session, status: 'FAILED' })
    } finally {
      stageTimers.forEach(window.clearTimeout)
      setIsInspecting(false)
      try {
        const sessions = await getTestSessions()
        setRecentTests(sessions.map(toRecentTest))
      } catch {
        // Keep the local status update if the recent-session refresh is unavailable.
      }
    }
  }

  async function handleGenerateTestPlan() {
    if (!sessionCreated || inspectionResult?.status !== 'COMPLETED' || isGeneratingTestPlan || isExecuting) return

    const sessionId = sessionCreated.id
    const stageTimers: number[] = []
    setIsGeneratingTestPlan(true)
    setTestPlan(null)
    setTestPlanError(null)
    setTestPlanStage('AI is analyzing the website...')
    stageTimers.push(window.setTimeout(() => setTestPlanStage('Generating test scenarios...'), 900))

    try {
      const result = await generateTestPlan(sessionId)
      setTestPlan(result)
      setTestPlanStage('Test plan generated.')
    } catch (error) {
      setTestPlanStage('Generation failed.')
      setTestPlanError(error instanceof ApiRequestError ? error.message : 'AI test generation is temporarily unavailable. Please try again.')
    } finally {
      stageTimers.forEach(window.clearTimeout)
      setIsGeneratingTestPlan(false)
    }
  }

  async function handleExecuteTestCases(testCaseIds: string[], confirmDestructive: boolean) {
    if (!sessionCreated || testCaseIds.length === 0 || isExecuting) return

    const sessionId = sessionCreated.id
    const stageTimers: number[] = []
    setIsExecuting(true)
    setExecutionError(null)
    setExecutionStage('Starting browser...')
    stageTimers.push(window.setTimeout(() => setExecutionStage(`Executing ${testCaseIds[0]}...`), 500))
    stageTimers.push(window.setTimeout(() => setExecutionStage('Performing browser actions...'), 1100))
    stageTimers.push(window.setTimeout(() => setExecutionStage('Evaluating result...'), 2100))

    const mergeResults = (incoming: TestExecutionResult[]) => {
      setExecutionResults((existing) => {
        const byId = new Map(existing.map((result) => [result.id, result]))
        incoming.forEach((result) => byId.set(result.id, result))
        return Array.from(byId.values())
      })
    }
    const pollTimer = window.setInterval(() => {
      void getSessionExecutions(sessionId).then(mergeResults).catch(() => undefined)
    }, 500)

    try {
      const results: TestExecutionResult[] = []
      for (let index = 0; index < testCaseIds.length; index += executionBatchSize) {
        const batchIds = testCaseIds.slice(index, index + executionBatchSize)
        setExecutionStage(`Executing ${batchIds[0]}...`)
        const batch = await executeTestCases(sessionId, batchIds, confirmDestructive)
        results.push(...batch.executions)
        mergeResults(batch.executions)
      }
      const allPassed = results.every((result) => result.status === 'PASSED')
      const anyFailed = results.some((result) => result.status === 'FAILED')
      const anyBlocked = results.some((result) => result.status === 'BLOCKED')
      setExecutionStage(anyFailed ? 'Some Tests Failed' : anyBlocked ? 'Some Tests Blocked' : allPassed ? (results.length === 1 ? 'Test Passed' : 'Tests Passed') : 'Execution Complete')
    } catch (error) {
      setExecutionStage('Execution failed.')
      setExecutionError(error instanceof ApiRequestError ? error.message : 'Unable to execute the selected tests. Please try again.')
    } finally {
      stageTimers.forEach(window.clearTimeout)
      window.clearInterval(pollTimer)
      setIsExecuting(false)
      try {
        mergeResults(await getSessionExecutions(sessionId))
      } catch {
        // Preserve execution results already returned by the execution request.
      }
    }
  }

  return (
    <Dashboard
      url={url}
      instruction={instruction}
      testMode={testMode}
      isSubmitting={isSubmitting}
      validationErrors={validationErrors}
      sessionCreated={sessionCreated}
      inspectionResult={inspectionResult}
      isInspecting={isInspecting}
      inspectionStage={inspectionStage}
      inspectionError={inspectionError}
      testPlan={testPlan}
      isGeneratingTestPlan={isGeneratingTestPlan}
      testPlanStage={testPlanStage}
      testPlanError={testPlanError}
      executionResults={executionResults}
      isExecuting={isExecuting}
      executionStage={executionStage}
      executionError={executionError}
      recentTests={recentTests}
      isLoadingRecentTests={isLoadingRecentTests}
      recentTestsError={recentTestsError}
      onUrlChange={setUrl}
      onInstructionChange={setInstruction}
      onTestModeChange={setTestMode}
      onSubmit={handleSubmit}
      onRefreshRecentTests={refreshRecentTests}
      onInspectWebsite={handleInspectWebsite}
      onGenerateTestPlan={handleGenerateTestPlan}
      onExecuteTestCases={handleExecuteTestCases}
    />
  )
}

export default App