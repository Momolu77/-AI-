export interface CopyClaim {
  sid: string
  response: string
  text: string
}
const claims = new Map<string, CopyClaim>()
export function copyMarkup(claim: CopyClaim) {
  const token = crypto.randomUUID()
  claims.set(token, claim)
  return (
    '<span data-workbench-copy="' +
    token +
    '">' +
    claim.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') +
    '</span>'
  )
}
export function verifyPaste(event: ClipboardEvent): CopyClaim | null {
  const html = event.clipboardData?.getData('text/html') || '',
    text = event.clipboardData?.getData('text/plain') || ''
  const token = new DOMParser()
    .parseFromString(html, 'text/html')
    .querySelector('[data-workbench-copy]')
    ?.getAttribute('data-workbench-copy')
  const claim = token ? claims.get(token) : null
  return claim && claim.text === text ? claim : null
}
export function selectedSources() {
  const selection = getSelection()
  if (!selection || selection.isCollapsed || !selection.rangeCount) return []
  const result: {
    response: string
    revision: number
    type: 'code' | 'text'
    ranges: { start: number; end: number }[]
  }[] = []
  for (const rangeIndex of Array.from({ length: selection.rangeCount }, (_, i) => i)) {
    const range = selection.getRangeAt(rangeIndex)
    for (const el of document.querySelectorAll<HTMLElement>('[data-response-id] [data-offset]')) {
      const node = el.firstChild
      if (!node || !range.intersectsNode(node)) continue
      const start = range.startContainer === node ? range.startOffset : 0,
        end = range.endContainer === node ? range.endOffset : node.textContent!.length
      if (end <= start) continue
      const host = el.closest<HTMLElement>('[data-response-id]')!,
        response = host.dataset.responseId!,
        revision = Number(host.dataset.revision),
        type = el.closest('code') ? 'code' : 'text'
      let row = result.find((r) => r.response === response && r.type === type)
      if (!row) {
        row = { response, revision, type, ranges: [] }
        result.push(row)
      }
      row.ranges.push({
        start: Number(el.dataset.offset) + start,
        end: Number(el.dataset.offset) + end,
      })
    }
  }
  return result
}
