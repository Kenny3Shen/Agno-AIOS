import type { ResourceVisibility } from "../types"

export const resourceVisibilityOptions: Array<{ labelKey: string; value: ResourceVisibility }> = [
  { labelKey: "visibility.private", value: "private" },
  { labelKey: "visibility.public", value: "public" },
]

export const normalizeResourceVisibility = (value: unknown): ResourceVisibility => {
  return value === "public" || value === "private" ? value : "private"
}

export const nextResourceVisibility = (value: ResourceVisibility): ResourceVisibility => {
  return value === "public" ? "private" : "public"
}
