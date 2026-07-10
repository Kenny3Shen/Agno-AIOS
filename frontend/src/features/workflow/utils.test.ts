import { describe, expect, it } from 'vitest'
import { buildWorkflowCode, moveStep } from './utils'
import type { WorkflowState } from './types'
const state: WorkflowState = { name: 'IR', description: 'response', input: 'alert', sessionId: 's1', selectedId: null, steps: [{ id: 'a', kind: 'agent', targetId: 'triage', name: 'Triage', instructions: 'inspect' }, { id: 'b', kind: 'team', targetId: 'soc', name: 'SOC', instructions: 'contain' }] }
describe('workflow behavior', () => { it('reorders steps without mutating the source', () => { const moved = moveStep(state.steps, 'a', 1); expect(moved.map((item) => item.id)).toEqual(['b', 'a']); expect(state.steps.map((item) => item.id)).toEqual(['a', 'b']) }); it('preserves execution and session settings in generated code', () => { const code = buildWorkflowCode(state); expect(code).toContain('executor_id'); expect(code).toContain('session_id="s1"'); expect(code).toContain('stream_events=True') }) })
