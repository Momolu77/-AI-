<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { TextLayer, type PDFDocumentProxy, type PDFPageProxy, type RenderTask } from 'pdfjs-dist'
const props = defineProps<{ document: PDFDocumentProxy; page: number; scale: number; thumbnail?: boolean }>()
const emit = defineEmits<{ rendered: [] }>()
const canvas = ref<HTMLCanvasElement>(), text = ref<HTMLElement>(), host = ref<HTMLElement>()
let renderTask: RenderTask | undefined, layer: TextLayer | undefined, generation = 0
let cachedPage: PDFPageProxy | undefined
async function render() {
  const own = ++generation
  renderTask?.cancel(); layer?.cancel()
  try {
    const page = cachedPage || await props.document.getPage(props.page)
    cachedPage = page
    if (own !== generation || !canvas.value || !host.value) return
    const viewport = page.getViewport({ scale: props.scale })
    const ratio = props.thumbnail ? 1 : Math.min(devicePixelRatio, 2)
    host.value.style.width = `${viewport.width}px`; host.value.style.height = `${viewport.height}px`
    host.value.style.setProperty('--scale-factor', String(viewport.scale))
    host.value.style.setProperty('--total-scale-factor', String(viewport.scale))
    host.value.style.setProperty('--scale-round-x', '1px')
    host.value.style.setProperty('--scale-round-y', '1px')
    canvas.value.width = Math.ceil(viewport.width * ratio); canvas.value.height = Math.ceil(viewport.height * ratio)
    canvas.value.style.width = `${viewport.width}px`; canvas.value.style.height = `${viewport.height}px`
    renderTask = page.render({ canvas: canvas.value, viewport, transform: [ratio, 0, 0, ratio, 0, 0] })
    await renderTask.promise
    if (own !== generation) return
    if (!props.thumbnail && text.value) {
      text.value.replaceChildren()
      layer = new TextLayer({ textContentSource: await page.getTextContent(), container: text.value, viewport })
      await layer.render()
    }
    emit('rendered')
  } catch (error) {
    if (own === generation && (error as Error).name !== 'RenderingCancelledException') host.value?.setAttribute('data-render-error', (error as Error).message)
  }
}
onMounted(render)
watch(() => props.scale, render, { flush: 'sync' })
onBeforeUnmount(() => { generation++; renderTask?.cancel(); layer?.cancel() })
</script>
<template><div ref="host" class="pdf-sheet"><canvas ref="canvas"></canvas><div v-if="!thumbnail" ref="text" class="textLayer"></div></div></template>
