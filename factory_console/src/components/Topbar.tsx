/* Renders the page heading and reviewer control. */
import { ReviewerSwitch } from './ReviewerSwitch'

/** Shows the current workspace heading and review identity control. */
export function Topbar() {
  return (
    <header className="topbar">
      <div>
        <h1>Model risk factory</h1>
        <p>Evidence, review, and model governance</p>
      </div>
      <ReviewerSwitch />
    </header>
  )
}
