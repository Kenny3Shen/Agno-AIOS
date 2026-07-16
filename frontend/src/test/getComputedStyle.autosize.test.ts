import { describe, expect, it } from 'vitest'
import calculateAutoSizeStyle from '@rc-component/input/es/calculateNodeHeight'

describe('jsdom getComputedStyle polyfill for TextArea autoSize', () => {
  it('keeps calculateAutoSizeStyle height finite', () => {
    const textarea = document.createElement('textarea')
    document.body.appendChild(textarea)
    textarea.value = 'hello'
    const style = calculateAutoSizeStyle(textarea, false, 1, 5)
    expect(Number.isFinite(style.height as number)).toBe(true)
    expect((style.height as number) > 0).toBe(true)
    textarea.remove()
  })
})
