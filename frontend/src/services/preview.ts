import { z } from 'zod'
const schema = z.object({
  event_id: z.string(),
  message_id: z.string(),
  occurred_at: z.string(),
  transport: z.object({
    producer_id: z.string(),
    producer_seq: z.number(),
    raw_time: z.string(),
    monotonic_ms: z.number(),
    clock_calibration_id: z.string().nullable(),
    time_source: z.literal('iframe_clock'),
    action_id: z.string(),
    causal_parent_ids: z.array(z.string()),
  }),
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
  interaction_type: z.enum(['activate', 'change', 'input_commit', 'submit']).optional(),
  target: z
    .object({
      tag: z.string(),
      id: z.string().nullable(),
      role: z.string().nullable(),
      label: z.string(),
    })
    .optional(),
  outcome_source: z.enum(['artifact', 'unknown']).optional(),
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
