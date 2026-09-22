import { describe, expect, it } from 'vitest'
import { diff, EditBuffer, replay } from '../../src/services/edits'

describe('编辑差分与边界', () => {
  it.each([
    ['', '中文😀 hello'],
    ['hello', ''],
    ['apple', 'apply'],
    ['中😀文', '中🍎文'],
    ['a\nb', 'a\nnew\nb'],
  ])('可重放 %s → %s', (before, after) => {
    const change = diff(before, after)!
    expect(replay(before, [change])).toBe(after)
    expect(replay(after, [diff(after, before)!])).toBe(before)
  })
  it('合并多轮编辑、清空与撤销；无修改不创建事件', () => {
    const buffer = new EditBuffer(),
      texts = ['', 'abc', 'abc你好', 'abc', '']
    expect(buffer.take()).toBeNull()
    for (let i = 1; i < texts.length; i++)
      buffer.add(diff(texts[i - 1]!, texts[i]!)!, i - 1, new Date().toISOString())
    const result = buffer.take()!
    expect(replay('', result.changes)).toBe('')
    expect(result.base).toBe(0)
    expect(result.changes).toHaveLength(4)
    expect(buffer.take()).toBeNull()
    expect(diff('same', 'same')).toBeNull()
  })
})
