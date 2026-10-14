<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useWorkbench } from '../stores/workbench'
import type { Example } from '../types'
const store = useWorkbench(),
  example = ref<Example | null>(null),
  video = ref<HTMLVideoElement>(),
  open = ref(false),
  failed = ref(false),
  retryKey = ref(0)
let playingSince: number | null = null,
  watched = 0,
  viewerId = crypto.randomUUID() as string
const positions = new Map<string, number>()
let lastMedia = 0
function playing() {
  if (!document.hidden && video.value) {
    playingSince = performance.now()
    lastMedia = video.value.currentTime
  }
}
function progress() {
  if (
    playingSince !== null &&
    video.value &&
    !document.hidden &&
    video.value.currentTime > lastMedia
  ) {
    watched += (performance.now() - playingSince) / 1000
    playingSince = performance.now()
    lastMedia = video.value.currentTime
  }
}
function seeked() {
  if (video.value && !video.value.paused) playing()
}
function tally() {
  progress()
  playingSince = null
}
function visible() {
  if (document.hidden) {
    playingSince = null
  } else if (video.value && !video.value.paused && video.value.readyState >= 3) playing()
}
onMounted(() => document.addEventListener('visibilitychange', visible))
onBeforeUnmount(() => document.removeEventListener('visibilitychange', visible))
function show(item: Example) {
  example.value = item
  viewerId = crypto.randomUUID()
  watched = 0
  playingSince = null
  failed.value = false
  open.value = true
  store.collector?.track('example_opened', {
    example_id: item.id,
    example_version: item.version,
    viewer_instance_id: viewerId,
    media_type: item.media_type,
  })
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
  store.collector?.track(
    'example_closed',
    {
      example_id: example.value.id,
      example_version: example.value.version,
      viewer_instance_id: viewerId,
      media_type: example.value.media_type,
      last_position_sec: example.value.media_type === 'video' ? position : null,
      watched_seconds: example.value.media_type === 'video' ? Math.max(0, watched) : null,
      close_reason: reason,
    },
    undefined,
    reason === 'end' ? 'system' : 'student',
  )
  open.value = false
}
function retryVideo() {
  retryKey.value++
  failed.value = false
}
function enter() {
  close('navigate')
  store.navigate('workbench')
}
async function renderedTask() {
  await nextTick()
  requestAnimationFrame(() => {
    void store.acknowledgeTask().catch(store.report)
  })
}
onMounted(renderedTask)
watch(() => store.task?.description, renderedTask)
watch(
  () => store.page,
  (value) => {
    if (value !== 'example' && value !== 'task') close('navigate')
  },
)
const end = () => close('end')
onMounted(() => window.addEventListener('session-ending', end))
onBeforeUnmount(() => window.removeEventListener('session-ending', end))
</script>
<template>
  <main class="task-page">
    <div v-if="store.session?.status === 'PREPARING'">
      <p>正在确认任务开始；连接恢复后可重试。</p>
      <button @click="store.acknowledgeTask().catch(store.report)">重试开始</button>
    </div>
    <div v-show="store.page === 'task'" class="task-intro" data-region="task">
      <p class="eyebrow">ENGLISH TEACHING LAB · 教学资源制作</p>
      <h1>{{ store.task?.title }}</h1>
      <h2 class="task-description-heading">任务说明：</h2>
      <p class="lead">{{ store.task?.description }}</p>
    </div>
    <div class="task-grid" :class="{ 'example-grid': store.page === 'example' }">
      <section v-show="store.page === 'task'" class="task-brief">
        <div class="section-heading">
          <span class="section-number">01</span>
          <h2>任务要求：</h2>
        </div>
        <ol class="constraints">
          <li v-for="(constraint, i) in store.task?.constraints" :key="i">
            <span>{{ i + 1 }}.</span>
            <p>{{ constraint }}</p>
          </li>
        </ol>
        <section v-if="store.task?.basic_requirements?.length" class="task-standards">
          <h2>作品基本要求</h2>
          <ul><li v-for="item in store.task.basic_requirements" :key="item">{{ item }}</li></ul>
        </section>
        <section v-if="store.task?.rubric?.length" class="task-standards">
          <h2>作品评价标准</h2>
          <table><thead><tr><th>评价维度</th><th>主要评价内容</th></tr></thead><tbody>
            <tr v-for="item in store.task.rubric" :key="item.dimension"><td>{{ item.dimension }}</td><td>{{ item.description }}</td></tr>
          </tbody></table>
        </section>
        <div class="entry-row">
          <v-btn color="primary" size="large" :disabled="store.ended" @click="enter"
            >{{ store.page === 'task' ? '去工作台' : '进入工作台' }}
            <span class="button-arrow" aria-hidden="true">→</span></v-btn
          ><span>随时可以返回查看任务</span>
        </div>
      </section>
      <aside v-show="store.page === 'example'" class="examples" data-region="example">
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
            ><span>{{
              item.media_type === 'video' ? item.duration + ' 秒 · 视频' : '网页交互'
            }}</span>
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
          v-if="example?.media_type === 'video'"
          :key="retryKey"
          ref="video"
          :src="example.url"
          controls
          preload="metadata"
          playsinline
          @loadedmetadata="restorePosition"
          @playing="playing"
          @timeupdate="progress"
          @pause="tally"
          @waiting="tally"
          @seeking="tally"
          @seeked="seeked"
          @ended="tally"
          @error="failed = true"
        ></video>
        <iframe
          v-if="example?.media_type === 'web'"
          :src="example.url"
          title="网页示例"
          sandbox="allow-scripts"
          class="example-frame"
        ></iframe>
        <div v-if="failed" class="inline-error">
          视频暂时无法加载。<button @click="retryVideo">重试</button>或关闭后直接进入工作台。
        </div>
      </section></v-dialog
    >
  </main>
</template>
