import { useState, useEffect } from 'react';
import { message } from 'antd';
import { useParams } from 'react-router-dom';
import WorkspaceLayout from '../components/WorkspaceLayout';
import { useWebSocket } from '../hooks/useWebSocket';
import type { MetacogState, Intervention } from '../types';

export default function SessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [currentState, setCurrentState] = useState<MetacogState | null>(null);
  const [stateHistory, setStateHistory] = useState<MetacogState[]>([]);

  const { isConnected, sendMessage, sendEvent } = useWebSocket({
    sessionId: sessionId!,
    onStateUpdate: (state) => {
      console.log('[State Update]', state);
      setCurrentState(state);
      setStateHistory((prev) => [...prev, state]);
    },
    onIntervention: (intervention) => {
      console.log('[Intervention]', intervention);
      (window as any).__chatInterface?.addIntervention(intervention);
      message.warning({
        content: `元认知干预: ${intervention.type}`,
        duration: 3,
      });
    },
    onAIReplyChunk: (chunk) => {
      console.log('[AI Chunk]', chunk);
      (window as any).__chatInterface?.appendAIChunk(chunk);
    },
    onAIReplyDone: (content) => {
      console.log('[AI Done]', content);
      (window as any).__chatInterface?.finishAIMessage();
    },
    onAIReply: (content) => {
      console.log('[AI Reply]', content);
      (window as any).__chatInterface?.addAIMessage(content);
    },
    onError: (error) => {
      console.error('[Error]', error);
      message.error(error);
    },
  });

  useEffect(() => {
    if (!sessionId) {
      message.error('Session ID 缺失');
      return;
    }
  }, [sessionId]);

  return (
    <WorkspaceLayout
      sessionId={sessionId!}
      isConnected={isConnected}
      currentState={currentState}
      stateHistory={stateHistory}
      onSendMessage={sendMessage}
      onSendEvent={sendEvent}
    />
  );
}
