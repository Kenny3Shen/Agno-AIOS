import { describe, expect, it } from 'vitest'
import { loginPath, nextPathFromLocation, sanitizeNextPath } from './routing'

describe('auth route helpers', () => {
  it('accepts internal next paths with query strings', () => {
    expect(sanitizeNextPath('/chat?session=abc')).toBe('/chat?session=abc')
    expect(nextPathFromLocation({ pathname: '/trace', searchStr: '?selected_session=s1' })).toBe('/trace?selected_session=s1')
  })

  it('rejects unsafe or circular next paths', () => {
    expect(sanitizeNextPath('')).toBeNull()
    expect(sanitizeNextPath('https://evil.test/dashboard')).toBeNull()
    expect(sanitizeNextPath('//evil.test/dashboard')).toBeNull()
    expect(sanitizeNextPath('/login')).toBeNull()
    expect(sanitizeNextPath('/login?next=/dashboard')).toBeNull()
  })

  it('builds the login route with an encoded next value', () => {
    expect(loginPath('/chat?session=abc')).toBe('/login?next=%2Fchat%3Fsession%3Dabc')
    expect(loginPath(null)).toBe('/login')
  })
})
