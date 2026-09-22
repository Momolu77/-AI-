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
