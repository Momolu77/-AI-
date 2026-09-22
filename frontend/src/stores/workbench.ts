import { computed, markRaw, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, api, post, setToken, sse } from '../services/api'
import { Collector } from '../services/events'
import { diff, EditBuffer } from '../services/edits'
import type { BufferData } from '../services/edits'
import { readDraft, writeDraft } from '../services/storage'
import type {
  AICommand,
  AIRequest,
  AIResponse,
  Attachment,
  ConsoleRow,
  PreviewMessage,
  Run,
  Session,
  Submission,
  SubmissionCommand,
  Task,
  WorkbenchState,
} from '../types'

interface LocalDraft {
  code: string
  codeRevision: number
  plan: string
  planRevision: number
  draft: string
  draftId: string
  codeBuffer: BufferData
  planBuffer: BufferData
  aiBuffer: BufferData
  viewed: boolean
  entered: boolean
  pendingAI: AICommand | null
  pendingSubmission: SubmissionCommand | null
  selected: Attachment[]
  away: boolean
}

export const useWorkbench = defineStore('workbench', () => {
  const session = ref<Session | null>(null),
    task = ref<Task | null>(null),
    collector = shallowRef<Collector | null>(null)
  const initialized = ref(false),
    fatal = ref(''),
    notice = ref(''),
    page = ref<'task' | 'workbench'>('task'),
    blocked = ref(false)
  const offset = ref(0),
    clockTick = ref(Date.now()),
    connected = ref(true)
  const code = ref(''),
    codeRevision = ref(0),
    plan = ref(''),
    planRevision = ref(0),
    draft = ref(''),
    draftId = ref(crypto.randomUUID() as string)
  const codeBuffer = new EditBuffer(),
    planBuffer = new EditBuffer(),
    aiBuffer = new EditBuffer()
  const codeSave = ref('已保存'),
    planSave = ref('已保存'),
    plannerOpen = ref(false)
  const selected = ref<Attachment[]>([]),
    requests = ref<AIRequest[]>([]),
    responses = ref<AIResponse[]>([]),
    streamError = ref('')
  const pendingAI = ref<AICommand | null>(null),
    pendingSubmission = ref<SubmissionCommand | null>(null)
  const activeRun = ref<Run | null>(null),
    running = ref(false),
    ranCode = ref(''),
    consoleRows = ref<ConsoleRow[]>([]),
    consoleOpen = ref(true)
  const submitDialog = ref(false),
    submitting = ref(false),
    submissions = ref<Submission[]>([])
  const diagnosticsOpen = ref(false),
    ended = computed(() => session.value?.status === 'ENDED')
  let viewed = false,
    entered = false,
    away = false,
    copied: { text: string; response: string } | null = null
  let localTimer: ReturnType<typeof setTimeout>, planTimer: ReturnType<typeof setTimeout>
  let codeSavedRevision = -1,
    saveQueue: Promise<unknown> = Promise.resolve()
  const now = () => new Date(Date.now() + offset.value).toISOString()
  const clock = computed(() =>
    new Date(clockTick.value + offset.value).toLocaleTimeString('zh-CN', {
      timeZone: 'Asia/Shanghai',
      hour12: false,
    }),
  )
  const generating = computed(() =>
    requests.value.some((r) => r.status === 'QUEUED' || r.status === 'STREAMING'),
  )
  const sendBlock = computed(() => {
    if (ended.value || blocked.value) return '当前会话不可编辑'
    if (pendingAI.value) return '上一条请求尚待确认，请重连'
    if (generating.value) return '正在生成回复'
    if (selected.value.some((a) => a.status !== 'READY'))
      return '请等待附件完成，或重试 / 移除失败附件'
    return draft.value.trim() || selected.value.length ? '' : '输入消息或添加附件'
  })
  const dirtyPreview = computed(() => activeRun.value !== null && code.value !== ranCode.value)
  const report = (error: unknown) => {
    notice.value = error instanceof Error ? error.message : String(error)
  }

  function localSnapshot(): LocalDraft {
    return {
      code: code.value,
      codeRevision: codeRevision.value,
      plan: plan.value,
      planRevision: planRevision.value,
      draft: draft.value,
      draftId: draftId.value,
      codeBuffer: structuredClone(codeBuffer.data),
      planBuffer: structuredClone(planBuffer.data),
      aiBuffer: structuredClone(aiBuffer.data),
      viewed,
      entered,
      pendingAI: pendingAI.value
        ? (JSON.parse(JSON.stringify(pendingAI.value)) as AICommand)
        : null,
      pendingSubmission: pendingSubmission.value
        ? (JSON.parse(JSON.stringify(pendingSubmission.value)) as SubmissionCommand)
        : null,
      selected: selected.value.map((a) => ({ ...a, file: a.file })),
      away,
    }
  }
  async function persistLocal() {
    if (!session.value) return
    const state = localSnapshot()
    localStorage.setItem('draft-emergency:' + session.value.id, JSON.stringify(state))
    await writeDraft(session.value.id, state)
  }
  const debounceLocal = () => {
    clearTimeout(localTimer)
    localTimer = setTimeout(() => void persistLocal().catch(report), 800)
  }
  function save(
    kind: 'code' | 'plan',
    content = kind === 'code' ? code.value : plan.value,
    revision = kind === 'code' ? codeRevision.value : planRevision.value,
  ) {
    const status = kind === 'code' ? codeSave : planSave
    status.value = '保存中'
    const operation = saveQueue
      .catch(() => {})
      .then(async () => {
        try {
          await api('/workbench/' + kind, {
            method: 'PUT',
            body: JSON.stringify({ content, revision }),
          })
          if (kind === 'code') codeSavedRevision = revision
          if (revision === (kind === 'code' ? codeRevision.value : planRevision.value))
            status.value = '已保存'
        } catch (error) {
          status.value = '保存失败 · 点击重试'
          throw error
        }
      })
    saveQueue = operation
    return operation
  }
  async function saveAll() {
    await persistLocal()
    const frozenCode = code.value,
      frozenPlan = plan.value,
      cr = codeRevision.value,
      pr = planRevision.value
    await save('code', frozenCode, cr)
    await save('plan', frozenPlan, pr)
  }
  function flush(kind: 'code' | 'plan' | 'ai', reason: string) {
    const buffer = kind === 'code' ? codeBuffer : kind === 'plan' ? planBuffer : aiBuffer
    const data = buffer.take()
    if (!data || !collector.value) return
    const payload = {
      edit_changes: data.changes,
      content_length_after: (kind === 'code'
        ? code.value
        : kind === 'plan'
          ? plan.value
          : draft.value
      ).length,
      edit_started_at: data.started,
      last_edit_at: data.last,
      flush_reason: reason,
    }
    if (kind === 'code')
      collector.value.track('code_edited', {
        ...payload,
        base_code_revision: data.base,
        code_revision: codeRevision.value,
      })
    if (kind === 'plan')
      collector.value.track('planner_edited', {
        ...payload,
        base_plan_revision: data.base,
        plan_revision: planRevision.value,
      })
    if (kind === 'ai')
      collector.value.track('ai_request_edited', { ...payload, draft_id: draftId.value })
  }
  function flushAll(reason: string) {
    flush('code', reason)
    flush('plan', reason)
    flush('ai', reason)
    void persistLocal().catch(report)
  }
  function editCode(value: string, paste = false) {
    if (ended.value || blocked.value) return
    const change = diff(code.value, value)
    if (!change) return
    if (paste) {
      flush('code', 'paste')
      // Save the boundary before paste so every edit event can be replayed to a revision.
      void save('code').catch(report)
      code.value = value
      codeRevision.value++
      collector.value?.track('code_pasted', {
        pasted_text: change.inserted_text,
        paste_source: copied?.text === change.inserted_text ? 'AI response' : 'other',
        source_response_id: copied?.text === change.inserted_text ? copied.response : null,
        edit_range: change.edit_range,
        code_revision: codeRevision.value,
      })
      void save('code').catch(report)
    } else {
      codeBuffer.add(change, codeRevision.value, now())
      code.value = value
      codeRevision.value++
    }
    codeSave.value = '尚未保存'
    debounceLocal()
  }
  function editPlan(value: string) {
    const change = diff(plan.value, value)
    if (!change) return
    planBuffer.add(change, planRevision.value, now())
    plan.value = value
    planRevision.value++
    planSave.value = '保存中'
    debounceLocal()
    clearTimeout(planTimer)
    planTimer = setTimeout(() => void save('plan').catch(report), 800)
  }
  function editDraft(value: string) {
    const change = diff(draft.value, value)
    if (change) aiBuffer.add(change, 0, now())
    draft.value = value
    debounceLocal()
  }
  function togglePlanner() {
    plannerOpen.value = !plannerOpen.value
    if (plannerOpen.value) collector.value?.track('planner_opened')
    else {
      flush('plan', 'close')
      void save('plan').catch(report)
      void persistLocal().catch(report)
    }
  }
  function navigate(target: 'task' | 'workbench') {
    if (target === page.value) return
    if (target === 'task') {
      flushAll('leave')
      void saveAll().catch(report)
      collector.value?.track('task_revisited', { from_page: 'workbench' })
    } else {
      collector.value?.track('workbench_entered', { entry_source: entered ? 'return' : 'first' })
      entered = true
    }
    page.value = target
    history.replaceState({}, '', '/' + target)
    void persistLocal().catch(report)
  }
  async function run() {
    if (running.value) return
    const frozen = {
      content: code.value,
      revision: codeRevision.value,
      run_id: crypto.randomUUID(),
      occurred_at: now(),
    }
    running.value = true
    flush('code', 'run')
    await persistLocal()
    try {
      await saveQueue.catch(() => {})
      const result = await post<Run>('/workbench/preview/run', frozen)
      codeSavedRevision = frozen.revision
      if (codeRevision.value === frozen.revision) codeSave.value = '已保存'
      consoleRows.value = []
      activeRun.value = result
      ranCode.value = frozen.content
    } finally {
      running.value = false
    }
  }
  function previewMessage(message: Omit<PreviewMessage, 'message_id'>) {
    if (!activeRun.value || ended.value) return
    const id = crypto.randomUUID(),
      body = { ...message, message_id: id }
    consoleRows.value.push({ id, run_id: activeRun.value.run_id, message: body })
    if (message.kind === 'error') consoleOpen.value = true
    collector.value?.job(`/workbench/preview/${activeRun.value.run_id}/interaction`, body, id)
    void collector.value?.flush()
  }
  async function upload(file: File) {
    const attachment: Attachment = {
      id: crypto.randomUUID(),
      file_name: file.name,
      file_size: file.size,
      status: 'UPLOADING',
      file: markRaw(file),
    }
    selected.value.push(attachment)
    await uploadItem(attachment.id)
  }
  async function uploadItem(id: string) {
    const item = selected.value.find((a) => a.id === id)
    if (!item?.file) {
      notice.value = '请移除此附件并重新选择文件。'
      return
    }
    item.status = 'UPLOADING'
    const form = new FormData()
    form.append('attachment_id', id)
    form.append('file', item.file)
    await persistLocal()
    try {
      item.status = 'PROCESSING'
      const result = await api<Attachment>('/attachments', { method: 'POST', body: form })
      Object.assign(item, result)
    } catch (error) {
      item.status = 'FAILED'
      item.error_message = (error as Error).message
    }
    await persistLocal()
  }
  async function retryAttachment(id: string) {
    const item = selected.value.find((a) => a.id === id)
    if (!item?.file) {
      notice.value = '刷新后请重新选择原文件。'
      return
    }
    const file = item.file
    await removeAttachment(id)
    await upload(file)
  }
  async function removeAttachment(id: string) {
    const item = selected.value.find((a) => a.id === id)
    if (item && !['UPLOADING', 'PROCESSING'].includes(item.status)) {
      try {
        await api('/attachments/' + id, { method: 'DELETE' })
      } catch (error) {
        if ((error as { status?: number }).status !== 404) throw error
      }
    }
    selected.value = selected.value.filter((a) => a.id !== id)
    await persistLocal()
  }
  async function connectStream(request: AIRequest) {
    streamError.value = ''
    let response = responses.value.find((r) => r.id === request.response_id)
    if (!response) {
      responses.value.push({
        id: request.response_id,
        request_id: request.id,
        response_text: '',
        status: 'PENDING',
        model_name: '',
      })
      response = responses.value[responses.value.length - 1]!
    }
    try {
      await sse(
        '/ai/requests/' + request.id + '/stream?offset=' + [...response.response_text].length,
        (event, raw) => {
          if (event === 'chunk') {
            const data = raw as { delta: string }
            response!.response_text += data.delta
            request.status = 'STREAMING'
          }
          if (event === 'done') {
            const data = raw as { request: AIRequest; response: AIResponse }
            Object.assign(request, data.request)
            Object.assign(response!, data.response)
          }
        },
      )
    } catch (error) {
      streamError.value = (error as Error).message
    }
  }
  async function send(retry?: AIRequest) {
    if (!retry && sendBlock.value && !pendingAI.value) return
    if (retry && generating.value) return
    if (!pendingAI.value) {
      flush('ai', 'send')
      pendingAI.value = {
        request_id: crypto.randomUUID(),
        draft_id: retry?.command.draft_id || draftId.value,
        message_text: retry?.command.message_text ?? draft.value,
        attachment_ids: retry?.command.attachment_ids || selected.value.map((a) => a.id),
        retry_of_request_id: retry?.id || null,
        occurred_at: now(),
      }
    }
    await persistLocal()
    const command = pendingAI.value!
    const route = command.retry_of_request_id
      ? `/ai/requests/${command.retry_of_request_id}/retry`
      : '/ai/requests'
    let result: AIRequest
    try {
      result = await post<AIRequest>(route, command)
    } catch (error) {
      if (error instanceof ApiError && !error.retryable) {
        pendingAI.value = null
        await persistLocal()
      }
      throw error
    }
    let request = requests.value.find((r) => r.id === result.id)
    if (!request) {
      requests.value.push(result)
      request = requests.value[requests.value.length - 1]!
    }
    if (!command.retry_of_request_id) {
      if (draft.value === command.message_text) {
        draft.value = ''
        draftId.value = crypto.randomUUID()
      }
      selected.value = selected.value.filter((a) => !command.attachment_ids.includes(a.id))
    }
    pendingAI.value = null
    await persistLocal()
    void connectStream(request)
  }
  async function copyResponse(response: AIResponse, content: string, type: 'text' | 'code') {
    await navigator.clipboard.writeText(content)
    copied = { text: content, response: response.id }
    collector.value?.track('ai_response_copied', { response_id: response.id, content_type: type })
    notice.value = type === 'code' ? '代码已复制，可粘贴到编辑器。' : '回复已复制。'
  }
  async function copyError(row: ConsoleRow) {
    await navigator.clipboard.writeText(row.message.text || '')
    collector.value?.track('preview_error_copied', { error_id: row.id })
    notice.value = '错误信息已复制。'
  }
  function openSubmit() {
    submitDialog.value = true
    collector.value?.track('submit_dialog_opened')
  }
  function cancelSubmit() {
    submitDialog.value = false
    collector.value?.track('submit_cancelled')
  }
  async function submit() {
    if (submitting.value) return
    if (!pendingSubmission.value) {
      pendingSubmission.value = {
        submission_id: crypto.randomUUID(),
        snapshot_id: crypto.randomUUID(),
        code: code.value,
        plan: plan.value,
        code_revision: codeRevision.value,
        plan_revision: planRevision.value,
        occurred_at: now(),
      }
      flushAll('submit')
    }
    submitDialog.value = false
    submitting.value = true
    try {
      await persistLocal()
      await saveQueue.catch(() => {})
      const result = await post<Submission>('/submissions', pendingSubmission.value)
      const index = submissions.value.findIndex((s) => s.id === result.id)
      if (index === -1) submissions.value.push(result)
      else submissions.value[index] = result
      pendingSubmission.value = null
      await persistLocal()
      if (result.status !== 'SUCCEEDED')
        throw new Error(result.error_message || '提交未完成，请重新确认提交。')
      notice.value = '作品提交成功。你可以继续修改并再次提交。'
    } catch (error) {
      if (error instanceof ApiError && !error.retryable) {
        pendingSubmission.value = null
        await persistLocal()
      }
      throw error
    } finally {
      submitting.value = false
    }
  }
  async function endSession() {
    flushAll('end')
    await saveAll()
    await collector.value?.flush()
    if (collector.value?.stats.pending) throw new Error('仍有事件等待补传，请恢复连接后再结束。')
    session.value = await post<Session>('/session/end')
    notice.value = '会话已结束，最后保存的草稿已归档。'
  }
  function visibility(hidden: boolean, reason: string) {
    if (!initialized.value || ended.value || blocked.value) return
    if (hidden && !away) {
      away = true
      flushAll('leave')
      collector.value?.track('window_left', { leave_reason: reason })
      void saveAll().catch(report)
    } else if (!hidden && away) {
      away = false
      collector.value?.track('window_returned', { return_reason: reason })
      void persistLocal().catch(report)
    }
  }
  async function start() {
    try {
      const query = new URLSearchParams(location.search),
        seat = query.get('seat'),
        seatToken = query.get('token')
      const begin = Date.now()
      if (seat && seatToken) {
        session.value = await post<Session>('/session/bootstrap', { seat, token: seatToken })
        localStorage.setItem('session-token', session.value.token!)
        setToken(session.value.token!)
        history.replaceState({}, '', '/task')
      } else {
        const jwt = localStorage.getItem('session-token')
        if (!jwt) throw new Error('请使用 seed_local.py 输出的座位入口打开本地工作台。')
        setToken(jwt)
        session.value = await api<Session>('/session/me')
      }
      offset.value = Date.parse(session.value.server_now) - (begin + Date.now()) / 2
      if (navigator.locks) {
        await new Promise<void>((resolve) => {
          void navigator.locks.request(
            'workbench-writer:' + session.value!.id,
            { ifAvailable: true },
            async (lock) => {
              if (!lock) {
                blocked.value = true
                fatal.value = '此会话已在另一个标签页打开。请关闭重复标签页后重新加载。'
                resolve()
                return
              }
              resolve()
              await new Promise<void>(() => {})
            },
          )
        })
        if (blocked.value) return
      }
      collector.value = markRaw(new Collector(session.value.id, now))
      await collector.value.recover()
      task.value = await api<Task>('/tasks/' + session.value.task_id)
      const state = await api<WorkbenchState>('/workbench/state')
      code.value = state.code.content
      codeRevision.value = codeSavedRevision = state.code.revision
      plan.value = state.plan.content
      planRevision.value = state.plan.revision
      requests.value = state.ai_requests
      responses.value = state.ai_responses
      submissions.value = state.submissions
      const local = await readDraft<LocalDraft>(session.value.id)
      const emergency = localStorage.getItem('draft-emergency:' + session.value.id)
      const recovered = emergency ? (JSON.parse(emergency) as LocalDraft) : local
      viewed = state.task_viewed
      entered = false
      if (recovered) {
        if (recovered.codeRevision >= codeRevision.value) {
          code.value = recovered.code
          codeRevision.value = recovered.codeRevision
          codeBuffer.data = recovered.codeBuffer
        }
        if (recovered.planRevision >= planRevision.value) {
          plan.value = recovered.plan
          planRevision.value = recovered.planRevision
          planBuffer.data = recovered.planBuffer
        }
        draft.value = recovered.draft
        draftId.value = recovered.draftId
        aiBuffer.data = recovered.aiBuffer
        viewed ||= recovered.viewed
        entered = recovered.entered
        away = recovered.away
        pendingAI.value = recovered.pendingAI
        pendingSubmission.value = recovered.pendingSubmission
        selected.value = recovered.selected.map((a) => ({
          ...a,
          file: local?.selected.find((b) => b.id === a.id)?.file,
          ...state.attachments.find((b) => b.id === a.id),
        }))
        for (const item of selected.value)
          if (item.status === 'PROCESSING' || item.status === 'UPLOADING') {
            item.status = 'FAILED'
            item.error_message = '上传中断，请重试。'
          }
      }
      initialized.value = true
      if (!viewed && !ended.value) {
        collector.value.track('task_viewed', { task_content_version: task.value.version })
        viewed = true
      }
      if (away) visibility(false, 'page_restore')
      await persistLocal()
      for (const request of requests.value)
        if (request.status === 'QUEUED' || request.status === 'STREAMING')
          void connectStream(request)
      setInterval(() => {
        clockTick.value = Date.now()
      }, 1000)
      setInterval(() => void collector.value?.flush(), 2000)
      setInterval(() => {
        if (!ended.value && codeRevision.value !== codeSavedRevision)
          void save('code').catch(report)
      }, 5000)
      setInterval(async () => {
        if (ended.value) return
        const start = Date.now()
        try {
          const info = await post<Session>('/session/heartbeat')
          offset.value = Date.parse(info.server_now) - (start + Date.now()) / 2
          if (info.token) {
            localStorage.setItem('session-token', info.token)
            setToken(info.token)
          }
          connected.value = true
        } catch {
          connected.value = false
        }
      }, session.value.heartbeat_interval_sec * 1000)
      window.addEventListener('online', () => void collector.value?.flush())
      document.addEventListener('visibilitychange', () =>
        visibility(document.hidden, 'visibilitychange'),
      )
      window.addEventListener('pagehide', () => visibility(true, 'pagehide'))
      window.addEventListener('pageshow', () => visibility(false, 'pageshow'))
      window.addEventListener('beforeunload', () => {
        flushAll('leave')
        void persistLocal()
      })
      void collector.value.flush()
    } catch (error) {
      fatal.value = (error as Error).message
    }
  }
  return {
    session,
    task,
    collector,
    initialized,
    fatal,
    notice,
    page,
    blocked,
    clock,
    connected,
    code,
    codeRevision,
    plan,
    planRevision,
    draft,
    codeSave,
    planSave,
    plannerOpen,
    selected,
    requests,
    responses,
    streamError,
    pendingAI,
    activeRun,
    running,
    consoleRows,
    consoleOpen,
    submitDialog,
    submitting,
    submissions,
    pendingSubmission,
    diagnosticsOpen,
    ended,
    generating,
    sendBlock,
    dirtyPreview,
    now,
    report,
    start,
    editCode,
    editPlan,
    editDraft,
    save,
    navigate,
    togglePlanner,
    run,
    previewMessage,
    upload,
    retryAttachment,
    removeAttachment,
    send,
    connectStream,
    copyResponse,
    copyError,
    openSubmit,
    cancelSubmit,
    submit,
    endSession,
  }
})
