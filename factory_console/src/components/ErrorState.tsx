/* Presents a request failure without disguising it as empty data. */
import { AlertTriangle } from 'lucide-react'

/** Shows an error message and optional retry control. */
export function ErrorState({
  title = 'Could not load this information',
  error,
  retry,
}: {
  title?: string
  error: unknown
  retry?: () => void
}) {
  const message = error instanceof Error ? error.message : 'An unexpected error occurred.'
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-rose-950" role="alert">
      <div className="flex items-start gap-3">
        <AlertTriangle size={20} aria-hidden="true" />
        <div>
          <h3 className="font-semibold">{title}</h3>
          <p className="mt-1 text-sm">{message}</p>
          {retry && (
            <button
              type="button"
              className="mt-3 rounded-md border border-rose-300 px-3 py-1.5 text-sm font-medium hover:bg-rose-100"
              onClick={retry}
            >
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
