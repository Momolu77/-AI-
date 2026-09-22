import { openDB } from 'idb'
export const database = openDB('teaching-workbench-v1.1', 1, {
  upgrade(db) {
    db.createObjectStore('drafts')
    const outbox = db.createObjectStore('outbox', { keyPath: 'id' })
    outbox.createIndex('session_id', 'session_id')
  },
})
export async function readDraft<T>(sid: string): Promise<T | undefined> {
  return (await database).get('drafts', sid)
}
export async function writeDraft(sid: string, draft: unknown) {
  return (await database).put('drafts', structuredClone(draft), sid)
}
