import { Compass, FlaskConical, Sparkles } from 'lucide-react'
import type { TestMode } from '../types/test'

const modes: { name: TestMode; description: string; icon: typeof Compass }[] = [
  { name: 'Explore', description: 'Analyze the website without performing destructive actions.', icon: Compass },
  { name: 'Test', description: 'Execute defined test scenarios.', icon: FlaskConical },
  { name: 'Full Test', description: 'Explore the website, generate test cases, execute them, and generate a report.', icon: Sparkles },
]

interface TestModeSelectorProps {
  value: TestMode
  onChange: (mode: TestMode) => void
}

function TestModeSelector({ value, onChange }: TestModeSelectorProps) {
  return (
    <fieldset className="mode-fieldset">
      <legend className="field-label">Test Mode</legend>
      <div className="mode-options">
        {modes.map(({ name, description, icon: Icon }) => (
          <label className={`mode-option${value === name ? ' is-selected' : ''}`} key={name}>
            <input
              type="radio"
              name="test-mode"
              value={name}
              checked={value === name}
              onChange={() => onChange(name)}
            />
            <span className="mode-option-top">
              <Icon size={17} aria-hidden="true" />
              <span>{name}</span>
            </span>
            <span className="mode-description">{description}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export default TestModeSelector