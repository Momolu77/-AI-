// Source text is rendered literally, so DOM UTF-16 offsets map directly to archived text.
export function visibleTextRanges(host: HTMLElement, clip: HTMLElement) {
  if (document.hidden || !host.checkVisibility()) return []
  const bounds = clip.getBoundingClientRect(),
    result: { start: number; end: number }[] = []
  const top = Math.max(0, bounds.top),
    bottom = Math.min(innerHeight, bounds.bottom),
    left = Math.max(0, bounds.left),
    right = Math.min(innerWidth, bounds.right)
  for (const line of host.querySelectorAll<HTMLElement>('[data-offset]')) {
    const box = line.getBoundingClientRect()
    if (box.bottom <= top || box.top >= bottom) continue
    const node = line.firstChild
    if (!node) continue
    const base = Number(line.dataset.offset),
      text = node.textContent || '',
      range = document.createRange()
    for (let i = 0; i < text.length; i++) {
      range.setStart(node, i)
      range.setEnd(node, i + 1)
      const r = range.getBoundingClientRect()
      if (r.bottom > top && r.top < bottom && r.right > left && r.left < right) {
        const previous = result.at(-1)
        if (previous?.end === base + i) previous.end++
        else result.push({ start: base + i, end: base + i + 1 })
      }
    }
  }
  return result
}
export function sourceLines(text: string) {
  let offset = 0
  return (text.match(/[^\n]*\n|[^\n]+$/g) || []).map((content) => {
    const item = { offset, content }
    offset += content.length
    return item
  })
}
