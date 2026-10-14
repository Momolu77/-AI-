import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkbench } from '../../src/stores/workbench'
import type { Attachment } from '../../src/types'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
})
it('发送按钮反映空输入、附件处理、失败与在途请求', () => {
  const store = useWorkbench()
  expect(store.sendBlock).toBeTruthy()
  store.session = {
    id: 's',
    session_id: 's',
    participant_id: 'p',
    seat_no: '01',
    task_id: 't',
    task_version: 'v',
    status: 'ACTIVE',
    prerequisite: null,
    schema_version: 'teaching-workbench-events-v1.3',
    writer_id: 'w',
    started_at: '',
    ended_at: null,
    server_now: '',
    heartbeat_interval_sec: 15,
  }
  store.editDraft('hello')
  expect(store.sendBlock).toBe('')
  const item: Attachment = { id: 'file', file_name: 'unit.txt', file_size: 3, status: 'PROCESSING' }
  store.selected.push(item)
  expect(store.sendBlock).toContain('附件')
  store.selected[0]!.status = 'FAILED'
  expect(store.sendBlock).toContain('附件')
  store.selected[0]!.status = 'READY'
  store.draft = ''
  expect(store.sendBlock).toBe('')
  store.requests.push({
    id: 'request',
    status: 'STREAMING',
    response_id: 'response',
    command: {
      event_id: 'event',
      transport: {
        producer_id: 'browser',
        producer_seq: 1,
        raw_time: null,
        monotonic_ms: null,
        clock_calibration_id: null,
        time_source: 'client_clock',
        causal_parent_ids: [],
      },
      draft_revision: 0,
      reference_ids: [],
      base_code_revision: 0,
      request_id: 'request',
      draft_id: 'draft',
      message_text: 'hi',
      attachment_ids: [],
      retry_of_request_id: null,
      occurred_at: '',
    },
  })
  expect(store.sendBlock).toContain('生成')
  vi.useRealTimers()
})
