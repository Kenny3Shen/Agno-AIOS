import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Markdown } from './Markdown'

describe('Markdown', () => {
  it('renders KaTeX for block and inline LaTeX delimiters', () => {
    const content = [
      'Edge prior:',
      '',
      '$$ I_c = w_1 \\cdot |G_x \\otimes I_0| + w_2 \\cdot |G_y \\otimes I_0| $$',
      '',
      'Inline $a + b$.',
    ].join('\n')
    const { container } = render(<Markdown content={content} openLinksInNewTab escapeRawHtml />)
    expect(container.querySelector('.katex')).toBeTruthy()
    expect(screen.getByText(/Edge prior/)).toBeTruthy()
  })

  it('renders \\[ ... \\] display math used by many models', () => {
    const content = 'Formula:\n\n\\[ I_c = w_1 \\cdot |G_x \\otimes I_0| \\]\n'
    const { container } = render(<Markdown content={content} openLinksInNewTab escapeRawHtml />)
    expect(container.querySelector('.katex')).toBeTruthy()
  })
})
