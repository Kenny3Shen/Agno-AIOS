export type UserInputField = {
  name: string
  field_type?: string
  description?: string
  required?: boolean
}

export const normalizeFieldType = (raw: string | undefined): string => {
  const value = (raw || 'str').trim().toLowerCase()
  if (['bool', 'boolean', 'checkbox', 'switch'].includes(value)) return 'bool'
  if (['int', 'integer', 'number', 'float', 'double', 'num'].includes(value)) return 'number'
  if (['text', 'textarea', 'markdown', 'long_text'].includes(value)) return 'text'
  return 'str'
}

export const parseUserInputSchema = (raw: unknown): UserInputField[] => {
  if (!Array.isArray(raw)) return []
  return raw.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const row = item as Record<string, unknown>
    const name = String(row.name ?? row.key ?? '').trim()
    if (!name) return []
    const fieldType = normalizeFieldType(
      row.field_type != null ? String(row.field_type) : row.type != null ? String(row.type) : 'str',
    )
    return [
      {
        name,
        field_type: fieldType,
        description: row.description != null ? String(row.description) : '',
        required: Boolean(row.required ?? true),
      },
    ]
  })
}

const coerceUserInputValue = (
  field: UserInputField,
  raw: string,
): string | number | boolean => {
  const type = normalizeFieldType(field.field_type)
  if (type === 'bool') {
    const text = raw.trim().toLowerCase()
    return text === 'true' || text === '1' || text === 'yes'
  }
  if (type === 'number') {
    const n = Number(raw)
    return Number.isFinite(n) ? n : raw
  }
  return raw
}

export const isUserInputFieldFilled = (field: UserInputField, raw: string | undefined): boolean => {
  const type = normalizeFieldType(field.field_type)
  if (type === 'bool') return raw === 'true' || raw === 'false'
  return Boolean((raw ?? '').trim())
}

export const seedUserInputValues = (schema: UserInputField[]): Record<string, string> => {
  const seed: Record<string, string> = {}
  for (const field of schema) {
    seed[field.name] = normalizeFieldType(field.field_type) === 'bool' ? 'false' : ''
  }
  return seed
}

export const buildUserInputPayload = (
  schema: UserInputField[],
  values: Record<string, string>,
  freeText: string,
): Record<string, string | number | boolean> => {
  if (!schema.length) return { response: freeText.trim() }
  return Object.fromEntries(
    schema.map((field) => [field.name, coerceUserInputValue(field, values[field.name] ?? '')]),
  )
}
