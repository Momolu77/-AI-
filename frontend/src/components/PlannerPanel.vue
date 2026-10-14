<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useWorkbench } from '../stores/workbench'
const store = useWorkbench(),
  width = ref(330)
let observer: ResizeObserver
function measure() {
  const rect = document.querySelector('[data-region="preview"]')?.getBoundingClientRect()
  width.value = store.page === 'workbench' && rect?.width ? Math.min(330, rect.width) : 330
}
watch(
  () => [store.page, store.plannerOpen],
  async () => {
    await nextTick()
    measure()
  },
)
onMounted(() => {
  observer = new ResizeObserver(measure)
  const el = document.querySelector('[data-region="preview"]')
  if (el) observer.observe(el)
  measure()
})
onBeforeUnmount(() => observer?.disconnect())
</script>
<template>
  <aside
    v-show="store.plannerOpen && !store.fullscreen && store.page !== 'tasks'"
    :style="{ width: width + 'px' }"
    data-region="planner"
    class="planner"
  >
    <header>
      <h2>我的备课记录 <span class="optional">选填</span></h2>
      <button aria-label="收起备课记录" @click="store.togglePlanner">收起 ×</button>
    </header>
    <label class="sr-only" for="plan-input">备课记录内容</label
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
</template>
