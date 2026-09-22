import { z } from 'zod'
import { reactive } from 'vue'
import { database } from './storage'
import { api, post } from './api'

const integer = z.number().int().nonnegative(),
  id = z.string().regex(/^[A-Za-z0-9_-]{1,80}$/)
const range = z.strictObject({ start: integer, end: integer })
const changes = z
  .array(
    z.strictObject({
      operation: z.enum(['insert', 'delete', 'replace']),
      inserted_text: z.string(),
      deleted_text: z.string(),
      edit_range: range,
    }),
  )
  .min(1)
const edit = {
  edit_changes: changes,
  content_length_after: integer,
  edit_started_at: z.iso.datetime({ offset: true }),
  last_edit_at: z.iso.datetime({ offset: true }),
  flush_reason: z.enum(['close', 'run', 'send', 'leave', 'submit', 'end', 'paste']),
}
export const eventSchemas = {
  task_viewed: z.strictObject({ task_content_version: z.string() }),
  example_opened: z.strictObject({ example_id: id }),
  example_closed: z.strictObject({
    example_id: id,
    last_position_sec: z.number().nonnegative(),
    watched_seconds: z.number().nonnegative(),
    close_reason: z.enum(['manual', 'navigate', 'end']),
  }),
  task_revisited: z.strictObject({ from_page: z.literal('workbench') }),
  workbench_entered: z.strictObject({ entry_source: z.enum(['first', 'return']) }),
  planner_opened: z.strictObject({}),
  planner_edited: z.strictObject({ ...edit, base_plan_revision: integer, plan_revision: integer }),
  ai_request_edited: z.strictObject({ ...edit, draft_id: id }),
  ai_response_copied: z.strictObject({ response_id: id, content_type: z.enum(['text', 'code']) }),
  code_pasted: z.strictObject({
    pasted_text: z.string(),
    paste_source: z.enum(['AI response', 'other']),
    source_response_id: id.nullable(),
    edit_range: range,
    code_revision: integer,
  }),
  code_edited: z.strictObject({ ...edit, base_code_revision: integer, code_revision: integer }),
  preview_error_copied: z.strictObject({ error_id: id }),
  window_left: z.strictObject({ leave_reason: z.string() }),
  window_returned: z.strictObject({ return_reason: z.string() }),
  submit_dialog_opened: z.strictObject({}),
  submit_cancelled: z.strictObject({}),
}
export type EventName = keyof typeof eventSchemas
export interface EventRecord {
  event_id: string
  event_name: EventName
  actor: 'student'
  occurred_at: string
  client_sequence_no: number
  payload: unknown
}
export interface Job {
  id: string
  session_id: string
  sequence: number
  event?: EventRecord
  path?: string
  body?: unknown
  status: 'pending' | 'rejected'
  attempts: number
  reason?: string
}

export class Collector {
  stats = reactive({ pending: 0, rejected: 0, error: '' })
  sending = false
  writeQueue: Promise<unknown> = Promise.resolve()
  constructor(
    public sid: string,
    public now: () => string,
  ) {}
  next() {
    const key = 'sequence:' + this.sid
    const n = Number(localStorage.getItem(key) || 0) + 1
    localStorage.setItem(key, String(n))
    return n
  }
  enqueue(job: Job) {
    // Synchronous journal covers unload before the IndexedDB transaction finishes.
    localStorage.setItem('journal:' + job.id, JSON.stringify(job))
    this.writeQueue = this.writeQueue
      .then(async () => {
        await (await database).put('outbox', job)
        localStorage.removeItem('journal:' + job.id)
        await this.refresh()
      })
      .catch((error: Error) => {
        this.stats.error = '本地采集存储失败：' + error.message
      })
    return this.writeQueue
  }
  track(name: EventName, payload: unknown = {}) {
    const value = eventSchemas[name].parse(payload),
      event_id = crypto.randomUUID(),
      sequence = this.next()
    void this.enqueue({
      id: event_id,
      session_id: this.sid,
      sequence,
      event: {
        event_id,
        event_name: name,
        actor: 'student',
        occurred_at: this.now(),
        client_sequence_no: sequence,
        payload: value,
      },
      status: 'pending',
      attempts: 0,
    })
    return event_id
  }
  job(path: string, body: unknown, id: string) {
    void this.enqueue({
      id,
      session_id: this.sid,
      sequence: this.next(),
      path,
      body,
      status: 'pending',
      attempts: 0,
    })
  }
  async recover() {
    for (const key of Object.keys(localStorage).filter((k) => k.startsWith('journal:'))) {
      const job = JSON.parse(localStorage.getItem(key)!) as Job
      if (job.session_id === this.sid) await this.enqueue(job)
    }
    await this.refresh()
  }
  async rows(): Promise<Job[]> {
    return (await database).getAllFromIndex('outbox', 'session_id', this.sid)
  }
  async refresh() {
    const rows = await this.rows()
    this.stats.pending = rows.filter((r) => r.status === 'pending').length
    this.stats.rejected = rows.length - this.stats.pending
  }
  async flush() {
    // Ending a session must await an in-flight periodic flush before draining newer entries.
    while (this.sending) await new Promise<void>((resolve) => setTimeout(resolve, 20))
    this.sending = true
    try {
      await this.writeQueue
      const db = await database,
        rows = (await this.rows())
          .filter((r) => r.status === 'pending')
          .sort((a, b) => a.sequence - b.sequence)
      for (let i = 0; i < rows.length; ) {
        if (rows[i].event) {
          const group: Job[] = []
          while (i < rows.length && rows[i].event && group.length < 50) group.push(rows[i++]!)
          const result = await post<{
            results: { event_id: string; status: string; reason?: string; retryable?: boolean }[]
          }>('/events/batch', { session_id: this.sid, events: group.map((r) => r.event) })
          for (const answer of result.results) {
            const row = group.find((r) => r.id === answer.event_id)
            if (!row) continue
            if (answer.status === 'accepted' || answer.status === 'accepted_duplicate')
              await db.delete('outbox', row.id)
            else {
              row.attempts++
              row.reason = answer.reason
              if (!answer.retryable) row.status = 'rejected'
              await db.put('outbox', row)
            }
          }
        } else {
          const row = rows[i++]!
          try {
            await api(row.path!, { method: 'POST', body: JSON.stringify(row.body) })
            await db.delete('outbox', row.id)
          } catch (error) {
            const e = error as Error & { retryable?: boolean }
            if (e.retryable === false) {
              row.status = 'rejected'
              row.reason = e.message
              await db.put('outbox', row)
            } else throw error
          }
        }
      }
      this.stats.error = ''
    } catch (error) {
      this.stats.error = (error as Error).message
    } finally {
      await this.refresh()
      this.sending = false
    }
  }
}
