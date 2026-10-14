import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Collector } from '../../src/services/events'
import { database } from '../../src/services/storage'

describe('持久化事件 outbox', () => {
  beforeEach(async () => {
    localStorage.clear()
    await (await database).clear('outbox')
    vi.restoreAllMocks()
  })
  it('结束收尾等待正在发送的批次，并继续发送期间新写入的记录', async () => {
    const collector = new Collector('concurrent', () => '2026-09-22T00:00:00.000Z')
    const first = collector.track('planner_opened')
    let release!: (response: Response) => void
    const blocked = new Promise<Response>((resolve) => {
      release = resolve
    })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementationOnce(() => blocked)
    const periodic = collector.flush()
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const second = collector.track('submit_cancelled')
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [{ event_id: second, status: 'accepted' }] })),
    )
    const ending = collector.flush()
    release(new Response(JSON.stringify({ results: [{ event_id: first, status: 'accepted' }] })))
    await Promise.all([periodic, ending])
    expect(collector.stats.pending).toBe(0)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
  it('断网保留、部分成功与永久拒绝分开处理，传输重试保持原 ID', async () => {
    const collector = new Collector('session-one', () => '2026-09-22T00:00:00.000Z')
    const first = collector.track('planner_opened'),
      second = collector.track('submit_cancelled')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('offline'))
    await collector.flush()
    expect(collector.stats.pending).toBe(2)
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          results: [
            { event_id: first, status: 'accepted_duplicate' },
            { event_id: second, status: 'rejected', reason: 'schema', retryable: false },
          ],
        }),
      ),
    )
    await collector.flush()
    expect(collector.stats.pending).toBe(0)
    expect(collector.stats.rejected).toBe(1)
    const payload = JSON.parse(fetchMock.mock.calls[1]![1]!.body as string)
    expect(payload.events.map((e: { event_id: string }) => e.event_id)).toEqual([first, second])
    expect((await collector.rows())[0]!.reason).toBe('schema')
  })
  it('同步应急日志能恢复到 IndexedDB，其他会话不会发送', async () => {
    const collector = new Collector('one', () => '2026-09-22T00:00:00.000Z')
    const job = {
      id: 'recover-id',
      session_id: 'one',
      sequence: 3,
      event: {
        event_id: 'recover-id',
        event_name: 'planner_opened',
        actor: 'student',
        occurred_at: '2026-09-22T00:00:00.000Z',
        client_sequence_no: 3,
        payload: {},
      },
      status: 'pending',
      attempts: 0,
    }
    localStorage.setItem('journal:recover-id', JSON.stringify(job))
    await collector.recover()
    expect((await collector.rows())[0]!.id).toBe('recover-id')
    expect(await new Collector('two', collector.now).rows()).toHaveLength(0)
    expect(localStorage.getItem('journal:recover-id')).toBeNull()
  })
})
