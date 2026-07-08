import type { WorkbenchRecord } from "../types"

export const statusTone = (status: string) => {
  const text = status.toLowerCase()
  if (["online", "ready", "enabled", "active", "completed", "stored", "success", "approved"].includes(text)) return "green"
  if (["pending", "draft", "idle", "loading", "running", "paused"].includes(text)) return "yellow"
  if (["error", "failed", "disabled", "cancelled", "timeout", "rejected"].includes(text)) return "red"
  return "blue"
}

export const formatTime = (value?: string | number | null, locale = "en-US") => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString(locale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export const compactValue = (value: unknown, locale = "en-US") => {
  const text = typeof value === "string" ? value : JSON.stringify(value)
  if (!text) return "-"
  if (/^\d{4}-\d{2}-\d{2}T/.test(text)) return formatTime(text, locale)
  return text.length > 48 ? `${text.slice(0, 45)}...` : text
}

export const formatJson = (value: unknown) => {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return String(value ?? "")
  }
}

export const parsePayloadJson = (value: string) => {
  if (!value.trim()) return {}
  const parsed = JSON.parse(value) as unknown
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid")
  return parsed as Record<string, unknown>
}

export const isIdEntry = (key: string, value: unknown) => {
  if (value == null || value === "") return false
  return key.toLowerCase().endsWith("id") || key.toLowerCase().includes("_id")
}

export const metaEntries = (record: WorkbenchRecord) => {
  return Object.entries(record.meta || {})
    .filter(([, value]) => value !== "" && value !== false && value != null)
    .slice(0, 6)
}
