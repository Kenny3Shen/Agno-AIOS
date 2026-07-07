# API Composables Split Design

## Goal

Split `frontend/src/composables/useApi.ts` into real same-level domain composable modules while keeping the existing import surface stable.

## Constraints

- Do not add nested API module directories for this step.
- Do not create pass-through domain wrappers.
- Each new file must own request logic for at least one real domain hook.
- Keep `frontend/src/composables/useApi.ts` as a compatibility re-export entry so existing Vue imports do not churn.
- Keep behavior and endpoint payloads unchanged.

## Module Boundary

- `useApiCore.ts`: shared fallback key type, i18n message helper, response error parsing, unknown error fallback, and clean query param helper.
- `useSecurityDataApi.ts`: CVE and URL-to-Markdown APIs.
- `useChatApi.ts`: streaming chat and chat session history APIs.
- `useControlPlaneApi.ts`: AgentOS/AIOS control-plane payload, memory mutation, approvals, and scheduler adapter APIs.
- `useSettingsApi.ts`: settings, model config, and model connectivity APIs.
- `useTraceApi.ts`: trace list/detail APIs.
- `useRuntimeToolsApi.ts`: Skills and MCP APIs.
- `useKnowledgeApi.ts`: Knowledge document, search, visibility, rebuild, and RAG settings APIs.
- `useAgentEvalsApi.ts`: Agent evaluation APIs.

## Testing

`frontend/src/modules/apiComposablesSourceContracts.test.mjs` enforces that:

- all same-level composable files exist,
- `useApi.ts` contains only re-exports and no request implementation,
- domain files contain the hooks and endpoint logic they own,
- shared helpers live in `useApiCore.ts`.

Behavior is verified by existing shell/auth/build commands.
