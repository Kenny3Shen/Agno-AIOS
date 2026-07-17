import { afterEach, describe, expect, it } from 'vitest'
import { isKeyboardTargetEditable, isOverlayEscapeTarget } from './keyboard'

describe('isKeyboardTargetEditable', () => {
  it('detects inputs and contenteditable attributes', () => {
    const input = document.createElement('input')
    expect(isKeyboardTargetEditable(input)).toBe(true)
    const div = document.createElement('div')
    expect(isKeyboardTargetEditable(div)).toBe(false)
    const editable = document.createElement('div')
    editable.setAttribute('contenteditable', 'true')
    expect(isKeyboardTargetEditable(editable)).toBe(true)
  })

  it('treats null as non-editable', () => {
    expect(isKeyboardTargetEditable(null)).toBe(false)
  })
})

describe('isOverlayEscapeTarget', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('detects focus inside an open modal', () => {
    const wrap = document.createElement('div')
    wrap.className = 'ant-modal-wrap'
    const input = document.createElement('input')
    wrap.appendChild(input)
    document.body.appendChild(wrap)
    expect(isOverlayEscapeTarget(input)).toBe(true)
  })

  it('detects an open drawer without focus', () => {
    const drawer = document.createElement('div')
    drawer.className = 'ant-drawer-open'
    document.body.appendChild(drawer)
    expect(isOverlayEscapeTarget(null)).toBe(true)
  })

  it('is false when no overlay is present', () => {
    expect(isOverlayEscapeTarget(document.body)).toBe(false)
  })
})
