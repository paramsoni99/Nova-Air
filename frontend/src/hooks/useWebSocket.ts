import { useEffect, useState, useRef, useCallback } from 'react';
import { WebSocketEvent } from '../types';
import { WS_URL } from '../config';

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';

export function useWebSocket(onEventReceived?: (event: WebSocketEvent) => void) {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [events, setEvents] = useState<WebSocketEvent[]>([]);
  const [lastUpdateUtc, setLastUpdateUtc] = useState<number>(() => Math.floor(Date.now() / 1000));
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);

  const connect = useCallback(() => {
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    setStatus('connecting');
    const wsUrl = WS_URL;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        setLastUpdateUtc(Math.floor(Date.now() / 1000));
      };

      ws.onmessage = (messageEvent) => {
        try {
          const data: WebSocketEvent = JSON.parse(messageEvent.data);
          setEvents((prev) => [data, ...prev].slice(0, 100)); // keep last 100
          setLastUpdateUtc(data.timestamp_utc || Math.floor(Date.now() / 1000));
          if (onEventReceived) {
            onEventReceived(data);
          }
        } catch {
          // ignore non-json keepalives
        }
      };

      ws.onclose = () => {
        setStatus('disconnected');
        wsRef.current = null;
        if (!reconnectTimeoutRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null;
            connect();
          }, 3000);
        }
      };

      ws.onerror = () => {
        setStatus('disconnected');
      };
    } catch {
      setStatus('disconnected');
    }
  }, [onEventReceived]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  return {
    status,
    events,
    lastUpdateUtc,
    clearEvents,
    reconnect: connect,
  };
}
