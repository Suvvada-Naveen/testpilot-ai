import { useState } from 'react'
import { Check, CircleAlert, Play, ShieldAlert, X } from 'lucide-react'
import { getExecutionScreenshotUrl } from '../services/testSessionApi'
import type { TestExecutionResult, TestPlan } from '../types/test'

interface TestPlanResultProps {
  plan: TestPlan
  sessionId: string
  executionResults: TestExecutionResult[]
  isExecuting: boolean
  executionStage: string | null
  executionError: string | null
  onExecuteTestCases: (testCaseIds: string[], confirmDestructive: boolean) => void
}

function titleCase(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

const actionDescriptions: Record<TestExecutionResult['actions'][number]['action'], string> = {
  navigate: 'Open page', click: 'Click', fill: 'Fill', select: 'Select', check: 'Check',
  uncheck: 'Uncheck', press: 'Press', scroll: 'Scroll', wait: 'Wait',
  read_page: 'Read page state', take_screenshot: 'Capture screenshot',
}

function TestPlanResult({
  plan,
  sessionId,
  executionResults,
  isExecuting,
  executionStage,
  executionError,
  onExecuteTestCases,
}: TestPlanResultProps) {
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([])
  const [pendingTestCaseIds, setPendingTestCaseIds] = useState<string[] | null>(null)
  const [allowDestructive, setAllowDestructive] = useState(false)
  const selectedCase = plan.test_cases.find((testCase) => testCase.id === selectedCaseId)
  const pendingTitle = pendingTestCaseIds?.length === 1
    ? plan.test_cases.find((testCase) => testCase.id === pendingTestCaseIds[0])?.title
    : `${pendingTestCaseIds?.length ?? 0} selected test cases`

  function requestExecution(testCaseIds: string[]) {
    if (testCaseIds.length === 0 || isExecuting) return
    setPendingTestCaseIds(testCaseIds)
    setAllowDestructive(false)
  }

  function toggleSelected(testCaseId: string) {
    setSelectedCaseIds((current) => current.includes(testCaseId)
      ? current.filter((id) => id !== testCaseId)
      : [...current, testCaseId])
  }

  function confirmExecution() {
    if (!pendingTestCaseIds) return
    onExecuteTestCases(pendingTestCaseIds, allowDestructive)
    setPendingTestCaseIds(null)
  }

  return (
    <section className="test-plan-panel" aria-labelledby="test-plan-title">
      <div className="test-plan-heading">
        <div>
          <span className="section-kicker">AI-GENERATED TEST PLAN</span>
          <h2 id="test-plan-title">Test Plan</h2>
        </div>
        <span className="not-executed-badge">Generated - Not Yet Executed</span>
      </div>
      <div className="test-plan-summary">
        <div><span>Summary</span><strong>{plan.summary}</strong></div>
        <div><span>Total Test Cases</span><strong>{plan.test_cases.length}</strong></div>
      </div>

      {plan.warnings.length > 0 ? (
        <div className="test-plan-warnings" role="note" aria-label="Test plan warnings">
          <strong>Warnings</strong>
          <ul>{plan.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul>
        </div>
      ) : null}

      {plan.test_cases.length > 0 ? (
        <>
          <div className="execution-toolbar">
            <button className="generate-plan-button" type="button" onClick={() => requestExecution(selectedCaseIds)} disabled={isExecuting || selectedCaseIds.length === 0}>
              <Play size={14} aria-hidden="true" /> Execute Selected ({selectedCaseIds.length})
            </button>
            <button className="execution-secondary-button" type="button" onClick={() => requestExecution(plan.test_cases.map((testCase) => testCase.id))} disabled={isExecuting}>
              Execute All
            </button>
          </div>
          <div className="test-plan-table-wrap">
            <table className="test-plan-table">
              <thead><tr><th scope="col"><span className="visually-hidden">Select</span></th><th scope="col">ID</th><th scope="col">Test Case</th><th scope="col">Type</th><th scope="col">Priority</th><th scope="col">Status</th><th scope="col">Run</th></tr></thead>
              <tbody>{plan.test_cases.map((testCase) => (
                <tr key={testCase.id} className={selectedCaseId === testCase.id ? 'is-selected' : undefined}>
                  <td><input aria-label={`Select ${testCase.id}`} type="checkbox" checked={selectedCaseIds.includes(testCase.id)} onChange={() => toggleSelected(testCase.id)} disabled={isExecuting} /></td>
                  <td>{testCase.id}</td>
                  <td><button type="button" className="test-case-select" aria-pressed={selectedCaseId === testCase.id} onClick={() => setSelectedCaseId(testCase.id)}>{testCase.title}</button></td>
                  <td>{titleCase(testCase.type)}</td>
                  <td><span className={`priority-label priority-${testCase.priority}`}>{titleCase(testCase.priority)}</span></td>
                  <td>{executionResults.filter((result) => result.test_case_id === testCase.id).at(-1)?.status ?? 'NOT RUN'}</td>
                  <td><button className="execute-case-button" type="button" onClick={() => requestExecution([testCase.id])} disabled={isExecuting}><Play size={13} aria-hidden="true" /> Execute Test</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          {selectedCase ? (
            <section className="test-case-detail" aria-labelledby="test-case-detail-title">
              <div className="test-case-detail-heading"><span>{selectedCase.id}</span><h3 id="test-case-detail-title">{selectedCase.title}</h3></div>
              <p>{selectedCase.description}</p>
              <div className="test-case-detail-grid">
                <div><h4>Preconditions</h4>{selectedCase.preconditions.length ? <ul>{selectedCase.preconditions.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p>None specified.</p>}</div>
                <div><h4>Steps</h4><ol>{selectedCase.steps.map((step, index) => <li key={`${step}-${index}`}>{step}</li>)}</ol></div>
                <div><h4>Expected Result</h4><p>{selectedCase.expected_result}</p></div>
                <div><h4>Target Elements</h4><ul>{selectedCase.target_elements.map((element, index) => <li key={`${element}-${index}`}>{element}</li>)}</ul></div>
              </div>
              {selectedCase.requires_credentials ? <p className="credentials-note">Requires credentials during a later execution phase. Credentials are not included in this plan.</p> : null}
            </section>
          ) : null}
        </>
      ) : <p className="test-plan-empty">No relevant test cases could be generated from the available page information.</p>}

      {executionStage ? <div className="execution-progress" role="status" aria-live="polite">{isExecuting ? <Play size={14} className="spin" aria-hidden="true" /> : null}<span>{executionStage}</span></div> : null}
      {executionError ? <div className="inspection-error" role="alert"><strong>Execution request failed.</strong><span>{executionError}</span></div> : null}
      {executionResults.length > 0 ? (
        <section className="execution-history" aria-labelledby="execution-history-title">
          <div className="execution-history-heading"><div><span className="section-kicker">BROWSER RUNS</span><h3 id="execution-history-title">Execution Results</h3></div><span>{executionResults.length} runs</span></div>
          {executionResults.map((result) => {
            const testCase = plan.test_cases.find((item) => item.id === result.test_case_id)
            return (
              <article className="execution-result" key={result.id}>
                <div className="execution-result-heading">
                  <div><strong>{result.test_case_id}</strong><span>{testCase?.title ?? result.test_case_id}</span></div>
                  <span className={`execution-status execution-${result.status.toLowerCase()}`}>{result.status}</span>
                </div>
                <div className="execution-stats"><span>Duration: {result.duration.toFixed(2)}s</span><span>Actions: {result.actions.length}</span></div>
                {result.actions.length > 0 ? (
                  <ol className="execution-timeline">
                    {result.actions.map((item) => (
                      <li className={`execution-action execution-action-${item.status.toLowerCase()}`} key={`${result.id}-${item.step}`}>
                        {item.status === 'SUCCESS' ? <Check size={14} aria-hidden="true" /> : <CircleAlert size={14} aria-hidden="true" />}
                        <span>{actionDescriptions[item.action]}{item.target ? ` ${item.target}` : ''}</span>
                        <small>{item.duration_ms} ms</small>
                        {item.error ? <span className="execution-action-error">{item.error}</span> : null}
                      </li>
                    ))}
                  </ol>
                ) : null}
                {result.actual_result ? <p className="execution-actual"><strong>Actual:</strong> {result.actual_result}</p> : null}
                {result.failure_reason ? <p className="execution-failure"><strong>Failure:</strong> {result.failure_reason}</p> : null}
                {result.console_errors.length || result.network_errors.length ? (
                  <div className="execution-logs">
                    {result.console_errors.map((entry, index) => <p key={`${result.id}-console-${index}`}>Console: {entry.text}</p>)}
                    {result.network_errors.map((entry, index) => <p key={`${result.id}-network-${index}`}>Network: {entry.method} {entry.url} ({entry.failure})</p>)}
                  </div>
                ) : null}
                {result.screenshot_id ? <img className="execution-screenshot" src={getExecutionScreenshotUrl(sessionId, result.id)} alt={`Final screenshot for ${result.test_case_id}`} /> : null}
              </article>
            )
          })}
        </section>
      ) : null}

      {pendingTestCaseIds ? (
        <div className="execution-confirm-backdrop">
          <section className="execution-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="execution-confirm-title" aria-describedby="execution-confirm-copy">
            <div className="execution-confirm-heading"><span className="execution-confirm-icon"><ShieldAlert size={18} aria-hidden="true" /></span><button type="button" className="execution-confirm-close" aria-label="Cancel execution" onClick={() => setPendingTestCaseIds(null)}><X size={16} aria-hidden="true" /></button></div>
            <h2 id="execution-confirm-title">Execute test cases?</h2>
            <p id="execution-confirm-copy">A real browser will interact with <strong>{pendingTitle}</strong>. Test values use the configured mock credential provider.</p>
            <label className="destructive-confirm-option"><input type="checkbox" checked={allowDestructive} onChange={(event) => setAllowDestructive(event.target.checked)} /><span>Allow potentially destructive actions such as delete, purchase, send, or cancel.</span></label>
            <div className="execution-confirm-actions"><button type="button" className="execution-secondary-button" onClick={() => setPendingTestCaseIds(null)}>Cancel</button><button type="button" className="generate-plan-button" onClick={confirmExecution}><Play size={14} aria-hidden="true" /> Confirm &amp; Execute</button></div>
          </section>
        </div>
      ) : null}
    </section>
  )
}

export default TestPlanResult
