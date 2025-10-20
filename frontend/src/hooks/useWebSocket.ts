import { useCallback, useRef } from 'react';
import { JobStatus } from '../types';

export const useWebSocket = () => {
  const connections = useRef<Map<string, WebSocket>>(new Map());

  const connectWebSocket = useCallback((jobId: string, onMessage: (status: JobStatus) => void) => {
    if (connections.current.has(jobId)) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const port = process.env.REACT_APP_WS_PORT || '8000';
    const host = process.env.REACT_APP_WS_HOST || window.location.hostname;
    const wsUrl = `${protocol}//${host}:${port}/ws/jobs/${jobId}`;
    
    const ws = new WebSocket(wsUrl);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as JobStatus;
        onMessage(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };
    
    ws.onclose = () => {
      connections.current.delete(jobId);
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      connections.current.delete(jobId);
    };
    
    connections.current.set(jobId, ws);
  }, []);

  const disconnectWebSocket = useCallback((jobId: string) => {
    const ws = connections.current.get(jobId);
    if (ws) {
      ws.close();
      connections.current.delete(jobId);
    }
  }, []);

  return {
    connectWebSocket,
    disconnectWebSocket
  };
};
