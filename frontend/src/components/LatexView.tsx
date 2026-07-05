import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

interface LatexViewProps {
  latex: string
  displayMode?: boolean
  className?: string
}

export default function LatexView({
  latex,
  displayMode = true,
  className = '',
}: LatexViewProps) {
  const html = useMemo(() => {
    if (!latex.trim()) {
      return { __html: '' }
    }
    try {
      const rendered = katex.renderToString(latex, {
        displayMode,
        throwOnError: false,
        strict: false,
      })
      return { __html: rendered }
    } catch {
      return { __html: latex }
    }
  }, [latex, displayMode])

  if (!html.__html) {
    return <span className="text-slate-400">-</span>
  }

  return (
    <span
      className={className}
      dangerouslySetInnerHTML={html}
      aria-label={latex}
    />
  )
}
