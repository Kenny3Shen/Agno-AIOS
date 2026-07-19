import '@/shared/i18n'
import '@testing-library/dom'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from './server'


// Minimal Notification so @ant-design/x XNotification constructor is "permissible"
// without requiring a real browser permission UI in jsdom.
class NotificationStub {
  static permission: NotificationPermission = 'denied'
  static maxActions = 0
  static requestPermission = async (): Promise<NotificationPermission> => 'denied'
  close() {}
  onclick: ((this: Notification, ev: Event) => unknown) | null = null
  onshow: ((this: Notification, ev: Event) => unknown) | null = null
  onclose: ((this: Notification, ev: Event) => unknown) | null = null
  onerror: ((this: Notification, ev: Event) => unknown) | null = null
}
Object.defineProperty(globalThis, 'Notification', {
  configurable: true,
  writable: true,
  value: NotificationStub,
})

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  localStorage.clear()
})
afterAll(() => server.close())

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

Object.defineProperty(window, 'scrollTo', { writable: true, value: () => undefined })

const getComputedStyleWithoutPseudo = window.getComputedStyle.bind(window)
/**
 * jsdom returns non-numeric CSS for borders (`medium`) and empty paddings.
 * antd TextArea autoSize (`calculateNodeHeight`) parseFloats those → NaN height.
 * Coerce layout-critical metrics to finite pixel values for tests.
 */
Object.defineProperty(window, 'getComputedStyle', {
  writable: true,
  value: (element: Element, _pseudoElt?: string | null) => {
    const style = getComputedStyleWithoutPseudo(element)
    const numericFallbacks: Record<string, string> = {
      'box-sizing': 'border-box',
      'padding-top': '0px',
      'padding-bottom': '0px',
      'padding-left': '0px',
      'padding-right': '0px',
      'border-top-width': '0px',
      'border-bottom-width': '0px',
      'border-left-width': '0px',
      'border-right-width': '0px',
      'border-width': '0px',
      'font-size': '14px',
      'line-height': '22px',
      'letter-spacing': '0px',
      'font-family': 'sans-serif',
      'font-weight': '400',
      width: '320px',
      'text-indent': '0px',
      'word-break': 'normal',
      'white-space': 'pre-wrap',
    }
    const needsNumeric = new Set(Object.keys(numericFallbacks))
    const resolve = (prop: string, raw: string) => {
      const value = raw == null ? '' : String(raw).trim()
      if (!needsNumeric.has(prop) && !(prop in numericFallbacks)) return raw
      if (value === '' || value === 'auto' || value === 'normal' || value === 'medium') {
        return numericFallbacks[prop] ?? '0px'
      }
      // keyword border widths
      if (value === 'thin') return '1px'
      if (value === 'thick') return '5px'
      if (needsNumeric.has(prop) && Number.isNaN(parseFloat(value))) {
        return numericFallbacks[prop] ?? '0px'
      }
      return raw
    }
    return new Proxy(style, {
      get(target, prop, receiver) {
        if (prop === 'getPropertyValue') {
          return (name: string) => resolve(name, target.getPropertyValue(name))
        }
        if (typeof prop === 'string') {
          const kebab = prop.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)
          if (kebab in numericFallbacks || prop in numericFallbacks) {
            const key = prop in numericFallbacks ? prop : kebab
            const direct = (target as unknown as Record<string, unknown>)[prop]
            const raw =
              typeof direct === 'string' ? direct : target.getPropertyValue(kebab)
            return resolve(key, raw)
          }
        }
        const value = Reflect.get(target, prop, receiver)
        return typeof value === 'function' ? value.bind(target) : value
      },
    })
  },
})

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverMock

// jsdom scrollHeight is often 0; give textareas a stable single-row metric for autoSize.
Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
  configurable: true,
  get() {
    if (this instanceof HTMLTextAreaElement) {
      const lines = Math.max(1, (this.value || this.placeholder || ' ').split('\n').length)
      return 22 * lines
    }
    return 0
  },
})
