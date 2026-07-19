import { describe, expect, it } from 'vitest'
import {
  buildUserInputPayload,
  isUserInputFieldFilled,
  normalizeFieldType,
  parseUserInputSchema,
  seedUserInputValues,
} from './userInput'

describe('userInput helpers', () => {
  it('normalizes field types', () => {
    expect(normalizeFieldType('boolean')).toBe('bool')
    expect(normalizeFieldType('int')).toBe('number')
    expect(normalizeFieldType('textarea')).toBe('text')
    expect(normalizeFieldType('str')).toBe('str')
  })

  it('parses schema rows', () => {
    const fields = parseUserInputSchema([
      { name: 'severity', type: 'integer', required: true },
      { key: 'ack', field_type: 'bool', description: 'Ack', required: false },
      { name: '  ', field_type: 'str' },
    ])
    expect(fields).toEqual([
      { name: 'severity', field_type: 'number', description: '', required: true },
      { name: 'ack', field_type: 'bool', description: 'Ack', required: false },
    ])
  })

  it('coerces values and builds payload', () => {
    const schema = parseUserInputSchema([
      { name: 'ok', field_type: 'bool' },
      { name: 'count', field_type: 'number' },
      { name: 'note', field_type: 'str' },
    ])
    expect(buildUserInputPayload(schema, { ok: 'true', count: '2', note: 'x' }, '')).toEqual({
      ok: true,
      count: 2,
      note: 'x',
    })
    expect(buildUserInputPayload([], {}, ' free ')).toEqual({ response: 'free' })
  })

  it('seeds defaults and validates required fills', () => {
    const schema = parseUserInputSchema([
      { name: 'flag', field_type: 'bool' },
      { name: 'title', field_type: 'str', required: true },
    ])
    expect(seedUserInputValues(schema)).toEqual({ flag: 'false', title: '' })
    expect(isUserInputFieldFilled(schema[0], 'false')).toBe(true)
    expect(isUserInputFieldFilled(schema[1], '  ')).toBe(false)
  })
})
