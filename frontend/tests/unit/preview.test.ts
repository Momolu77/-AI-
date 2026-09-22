import { expect, it } from 'vitest'
import { validatePreview } from '../../src/services/preview'
it('仅接受当前 iframe、run 和随机通道；不依赖不透明 origin', () => {
  const data = {
    app: 'teaching-preview',
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
