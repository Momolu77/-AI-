import { useEffect, useRef, useCallback, useState } from 'react';
import type { WSMessage, MetacogState, Intervention } from '../types';

interface UseWebSocketOptions {
  sessionId: string;
  onStateUpdate?: (state: MetacogState) => void;
  onIntervention?: (intervention: Intervention) => void;
  onAIReply?: (content: string) => void;
  onAIReplyChunk?: (chunk: string) => void;
  onAIReplyDone?: (fullContent: string) => void;
  onError?: (error: string) => void;
}

export function useWebSocket({
  sessionId,
  onStateUpdate,
  onIntervention,
  onAIReply,
  onAIReplyChunk,
  onAIReplyDone,
  onError,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number>();
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000';
    const ws = new WebSocket(`${wsBaseUrl}/ws/session/${sessionId}`);

    ws.onopen = () => {
      console.log('[WS] Connected');
      setIsConnected(true);
      setReconnectAttempts(0);
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);

        switch (msg.type) {
          case 'state_update':
            onStateUpdate?.(msg.data);
            break;
          case 'intervention':
            onIntervention?.({
              ...msg.data,
              timestamp: new Date(),
            });
            break;
          case 'ai_reply_chunk':
            onAIReplyChunk?.(msg.data.content);
            break;
          case 'ai_reply_done':
            onAIReplyDone?.(msg.data.content);
            break;
          case 'ai_reply':
            onAIReply?.(msg.data.content);
            break;
          case 'error':
            onError?.(msg.data.message || 'Unknown error');
            break;
          case 'pong':
            // Heartbeat response
            break;
        }
      } catch (err) {
        console.error('[WS] Parse error:', err);
      }
    };

    ws.onerror = (event) => {
      console.error('[WS] Error:', event);
      setIsConnected(false);
    };

    ws.onclose = () => {
      console.log('[WS] Closed');
      setIsConnected(false);
      wsRef.current = null;

      // Exponential backoff: 1s, 2s, 4s, max 10s
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
      reconnectTimeoutRef.current = window.setTimeout(() => {
        console.log(`[WS] Reconnecting (attempt ${reconnectAttempts + 1})...`);
        setReconnectAttempts((prev) => prev + 1);
        connect();
      }, delay);
    };

    wsRef.current = ws;
  }, [sessionId, reconnectAttempts, onStateUpdate, onIntervention, onAIReply, onAIReplyChunk, onAIReplyDone, onError]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  const sendEvent = useCallback((eventType: string, content: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        event_type: eventType,
        content: typeof content === 'string' ? content : JSON.stringify(content),
      }));
    } else {
      console.warn('[WS] Not connected, cannot send event');
    }
  }, []);

  const sendMessage = useCallback((content: string) => {
    sendEvent('prompt', content);
  }, [sendEvent]);

  return {
    isConnected,
    sendMessage,
    sendEvent,
  };
}
