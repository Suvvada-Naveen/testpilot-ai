import { useState } from 'react'
import type { FormEvent } from 'react'
import { Activity, ArrowDownRight, CircleDot, Globe2, ShieldCheck } from 'lucide-react'
import type { InspectionResult, RecentTest, TestExecutionResult, TestMode, TestPlan, TestSession, ValidationErrors } from '../types/test'
import { getInspectionScreenshotUrl, toModeLabel, toStatusLabel } from '../services/testSessionApi'
import Header from '../components/Header'
import RecentTests from '../components/RecentTests'
import Sidebar from '../components/Sidebar'
import TestForm from '../components/TestForm'
import TestPlanResult from '../components/TestPlanResult'

interface DashboardProps {
  url: string
  instruction: string
  testMode: TestMode
  isSubmitting: boolean
  validationErrors: ValidationErrors
  sessionCreated: TestSession | null
  inspectionResult: InspectionResult | null
  isInspecting: boolean
  inspectionStage: string | null
  inspectionError: string | null
  testPlan: TestPlan | null
  isGeneratingTestPlan: boolean
  testPlanStage: string | null
  testPlanError: string | null
  executionResults: TestExecutionResult[]
  isExecuting: boolean
  executionStage: string | null
  executionError: string | null
  recentTests: RecentTest[]
  isLoadingRecentTests: boolean
  recentTestsError: string | null
  onUrlChange: (value: string) => void
  onInstructionChange: (value: string) => void
  onTestModeChange: (mode: TestMode) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onRefreshRecentTests: () => void
  onInspectWebsite: () => void
  onGenerateTestPlan: () => void
  onExecuteTestCases: (testCaseIds: string[], confirmDestructive: boolean) => void
}

