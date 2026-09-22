<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
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
onMounted(() => window.addEventListener('message', message))
onBeforeUnmount(() => window.removeEventListener('message', message))
</script>
<template>
  <main class="workbench">
    <ChatPanel />
    <section class="panel editor-panel">
      <header class="panel-heading">
        <div>
          <h2>HTML 编辑器</h2>
          <span class="subtle">index.html</span>
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
      <CodeEditor :model-value="store.code" :readonly="store.ended" @change="store.editCode" />
      <div class="editor-status">
        <button
          :class="{ 'error-text': store.codeSave.startsWith('保存失败') }"
          @click="store.save('code').catch(store.report)"
        >
          {{ store.codeSave }}</button
        ><span>Ctrl + F 查找 · Ctrl + Z 撤销</span>
      </div>
      <section class="console" :class="{ collapsed: !store.consoleOpen }">
        <header>
          <button class="console-toggle" @click="store.consoleOpen = !store.consoleOpen">
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
              <pre>{{ row.message.text }}</pre>
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
    <section class="panel preview-panel">
      <header class="panel-heading">
        <h2>交互预览</h2>
        <span class="subtle">{{ store.activeRun ? '手动运行' : '尚未运行' }}</span>
      </header>
      <div v-if="store.dirtyPreview" class="dirty-banner">代码已修改，运行后更新预览</div>
      <div class="preview-body">
        <iframe
          v-if="store.activeRun"
          :key="store.activeRun.run_id"
          ref="iframe"
          title="游戏预览"
          :src="store.activeRun.url"
          sandbox="allow-scripts"
          referrerpolicy="no-referrer"
        ></iframe>
        <div v-else class="preview-empty">
          <span class="preview-placeholder">〈 / 〉</span>
          <h3>在这里体验你的游戏</h3>
          <p>编写或粘贴 HTML 代码，<br />点击编辑器上方的「运行」。</p>
        </div>
      </div>
      <aside v-show="store.plannerOpen" class="planner">
        <header>
          <h2>我的计划 <span class="optional">选填</span></h2>
          <button aria-label="收起计划" @click="store.togglePlanner">收起 ×</button>
        </header>
        <label class="sr-only" for="plan-input">计划内容</label
        ><textarea
          id="plan-input"
          :value="store.plan"
          :disabled="store.ended"
          @input="store.editPlan(($event.target as HTMLTextAreaElement).value)"
        ></textarea
        ><button
          class="plan-status"
          :class="{ 'error-text': store.planSave.startsWith('保存失败') }"
          @click="store.save('plan').catch(store.report)"
        >
          {{ store.planSave }}
        </button>
      </aside>
    </section>
  </main>
</template>
