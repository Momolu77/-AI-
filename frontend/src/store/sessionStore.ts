import { create } from 'zustand'

export interface MetacogState {
  planning: number
  monitoring: number
  evaluation: number
  timestamp?: number
}

export interface Message {
  role: 'user' | 'assistant' | 'intervention'
  content: string
  interventionType?: string
  timestamp: number
}

interface SessionStore {
  sessionId: string | null
  metacogState: MetacogState
  stateHistory: MetacogState[]
  messages: Message[]
  connected: boolean

  setSessionId: (id: string) => void
  setConnected: (v: boolean) => void
  updateMetacogState: (s: MetacogState) => void
  addMessage: (m: Message) => void
  reset: () => void
}

const defaultState: MetacogState = { planning: 0, monitoring: 0, evaluation: 0 }

export const useSessionStore = create<SessionStore>((set) => ({
  sessionId: null,
  metacogState: defaultState,
  stateHistory: [],
  messages: [],
  connected: false,

  setSessionId: (id) => set({ sessionId: id }),
  setConnected: (v) => set({ connected: v }),

  updateMetacogState: (s) =>
    set((prev) => ({
      metacogState: s,
      stateHistory: [...prev.stateHistory.slice(-59), { ...s, timestamp: Date.now() }],
    })),

  addMessage: (m) =>
    set((prev) => ({ messages: [...prev.messages, m] })),

  reset: () =>
    set({ sessionId: null, metacogState: defaultState, stateHistory: [], messages: [], connected: false }),
}))
