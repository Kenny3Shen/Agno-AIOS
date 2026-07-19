import { useMemo } from 'react'
import XMarkdown from '@ant-design/x-markdown'
import Latex from '@ant-design/x-markdown/plugins/Latex'
import type { ComponentProps } from 'react'

type XMarkdownProps = ComponentProps<typeof XMarkdown>

const latexExtensions = Latex({
  katexOptions: {
    throwOnError: false,
    strict: 'ignore',
  },
})

const markdownConfig = {
  extensions: latexExtensions,
} as const

type MarkdownProps = Omit<XMarkdownProps, 'config'> & {
  /** Merge extra marked extensions after the shared Latex plugin. */
  extensions?: NonNullable<XMarkdownProps['config']>['extensions']
}

/**
 * Workbench Markdown renderer with KaTeX formulas enabled.
 * Supports `$...$`, `$$...$$`, `\\(...\\)`, and `\\[...\\]`.
 */
export function Markdown({ extensions, ...props }: MarkdownProps) {
  const config = useMemo(() => {
    if (!extensions) return markdownConfig
    const extra = Array.isArray(extensions) ? extensions : [extensions]
    return { extensions: [...latexExtensions, ...extra] }
  }, [extensions])

  return <XMarkdown {...props} config={config} />
}
