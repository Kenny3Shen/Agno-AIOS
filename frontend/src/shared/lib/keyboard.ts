/** Keyboard target helpers shared by Chat and Workflow Studio. */

const isElement = (target: EventTarget | null): target is Element =>
  typeof Element !== 'undefined' && target instanceof Element

/** True when the event target is an editable control (incl. Ant Design hosts). */
export const isKeyboardTargetEditable = (target: EventTarget | null): boolean => {
  if (!isElement(target)) return false
  const el = target as HTMLElement
  if (el.isContentEditable) return true
  const contentEditableAttr = (el.getAttribute?.('contenteditable') || '').toLowerCase()
  if (contentEditableAttr === 'true') return true
  // Bare contenteditable attribute means true in HTML.
  if (el.hasAttribute?.('contenteditable') && contentEditableAttr !== 'false') return true
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (
    el.closest?.(
      'input, textarea, select, [contenteditable="true"], .ant-select, .ant-select-selector, .ant-picker, .ant-input-number, .ant-mentions, .ant-cascader, .cel-expression-field',
    )
  ) {
    return true
  }
  return false
}

/**
 * True when a modal/drawer/dropdown is open and should own Escape.
 * Used so global Esc-to-stop does not cancel a run while dismissing UI.
 */
export const isOverlayEscapeTarget = (target: EventTarget | null = null): boolean => {
  if (typeof document === 'undefined') return false
  const root = isElement(target)
    ? target
    : target && typeof Node !== 'undefined' && target instanceof Node
      ? (target as Node).parentElement
      : null
  if (
    root?.closest?.(
      '.ant-modal-wrap, .ant-modal-root, .ant-drawer, .ant-drawer-content-wrapper, .ant-popconfirm, .ant-dropdown, .ant-select-dropdown, .ant-picker-dropdown, .ant-cascader-dropdown, [role="dialog"]',
    )
  ) {
    return true
  }
  // Open overlay without focus inside (body focused). Prefer open-state classes.
  return Boolean(
    document.querySelector('.ant-modal-wrap, .ant-drawer-open, .ant-modal-mask:not([style*="display: none"])'),
  )
}
