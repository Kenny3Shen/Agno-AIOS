# API Composables Split Design

## Goal

Split the aggregate frontend API surface into real same-level domain composable modules.

## Current Status

This design was the first-stage frontend API split. The latest implementation
removes `frontend/src/composables/useApi.ts` entirely: Vue pages import their
domain composables directly. OS control was later split again by functional area;
the intermediate control-plane composable was removed with the old aggregate runtime facade.

## Constraints

- Do not add nested API module directories for this step.
- Do not create pass-through domain wrappers.
- Each new file must own request logic for at least one real domain hook.
- Do not keep an aggregate API barrel; components import domain composables directly.
- Keep behavior and endpoint payloads unchanged.

## Module Boundary

- `useApiCore.ts`: shared fallback key type, i18n message helper, response error parsing, unknown error fallback, and clean query param helper.
- `useSecurityDataApi.ts`: CVE and URL-to-Markdown APIs.
- `useChatApi.ts`: streaming chat and chat session history APIs.
- `useMemoryControlApi.ts`: Agno user memory list/update/delete APIs.
- `useApprovalsApi.ts`: Agno approval list/detail/resolve APIs.
- `useSchedulerApi.ts`: AgentOS scheduler adapter APIs.
- `useSettingsApi.ts`: settings, model config, and model connectivity APIs.
- `useTraceApi.ts`: trace list/detail APIs.
- `useRuntimeToolsApi.ts`: Skills and MCP APIs.
- `useKnowledgeApi.ts`: Knowledge document, search, visibility, rebuild, and RAG settings APIs.
- `useAgentEvalsApi.ts`: Agent evaluation APIs.

## Testing

`frontend/src/modules/apiComposablesSourceContracts.test.mjs` enforces that:

- all same-level composable files exist,
- `useApi.ts` does not exist,
- domain files contain the hooks and endpoint logic they own,
- shared helpers live in `useApiCore.ts`.

Behavior is verified by existing shell/auth/build commands.
