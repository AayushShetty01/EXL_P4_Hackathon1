/* Displays source with line numbers, cited-range highlights, and scrolling. */
import { useEffect, useId, useRef } from 'react'
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json'
import markdown from 'react-syntax-highlighter/dist/esm/languages/prism/markdown'
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python'
import r from 'react-syntax-highlighter/dist/esm/languages/prism/r'
import type { FileView } from '../api/types'
import { EmptyState } from './EmptyState'

SyntaxHighlighter.registerLanguage('json', json)
SyntaxHighlighter.registerLanguage('markdown', markdown)
SyntaxHighlighter.registerLanguage('python', python)
SyntaxHighlighter.registerLanguage('r', r)

/** Renders code or text with line numbers and selected line ranges. */
export function CodeViewer({
  file,
  highlightStart,
  highlightEnd,
  height = 380,
}: {
  file: FileView | null
  highlightStart?: number
  highlightEnd?: number
  height?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerId = `source-${useId().replaceAll(':', '')}`

  useEffect(() => {
    if (!file || highlightStart == null) return
    const target = containerRef.current?.querySelector<HTMLElement>(
      `#${viewerId}-line-${highlightStart}`,
    )
    target?.scrollIntoView({ block: 'center' })
  }, [file, highlightStart, viewerId])

  if (!file) {
    return (
      <EmptyState
        title="Source file unavailable"
        description="The requested file is not included in this data source."
      />
    )
  }

  const language = syntaxLanguage(file.language)
  const content = file.content.replace(/\r?\n$/, '')
  return (
    <section className="overflow-hidden rounded-lg border border-slate-800 bg-[#1e1e1e]" aria-label={`Source file ${file.path}`}>
      <div className="truncate border-b border-slate-700 px-4 py-2 font-mono text-xs text-slate-300">{file.path}</div>
      <div ref={containerRef} className="overflow-auto" style={{ maxHeight: height }}>
        <SyntaxHighlighter
          language={language}
          style={vscDarkPlus}
          showLineNumbers
          startingLineNumber={1}
          wrapLines
          lineProps={(lineNumber) => ({
            id: `${viewerId}-line-${lineNumber}`,
            style: {
              display: 'block',
              backgroundColor:
                highlightStart != null &&
                lineNumber >= highlightStart &&
                lineNumber <= (highlightEnd ?? highlightStart)
                  ? 'rgba(250, 204, 21, 0.18)'
                  : undefined,
              borderLeft:
                highlightStart != null &&
                lineNumber >= highlightStart &&
                lineNumber <= (highlightEnd ?? highlightStart)
                  ? '3px solid #facc15'
                  : '3px solid transparent',
            },
          })}
          customStyle={{
            margin: 0,
            minWidth: '100%',
            background: '#1e1e1e',
            fontSize: '12px',
            lineHeight: 1.65,
          }}
          lineNumberStyle={{ color: '#94a3b8', paddingRight: '1.25rem' }}
        >
          {content}
        </SyntaxHighlighter>
      </div>
    </section>
  )
}

/** Maps server file languages to syntax highlighter grammars. */
function syntaxLanguage(language: string): string {
  const normalized = language.toLowerCase()
  if (normalized === 'sas') return 'plain'
  if (normalized === 'python' || normalized === 'r' || normalized === 'json' || normalized === 'markdown') {
    return normalized
  }
  return 'plain'
}
