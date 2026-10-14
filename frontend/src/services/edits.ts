import type { EditChange } from '../types'

// CodeMirror and browser selections use UTF-16 code unit offsets (not Unicode code points).
export function diff(before: string, after: string): EditChange | null {
  if (before === after) return null
  let start = 0,
    endBefore = before.length,
    endAfter = after.length
  while (start < endBefore && start < endAfter && before[start] === after[start]) start++
  while (endBefore > start && endAfter > start && before[endBefore - 1] === after[endAfter - 1]) {
    endBefore--
    endAfter--
  }
  const inserted_text = after.slice(start, endAfter),
    deleted_text = before.slice(start, endBefore)
  return {
    base_revision: 0,
    result_revision: 1,
    operation: inserted_text ? (deleted_text ? 'replace' : 'insert') : 'delete',
    inserted_text,
    deleted_text,
    edit_range: { start, end: endBefore },
  }
}
export function replay(text: string, changes: EditChange[]) {
  for (const c of changes) {
    if (text.slice(c.edit_range.start, c.edit_range.end) !== c.deleted_text)
      throw new Error('删除内容与差分范围不一致')
    text = text.slice(0, c.edit_range.start) + c.inserted_text + text.slice(c.edit_range.end)
  }
  return text
}
export interface BufferData {
  changes: EditChange[]
  base: number
  started: string
  last: string
}
export class EditBuffer {
  data: BufferData = { changes: [], base: 0, started: '', last: '' }
  add(change: EditChange, base: number, now: string) {
    if (!this.data.changes.length) this.data = { changes: [], base, started: now, last: now }
    this.data.changes.push({ ...change, base_revision: base, result_revision: base + 1 })
    this.data.last = now
  }
  take() {
    const data = this.data
    this.data = { changes: [], base: 0, started: '', last: '' }
    return data.changes.length ? data : null
  }
}
