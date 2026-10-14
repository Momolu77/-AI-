import { reactive } from 'vue'
import { database } from './storage'
import { api, post } from './api'

import {
  eventSchemas,
  eventActors,
  eventOwners,
  schemaVersion as SCHEMA_VERSION,
} from '../generated/event-contract'
import type { Occurrence } from '../types'
export { eventSchemas }
export type EventName = keyof typeof eventSchemas
export interface EventRecord {
  event_id: string
  event_name: EventName
  actor: 'student' | 'system'
  schema_version: string
  transport: Occurrence['transport']
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
  producer = crypto.randomUUID()
  producerSeq = 0
  calibrationId: string | null = null
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
  occurrence(actionId: string | null = null): Occurrence {
    const event_id = crypto.randomUUID()
    return {
      event_id,
      occurred_at: this.now(),
      transport: {
        producer_id: this.producer,
        producer_seq: ++this.producerSeq,
        raw_time: new Date().toISOString(),
        monotonic_ms: performance.now(),
        clock_calibration_id: this.calibrationId,
        time_source: 'client_clock',
        action_id: actionId || event_id,
        causal_parent_ids: [],
        client_sequence_no: this.next(),
      },
    }
  }
  track(
    name: EventName,
    payload: unknown = {},
    context?: Occurrence,
    actor?: 'student' | 'system',
  ) {
    if (eventOwners[name] !== 'browser') throw new Error('此事件由业务服务记录')
    const value = eventSchemas[name].parse(payload),
      occurrence = context || this.occurrence()
    const event = {
      schema_version: SCHEMA_VERSION,
      ...occurrence,
      event_name: name,
      actor: actor || (eventActors[name] === 'system' ? 'system' : 'student'),
      client_sequence_no: occurrence.transport.client_sequence_no!,
      payload: value,
    }
    void this.enqueue({
      id: event.event_id,
      session_id: this.sid,
      sequence: event.client_sequence_no,
      event,
      status: 'pending',
      attempts: 0,
    })
    return event.event_id
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
