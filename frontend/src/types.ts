export interface Session {
  id: string
  session_id: string
  participant_id: string
  seat_no: string
  task_id: string
  task_version: string
  status: 'ACTIVE' | 'ENDED'
  started_at: string
  ended_at: string | null
  server_now: string
  heartbeat_interval_sec: number
  token?: string
}
export interface Example {
  id: string
  title: string
  description: string
  url: string
  duration: number
}
export interface Task {
  task_id: string
  version: string
  title: string
  description: string
  constraints: string[]
  examples: Example[]
  upload: { max_bytes: number; types: string }
  ai_provider: string
}
export interface Revision {
  revision: number
  content: string
  content_ref: string | null
}
export interface EditChange {
  operation: 'insert' | 'delete' | 'replace'
  inserted_text: string
  deleted_text: string
  edit_range: { start: number; end: number }
}
export interface Attachment {
  id: string
  file_name: string
  status: 'SELECTED' | 'UPLOADING' | 'PROCESSING' | 'READY' | 'FAILED' | 'REMOVED'
  error_message?: string
  file_size: number
  file?: File
}
export interface AICommand {
  request_id: string
  draft_id: string
  message_text: string
  attachment_ids: string[]
  retry_of_request_id: string | null
  occurred_at: string
}
export interface AIRequest {
  id: string
  command: AICommand
  status: 'QUEUED' | 'STREAMING' | 'SUCCEEDED' | 'FAILED'
  response_id: string
  error?: { error_message: string; retryable: boolean }
}
export interface AIResponse {
  id: string
  request_id: string
  response_text: string
  status: string
  model_name: string
}
export interface Run {
  run_id: string
  channel: string
  url: string
  code_revision: number
}
export interface PreviewMessage {
  message_id: string
  channel: string
  kind: 'ready' | 'log' | 'warn' | 'error' | 'interaction'
  text?: string
  error_type?: string
  error_phase?: 'load' | 'interaction'
  line?: number | null
  column?: number | null
  stack?: string | null
  interaction_type?: 'click' | 'change' | 'submit'
  target?: string
  outcome?: string | null
}
export interface ConsoleRow {
  id: string
  run_id: string
  message: PreviewMessage
}
export interface SubmissionCommand {
  submission_id: string
  snapshot_id: string
  code: string
  plan: string
  code_revision: number
  plan_revision: number
  occurred_at: string
}
export interface Submission {
  id: string
  status: 'PENDING' | 'SUCCEEDED' | 'FAILED'
  command: SubmissionCommand
  error_message?: string
}
export interface WorkbenchState {
  code: Revision
  plan: Revision
  attachments: Attachment[]
  ai_requests: AIRequest[]
  ai_responses: AIResponse[]
  submissions: Submission[]
  preview_logs: ConsoleRow[]
  task_viewed: boolean
}
