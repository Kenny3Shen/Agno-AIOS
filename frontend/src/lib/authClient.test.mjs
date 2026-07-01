import assert from "node:assert/strict"
import test from "node:test"
import {
  AUTH_TOKEN_STORAGE_KEY,
  fetchCurrentUser,
  loginWithPassword,
  logout,
  registerWithPassword,
} from "../../dist-test/lib/authClient.js"

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function createStorage(initial = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem(key) {
      return data.get(key) ?? null
    },
    setItem(key, value) {
      data.set(key, String(value))
    },
    removeItem(key) {
      data.delete(key)
    },
  }
}

test("loginWithPassword submits FastAPI Users form data", async () => {
  const calls = []
  const fetchImpl = async (url, init) => {
    calls.push({ url, init })
    return jsonResponse({ access_token: "token-1", token_type: "bearer" })
  }

  const token = await loginWithPassword(
    { email: "operator@example.com", password: "correct horse battery" },
    { fetch: fetchImpl },
  )

  assert.equal(token.access_token, "token-1")
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, "/api/auth/jwt/login")
  assert.equal(calls[0].init.method, "POST")
  assert.equal(calls[0].init.headers["Content-Type"], "application/x-www-form-urlencoded")
  assert.equal(calls[0].init.body.get("username"), "operator@example.com")
  assert.equal(calls[0].init.body.get("password"), "correct horse battery")
})

test("registerWithPassword submits JSON registration payload", async () => {
  const calls = []
  const fetchImpl = async (url, init) => {
    calls.push({ url, init })
    return jsonResponse({ id: "user-1", email: "operator@example.com", is_active: true })
  }

  await registerWithPassword(
    { email: "operator@example.com", password: "correct horse battery" },
    { fetch: fetchImpl },
  )

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, "/api/auth/register")
  assert.equal(calls[0].init.method, "POST")
  assert.equal(calls[0].init.headers["Content-Type"], "application/json")
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    email: "operator@example.com",
    password: "correct horse battery",
  })
})

test("fetchCurrentUser sends Bearer token", async () => {
  const calls = []
  const fetchImpl = async (url, init) => {
    calls.push({ url, init })
    return jsonResponse({ id: "user-1", email: "operator@example.com", is_active: true })
  }

  const user = await fetchCurrentUser("token-1", { fetch: fetchImpl })

  assert.equal(user.email, "operator@example.com")
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, "/api/auth/users/me")
  assert.equal(calls[0].init.headers.Authorization, "Bearer token-1")
})

test("logout clears stored token even when server logout fails", async () => {
  const storage = createStorage({ [AUTH_TOKEN_STORAGE_KEY]: "token-1" })
  const calls = []
  const fetchImpl = async (url, init) => {
    calls.push({ url, init })
    return jsonResponse({ detail: "server error" }, 500)
  }

  await logout("token-1", { fetch: fetchImpl, storage })

  assert.equal(calls[0].url, "/api/auth/logout")
  assert.equal(calls[0].init.headers.Authorization, "Bearer token-1")
  assert.equal(storage.getItem(AUTH_TOKEN_STORAGE_KEY), null)
})
