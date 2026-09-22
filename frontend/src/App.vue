<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useWorkbench } from './stores/workbench'
import TaskView from './components/TaskView.vue'
import WorkbenchView from './components/WorkbenchView.vue'
import type { Job } from './services/events'
const store = useWorkbench(),
  endDialog = ref(false),
  diagnostics = ref<Job[]>([])
onMounted(() => void store.start())
const reload = () => window.location.reload()
async function inspect() {
  diagnostics.value = (await store.collector?.rows()) || []
  store.diagnosticsOpen = true
}
async function end() {
  try {
    await store.endSession()
    endDialog.value = false
  } catch (error) {
    store.report(error)
  }
}
</script>
<template>
  <v-app>
    <div class="app-shell">
      <header class="topbar">
        <div class="brand">
          <span class="brand-mark">E<span>·</span></span>
          <div><strong>英语教学资源工作台</strong><small>AI 协作 · 单文件游戏制作</small></div>
        </div>
        <nav v-if="store.initialized" class="top-actions">
          <button
            v-if="store.page === 'workbench'"
            class="nav-back"
            @click="store.navigate('task')"
          >
            ← 查看任务</button
          ><span class="clock">{{ store.clock }}</span
          ><span class="seat"
            >座位 <b>{{ store.session?.seat_no }}</b></span
          ><span class="toolbar-divider"></span
          ><button
            :disabled="store.ended"
            :class="{ selected: store.plannerOpen }"
            @click="
              store.page === 'task'
                ? (store.navigate('workbench'), store.togglePlanner())
                : store.togglePlanner()
            "
          >
            我的计划</button
          ><v-btn
            color="primary"
            :disabled="store.submitting || store.ended"
            @click="
              store.pendingSubmission ? store.submit().catch(store.report) : store.openSubmit()
            "
            >{{
              store.submitting ? '提交中…' : store.pendingSubmission ? '重试上次提交' : '提交作品'
            }}</v-btn
          ><button class="end-button" :disabled="store.ended" @click="endDialog = true">
            结束
          </button>
        </nav>
      </header>
      <main v-if="store.fatal" class="entry-error">
        <p class="eyebrow">本地工作台</p>
        <h1>暂时无法进入</h1>
        <p>{{ store.fatal }}</p>
        <button @click="reload">重新加载</button>
      </main>
      <div v-else-if="!store.initialized" class="loading">正在恢复工作台…</div>
      <template v-else
        ><div v-if="store.ended" class="ended-banner">
          此会话已结束。已保存内容可查看；使用原座位入口可开始新会话。<button
            v-if="store.page === 'task'"
            @click="store.page = 'workbench'"
          >
            查看作品
          </button>
        </div>
        <TaskView v-show="store.page === 'task'" /><WorkbenchView
          v-show="store.page === 'workbench'"
        />
        <footer class="statusbar">
          <span :class="{ 'error-text': !store.connected }"
            >● {{ store.connected ? '本地服务已连接' : '正在等待本地服务' }}</span
          ><button @click="inspect">
            {{ store.collector?.stats.pending || 0 }} 条待同步<span
              v-if="store.collector?.stats.rejected"
            >
              · {{ store.collector.stats.rejected }} 条需检查</span
            ></button
          ><span v-if="store.collector?.stats.error" class="error-text">{{
            store.collector.stats.error
          }}</span
          ><span class="status-spacer"></span
          ><span v-if="store.submissions.some((s) => s.status === 'SUCCEEDED')"
            >已成功提交
            {{ store.submissions.filter((s) => s.status === 'SUCCEEDED').length }} 次</span
          ><span>{{ store.task?.version }}</span>
        </footer></template
      >
      <div v-if="store.notice" role="status" class="toast">
        <span>{{ store.notice }}</span
        ><button aria-label="关闭消息" @click="store.notice = ''">×</button>
      </div>
      <v-dialog :model-value="store.submitDialog" max-width="460" persistent
        ><section class="dialog-card">
          <p class="eyebrow">提交作品</p>
          <h2>保存当前这一版？</h2>
          <p>将保存你点击确认时的代码和计划。代码无需先运行；提交后仍可以继续修改，再次提交。</p>
          <div class="dialog-actions">
            <v-btn variant="text" @click="store.cancelSubmit">取消</v-btn
            ><v-btn color="primary" @click="store.submit().catch(store.report)">确认提交</v-btn>
          </div>
        </section></v-dialog
      >
      <v-dialog v-model="endDialog" max-width="460"
        ><section class="dialog-card">
          <h2>结束本次制作？</h2>
          <p>结束前将同步草稿和操作记录。没有提交作品时，也会归档最后保存的草稿。</p>
          <div class="dialog-actions">
            <v-btn variant="text" @click="endDialog = false">继续制作</v-btn
            ><v-btn color="primary" @click="end">确认结束</v-btn>
          </div>
        </section></v-dialog
      >
      <v-dialog v-model="store.diagnosticsOpen" max-width="800"
        ><section class="dialog-card diagnostics">
          <h2>本地同步记录</h2>
          <p>待同步记录将在连接恢复后补传；被拒绝记录保留原因供开发测试核查。</p>
          <button @click="store.collector?.flush().then(inspect)">立即重试同步</button>
          <pre>{{ JSON.stringify(diagnostics, null, 2) }}</pre>
          <button @click="store.diagnosticsOpen = false">关闭</button>
        </section></v-dialog
      >
    </div>
  </v-app>
</template>
