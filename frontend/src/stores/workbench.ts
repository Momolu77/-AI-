import { computed, markRaw, ref, shallowRef, nextTick } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, api, post, setToken, sse, writerId, getToken } from '../services/api'
import { copyMarkup, selectedSources, type CopyClaim } from '../services/copy'
import { Collector } from '../services/events'
import { diff, EditBuffer } from '../services/edits'
import type { BufferData } from '../services/edits'
import { readDraft, writeDraft } from '../services/storage'
import type {
  Page,
  TaskSummary,
  Resource,
  ResourceReference,
  Proposal,
  Application,
  EditChange,
  Occurrence,
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
  designRationale?: string
  draftRevision: number
  references: ResourceReference[]
  deltaCount: number
  deltaIds: string[]
  pendingRun: (Occurrence & { run_id: string; content: string; revision: number }) | null
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
    page = ref<Page>('task'),
    blocked = ref(false)
  const tasks = ref<TaskSummary[]>([]),
    resources = ref<Resource[]>([]),
    references = ref<ResourceReference[]>([]),
    proposals = ref<Proposal[]>([]),
    applications = ref<Application[]>([]),
    draftRevision = ref(0),
    referenceBusy = ref(false),
    applying = ref(false),
    applicationBusy = ref(false),
    fullscreen = ref(false)
  const pendingRun = ref<
    (Occurrence & { run_id: string; content: string; revision: number }) | null
  >(null)
  let deltaCount = 0,
    deltaIds: string[] = [],
    visitIndex = 0
  let deltaTimer: ReturnType<typeof setTimeout>, maxEditTimer: ReturnType<typeof setTimeout>
  const occurrence = () => collector.value!.occurrence()
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
    sending = ref(false),
    pendingSubmission = ref<SubmissionCommand | null>(null)
  const activeRun = ref<Run | null>(null),
    running = ref(false),
    ranCode = ref(''),
    consoleRows = ref<ConsoleRow[]>([]),
    consoleOpen = ref(true)
  const submitDialog = ref(false),
    designRationale = ref(''),
    submitting = ref(false),
    submissions = ref<Submission[]>([])
  const diagnosticsOpen = ref(false),
    ended = computed(() => ['ENDED', 'ABANDONED'].includes(session.value?.status || ''))
  const active = computed(() => session.value?.status === 'ACTIVE' && !blocked.value)
  const previewState = ref<'empty' | 'loading' | 'loaded' | 'failed' | 'timeout'>('empty')
  let loadId = '', loadTimer: ReturnType<typeof setTimeout>
  let viewed = false,
    entered = false,
    away = false,
    copied: CopyClaim | null = null
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
    if (!active.value || blocked.value) return '当前会话不可编辑'
    if (sending.value) return '正在发送'
    if (referenceBusy.value) return '正在加入教材引用'
    if (pendingAI.value) return '上一条请求尚待确认，请重连'
    if (generating.value) return '正在生成回复'
    if (selected.value.some((a) => a.status !== 'READY'))
      return '请等待附件完成，或重试 / 移除失败附件'
    return draft.value.trim() || selected.value.length || references.value.length
      ? ''
      : '输入消息或添加附件'
  })
  const dirtyPreview = computed(() => activeRun.value !== null && code.value !== ranCode.value)
  const report = (error: unknown) => {
    notice.value = error instanceof Error ? error.message : String(error)
  }

  function localSnapshot(): LocalDraft {
    return {
      designRationale: designRationale.value,
      draftRevision: draftRevision.value,
      references: JSON.parse(JSON.stringify(references.value)),
      deltaCount,
      deltaIds: [...deltaIds],
      pendingRun: pendingRun.value ? JSON.parse(JSON.stringify(pendingRun.value)) : null,
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
    await saveRequestDraft()
  }
  function flush(kind: 'code' | 'plan' | 'ai', reason: string) {
    if (kind === 'code') flushDelta(reason)
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
        delta_ids: [...deltaIds],
      })
    if (kind === 'plan')
      collector.value.track('planner_edited', {
        ...payload,
        base_plan_revision: data.base,
        plan_revision: planRevision.value,
      })
    if (kind === 'ai')
      collector.value.track('ai_request_edited', {
        ...payload,
        draft_id: draftId.value,
        base_draft_revision: data.base,
        draft_revision: draftRevision.value,
      })
    if (kind === 'code') {
      deltaCount = 0
      deltaIds = []
      clearTimeout(maxEditTimer)
    }
  }
  function flushAll(reason: string) {
    flush('code', reason)
    flush('plan', reason)
    flush('ai', reason)
    void persistLocal().catch(report)
  }
  function flushDelta(reason: string) {
    const changes = codeBuffer.data.changes.slice(deltaCount)
    if (!changes.length || !collector.value) return
    const delta_id = crypto.randomUUID()
    collector.value.track('code_edit_delta', {
      delta_id,
      base_code_revision: changes[0]!.base_revision,
      code_revision: changes.at(-1)!.result_revision,
      changes,
      trigger_reason: reason,
    })
    deltaCount += changes.length
    deltaIds.push(delta_id)
    void persistLocal().catch(report)
  }
  function editCode(
    value: string,
    paste = false,
    transactionChanges?: EditChange[],
    pasteClaim?: CopyClaim | null,
  ) {
    if (!active.value || blocked.value || applying.value) return
    const change = diff(code.value, value)
    if (!change) return
    if (paste) {
      copied = pasteClaim && pasteClaim.sid === session.value?.id ? pasteClaim : null
      flush('code', 'paste')
      // Save the boundary before paste so every edit event can be replayed to a revision.
      void save('code').catch(report)
      code.value = value
      codeRevision.value++
      collector.value?.track('code_pasted', {
        pasted_text: change.inserted_text,
        paste_source: copied?.text === change.inserted_text ? 'ai_response' : 'other',
        source_response_id: copied?.text === change.inserted_text ? copied.response : null,
        edit_range: change.edit_range,
        base_code_revision: codeRevision.value - 1,
        code_revision: codeRevision.value,
      })
      void save('code').catch(report)
    } else {
      if (!codeBuffer.data.changes.length)
        maxEditTimer = setTimeout(() => {
          flush('code', 'idle')
          void persistLocal().catch(report)
        }, 30000)
      for (const atom of transactionChanges || [change])
        codeBuffer.add(atom, codeRevision.value, now())
      clearTimeout(deltaTimer)
      deltaTimer = setTimeout(() => flushDelta('debounce'), 500)
      code.value = value
      codeRevision.value++
    }
    codeSave.value = '尚未保存'
    debounceLocal()
  }
  function editPlan(value: string) {
    if (!active.value) return
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
    if (!active.value) return
    const change = diff(draft.value, value)
    if (change) {
      aiBuffer.add(change, draftRevision.value, now())
      draftRevision.value++
    }
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
  function navigate(target: Page) {
    if (target === page.value) return
    if (!active.value && !ended.value) return
    if (active.value) {
      flushAll('tab_switch')
      void saveAll().catch(report)
      const action = crypto.randomUUID()
      collector.value?.track(
        'nav_changed',
        { from_page: page.value, to_page: target, visit_index: ++visitIndex },
        collector.value.occurrence(action),
      )
      if (target === 'task')
        collector.value?.track(
          'task_revisited',
          { from_page: page.value, task_content_version: task.value!.task_content_version || task.value!.version },
          collector.value.occurrence(action),
        )
      if (target === 'workbench') {
        collector.value?.track(
          'workbench_entered',
          { entry_source: entered ? 'return' : 'first' },
          collector.value.occurrence(action),
        )
        entered = true
      }
    }
    page.value = target
    void nextTick(() => layout('nav'))
    history.replaceState({}, '', '/' + target)
    void persistLocal().catch(report)
  }
  async function saveRequestDraft() {
    if (!active.value) return
    await api('/drafts/' + draftId.value, {
      method: 'PUT',
      body: JSON.stringify({
        content: draft.value,
        revision: draftRevision.value,
        attachment_ids: selected.value.map((a) => a.id),
        reference_ids: references.value.map((r) => r.reference_id),
      }),
    })
  }
  async function addReference(resource: Resource, page: number, purpose: string | null = null, note: string | null = null) {
    if (referenceBusy.value) return
    referenceBusy.value = true
    try {
    const draftAtClick = draftId.value
    const body = {
      ...occurrence(),
      reference_id: crypto.randomUUID(),
      resource_id: resource.id,
      resource_version: resource.version,
      draft_revision: draftRevision.value,
      page,
      fragment: null,
      reference_purpose: purpose,
      reference_note: note,
    }
    const item = await post<ResourceReference>('/drafts/' + draftAtClick + '/references', body)
    if (draftAtClick === draftId.value) references.value.push(item)
    await saveRequestDraft()
    await persistLocal()
    notice.value = '已加入当前 AI 消息引用'
    } finally { referenceBusy.value = false }
  }
  async function removeReference(item: ResourceReference) {
    await api('/drafts/' + draftId.value + '/references/' + item.reference_id, {
      method: 'DELETE',
      body: JSON.stringify({ ...occurrence(), draft_revision: draftRevision.value }),
    })
    references.value = references.value.filter((r) => r.reference_id !== item.reference_id)
    await saveRequestDraft()
    await persistLocal()
  }
  function layout(reason: string) {
    if (!active.value || !collector.value) return
    const regions = [
      'chat',
      'editor',
      'preview',
      'planner',
      'console',
      'task',
      'example',
      'textbook',
    ].map((region_id) => {
      const element = document.querySelector<HTMLElement>('[data-region="' + region_id + '"]'),
        rect = element?.getBoundingClientRect()
      const visible = !!(
        rect &&
        rect.width &&
        rect.height &&
        element?.checkVisibility() &&
        !document.hidden &&
        (region_id !== 'console' || consoleOpen.value)
      )
      const occluded_bounds: { x: number; y: number; width: number; height: number }[] = []
      const planner = document.querySelector<HTMLElement>('[data-region="planner"]')
      if (
        visible &&
        ['preview', 'task', 'example', 'textbook'].includes(region_id) &&
        rect &&
        planner?.checkVisibility()
      ) {
        const overlay = planner.getBoundingClientRect()
        const x = Math.max(rect.left, overlay.left),
          y = Math.max(rect.top, overlay.top)
        const right = Math.min(rect.right, overlay.right),
          bottom = Math.min(rect.bottom, overlay.bottom)
        if (right > x && bottom > y)
          occluded_bounds.push({ x, y, width: right - x, height: bottom - y })
      }
      return {
        region_id,
        is_visible: visible,
        bounds: rect
          ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
          : { x: 0, y: 0, width: 0, height: 0 },
        occluded_bounds,
      }
    })
    collector.value.track('ui_region_visibility_changed', {
      change_reason: reason,
      regions,
      viewport: { width: innerWidth, height: innerHeight, device_pixel_ratio: devicePixelRatio },
    })
  }
  async function decideProposal(
    p: Proposal,
    decision: 'accept' | 'reject',
    displayId: string | null,
    elapsed: number | null,
  ) {
    const key = 'decision:' + p.id,
      saved = localStorage.getItem(key)
    const command = saved
      ? JSON.parse(saved)
      : {
          ...occurrence(),
          decision,
          display_event_id: displayId,
          decision_display_elapsed_ms: elapsed,
        }
    localStorage.setItem(key, JSON.stringify(command))
    await collector.value?.flush()
    const value = await post<Proposal>('/ai/proposals/' + p.id + '/decision', command)
    localStorage.removeItem(key)
    Object.assign(p, value)
  }
  async function applyProposal(p: Proposal) {
    if (applicationBusy.value) return
    const key = 'application:' + p.id,
      old = localStorage.getItem(key)
    if (applying.value && !old) return
    if (!old) flush('code', 'proposal')
    applying.value = true
    applicationBusy.value = true
    let settled = false
    try {
      if (!old) await save('code')
      await persistLocal()
      const command = old
        ? JSON.parse(old)
        : {
            application_id: crypto.randomUUID(),
            retry_of_application_id:
              applications.value
                .filter((a) => a.proposal_id === p.id && a.status === 'FAILED')
                .at(-1)?.application_id || null,
            current_revision: codeRevision.value,
          }
      localStorage.setItem(key, JSON.stringify(command))
      const result = await post<Application>('/ai/proposals/' + p.id + '/applications', command)
      if (!applications.value.some((a) => a.application_id === result.application_id))
        applications.value.push(result)
      settled = true
      if (result.status === 'APPLIED' && result.code_revision! >= codeRevision.value) {
        code.value = result.content!
        codeRevision.value = result.code_revision!
        codeSavedRevision = codeRevision.value
        codeSave.value = '已保存'
      } else notice.value = result.error_message || '应用失败'
      localStorage.removeItem(key)
      await persistLocal()
    } catch (error) {
      if (error instanceof ApiError && !error.retryable) {
        settled = true
        localStorage.removeItem(key)
      }
      throw error
    } finally {
      applicationBusy.value = false
      applying.value = !settled
    }
  }
  async function run() {
    if (running.value || applying.value) return
    if (!pendingRun.value) flush('code', 'run')
    const frozen = pendingRun.value || {
      ...occurrence(),
      content: code.value,
      revision: codeRevision.value,
      run_id: crypto.randomUUID(),
    }
    pendingRun.value = frozen
    running.value = true
    await persistLocal()
    try {
      await saveQueue.catch(() => {})
      const result = await post<Run>('/workbench/preview/run', frozen)
      codeSavedRevision = frozen.revision
      if (codeRevision.value === frozen.revision) codeSave.value = '已保存'
      consoleRows.value = []
      beginPreview(result)
      ranCode.value = frozen.content
      pendingRun.value = null
      await persistLocal()
    } catch (error) {
      if (error instanceof ApiError && error.code === 'SAVE_FAILED') {
        pendingRun.value = null
        await persistLocal()
      }
      throw error
    } finally {
      running.value = false
    }
  }
  function beginPreview(run: Run) {
    clearTimeout(loadTimer)
    loadId = crypto.randomUUID()
    activeRun.value = run
    previewState.value = 'loading'
    const command = { ...occurrence(), load_id: loadId, state: 'loading', reason: 'iframe_bound' }
    collector.value?.job(`/workbench/preview/${run.run_id}/load`, command, command.event_id)
    void collector.value?.flush()
    loadTimer = setTimeout(() => previewFailed('handshake_timeout'), 15000)
  }
  function previewFailed(reason: string) {
    if (!activeRun.value || previewState.value !== 'loading') return
    clearTimeout(loadTimer)
    previewState.value = reason === 'handshake_timeout' ? 'timeout' : 'failed'
    const command = { ...occurrence(), load_id: loadId, state: previewState.value, reason }
    collector.value?.job(`/workbench/preview/${activeRun.value.run_id}/load`, command, command.event_id)
    void collector.value?.flush()
  }
  function previewMessage(message: PreviewMessage) {
    if (!activeRun.value || ended.value) return
    const id = message.message_id,
      body = {
        ...message,
        load_id: loadId,
        occurred_at: new Date(Date.parse(message.occurred_at) + offset.value).toISOString(),
        transport: {
          ...message.transport,
          clock_calibration_id: collector.value?.calibrationId || null,
        },
      }
    consoleRows.value.push({ id, run_id: activeRun.value.run_id, message: body })
    if (message.kind === 'ready') {
      clearTimeout(loadTimer)
      previewState.value = 'loaded'
    }
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
        await api('/attachments/' + id, {
          method: 'DELETE',
          body: JSON.stringify({
            ...occurrence(),
            draft_id: draftId.value,
            draft_revision: draftRevision.value,
          }),
        })
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
        content_revision: 0,
      })
      response = responses.value[responses.value.length - 1]!
    }
    try {
      await sse(
        '/ai/requests/' + request.id + '/stream?offset=' + [...response.response_text].length,
        (event, raw) => {
          if (event === 'chunk') {
            const data = raw as { response_text: string; content_revision: number }
            response!.response_text = data.response_text
            response!.content_revision = data.content_revision
            request.status = 'STREAMING'
          }
          if (event === 'done') {
            const data = raw as { request: AIRequest; response: AIResponse }
            Object.assign(request, data.request)
            Object.assign(response!, data.response)
          }
        },
      )
      const state = await api<WorkbenchState>('/workbench/state')
      proposals.value = state.ai_proposals
    } catch (error) {
      streamError.value = (error as Error).message
    }
  }
  async function send(retry?: AIRequest) {
    if (sending.value) return
    if (!retry && sendBlock.value && !pendingAI.value) return
    if (retry && generating.value) return
    sending.value = true
    try {
      await performSend(retry)
    } finally {
      sending.value = false
    }
  }
  async function performSend(retry?: AIRequest) {
    if (!pendingAI.value) {
      const frozenCode = code.value,
        frozenRevision = codeRevision.value
      const command: AICommand = {
        ...occurrence(),
        draft_revision: retry?.command.draft_revision ?? draftRevision.value,
        reference_ids: retry?.command.reference_ids || references.value.map((r) => r.reference_id),
        base_code_revision: retry?.command.base_code_revision ?? frozenRevision,
        request_id: crypto.randomUUID(),
        draft_id: retry?.command.draft_id || draftId.value,
        message_text: retry?.command.message_text ?? draft.value,
        attachment_ids: retry?.command.attachment_ids || selected.value.map((a) => a.id),
        retry_of_request_id: retry?.id || null,
      }
      flush('ai', 'send')
      // Invoke while the click-time draft is still current; API serializes synchronously.
      await saveRequestDraft()
      await save('code', frozenCode, frozenRevision)
      pendingAI.value = command
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
        draftRevision.value = 0
        references.value = []
        draftId.value = crypto.randomUUID()
      }
      selected.value = selected.value.filter((a) => !command.attachment_ids.includes(a.id))
    }
    pendingAI.value = null
    await persistLocal()
    void connectStream(request)
  }
  async function copyResponse(response: AIResponse, content: string, type: 'text' | 'code') {
    const context = occurrence(),
      revision = response.content_revision
    try {
      const html = copyMarkup({ sid: session.value!.id, text: content, response: response.id })
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/plain': new Blob([content], { type: 'text/plain' }),
          'text/html': new Blob([html], { type: 'text/html' }),
        }),
      ])
    } catch {
      await navigator.clipboard.writeText(content)
    }
    collector.value?.track(
      'ai_response_copied',
      {
        response_id: response.id,
        content_type: type,
        content_revision: revision,
        selection_ranges: response.response_text.includes(content)
          ? [
              {
                start: response.response_text.indexOf(content),
                end: response.response_text.indexOf(content) + content.length,
              },
            ]
          : null,
      },
      context,
    )
    notice.value = type === 'code' ? '代码已复制，可粘贴到编辑器。' : '回复已复制。'
  }
  function nativeCopy(event: ClipboardEvent) {
    if (!active.value || !collector.value) return
    const selection = getSelection(),
      text = selection?.toString() || ''
    if (!text || !selection?.rangeCount) return
    const sources = selectedSources(),
      gesture = crypto.randomUUID()
    for (const source of sources)
      collector.value.track(
        'ai_response_copied',
        {
          response_id: source.response,
          content_revision: source.revision,
          content_type: source.type,
          selection_ranges: source.ranges,
        },
        collector.value.occurrence(gesture),
      )
    const errorIds = new Set<string>()
    for (const el of document.querySelectorAll<HTMLElement>('[data-error-id]'))
      if (selection.getRangeAt(0).intersectsNode(el)) errorIds.add(el.dataset.errorId!)
    for (const error_id of errorIds)
      collector.value.track(
        'preview_error_copied',
        { error_id },
        collector.value.occurrence(gesture),
      )
    const ids = new Set(sources.map((s) => s.response))
    const covered = sources
      .flatMap((s) => s.ranges.map((r) => ({ response: s.response, ...r })))
      .sort((a, b) => a.start - b.start)
      .map(
        (r) =>
          responses.value.find((x) => x.id === r.response)?.response_text.slice(r.start, r.end) ||
          '',
      )
      .join('')
    if (ids.size === 1 && covered === text && !errorIds.size && event.clipboardData) {
      event.clipboardData.setData('text/plain', text)
      event.clipboardData.setData(
        'text/html',
        copyMarkup({ sid: session.value!.id, response: sources[0]!.response, text }),
      )
      event.preventDefault()
    }
  }
  async function copyError(row: ConsoleRow) {
    const context = occurrence()
    await navigator.clipboard.writeText(row.message.text || '')
    collector.value?.track('preview_error_copied', { error_id: row.id }, context)
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
        ...occurrence(),
        submission_id: crypto.randomUUID(),
        snapshot_id: crypto.randomUUID(),
        code: code.value,
        plan: plan.value,
        design_rationale: designRationale.value || null,
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
    window.dispatchEvent(new Event('session-ending'))
    flushAll('session_end')
    await saveAll()
    await collector.value?.flush()
    if (collector.value?.stats.pending) throw new Error('仍有事件等待补传，请恢复连接后再结束。')
    session.value = await post<Session>('/session/end', occurrence())
    notice.value = '会话已结束，最后保存的草稿已归档。'
  }
  function visibility(hidden: boolean, reason: string) {
    if (!initialized.value || !active.value || blocked.value) return
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
      if (seat && seatToken) {
        const entry = await post<{ token: string; tasks: TaskSummary[] }>('/entry/bootstrap', {
          seat,
          token: seatToken,
        })
        localStorage.setItem('entry-token', entry.token)
        setToken(entry.token)
        tasks.value = entry.tasks
        page.value = 'tasks'
        initialized.value = true
        history.replaceState({}, '', '/tasks')
        return
      }
      const token = localStorage.getItem('session-token')
      if (!token) throw new Error('请使用研究者提供的入口链接打开工作台。')
      setToken(token)
      session.value = await api<Session>('/session/me')
      if (!['ENDED', 'ABANDONED'].includes(session.value.status))
        session.value = await post<Session>('/session/heartbeat')
      await loadSession()
    } catch (error) {
      fatal.value = (error as Error).message
    }
  }
  async function selectTask(item: TaskSummary) {
    if (session.value?.task_id === item.task_id && active.value) {
      navigate('task')
      return
    }
    setToken(localStorage.getItem('entry-token') || getToken())
    const info = await post<Session>('/session/bootstrap', {
      task_id: item.task_id,
      assignment_id: item.assignment_id,
      writer_id: writerId,
    })
    localStorage.setItem('session-token', info.token!)
    setToken(info.token!)
    location.assign('/task')
  }
  async function completePrerequisite(
    responses: { question_id: string; answer_value: string | number | null }[],
  ) {
    const key = 'prerequisite:' + session.value!.id
    const previous = localStorage.getItem(key)
    const command = previous
      ? JSON.parse(previous)
      : { ...occurrence(), version: task.value!.prerequisite.version, responses }
    localStorage.setItem(key, JSON.stringify(command))
    session.value = await post<Session>('/session/prerequisite', command)
    localStorage.removeItem(key)
    task.value = await api<Task>('/tasks/' + session.value.task_id)
  }
  async function acknowledgeTask() {
    if (!session.value || !task.value?.description || page.value !== 'task') return
    let startAction: string | null = null
    if (session.value.status === 'PREPARING') {
      const key = 'task-start:' + session.value.id,
        previous = localStorage.getItem(key)
      const command = previous ? JSON.parse(previous) : occurrence()
      localStorage.setItem(key, JSON.stringify(command))
      session.value = await post<Session>('/session/start', command)
      startAction = command.transport.action_id
      localStorage.removeItem(key)
    }
    if (active.value && !viewed) {
      collector.value!.track(
        'task_viewed',
        { task_content_version: task.value.task_content_version || task.value.version },
        collector.value!.occurrence(startAction),
      )
      if (startAction)
        collector.value!.track(
          'nav_changed',
          { from_page: 'preparation', to_page: 'task', visit_index: ++visitIndex },
          collector.value!.occurrence(startAction),
        )
      viewed = true
      await persistLocal()
    }
    if (!resources.value.length)
      resources.value = (
        await api<{ resources: Resource[] }>('/tasks/' + session.value.task_id + '/resources')
      ).resources
  }
  async function calibrate() {
    const begin = Date.now(),
      mono = performance.now(),
      raw = new Date(begin).toISOString()
    const reply = await api<{ server_time: string }>('/clock'),
      end = Date.now()
    offset.value = Date.parse(reply.server_time) - (begin + end) / 2
    const value = {
      id: crypto.randomUUID(),
      producer_id: collector.value!.producer,
      client_send_time: raw,
      client_receive_time: new Date(end).toISOString(),
      server_time: reply.server_time,
      round_trip_ms: performance.now() - mono,
      offset_ms: offset.value,
      uncertainty_ms: (performance.now() - mono) / 2,
    }
    await post('/clock/calibrations', value)
    collector.value!.calibrationId = value.id
  }
  async function loadSession() {
    try {
      if (!session.value) return
      offset.value = Date.parse(session.value.server_now) - Date.now()
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
      await calibrate()
      tasks.value = (await api<{ tasks: TaskSummary[] }>('/tasks')).tasks
      task.value = await api<Task>('/tasks/' + session.value.task_id)
      const state = await api<WorkbenchState>('/workbench/state')
      code.value = state.code.content
      codeRevision.value = codeSavedRevision = state.code.revision
      plan.value = state.plan.content
      planRevision.value = state.plan.revision
      requests.value = state.ai_requests
      responses.value = state.ai_responses
      submissions.value = state.submissions
      proposals.value = state.ai_proposals
      applications.value = state.proposal_applications
      for (const p of proposals.value) {
        const key = 'application:' + p.id,
          raw = localStorage.getItem(key)
        if (raw) {
          const pending = JSON.parse(raw)
          if (applications.value.some((a) => a.application_id === pending.application_id))
            localStorage.removeItem(key)
          else applying.value = true
        }
      }
      const unsent = state.request_drafts
        .filter(
          (d) =>
            !state.ai_requests.some(
              (r) =>
                r.command.draft_id === d.id &&
                r.command.draft_revision === d.revision &&
                r.command.message_text === d.content,
            ),
        )
        .at(-1)
      if (unsent) {
        draft.value = unsent.content
        draftRevision.value = unsent.revision
        draftId.value = unsent.id
        references.value = state.resource_references.filter((r) =>
          unsent.reference_ids.includes(r.reference_id),
        )
        selected.value = state.attachments.filter((a) => unsent.attachment_ids.includes(a.id))
      }
      const savedRun = state.preview_runs
        .filter((r) => ['READY', 'SAVED'].includes(r.status))
        .at(-1)
      if (savedRun) {
        if (active.value) beginPreview(await api<Run>('/workbench/preview/' + savedRun.id))
        ranCode.value = savedRun.command.content
        consoleRows.value = []
      }
      const local = await readDraft<LocalDraft>(session.value.id)
      const emergency = localStorage.getItem('draft-emergency:' + session.value.id)
      const recovered = emergency ? (JSON.parse(emergency) as LocalDraft) : local
      viewed = state.task_viewed
      entered = false
      if (recovered) {
        designRationale.value = recovered.designRationale || ''
        draftRevision.value = recovered.draftRevision || 0
        references.value = recovered.references || []
        deltaCount = recovered.deltaCount || 0
        deltaIds = recovered.deltaIds || []
        pendingRun.value = recovered.pendingRun || null
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
      if (away) visibility(false, 'page_restore')
      await persistLocal()
      for (const request of requests.value)
        if (request.status === 'QUEUED' || request.status === 'STREAMING')
          void connectStream(request)
      setInterval(() => {
        clockTick.value = Date.now()
      }, 1000)
      setInterval(() => { if (!blocked.value) void collector.value?.flush() }, 2000)
      setInterval(() => {
        if (active.value) void saveRequestDraft().catch(report)
        if (active.value && codeRevision.value !== codeSavedRevision)
          void save('code').catch(report)
      }, 5000)
      setInterval(async () => {
        if (ended.value || !session.value) return
        try {
          const info = await post<Session>('/session/heartbeat')
          if (info.status === 'ACTIVE' || info.status === 'PREPARING') await calibrate()
          if (info.token) {
            localStorage.setItem('session-token', info.token)
            setToken(info.token)
          }
          session.value = info
          connected.value = true
        } catch {
          connected.value = false
        }
      }, session.value.heartbeat_interval_sec * 1000)
      document.addEventListener('copy', nativeCopy)
      window.addEventListener('research-stopped', () => {
        blocked.value = true
        clearTimeout(localTimer); clearTimeout(planTimer); clearTimeout(deltaTimer); clearTimeout(maxEditTimer); clearTimeout(loadTimer)
        notice.value = '研究采集已停止，请联系研究者。'
      })
      window.addEventListener('online', () => void collector.value?.flush())
      document.addEventListener('visibilitychange', () => {
        visibility(document.hidden, 'visibilitychange')
        layout('visibilitychange')
      })
      window.addEventListener('pagehide', (event) => {
        visibility(true, 'pagehide')
        void api('/session/detach', {
          method: 'POST',
          keepalive: true,
          body: JSON.stringify({ ...occurrence(), persisted: event.persisted }),
        }).catch(() => {})
      })
      window.addEventListener('pageshow', () => {
        visibility(false, 'pageshow')
        if (session.value && !ended.value)
          void post<Session>('/session/heartbeat')
            .then((s) => {
              session.value = s
            })
            .catch(report)
      })
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
    referenceBusy,
    designRationale,
    persistLocal,
    previewState,
    previewFailed,
    tasks,
    resources,
    references,
    proposals,
    applications,
    applying,
    applicationBusy,
    fullscreen,
    pendingRun,
    active,
    selectTask,
    completePrerequisite,
    acknowledgeTask,
    addReference,
    removeReference,
    decideProposal,
    applyProposal,
    layout,
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
