<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useWorkbench } from '../stores/workbench'
import type { Proposal } from '../types'
const props = defineProps<{ proposal: Proposal }>(),
  store = useWorkbench(),
  host = ref<HTMLElement>(),
  details = ref(false),
  busy = ref(false)
let observer: IntersectionObserver,
  displayId: string | null = null,
  displayedAt: number | null = null,
  last: boolean | null = null
function display(visible: boolean) {
  if (last === visible || !store.active) return
  last = visible
  const p = props.proposal
  const id = store.collector?.track('ai_proposal_displayed', {
    proposal_id: p.id,
    response_id: p.response_id,
    proposal_content_ref: p.proposal_content_ref,
    base_code_revision: p.base_code_revision,
    is_visible: visible,
  })
  if (visible) {
    displayId = id || null
    displayedAt = performance.now()
  }
}
function refreshVisibility() {
  const el = host.value,
    root = el?.closest('.messages')
  const rect = el?.getBoundingClientRect(),
    clip = root?.getBoundingClientRect()
  display(
    !!(
      rect &&
      clip &&
      el?.checkVisibility() &&
      !document.hidden &&
      store.page === 'workbench' &&
      !store.fullscreen &&
      rect.bottom > Math.max(0, clip.top) &&
      rect.top < Math.min(innerHeight, clip.bottom) &&
      rect.right > Math.max(0, clip.left) &&
      rect.left < Math.min(innerWidth, clip.right)
    ),
  )
}
function review() {
  details.value = !details.value
  if (details.value)
    store.collector?.track('ai_proposal_reviewed', {
      proposal_id: props.proposal.id,
      base_code_revision: props.proposal.base_code_revision,
      detail_content_ref: props.proposal.proposal_content_ref,
    })
}
async function decide(decision: 'accept' | 'reject') {
  busy.value = true
  try {
    await store.decideProposal(
      props.proposal,
      decision,
      displayId,
      displayedAt === null ? null : performance.now() - displayedAt,
    )
  } catch (e) {
    store.report(e)
  } finally {
    busy.value = false
  }
}
onMounted(() => {
  observer = new IntersectionObserver(refreshVisibility, { root: host.value!.closest('.messages') })
  observer.observe(host.value!)
  document.addEventListener('visibilitychange', refreshVisibility)
})
watch(
  () => [store.page, store.fullscreen],
  async () => {
    await nextTick()
    refreshVisibility()
  },
)
onBeforeUnmount(() => {
  observer?.disconnect()
  document.removeEventListener('visibilitychange', refreshVisibility)
})
</script>
<template>
  <section ref="host" class="proposal-card">
    <h3>{{ proposal.title }}</h3>
    <p>此提议将替换代码。先查看改动，再决定是否使用。</p>
    <button @click="review">{{ details ? '收起改动' : '查看改动' }}</button>
    <div v-if="details">
      <p>当前代码（用于比较）</p>
      <pre>{{ store.code }}</pre>
      <p>提议代码</p>
      <pre>{{ proposal.code }}</pre>
    </div>
    <div v-if="!proposal.decision">
      <button :disabled="busy || !store.active" @click="decide('accept')">接受提议</button
      ><button :disabled="busy || !store.active" @click="decide('reject')">拒绝提议</button>
    </div>
    <p v-else>{{ proposal.decision === 'accept' ? '已接受' : '已拒绝' }}</p>
    <button
      v-if="proposal.decision === 'accept'"
      :disabled="store.applicationBusy || !store.active"
      @click="store.applyProposal(proposal).catch(store.report)"
    >
      {{ store.applying ? '核对应用结果' : '应用到编辑器' }}
    </button>
    <p
      v-for="a in store.applications.filter((a) => a.proposal_id === proposal.id)"
      :key="a.application_id"
    >
      {{ a.status === 'APPLIED' ? '已应用；点击运行查看效果' : a.error_message }}
    </p>
  </section>
</template>
