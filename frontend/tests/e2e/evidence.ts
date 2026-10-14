import type { Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const observed = new WeakSet<Page>()
export function captureEvents(page: Page) {
  if (observed.has(page)) return
  observed.add(page)
  page.on('request', (request) => {
    if (!request.url().endsWith('/api/v1/events/batch') || request.method() !== 'POST') return
    const batch = request.postDataJSON() as { session_id: string; events: { event_id: string }[] }
    const run = JSON.parse(
      fs.readFileSync(path.resolve('../artifacts/e2e-current.json'), 'utf8'),
    ) as { data_dir: string }
    fs.appendFileSync(
      path.join(run.data_dir, 'expected-client-events.jsonl'),
      batch.events
        .map((e) => JSON.stringify({ session_id: batch.session_id, event_id: e.event_id }))
        .join('\n') + '\n',
    )
  })
}
