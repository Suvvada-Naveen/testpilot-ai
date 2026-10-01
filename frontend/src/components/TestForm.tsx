import type { FormEvent } from 'react'
import { ArrowUpRight, LoaderCircle, Link2, ShieldCheck } from 'lucide-react'
import type { TestMode, ValidationErrors } from '../types/test'
import TestModeSelector from './TestModeSelector'

interface TestFormProps {
  url: string
  instruction: string
  testMode: TestMode
  isSubmitting: boolean
  isBusy: boolean
  validationErrors: ValidationErrors
  submitError: string | null
  onUrlChange: (value: string) => void
  onInstructionChange: (value: string) => void
  onTestModeChange: (mode: TestMode) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

function TestForm({
  url,
  instruction,
  testMode,
  isSubmitting,
  isBusy,
  validationErrors,
  submitError,
  onUrlChange,
  onInstructionChange,
  onTestModeChange,
  onSubmit,
}: TestFormProps) {
  return (
    <section className="panel test-form-panel" id="new-test" aria-labelledby="new-test-title">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">NEW SESSION</span>
          <h2 id="new-test-title">Start a New Test</h2>
        </div>
        <span className="panel-heading-icon"><Link2 size={19} aria-hidden="true" /></span>
      </div>

      <form className="test-form" onSubmit={onSubmit} noValidate>
        <div className="form-field">
          <label className="field-label" htmlFor="website-url">Website URL</label>
          <div className={`input-wrap${validationErrors.url ? ' has-error' : ''}`}>
            <Link2 size={17} aria-hidden="true" />
            <input
              id="website-url"
              name="website-url"
              type="url"
              placeholder="https://example.com"
              value={url}
              onChange={(event) => onUrlChange(event.target.value)}
              autoComplete="url"
              aria-invalid={Boolean(validationErrors.url)}
              aria-describedby={validationErrors.url ? 'website-url-error website-url-help' : 'website-url-help'}
            />
          </div>
          {validationErrors.url ? (
            <span className="field-error" id="website-url-error" role="alert">{validationErrors.url}</span>
          ) : null}
          <span className="field-help" id="website-url-help">Enter the website you want the testing agent to analyze.</span>
        </div>

        <div className="form-field">
          <label className="field-label" htmlFor="test-instruction">What would you like to test?</label>
          <textarea
            id="test-instruction"
            name="test-instruction"
            rows={4}
            placeholder="Example: Test the login functionality, including valid login, invalid credentials, empty fields, and validation messages."
            value={instruction}
            onChange={(event) => onInstructionChange(event.target.value)}
            aria-invalid={Boolean(validationErrors.instruction)}
            aria-describedby={validationErrors.instruction ? 'test-instruction-error' : undefined}
          />
          {validationErrors.instruction ? (
            <span className="field-error" id="test-instruction-error" role="alert">{validationErrors.instruction}</span>
          ) : null}
        </div>

        <TestModeSelector value={testMode} onChange={onTestModeChange} />

        <div className="form-submit-row">
          <span className="form-assurance"><ShieldCheck size={15} aria-hidden="true" /> Headless browser inspection</span>
          <button className="primary-button" type="submit" disabled={isSubmitting || isBusy}>
            {isSubmitting ? (
              <><LoaderCircle className="spin" size={17} aria-hidden="true" /> Starting Testing Session...</>
            ) : (
              <>Start Testing <ArrowUpRight size={17} aria-hidden="true" /></>
            )}
          </button>
        </div>
        {submitError ? <span className="field-error submit-error" role="alert">{submitError}</span> : null}
      </form>
    </section>
  )
}

export default TestForm