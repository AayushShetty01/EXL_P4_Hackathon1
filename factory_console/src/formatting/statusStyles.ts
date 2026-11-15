/* Maps contract statuses to readable labels, icons, and accessible colors. */
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Clock3,
  LoaderCircle,
  MinusCircle,
  XCircle,
  type LucideIcon,
} from 'lucide-react'
import type { ResultError } from '../api/types'

/** Placeholder for inventory fields that are filled by the discover stage. */
export const NOT_DISCOVERED = 'Not discovered yet'

/** Readable text of a result error, which is a plain message or a code with a message. */
export function formatResultError(error: ResultError): string {
  if (!error) return ''
  return typeof error === 'string' ? error : `${error.message} (${error.code})`
}

/** Returns the display label, icon, and color classes for a status. */
export function statusPresentation(status: string): {
  label: string
  className: string
  Icon: LucideIcon
} {
  switch (status) {
    case 'APPROVED':
    case 'GREEN':
    case 'CURRENT':
    case 'MET':
    case 'VERIFIED':
    case 'PASSED':
      return { label: status.replaceAll('_', ' '), className: 'text-emerald-800 bg-emerald-50', Icon: CheckCircle2 }
    case 'AWAITING_REVIEW':
    case 'AMBER':
    case 'OUTDATED':
    case 'PARTIAL':
    case 'UNVERIFIED':
      return { label: status.replaceAll('_', ' '), className: 'text-amber-800 bg-amber-50', Icon: Clock3 }
    case 'RUNNING':
      return { label: 'RUNNING', className: 'text-sky-800 bg-sky-50', Icon: LoaderCircle }
    case 'REJECTED':
    case 'FAILED':
    case 'RED':
    case 'HIGH':
    case 'NOT_MET':
      return { label: status.replaceAll('_', ' '), className: 'text-rose-800 bg-rose-50', Icon: XCircle }
    case 'SKIPPED':
    case 'OUT_OF_SCOPE':
      return { label: status.replaceAll('_', ' '), className: 'text-slate-700 bg-slate-100', Icon: MinusCircle }
    case 'MISSING':
    case 'MEDIUM':
    case 'SME_INPUT_NEEDED':
      return { label: status.replaceAll('_', ' '), className: 'text-orange-800 bg-orange-50', Icon: AlertCircle }
    case 'LOW':
      return { label: 'LOW', className: 'text-slate-700 bg-slate-100', Icon: Circle }
    default:
      return { label: status.replaceAll('_', ' '), className: 'text-slate-700 bg-slate-100', Icon: Circle }
  }
}
