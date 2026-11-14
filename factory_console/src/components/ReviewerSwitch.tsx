/* Lets the user select the shared reviewer identity for gate decisions. */
import { useReviewerIdentity } from './ReviewerProvider'

/** Lets a demo reviewer select an identity and role. */
export function ReviewerSwitch() {
  const { identity, options, selectRole } = useReviewerIdentity()

  return (
    <label className="reviewer-switch">
      <span>Reviewing as</span>
      <select
        aria-label="Reviewing as"
        value={identity.role}
        onChange={(event) => {
          const option = options.find((item) => item.role === event.target.value)
          if (option) selectRole(option.role)
        }}
      >
        {options.map((option) => (
          <option key={option.role} value={option.role}>
            {option.reviewer} · {option.role}
          </option>
        ))}
      </select>
    </label>
  )
}
