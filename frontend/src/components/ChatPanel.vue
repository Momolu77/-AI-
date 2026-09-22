<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { useWorkbench } from '../stores/workbench'
import type { AIResponse } from '../types'
const store = useWorkbench(),
  fileInput = ref<HTMLInputElement>(),
  messages = ref<HTMLDivElement>()
const rendered = (text: string) =>
  DOMPurify.sanitize(marked.parse(text, { async: false }), {
    FORBID_TAGS: ['img', 'iframe', 'video', 'audio', 'style'],
    FORBID_ATTR: ['style'],
  })
const responseFor = (id: string) => store.responses.find((r) => r.request_id === id)
const codeBlocks = (response: AIResponse) =>
  [...response.response_text.matchAll(/```(?:html|javascript|css|js)?\s*\n([\s\S]*?)```/g)].map(
    (m) => m[1]!.replace(/\n$/, ''),
  )
const replyLength = computed(() => store.responses.reduce((n, r) => n + r.response_text.length, 0))
watch(replyLength, async () => {
  const nearBottom =
    !messages.value ||
    messages.value.scrollHeight - messages.value.scrollTop - messages.value.clientHeight < 100
  await nextTick()
  if (nearBottom && messages.value) messages.value.scrollTop = messages.value.scrollHeight
})
async function choose(event: Event) {
  const files = (event.target as HTMLInputElement).files
  if (files) for (const file of files) void store.upload(file).catch(store.report)
  ;(event.target as HTMLInputElement).value = ''
}
</script>
<template>
  <section class="panel chat-panel">
    <header class="panel-heading">
      <h2>AI 对话</h2>
      <span class="subtle">{{
        store.task?.ai_provider === 'fake' ? '本地测试模型' : 'DeepSeek'
      }}</span>
    </header>
    <div ref="messages" class="messages">
      <div v-if="!store.requests.length" class="chat-empty">
        <span class="small-symbol">✦</span>
        <h3>从你的想法开始</h3>
        <p>描述你想制作的教学游戏，也可以添加教材或说明文件。</p>
        <p class="subtle">回复中的代码可以自行复制到编辑器。</p>
      </div>
      <article v-for="request in store.requests" :key="request.id" class="exchange">
        <div class="message user-message">
          <span class="message-author">你</span>
          <p>{{ request.command.message_text || '（仅附件）' }}</p>
          <span v-if="request.command.attachment_ids.length" class="subtle"
            >{{ request.command.attachment_ids.length }} 个附件</span
          >
        </div>
        <div class="message assistant-message">
          <span class="message-author"
            >AI <small>{{ responseFor(request.id)?.model_name }}</small></span
          >
          <div
            v-if="responseFor(request.id)"
            class="markdown"
            v-html="rendered(responseFor(request.id)!.response_text)"
          ></div>
          <span v-if="['QUEUED', 'STREAMING'].includes(request.status)" class="generating">{{
            request.status === 'QUEUED' ? '等待生成…' : '正在回复…'
          }}</span>
          <div v-if="responseFor(request.id)?.response_text" class="message-actions">
            <button
              @click="
                store
                  .copyResponse(
                    responseFor(request.id)!,
                    responseFor(request.id)!.response_text,
                    'text',
                  )
                  .catch(store.report)
              "
            >
              复制回复</button
            ><button
              v-for="(block, index) in codeBlocks(responseFor(request.id)!)"
              :key="index"
              @click="
                store.copyResponse(responseFor(request.id)!, block, 'code').catch(store.report)
              "
            >
              复制代码{{ codeBlocks(responseFor(request.id)!).length > 1 ? index + 1 : '' }}
            </button>
          </div>
          <div v-if="request.status === 'FAILED'" class="inline-error">
            <p>{{ request.error?.error_message }}</p>
            <button
              :disabled="store.generating || store.ended"
              @click="store.send(request).catch(store.report)"
            >
              重试此请求
            </button>
          </div>
        </div>
      </article>
    </div>
    <div v-if="store.streamError" class="inline-error">
      {{ store.streamError
      }}<button
        v-for="request in store.requests.filter((r) => ['QUEUED', 'STREAMING'].includes(r.status))"
        :key="request.id"
        @click="store.connectStream(request)"
      >
        重新连接回复
      </button>
    </div>
    <div class="composer">
      <ul v-if="store.selected.length" class="attachment-list">
        <li v-for="item in store.selected" :key="item.id">
          <div>
            <strong>{{ item.file_name }}</strong
            ><small>{{
              {
                SELECTED: '已选择',
                UPLOADING: '上传中',
                PROCESSING: '处理中',
                READY: '可发送',
                FAILED: '失败',
                REMOVED: '已移除',
              }[item.status]
            }}</small>
            <p v-if="item.error_message" class="error-text">{{ item.error_message }}</p>
          </div>
          <button
            v-if="item.status === 'FAILED'"
            @click="store.retryAttachment(item.id).catch(store.report)"
          >
            重试</button
          ><button
            :disabled="['UPLOADING', 'PROCESSING'].includes(item.status)"
            :aria-label="'移除 ' + item.file_name"
            @click="store.removeAttachment(item.id).catch(store.report)"
          >
            ×
          </button>
        </li>
      </ul>
      <label class="sr-only" for="message-input">给 AI 的消息</label
      ><textarea
        id="message-input"
        :value="store.draft"
        :disabled="store.ended"
        rows="4"
        placeholder="输入你的问题或制作要求…"
        @input="store.editDraft(($event.target as HTMLTextAreaElement).value)"
      ></textarea>
      <div class="composer-tools">
        <button :disabled="store.ended" @click="fileInput?.click()">＋ 添加附件</button
        ><input
          ref="fileInput"
          type="file"
          hidden
          multiple
          :accept="store.task?.upload.types"
          @change="choose"
        /><v-btn
          color="primary"
          size="small"
          :disabled="!!store.sendBlock"
          @click="store.send().catch(store.report)"
          >发送 ↑</v-btn
        >
      </div>
      <p class="upload-hint">
        {{ store.task?.upload.types }} · 每个文件 ≤
        {{ (store.task?.upload.max_bytes || 0) / 1048576 }} MB
      </p>
      <p v-if="store.sendBlock && (store.selected.length || store.generating)" class="subtle">
        {{ store.sendBlock }}
      </p>
      <button v-if="store.pendingAI" class="retry-link" @click="store.send().catch(store.report)">
        重新确认上次请求（不会重复生成）
      </button>
    </div>
  </section>
</template>
