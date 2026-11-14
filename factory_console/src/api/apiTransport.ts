/* Provides shared mode configuration, mock delay, and HTTP error handling. */
export type ApiMode = 'mock' | 'live' | 'snapshot'

const configuredMode = import.meta.env.VITE_API_MODE || 'mock'
if (!['mock', 'live', 'snapshot'].includes(configuredMode)) {
  throw new Error(`Unsupported VITE_API_MODE: ${configuredMode}`)
}

export const apiMode = configuredMode as ApiMode
export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(
  /\/$/,
  '',
)

/** Describes an HTTP error returned by factory_core. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | null

  /** Builds an error with the backend status and contract error code. */
  constructor(message: string, status: number, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** Waits briefly so mock interactions feel like asynchronous service calls. */
export function mockDelay() {
  return new Promise<void>((resolve) => window.setTimeout(resolve, 180))
}

/** Requests JSON from factory_core or the static snapshot directory. */
export async function requestJson<T>(path: string, init?: RequestInit): Promise<T | null> {
  const isSnapshot = apiMode === 'snapshot'
  const url = isSnapshot ? `/snapshot/${path}` : `${apiBaseUrl}${path}`
  const response = await fetch(url, init)
  if (response.ok) {
    return (await response.json()) as T
  }

  const responseText = await response.text()
  let responseBody: { error?: { code?: string; message?: string } } | null = null
  try {
    responseBody = JSON.parse(responseText) as { error?: { code?: string; message?: string } }
  } catch {
    responseBody = null
  }
  if (response.status === 404 && (isSnapshot || responseBody?.error?.code === 'NOT_AVAILABLE')) {
    return null
  }

  const message =
    responseBody?.error?.message || responseText || response.statusText || 'The request failed.'
  throw new ApiError(message, response.status, responseBody?.error?.code ?? null)
}
