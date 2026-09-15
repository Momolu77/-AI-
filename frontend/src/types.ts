export interface MetacogState {
  planning: number | null;
  monitoring: number | null;
  evaluation: number | null;
  confidence: {
    planning: number;
    monitoring: number;
    evaluation: number;
  };
  status: {
    planning: string;
    monitoring: string;
    evaluation: string;
  };
  feature_coverage: number;
  computation_version?: string;
  features?: Record<string, any>;
  timestamp?: Date;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

export interface Intervention {
  type: string;
  reason: string;
  content: string;
  timestamp: Date;
}

export interface WSMessage {
  type: 'state_update' | 'intervention' | 'ai_reply' | 'ai_reply_chunk' | 'ai_reply_done' | 'ack' | 'error' | 'pong';
  data: any;
}

export interface SessionInfo {
  sessionId: string;
  userId: string;
  taskType: 'subject' | 'writing' | 'problem_solving';
  taskDescription?: string;
}
