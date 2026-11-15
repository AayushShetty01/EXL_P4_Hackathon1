/* Shares the selected review role across the top bar and gate panel. */
import { createContext, useContext, useState, type ReactNode } from 'react'
import type { ReviewerRole } from '../api/types'

export interface ReviewerIdentity {
  reviewer: string
  role: ReviewerRole
}

const reviewerOptions: ReviewerIdentity[] = [
  { reviewer: 'Developer reviewer', role: 'developer' },
  { reviewer: 'Validator reviewer', role: 'validator' },
  { reviewer: 'Model owner', role: 'owner' },
]

interface ReviewerContextValue {
  identity: ReviewerIdentity
  options: ReviewerIdentity[]
  selectRole: (role: ReviewerRole) => void
}

const reviewerContext = createContext<ReviewerContextValue | null>(null)
const reviewerStorageKey = 'modelpassport-reviewer'

/** Provides one persisted reviewer identity for all nested console views. */
export function ReviewerProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<ReviewerIdentity>(() => {
    const storedRole = localStorage.getItem(reviewerStorageKey)
    return reviewerOptions.find((option) => option.role === storedRole) ?? reviewerOptions[0]
  })

  /** Selects a review role and saves it in this browser. */
  function selectRole(role: ReviewerRole) {
    const selected = reviewerOptions.find((option) => option.role === role)
    if (!selected) return
    setIdentity(selected)
    localStorage.setItem(reviewerStorageKey, selected.role)
  }

  return (
    <reviewerContext.Provider value={{ identity, options: reviewerOptions, selectRole }}>
      {children}
    </reviewerContext.Provider>
  )
}

/** Returns the shared reviewer selection, requiring the provider. */
export function useReviewerIdentity() {
  const value = useContext(reviewerContext)
  if (!value) {
    throw new Error('useReviewerIdentity must be used within ReviewerProvider.')
  }
  return value
}
