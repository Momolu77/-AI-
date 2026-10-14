import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { SourceMarkdown } from '../../src/services/markdown-source'
it('Markdown text and highlighted code retain exact UTF-16 source offsets without executable HTML', () => {
  const source =
    '# Hello **world😀**\n\n- first\n- second\n\n```html\n<button>😀</button>\n```\n\n<script>window.bad=true</script>\n\n```proposal\n{"title":"提议","code":"private-proposal-json"}\n```\n\n最后一段'
  const wrapper = mount(SourceMarkdown, { props: { text: source } })
  expect(wrapper.find('h1 strong').text()).toBe('world😀')
  expect(wrapper.find('script').exists()).toBe(false)
  expect(wrapper.find('code').text()).toBe('<button>😀</button>')
  expect(wrapper.text()).not.toContain('private-proposal-json')
  for (const span of wrapper.findAll('[data-offset]')) {
    const offset = Number(span.attributes('data-offset')),
      text = span.element.textContent || ''
    expect(source.slice(offset, offset + text.length)).toBe(text)
  }
})
