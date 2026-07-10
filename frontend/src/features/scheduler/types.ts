export interface Schedule { id: string; name: string; description?: string; endpoint: string; cron_expr: string; timezone: string; enabled: boolean; next_run_at?: number; payload?: Record<string, unknown> }
export interface ScheduleRun { id: string; schedule_id: string; status: string; run_id?: string; session_id?: string; triggered_at?: number; completed_at?: number; error?: string }
