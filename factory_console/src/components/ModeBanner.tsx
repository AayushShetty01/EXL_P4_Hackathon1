/* Makes the active data source visible throughout the console. */
import { FlaskConical, Radio, ScrollText } from 'lucide-react'
import { apiMode } from '../api/client'

const modeDetails = {
  mock: {
    label: 'Mock data',
    description: 'Illustrative sample data. Values are not validation results.',
    Icon: FlaskConical,
  },
  live: {
    label: 'Live factory_core',
    description: 'Connected to the factory_core API.',
    Icon: Radio,
  },
  snapshot: {
    label: 'Recorded run',
    description: 'Read-only data from the saved snapshot.',
    Icon: ScrollText,
  },
} as const

/** Identifies whether the console is using mock, live, or snapshot data. */
export function ModeBanner() {
  const detail = modeDetails[apiMode]
  const Icon = detail.Icon

  return (
    <div className="mode-banner" data-mode={apiMode} role="status">
      <Icon size={16} aria-hidden="true" />
      <strong>{detail.label}</strong>
      <span>{detail.description}</span>
    </div>
  )
}
