import userEvent from '@testing-library/user-event'

const options = {
  delay: null,
  pointerEventsCheck: 0,
} as const

/** Prefer instant user events in unit tests; use real timers only when testing animations. */
export const setupUser = () => userEvent.setup(options)

/**
 * Shared instant user-event instance for simple click/type flows.
 * Prefer setupUser() when a test needs an isolated session.
 */
export const user = userEvent.setup(options)
