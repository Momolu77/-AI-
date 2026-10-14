<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useWorkbench } from '../stores/workbench'
const store = useWorkbench(),
  answers = ref<Record<string, string | number | null>>({}),
  saving = ref(false)
const key = 'background-draft:' + store.session!.id
try {
  answers.value = JSON.parse(localStorage.getItem(key) || '{}')
} catch {
  answers.value = {}
}
watch(answers, () => localStorage.setItem(key, JSON.stringify(answers.value)), { deep: true })
const complete = computed(() =>
  store.task?.prerequisite.questions.every((q) => answers.value[q.id] !== undefined),
)
async function submit() {
  saving.value = true
  try {
    await store.completePrerequisite(
      Object.entries(answers.value).map(([question_id, answer_value]) => ({
        question_id,
        answer_value,
      })),
    )
  } catch (e) {
    store.report(e)
  } finally {
    saving.value = false
  }
}
</script>
<template>
  <main class="task-page preparation">
    <h1>开始前的背景信息</h1>
    <p>每题可作答或选择“不愿回答”。提交后显示任务要求，并开始记录任务时间。</p>
    <form @submit.prevent="submit">
      <fieldset v-for="question in store.task?.prerequisite.questions" :key="question.id">
        <legend>{{ question.label }}</legend>
        <label v-for="option in question.options" :key="option.value"
          ><input
            v-model="answers[question.id]"
            type="radio"
            :name="question.id"
            :value="option.value"
          />
          {{ option.label }}</label
        >
        <label v-if="question.allow_refusal"><input v-model="answers[question.id]" type="radio" :name="question.id" :value="null" />不愿回答</label>
      </fieldset>
      <v-btn type="submit" color="primary" :disabled="!complete || saving">{{
        saving ? '正在保存…' : '提交并查看任务'
      }}</v-btn>
    </form>
  </main>
</template>
