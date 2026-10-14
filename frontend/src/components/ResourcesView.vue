<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'
import PdfPage from './PdfPage.vue'
import { useWorkbench } from '../stores/workbench'
import { getToken } from '../services/api'
import type { Resource } from '../types'
GlobalWorkerOptions.workerSrc = workerUrl
const store = useWorkbench(), selected = ref<Resource | null>(null), documentPdf = shallowRef<PDFDocumentProxy>(),
  viewer = ref<HTMLElement>(), thumbnailList = ref<HTMLElement>(), pageInput = ref<HTMLInputElement>(), current = ref(1), scale = ref(1), thumbnails = ref(true), loading = ref(false),
  failure = ref(''), target = ref(1), purpose = ref(''), note = ref(''), adding = ref(false)
const pages = computed(() => selected.value?.pages || []),
  currentData = computed(() => pages.value.find(p => p.page === current.value)),
  canReference = computed(() => store.active && currentData.value?.ai_input_status === 'ready' && !loading.value && !failure.value)
let instance = '', timer: ReturnType<typeof setTimeout>, opened = false, generation = 0, explicitPageUntil = 0
let pendingPage: number | null = null
const key = () => 'reader:' + store.session?.id + ':' + selected.value?.id + ':' + selected.value?.version
function base() { return { resource_id: selected.value!.id, resource_version: selected.value!.version, viewer_instance_id: instance } }
function locator() { return { page: current.value, fragment: null, visible_range: null } }
function savePosition() {
  if (selected.value && viewer.value) localStorage.setItem(key(), JSON.stringify({ page: current.value, scroll: viewer.value.scrollTop, scale: scale.value, thumbnails: thumbnails.value }))
}
function measure() {
  if (!viewer.value || store.page !== 'textbook' || document.hidden) return
  if (Date.now() < explicitPageUntil) return
  const rect = viewer.value.getBoundingClientRect()
  let best = 0, page = 0
  for (const item of viewer.value.querySelectorAll<HTMLElement>('[data-pdf-page]')) {
    const box = item.getBoundingClientRect()
    const area = Math.max(0, Math.min(rect.bottom, box.bottom) - Math.max(rect.top, box.top)) * Math.max(0, Math.min(rect.right, box.right) - Math.max(rect.left, box.left))
    if (area > best) { best = area; page = Number(item.dataset.pdfPage) }
  }
  if (page) {
    current.value = page
    if (document.activeElement !== pageInput.value) target.value = page
  }
}
function changed() {
  clearTimeout(timer)
  timer = setTimeout(() => {
    measure(); savePosition()
    if (opened && store.active && store.page === 'textbook' && !document.hidden) store.collector?.track('resource_view_changed', { ...base(), ...locator() })
  }, 250)
}
function syncThumbnail() {
  const list = thumbnailList.value
  const item = list?.querySelector<HTMLElement>('[data-thumbnail-page="' + current.value + '"]')
  if (!list || !item || !thumbnails.value) return
  const box = item.getBoundingClientRect(), bounds = list.getBoundingClientRect()
  if (box.top < bounds.top) list.scrollTop += box.top - bounds.top
  else if (box.bottom > bounds.bottom) list.scrollTop += box.bottom - bounds.bottom
}
function alignPage(page: number) {
  const item = viewer.value?.querySelector<HTMLElement>('[data-pdf-page="' + page + '"]')
  if (item && viewer.value) viewer.value.scrollTop += item.getBoundingClientRect().top - viewer.value.getBoundingClientRect().top - 20
}
function rendered(page: number) {
  if (pendingPage !== null && page <= pendingPage) alignPage(pendingPage)
  syncThumbnail()
  changed()
}
async function jump(page: number) {
  if (!Number.isInteger(page) || page < 1 || page > pages.value.length) { target.value = current.value; return }
  current.value = target.value = page
  explicitPageUntil = Date.now() + 800
  pendingPage = page
  await nextTick()
  alignPage(page)
  syncThumbnail()
  changed()
}
async function zoom(value: number) {
  const page = current.value
  pendingPage = page
  scale.value = Math.min(2.5, Math.max(0.4, value))
  await nextTick(); await jump(page)
}
async function fit() {
  if (!documentPdf.value || !viewer.value) return
  const first = await documentPdf.value.getPage(current.value)
  await zoom((viewer.value.clientWidth - 40) / first.getViewport({ scale: 1 }).width)
}
function close(reason: 'navigate' | 'end' | 'manual' = 'navigate') {
  clearTimeout(timer); savePosition()
  if (opened && store.active) store.collector?.track('resource_closed', { ...base(), close_reason: reason }, undefined, reason === 'end' ? 'system' : 'student')
  opened = false
}
async function open() {
  if (loading.value || opened || store.page !== 'textbook' || !store.active) return
  const resource = store.resources.find(r => r.type === 'textbook')
  if (!resource) return
  const own = ++generation
  loading.value = true; failure.value = ''
  try {
    if (!selected.value || selected.value.id !== resource.id || selected.value.version !== resource.version) {
      documentPdf.value?.destroy(); documentPdf.value = undefined
      current.value = target.value = 1; scale.value = 1; purpose.value = ''; note.value = ''
      selected.value = resource
      try {
        const saved = JSON.parse(localStorage.getItem(key()) || 'null')
        if (saved) { current.value = target.value = saved.page; scale.value = saved.scale; thumbnails.value = saved.thumbnails }
      } catch { /* Invalid local restoration is ignored. */ }
      if (resource.mime === 'application/pdf') {
        const response = await fetch('/api/v1/resources/' + resource.id + '/versions/' + resource.version + '?download=true', { headers: { Authorization: 'Bearer ' + getToken() } })
        if (!response.ok) throw new Error('教材暂时无法加载')
        const pdf = await getDocument({ data: new Uint8Array(await response.arrayBuffer()), cMapUrl: '/pdfjs/cmaps/', cMapPacked: true, standardFontDataUrl: '/pdfjs/standard_fonts/', wasmUrl: '/pdfjs/wasm/', isEvalSupported: false }).promise
        if (own !== generation) { await pdf.destroy(); return }
        documentPdf.value = markRaw(pdf)
      }
    }
    await nextTick()
    const saved = JSON.parse(localStorage.getItem(key()) || 'null')
    if (viewer.value && saved) viewer.value.scrollTop = saved.scroll
    syncThumbnail()
    if (store.page !== 'textbook' || !store.active) return
    instance = crypto.randomUUID(); opened = true
    store.collector?.track('resource_opened', { ...base(), resource_type: 'textbook', ...locator() })
  } catch (error) { failure.value = (error as Error).message; selected.value = null }
  finally { loading.value = false }
}
async function reference() {
  measure()
  if (!canReference.value || !selected.value || adding.value) return
  const frozenPage = current.value
  const frozenPurpose = purpose.value || null, frozenNote = note.value.trim() || null
  adding.value = true
  try {
    await store.addReference(selected.value, frozenPage, frozenPurpose, frozenNote)
    if (current.value === frozenPage) { purpose.value = ''; note.value = '' }
  }
  catch (error) { store.report(error) }
  finally { adding.value = false }
}
watch(current, () => { purpose.value = ''; note.value = ''; void nextTick(syncThumbnail) }, { flush: 'sync' })
watch(thumbnails, () => void nextTick(syncThumbnail))
watch(() => [store.page, store.resources.length, store.active], async () => { if (store.page === 'textbook' && store.active) { await nextTick(); await open() } else close() })
const ending = () => close('end')
onMounted(() => window.addEventListener('session-ending', ending))
onBeforeUnmount(() => { generation++; clearTimeout(timer); window.removeEventListener('session-ending', ending); documentPdf.value?.destroy() })
</script>
<template>
  <main class="textbook-page" data-region="textbook">
    <header class="reader-toolbar">
      <button :aria-expanded="thumbnails" @click="thumbnails = !thumbnails; changed()">{{ thumbnails ? '收起缩略图' : '显示缩略图' }}</button>
      <strong :title="selected?.title">{{ selected?.title || '单元教材' }}</strong>
      <div class="reader-actions">
        <button class="reader-reference-button" :disabled="!canReference || adding" @click="reference">{{ adding ? '正在加入…' : '引用当前页' }}</button>
        <button @click="store.navigate('workbench')">去工作台</button>
        <details class="reference-options"><summary>第 {{ current }} 页 · 引用用途 / 备注（选填）</summary>
          <div class="reference-fields">
            <label>引用用途
              <select v-model="purpose" aria-label="引用用途"><option value="">选择用途（选填）</option><option value="teaching_goal">教学目标</option><option value="knowledge_point">知识点</option><option value="interaction_idea">互动活动</option><option value="feedback_design">反馈设计</option><option value="uncertainty">待核对</option><option value="other">其他</option></select>
            </label>
            <label>引用备注
              <input v-model="note" maxlength="2000" aria-label="引用备注" placeholder="可补充本页需要关注的内容" />
            </label>
          </div>
        </details>
      </div>
    </header>
    <p v-if="loading" role="status">正在加载教材…</p>
    <p v-if="failure" role="alert">{{ failure }} <button @click="open">重试</button></p>
    <p v-if="!loading && !selected && !failure">当前任务尚未配置教材。</p>
    <div v-if="selected" class="reader-layout" :class="{ 'no-thumbnails': !thumbnails }">
      <aside v-show="thumbnails" ref="thumbnailList" class="pdf-thumbnails" aria-label="教材缩略图">
        <button v-for="page in pages" :key="page.page" :data-thumbnail-page="page.page" :aria-current="page.page === current ? 'page' : undefined" :class="{ selected: page.page === current }" @click="jump(page.page)">
          <PdfPage v-if="documentPdf" :document="documentPdf" :page="page.page" :scale="0.18" thumbnail @rendered="syncThumbnail" />
          <span>第 {{ page.page }} 页<span v-if="page.printed_page !== null"> · 书页 {{ page.printed_page }}</span></span>
        </button>
      </aside>
      <section ref="viewer" class="resource-reader pdf-scroll" tabindex="0" aria-label="教材阅读区" @scroll="changed" @wheel="pendingPage = null; explicitPageUntil = 0" @pointerdown="pendingPage = null; explicitPageUntil = 0" @touchstart="pendingPage = null; explicitPageUntil = 0" @keydown="pendingPage = null; explicitPageUntil = 0">
        <article v-for="page in pages" :key="page.page" :data-pdf-page="page.page" class="pdf-page">
          <PdfPage v-if="documentPdf" :document="documentPdf" :page="page.page" :scale="scale" @rendered="rendered(page.page)" />
          <pre v-else>{{ page.text }}</pre>
          <small>文件第 {{ page.page }} 页<span v-if="page.printed_page !== null"> · 印刷页码 {{ page.printed_page }}</span></small>
        </article>
      </section>
    </div>
    <footer v-if="selected" class="reader-controls">
      <div class="reader-pagination">
        <button :disabled="current <= 1" @click="jump(current - 1)">上一页</button>
        <label>第 <input ref="pageInput" v-model.number="target" type="number" min="1" :max="pages.length" aria-label="教材页序" @change="jump(target)" @keydown.enter="jump(target)" /> / {{ pages.length }} 页</label>
        <button :disabled="current >= pages.length" @click="jump(current + 1)">下一页</button>
        <span v-if="currentData?.printed_page != null" class="subtle">书页 {{ currentData.printed_page }}</span>
      </div>
      <div class="reader-zoom">
        <button :disabled="scale <= 0.4" aria-label="缩小教材" @click="zoom(scale - 0.1)">− 缩小</button><span class="zoom-value">{{ Math.round(scale * 100) }}%</span><button :disabled="scale >= 2.5" aria-label="放大教材" @click="zoom(scale + 0.1)">＋ 放大</button><button @click="fit">适宽</button>
      </div>
      <span v-if="currentData?.ai_input_status !== 'ready'" class="subtle">此页可阅读；暂无可供 AI 引用的文字。</span>
    </footer>
  </main>
</template>