function Dashboard(props: DashboardProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  return (
    <div className="app-shell" id="dashboard">
      <Sidebar isOpen={isMenuOpen} onClose={() => setIsMenuOpen(false)} />
      <main className="main-shell">
        <Header onMenuClick={() => setIsMenuOpen(true)} />
        <div className="dashboard-content">
          <section className="page-intro">
            <div className="intro-copy">
              <div className="intro-overline"><span className="overline-line" /> YOUR TESTING WORKSPACE</div>
              <h1>AI Testing Agent<span className="heading-period">.</span></h1>
              <p>Test your website automatically with AI.<br className="desktop-break" /> Provide a URL and tell the agent what you want to test.</p>
            </div>
            <div className="intro-status">
              <span className="status-orbit"><Activity size={18} aria-hidden="true" /></span>
              <div><strong>Agent ready</strong><span>Waiting for a new session</span></div>
              <ArrowDownRight className="intro-status-arrow" size={16} aria-hidden="true" />
            </div>
          </section>

          {props.sessionCreated ? (
            <section className="session-created" role="status" aria-live="polite">
              <div className="session-created-icon"><ShieldCheck size={19} aria-hidden="true" /></div>
              <div className="session-created-copy">
                <strong>Testing session created.</strong>
                <span><b>{props.sessionCreated.id}</b><i />{props.sessionCreated.url}<i />{toModeLabel(props.sessionCreated.mode)}<i /><span className="session-pending">{toStatusLabel(props.sessionCreated.status)}</span></span>
              </div>
              <button className="inspect-button" type="button" onClick={props.onInspectWebsite} disabled={props.isInspecting || props.isGeneratingTestPlan || props.isExecuting}>
                {props.isInspecting ? <Activity size={15} className="spin" aria-hidden="true" /> : <Globe2 size={15} aria-hidden="true" />}
                {props.isInspecting ? 'Inspecting...' : props.inspectionResult ? 'Inspect Again' : 'Inspect Website'}
              </button>
              <CircleDot size={17} className="session-live-dot" aria-hidden="true" />
            </section>
          ) : null}

          {props.isInspecting || props.inspectionStage ? (
            <div className={`inspection-progress${props.inspectionStage === 'Failed' ? ' is-failed' : ''}`} role="status" aria-live="polite">
              <Activity size={15} className={props.isInspecting ? 'spin' : undefined} aria-hidden="true" />
              <span>{props.inspectionStage}</span>
            </div>
          ) : null}

          {props.inspectionError ? (
            <div className="inspection-error" role="alert">
              <strong>Unable to inspect this website.</strong>
              <span>{props.inspectionError}</span>
            </div>
          ) : null}

          {props.inspectionResult?.status === 'COMPLETED' ? (
            <section className="inspection-panel" aria-labelledby="inspection-title">
              <div className="inspection-heading">
                <div><span className="section-kicker">BROWSER INSPECTION</span><h2 id="inspection-title">Inspection Results</h2></div>
                <div className="inspection-actions">
                  <span className="inspection-status">COMPLETED</span>
                  <button className="generate-plan-button" type="button" onClick={props.onGenerateTestPlan} disabled={props.isGeneratingTestPlan || props.isExecuting}>
                    {props.isGeneratingTestPlan ? 'Generating...' : props.testPlan ? 'Generate Again' : 'Generate Test Plan'}
                  </button>
                </div>
              </div>
              <dl className="inspection-metadata">
                <div><dt>Website</dt><dd>{props.inspectionResult.page.requested_url}</dd></div>
                <div><dt>HTTP status</dt><dd>{props.inspectionResult.page.status_code ?? 'Unavailable'}</dd></div>
                <div><dt>Page title</dt><dd>{props.inspectionResult.page.title || 'Untitled page'}</dd></div>
                <div><dt>Final URL</dt><dd>{props.inspectionResult.page.final_url}</dd></div>
              </dl>

              <div className="inspection-section">
                <h3>Page Content</h3>
                <p className="inspection-visible-text">{props.inspectionResult.visible_text || 'No visible text found.'}</p>
              </div>
              <div className="inspection-columns">
                <div className="inspection-section"><h3>Headings</h3>
                  {props.inspectionResult.elements.headings.length ? <ul>{props.inspectionResult.elements.headings.map((heading, index) => <li key={`${heading}-${index}`}>{heading}</li>)}</ul> : <p className="inspection-empty">No headings found.</p>}
                </div>
                <div className="inspection-section"><h3>Buttons</h3>
                  {props.inspectionResult.elements.buttons.length ? <ul>{props.inspectionResult.elements.buttons.map((button, index) => <li key={`${button.text}-${index}`}>{button.text || button.aria_label || 'Unlabeled button'}{button.disabled ? ' (disabled)' : ''}</li>)}</ul> : <p className="inspection-empty">No buttons found.</p>}
                </div>
                <div className="inspection-section"><h3>Input Fields</h3>
                  {props.inspectionResult.elements.inputs.length ? <ul>{props.inspectionResult.elements.inputs.map((input, index) => <li key={`${input.name}-${input.id}-${index}`}><strong>{input.name || input.id || input.aria_label || 'Input'}</strong><span>{input.type}{input.required ? ' · required' : ''}{input.placeholder ? ` · ${input.placeholder}` : ''}</span></li>)}</ul> : <p className="inspection-empty">No input fields found.</p>}
                </div>
                <div className="inspection-section"><h3>Links</h3>
                  {props.inspectionResult.elements.links.length ? <ul>{props.inspectionResult.elements.links.map((link, index) => <li key={`${link.href}-${index}`}><a href={link.href} target="_blank" rel="noreferrer">{link.text || link.href}</a></li>)}</ul> : <p className="inspection-empty">No links found.</p>}
                </div>
              </div>
              <div className="inspection-columns inspection-diagnostics">
                <div className="inspection-section"><h3>Console Errors</h3>
                  {props.inspectionResult.console_errors.length ? <ul>{props.inspectionResult.console_errors.map((entry, index) => <li key={`${entry.text}-${index}`}>{entry.text}</li>)}</ul> : <p className="inspection-empty">No console errors.</p>}
                </div>
                <div className="inspection-section"><h3>Network Errors</h3>
                  {props.inspectionResult.network_errors.length ? <ul>{props.inspectionResult.network_errors.map((entry, index) => <li key={`${entry.url}-${index}`}><strong>{entry.method}</strong> {entry.url}<span>{entry.failure}</span></li>)}</ul> : <p className="inspection-empty">No failed network requests.</p>}
                </div>
              </div>
              <div className="inspection-section screenshot-section"><h3>Screenshot</h3>
                <img src={getInspectionScreenshotUrl(props.inspectionResult.session_id)} alt={`Screenshot of ${props.inspectionResult.page.title || props.inspectionResult.page.final_url}`} />
              </div>
            </section>
          ) : null}

          {props.testPlanStage ? (
            <div className={`test-plan-progress${props.testPlanError ? ' is-failed' : ''}`} role="status" aria-live="polite">
              <Activity size={15} className={props.isGeneratingTestPlan ? 'spin' : undefined} aria-hidden="true" />
              <span>{props.testPlanStage}</span>
            </div>
          ) : null}
          {props.testPlanError ? <div className="inspection-error" role="alert"><strong>Unable to generate a test plan.</strong><span>{props.testPlanError}</span></div> : null}
          {props.testPlan ? (
            <TestPlanResult
              plan={props.testPlan}
              sessionId={props.sessionCreated?.id ?? ''}
              executionResults={props.executionResults}
              isExecuting={props.isExecuting}
              executionStage={props.executionStage}
              executionError={props.executionError}
              onExecuteTestCases={props.onExecuteTestCases}
            />
          ) : null}

          <div className="workspace-grid">
            <TestForm
              url={props.url}
              instruction={props.instruction}
              testMode={props.testMode}
              isSubmitting={props.isSubmitting}
              isBusy={props.isInspecting || props.isGeneratingTestPlan || props.isExecuting}
              validationErrors={props.validationErrors}
              submitError={props.validationErrors.submit ?? null}
              onUrlChange={props.onUrlChange}
              onInstructionChange={props.onInstructionChange}
              onTestModeChange={props.onTestModeChange}
              onSubmit={props.onSubmit}
            />
            <aside className="runtime-panel" aria-label="Session environment">
              <div className="runtime-heading"><span className="runtime-icon"><Globe2 size={18} aria-hidden="true" /></span><span>SESSION ENVIRONMENT</span><span className="mock-pill">PHASE 4</span></div>
              <div className="runtime-divider" />
              <div className="runtime-mode-label">SELECTED MODE</div>
              <strong className="runtime-mode">{props.testMode}</strong>
              <p className="runtime-description">{props.testMode === 'Explore'
                ? 'Analyze the website without performing destructive actions.'
                : props.testMode === 'Test'
                  ? 'Generate a structured test plan for the inspected website.'
                  : 'Inspect the website, prepare test cases, and execute selected scenarios.'}</p>
              <div className="runtime-details">
                <div><span>Browser access</span><strong><i className="runtime-on-dot" /> Headless Chromium</strong></div>
                <div><span>Session output</span><strong>In-memory API</strong></div>
              </div>
              <div className="runtime-footnote"><ShieldCheck size={15} aria-hidden="true" /><span>Local and private network addresses are blocked by default.</span></div>
            </aside>
          </div>

          <RecentTests
            tests={props.recentTests}
            isLoading={props.isLoadingRecentTests}
            error={props.recentTestsError}
            onRetry={props.onRefreshRecentTests}
          />
          <footer className="page-footer"><span>TESTPILOT AI</span><span>PHASE 5 <i /> BROWSER EXECUTION</span></footer>
        </div>
      </main>
    </div>
  )
}

export default Dashboard