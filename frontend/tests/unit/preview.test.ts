import { expect, it } from 'vitest'
import { validatePreview } from '../../src/services/preview'
it('仅接受当前 iframe、run 和随机通道；不依赖不透明 origin', () => {
  const data = {
    app: 'teaching-preview',
    event_id: 'event',
    message_id: 'event',
    occurred_at: new Date().toISOString(),
    transport: {
      producer_id: 'frame',
      producer_seq: 1,
      raw_time: new Date().toISOString(),
      monotonic_ms: 1,
      clock_calibration_id: null,
      time_source: 'iframe_clock',
      action_id: 'event',
      causal_parent_ids: [],
    },
    run_id: 'run-1',
    channel: 'secret',
    kind: 'error',
    text: 'raw error',
    line: null,
  }
  const run = { run_id: 'run-1', channel: 'secret' }
  const event = new MessageEvent('message', { data, source: window, origin: 'null' })
  expect(validatePreview(event, window, run)?.text).toBe('raw error')
  expect(validatePreview(event, null, run)).toBeNull()
  expect(validatePreview(event, window, { ...run, run_id: 'old' })).toBeNull()
  expect(validatePreview(event, window, { ...run, channel: 'wrong' })).toBeNull()
  expect(
    validatePreview(
      new MessageEvent('message', { data: { ...data, kind: 'mousemove' }, source: window }),
      window,
      run,
    ),
  ).toBeNull()
})
