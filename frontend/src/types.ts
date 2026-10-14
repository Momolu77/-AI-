export type Page = 'tasks' | 'task' | 'example' | 'textbook' | 'workbench'
export interface Occurrence {
  event_id: string
  occurred_at: string
  transport: {
    producer_id: string
    producer_seq: number
    raw_time: string | null
    monotonic_ms: number | null
    clock_calibration_id: string | null
    time_source: 'client_clock' | 'iframe_clock' | 'server_clock' | 'unknown_legacy'
    action_id?: string | null
    causal_parent_ids: string[]
    client_sequence_no?: number | null
  }
}
export interface TaskSummary {
  task_id: string
  assignment_id: string
  title: string
  summary: string
  active_session_id: string | null
}
export interface Resource {
  id: string
  version: string
  title: string
  type: 'textbook' | 'asset'
  mime: string
  extracted_text: string
  ai_input_status: 'ready' | 'unsupported' | 'failed'
  reference_mode?: 'current_page' | 'resource'
  page_count?: number
  pages?: { page: number; printed_page: string | number | null; text: string; ai_input_status: string }[]
}
export interface ResourceReference {
  reference_id: string
  resource_id: string
  resource_version: string
  draft_id: string
  draft_revision: number
  page: number | null
  fragment: string | null
  reference_purpose: string | null
  reference_note: string | null
  printed_page?: string | number | null
  status: string
}
export interface Proposal {
  id: string
  response_id: string
  base_code_revision: number
  proposal_content_ref: string
  title: string
  code: string
  decision: 'accept' | 'reject' | null
}
export interface Application {
  application_id: string
  proposal_id: string
  status: 'APPLIED' | 'FAILED'
  code_revision?: number
  content?: string
  error_message?: string
}
export interface Session {
  id: string
  session_id: string
  participant_id: string
  seat_no: string
  task_id: string
  task_version: string
  status: 'PREPARING' | 'ACTIVE' | 'ENDING' | 'ENDED' | 'ABANDONED'
  prerequisite: {
    version: string
    responses: { question_id: string; answer_value: string | number | null }[]
  } | null
  schema_version: string
  writer_id: string
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
  version: string
  media_type: 'video' | 'web'
}
export interface Task {
  task_id: string
  version: string
  title: string
  description: string
  task_content_version?: string
  rubric_version?: string
  basic_requirements?: string[]
  rubric?: { dimension: string; description: string }[]
  constraints: string[]
  examples: Example[]
  upload: { max_bytes: number; types: string }
  ai_provider: string
  prerequisite: {
    version: string
    questions: { id: string; label: string; allow_refusal?: boolean; options: { value: string | number; label: string }[] }[]
  }
}
export interface Revision {
  revision: number
  content: string
  content_ref: string | null
}
export interface EditChange {
  operation: 'insert' | 'delete' | 'replace' | 'undo' | 'redo'
  base_revision: number
  result_revision: number
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
export interface AICommand extends Occurrence {
  draft_revision: number
  reference_ids: string[]
  base_code_revision: number
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
  content_revision: number
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
export interface PreviewMessage extends Occurrence {
  load_id?: string | null
  message_id: string
  channel: string
  kind: 'ready' | 'log' | 'warn' | 'error' | 'interaction'
  text?: string
  error_type?: string
  error_phase?: 'load' | 'interaction'
  line?: number | null
  column?: number | null
  stack?: string | null
  interaction_type?: 'activate' | 'change' | 'input_commit' | 'submit'
  target?: { tag: string; id: string | null; role: string | null; label: string }
  outcome_source?: 'artifact' | 'unknown'
  outcome?: string | null
}
export interface ConsoleRow {
  id: string
  run_id: string
  message: PreviewMessage
}
export interface SubmissionCommand extends Occurrence {
  design_rationale?: string | null
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
  request_drafts: {
    id: string
    content: string
    revision: number
    reference_ids: string[]
    attachment_ids: string[]
  }[]
  resource_references: ResourceReference[]
  ai_proposals: Proposal[]
  proposal_applications: Application[]
  preview_runs: (Run & { id: string; status: string; command: { content: string } })[]
}
