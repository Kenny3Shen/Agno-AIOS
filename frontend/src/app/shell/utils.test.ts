import { describe, expect, it } from 'vitest'
import { joinMenuGroups, splitNavigation } from './utils'

describe('shell navigation groups', () => {
  it('groups navigation items using the control-plane hierarchy', () => {
    expect(splitNavigation(Array.from({ length: 15 }, (_, index) => index)).map((group) => group.length)).toEqual([4, 3, 5, 2, 1])
  })

  it('adds dividers only between visible groups', () => {
    expect(joinMenuGroups([['a'], [], ['b']])).toEqual(['a', { type: 'divider', key: 'divider-1' }, 'b'])
  })
})
