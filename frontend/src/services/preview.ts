import { z } from 'zod'
const schema = z.object({
  app: z.literal('teaching-preview'),
  run_id: z.string(),
  channel: z.string(),
  kind: z.enum(['ready', 'log', 'warn', 'error', 'interaction']),
  text: z.string().max(20000).optional(),
  error_type: z.string().optional(),
  error_phase: z.enum(['load', 'interaction']).optional(),
  line: z.number().int().nonnegative().nullable().optional(),
  column: z.number().int().nonnegative().nullable().optional(),
  stack: z.string().nullable().optional(),
  interaction_type: z.enum(['click', 'change', 'submit']).optional(),
  target: z.string().max(500).optional(),
  outcome: z.string().nullable().optional(),
})
export function validatePreview(
  event: MessageEvent,
  source: Window | null,
  run: { run_id: string; channel: string } | null,
) {
  if (!source || event.source !== source || !run) return null
  const result = schema.safeParse(event.data)
  if (!result.success || result.data.run_id !== run.run_id || result.data.channel !== run.channel)
    return null
  const { app: _app, run_id: _run, ...message } = result.data
  void _app
  void _run
  return message
}
