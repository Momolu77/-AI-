<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { useWorkbench } from '../stores/workbench'
import { validatePreview } from '../services/preview'
import CodeEditor from './CodeEditor.vue'
import ChatPanel from './ChatPanel.vue'
const store = useWorkbench(),
  iframe = ref<HTMLIFrameElement>()
function message(event: MessageEvent) {
  const body = validatePreview(event, iframe.value?.contentWindow || null, store.activeRun)
  if (body) store.previewMessage(body)
}
const widths = ref([30, 35, 35]),
  host = ref<HTMLElement>()
function drag(event: PointerEvent, index: number) {
  const start = event.clientX,
    original = [...widths.value],
    total = host.value!.clientWidth
  const move = (e: PointerEvent) => {
    const delta = ((e.clientX - start) / total) * 100
    if (original[index]! + delta < 15 || original[index + 1]! - delta < 15) return
    const next = [...original]
    next[index] += delta
    next[index + 1] -= delta
    widths.value = next
  }
  const end = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', end)
    store.layout('drag')
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', end)
}
watch(
  () => store.fullscreen,
  async (value) => {
    await nextTick()
    store.layout(value ? 'fullscreen_enter' : 'fullscreen_exit')
  },
)
watch(
  () => store.plannerOpen,
  async (value) => {
    await nextTick()
    store.layout(value ? 'planner_open' : 'planner_close')
  },
)
watch(
  () => store.consoleOpen,
  async (value) => {
    await nextTick()
    store.layout(value ? 'console_open' : 'console_close')
  },
)
onMounted(() => window.addEventListener('message', message))
onBeforeUnmount(() => window.removeEventListener('message', message))
</script>
<template>
  <main
    ref="host"
    class="workbench"
    :class="{ 'preview-fullscreen': store.fullscreen }"
    :style="{
      gridTemplateColumns: store.fullscreen
        ? '1fr'
        : `${widths[0]}fr 6px ${widths[1]}fr 6px ${widths[2]}fr`,
    }"
  >
    <ChatPanel />
    <div class="panel-resizer" @pointerdown.prevent="drag($event, 0)"></div>
    <section class="panel editor-panel" data-region="editor">
      <header class="panel-heading">
        <div class="panel-title">
          <h2>HTML 编辑器</h2>
          <span class="subtle">index.html · 编辑版本 v{{ store.codeRevision }}</span>
        </div>
        <v-btn
          color="primary"
          variant="tonal"
          size="small"
          :disabled="store.running || store.ended"
          @click="store.run().catch(store.report)"
          >{{ store.running ? '保存中…' : '▶ 运行' }}</v-btn
        >
      </header>
      <CodeEditor
        :model-value="store.code"
        :readonly="!store.active || store.applying"
        @change="store.editCode"
      />
      <div class="editor-status">
        <button
          :class="{ 'error-text': store.codeSave.startsWith('保存失败') }"
          @click="store.save('code').catch(store.report)"
        >
          {{ store.codeSave }}</button
        ><span>Ctrl + F 查找 · Ctrl + Z 撤销</span>
      </div>
      <section data-region="console" class="console" :class="{ collapsed: !store.consoleOpen }">
        <header>
          <button class="console-toggle" :aria-expanded="store.consoleOpen" @click="store.consoleOpen = !store.consoleOpen">
            {{ store.consoleOpen ? '▾' : '▸' }} 运行控制台
            <span>{{
              store.consoleRows.filter((r) => ['log', 'warn', 'error'].includes(r.message.kind))
                .length
            }}</span></button
          ><span class="subtle">原始输出</span>
        </header>
        <div v-show="store.consoleOpen" class="console-content">
          <p
            v-if="!store.consoleRows.some((r) => ['log', 'warn', 'error'].includes(r.message.kind))"
            class="console-empty"
          >
            运行后在这里查看日志与错误。
          </p>
          <div
            v-for="row in store.consoleRows.filter((r) =>
              ['log', 'warn', 'error'].includes(r.message.kind),
            )"
            :key="row.id"
            class="console-row"
            :class="row.message.kind"
          >
            <div>
              <span>{{ row.message.kind }}</span>
              <pre :data-error-id="row.message.kind === 'error' ? row.id : undefined">{{
                row.message.text
              }}</pre>
              <small v-if="row.message.line"
                >行 {{ row.message.line }} : {{ row.message.column }}</small
              >
              <details v-if="row.message.stack">
                <summary>调用栈</summary>
                <pre>{{ row.message.stack }}</pre>
              </details>
            </div>
            <button
              v-if="row.message.kind === 'error'"
              @click="store.copyError(row).catch(store.report)"
            >
              复制错误
            </button>
          </div>
        </div>
      </section>
    </section>
    <div class="panel-resizer" @pointerdown.prevent="drag($event, 1)"></div>
    <section class="panel preview-panel" data-region="preview">
      <header class="panel-heading">
        <div class="panel-title">
          <h2>交互预览</h2>
          <span class="subtle" data-testid="preview-version">{{ store.previewState === 'loaded' ? `预览版本 v${store.activeRun?.code_revision}` : store.previewState === 'loading' ? '预览加载中 · 当前画面尚未就绪' : store.activeRun ? '预览不可用 · 请再次运行' : '尚未运行' }}</span>
        </div>
        <button @click="store.fullscreen = !store.fullscreen">
          {{ store.fullscreen ? '退出全屏' : '全屏预览' }}
        </button>
      </header>
      <div v-if="store.dirtyPreview" class="dirty-banner">代码已修改，运行后更新预览</div>
      <div class="preview-body">
        <iframe
          v-if="store.activeRun"
          :key="store.activeRun.run_id"
          ref="iframe"
          title="网站预览"
          :src="store.activeRun.url"
          sandbox="allow-scripts allow-forms"
          referrerpolicy="no-referrer"
          @error="store.previewFailed('iframe_error')"
        ></iframe>
        <div v-else class="preview-empty">
          <span class="preview-placeholder">〈 / 〉</span>
          <h3>在这里体验你的网站</h3>
          <p>编写或粘贴 HTML 代码，<br />点击编辑器上方的「运行」。</p>
        </div>
      </div>
    </section>
  </main>
</template>
