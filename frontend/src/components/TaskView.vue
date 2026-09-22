<script setup lang="ts">
import { ref } from 'vue'
import { useWorkbench } from '../stores/workbench'
import type { Example } from '../types'
const store = useWorkbench(),
  example = ref<Example | null>(null),
  video = ref<HTMLVideoElement>(),
  open = ref(false),
  failed = ref(false),
  retryKey = ref(0)
let playingSince: number | null = null,
  watched = 0
const positions = new Map<string, number>()
function playing() {
  playingSince = performance.now()
}
function seeked() {
  if (video.value && !video.value.paused) playing()
}
function tally() {
  if (playingSince !== null) {
    watched += (performance.now() - playingSince) / 1000
    playingSince = null
  }
}
function show(item: Example) {
  example.value = item
  watched = 0
  playingSince = null
  failed.value = false
  open.value = true
  store.collector?.track('example_opened', { example_id: item.id })
}
function restorePosition() {
  if (video.value && example.value) {
    video.value.currentTime = positions.get(example.value.id) || 0
    video.value.pause()
  }
}
function close(reason: 'manual' | 'navigate' | 'end' = 'manual') {
  if (!open.value || !example.value) return
  tally()
  video.value?.pause()
  const position = video.value?.currentTime || 0
  positions.set(example.value.id, position)
  store.collector?.track('example_closed', {
    example_id: example.value.id,
    last_position_sec: position,
    watched_seconds: Math.max(0, watched),
    close_reason: reason,
  })
  open.value = false
}
function retryVideo() { retryKey.value++; failed.value = false }
function enter() {
  close('navigate')
  store.navigate('workbench')
}
</script>
<template>
  <main class="task-page">
    <div class="task-intro">
      <p class="eyebrow">ENGLISH TEACHING LAB · 教学资源制作</p>
      <h1>{{ store.task?.title }}</h1>
      <p class="lead">{{ store.task?.description }}</p>
    </div>
    <div class="task-grid">
      <section class="task-brief">
        <div class="section-heading">
          <span class="section-number">01</span>
          <h2>任务要求</h2>
        </div>
        <ol class="constraints">
          <li v-for="(constraint, i) in store.task?.constraints" :key="i">
            <span>{{ String(i + 1).padStart(2, '0') }}</span>
            <p>{{ constraint }}</p>
          </li>
        </ol>
        <div class="entry-row">
          <v-btn color="primary" size="large" :disabled="store.ended" @click="enter"
            >{{ store.page === 'task' ? '去工作区' : '进入工作区' }}
            <span class="button-arrow" aria-hidden="true">→</span></v-btn
          ><span>随时可以返回查看任务</span>
        </div>
      </section>
      <aside class="examples">
        <div class="section-heading">
          <span class="section-number">02</span>
          <h2>交互示例</h2>
          <span class="optional">选看</span>
        </div>
        <button
          v-for="item in store.task?.examples"
          :key="item.id"
          class="example-card"
          @click="show(item)"
        >
          <div class="example-art">
            <span class="word-tile">apple</span><span class="word-tile secondary">苹果</span
            ><span class="play-mark">▶</span>
          </div>
          <div class="example-caption">
            <strong>{{ item.title }}</strong
            ><span>{{ item.duration }} 秒 · 本地视频</span>
            <p>{{ item.description }}</p>
          </div>
        </button>
        <p class="aside-note">你可以直接开始，也可以在制作过程中再回来查看。</p>
      </aside>
    </div>
    <v-dialog
      :model-value="open"
      max-width="800"
      @update:model-value="
        (value) => {
          if (!value) close()
        }
      "
      ><section class="video-dialog">
        <div class="dialog-heading">
          <h2>{{ example?.title }}</h2>
          <button aria-label="关闭示例" @click="close()">关闭 ×</button>
        </div>
        <video
          v-if="example"
          :key="retryKey"
          ref="video"
          :src="example.url"
          controls
          preload="metadata"
          playsinline
          @loadedmetadata="restorePosition"
          @playing="playing"
          @pause="tally"
          @waiting="tally"
          @seeking="tally"
          @seeked="seeked"
          @ended="tally"
          @error="failed = true"
        ></video>
        <div v-if="failed" class="inline-error">
          视频暂时无法加载。<button
            @click="retryVideo"
          >
            重试</button
          >或关闭后直接进入工作区。
        </div>
      </section></v-dialog
    >
  </main>
</template>
