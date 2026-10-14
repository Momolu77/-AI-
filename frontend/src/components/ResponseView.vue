<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import type { AIResponse } from '../types'
import { useWorkbench } from '../stores/workbench'
import { SourceMarkdown } from '../services/markdown-source'
import { visibleTextRanges } from '../services/visible-text'
const props = defineProps<{ response: AIResponse }>(),
  store = useWorkbench(),
  host = ref<HTMLElement>()
let first = true,
  complete = false,
  last = '',
  frame = 0,
  observer: ResizeObserver
function measure() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    if (!host.value || !store.active || !props.response.response_text) return
    const clip = host.value.closest<HTMLElement>('.messages')!,
      visible_ranges = visibleTextRanges(host.value, clip)
    const display_stage = first
      ? 'first_chunk'
      : !complete && ['SUCCEEDED', 'PARTIAL', 'FAILED'].includes(props.response.status)
        ? 'complete'
        : 'visibility_change'
    const value = {
      request_id: props.response.request_id,
      response_id: props.response.id,
      display_stage,
      content_revision: props.response.content_revision,
      rendered_range: { start: 0, end: props.response.response_text.length },
      visible_ranges,
      is_visible: visible_ranges.length > 0,
    }
    const fingerprint = JSON.stringify(value)
    if (fingerprint === last) return
    store.collector?.track('ai_response_displayed', value)
    last = fingerprint
    first = false
    if (display_stage === 'complete') complete = true
  })
}
watch(
  () => [props.response.response_text, props.response.status, store.page, store.fullscreen],
  async () => {
    await nextTick()
    measure()
  },
)
onMounted(() => {
  document.addEventListener('scroll', measure, true)
  document.addEventListener('visibilitychange', measure)
  observer = new ResizeObserver(measure)
  observer.observe(host.value!)
  measure()
})
onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
  document.removeEventListener('scroll', measure, true)
  document.removeEventListener('visibilitychange', measure)
})
</script>
<template>
  <div
    ref="host"
    class="markdown"
    :data-response-id="response.id"
    :data-revision="response.content_revision"
  >
    <SourceMarkdown :text="response.response_text" />
  </div>
</template>
