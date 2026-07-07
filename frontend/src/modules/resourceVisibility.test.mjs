import assert from "node:assert/strict"
import {
  nextResourceVisibility,
  normalizeResourceVisibility,
  resourceVisibilityOptions,
} from "./resourceVisibility.ts"

assert.equal(normalizeResourceVisibility(undefined), "private")
assert.equal(normalizeResourceVisibility("public"), "public")
assert.equal(normalizeResourceVisibility("private"), "private")
assert.equal(normalizeResourceVisibility("unexpected"), "private")
assert.equal(nextResourceVisibility("private"), "public")
assert.equal(nextResourceVisibility("public"), "private")
assert.deepEqual(
  resourceVisibilityOptions.map((option) => option.value),
  ["private", "public"],
)
