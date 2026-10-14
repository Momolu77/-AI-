export const writerId = sessionStorage.getItem('writer-id') || crypto.randomUUID()
sessionStorage.setItem('writer-id', writerId)
let token = ''
export const setToken = (value: string) => {
  token = value
}
export const getToken = () => token
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public retryable: boolean,
    public status: number,
  ) {
    super(message)
  }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch('/api/v1' + path, {
      ...options,
      signal: options.signal ?? AbortSignal.timeout(60000),
      headers: {
        ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        Authorization: 'Bearer ' + token,
        'X-Writer-Id': writerId,
        ...options.headers,
      },
    })
  } catch {
    throw new ApiError('NETWORK', '本地服务暂未连接，内容已保留，请重试。', true, 0)
  }
  const body = await response.json()
  if (body.code === 'RESEARCH_STOPPED') window.dispatchEvent(new Event('research-stopped'))
  if (!response.ok)
    throw new ApiError(body.code, body.message || '请求失败', body.retryable, response.status)
  return body as T
}
export const post = <T>(path: string, body?: unknown) => {
  const command = body && typeof body === 'object' ? (body as Record<string, unknown>) : {}
  const key = command.request_id ?? command.submission_id ?? command.run_id
  return api<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: typeof key === 'string' ? { 'Idempotency-Key': key } : {},
  })
}

export async function sse(path: string, receive: (event: string, data: unknown) => void) {
  const response = await fetch('/api/v1' + path, { headers: { Authorization: 'Bearer ' + token } })
  if (!response.ok || !response.body) throw new Error('回复连接中断，可以重新连接查看已保存内容。')
  const reader = response.body.getReader(),
    decoder = new TextDecoder()
  let buffer = '',
    doneReceived = false
  while (true) {
    const part = await reader.read()
    buffer += decoder.decode(part.value, { stream: !part.done }).replace(/\r\n/g, '\n')
    let boundary: number
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const event = block
        .split('\n')
        .find((l) => l.startsWith('event:'))
        ?.slice(6)
        .trim()
      const data = block
        .split('\n')
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).trimStart())
        .join('\n')
      if (event && data) {
        receive(event, JSON.parse(data))
        if (event === 'done') doneReceived = true
      }
    }
    if (part.done) break
  }
  if (!doneReceived) throw new Error('回复流提前断开，已收到的内容仍然保留。')
}
