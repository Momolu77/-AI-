import { defineComponent, h, type VNode } from 'vue'
import { marked } from 'marked'

interface SourceToken {
  type: string
  raw: string
  text?: string
  depth?: number
  lang?: string
  ordered?: boolean
  tokens?: SourceToken[]
  items?: SourceToken[]
}
const span = (text: string, offset: number, klass?: string) =>
  h('span', { 'data-offset': offset, class: klass }, text)
function code(text: string, offset: number) {
  const parts: VNode[] = []
  const pattern =
    /<!--[\s\S]*?-->|<\/?[\w-]+|"[^"\n]*"|'[^'\n]*'|\b(?:function|const|let|return|if|else|true|false)\b/g
  let cursor = 0
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) parts.push(span(text.slice(cursor, match.index), offset + cursor))
    parts.push(span(match[0], offset + match.index, 'syntax-token'))
    cursor = match.index + match[0].length
  }
  if (cursor < text.length) parts.push(span(text.slice(cursor), offset + cursor))
  return parts
}
function render(tokens: SourceToken[], source: string, offset: number): VNode[] {
  const result: VNode[] = []
  let cursor = 0
  for (const token of tokens) {
    const start = source.indexOf(token.raw, cursor)
    if (start < 0) {
      result.push(span(source.slice(cursor), offset + cursor))
      return result
    }
    if (start > cursor) result.push(span(source.slice(cursor, start), offset + cursor))
    const raw = token.raw,
      base = offset + start,
      text = token.text || '',
      inside =
        token.type === 'code' && /^(```|~~~)/.test(raw)
          ? raw.indexOf(text, raw.indexOf('\n') + 1)
          : raw.indexOf(text)
    const children = () =>
      token.tokens && inside >= 0
        ? render(token.tokens, text, base + inside)
        : [span(inside >= 0 ? text : raw, base + (inside >= 0 ? inside : 0))]
    if (token.type === 'code' && token.lang === 'proposal') {
      try {
        const proposal = JSON.parse(text)
        if (typeof proposal.title === 'string' && typeof proposal.code === 'string') {
          result.push(h('p', { class: 'subtle' }, '代码提议已生成，可在下方查看改动。'))
          cursor = start + raw.length
          continue
        }
      } catch {
        /* An incomplete or invalid block remains visible as ordinary text. */
      }
    }
    if (token.type === 'code')
      result.push(
        h('pre', {}, [
          h(
            'code',
            { 'data-content-type': 'code' },
            code(inside >= 0 ? text : raw, base + Math.max(0, inside)),
          ),
        ]),
      )
    else if (token.type === 'codespan')
      result.push(h('code', { 'data-content-type': 'code' }, children()))
    else if (token.type === 'heading')
      result.push(h('h' + Math.min(6, token.depth || 2), {}, children()))
    else if (token.type === 'paragraph') result.push(h('p', {}, children()))
    // Keep source offsets while letting block margins handle Markdown separators.
    else if (token.type === 'space') result.push(span(raw, base, 'markdown-space'))
    else if (['strong', 'em', 'del'].includes(token.type))
      result.push(h(token.type, {}, children()))
    else if (token.type === 'list' && token.items)
      result.push(
        h(
          token.ordered ? 'ol' : 'ul',
          {},
          token.items.map((item) =>
            h(
              'li',
              {},
              render(
                item.tokens || [],
                item.text || item.raw,
                base + raw.indexOf(item.raw) + Math.max(0, item.raw.indexOf(item.text || item.raw)),
              ),
            ),
          ),
        ),
      )
    else if (token.type === 'text' || token.type === 'link') result.push(h('span', {}, children()))
    else result.push(span(raw, base))
    cursor = start + raw.length
  }
  if (cursor < source.length) result.push(span(source.slice(cursor), offset + cursor))
  return result
}
// Only Vue text nodes and a fixed tag allowlist are produced; model HTML is never executed.
export const SourceMarkdown = defineComponent({
  props: { text: { type: String, required: true } },
  setup: (props) => () =>
    h('div', {}, render(marked.lexer(props.text) as SourceToken[], props.text, 0)),
})
