import { useCallback, useRef } from 'react';
import { JobStatus } from '../types';
import { logger } from '../utils/logger';

export const useWebSocket = () => {
  const connections = useRef<Map<string, WebSocket>>(new Map());

  const connectWebSocket = useCallback((jobId: string, onMessage: (status: JobStatus) => void) => {
    if (connections.current.has(jobId)) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//dje-1-3.onrender.com/ws/jobs/${jobId}`;
    logger.info('Connecting to WebSocket', { wsUrl });

    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as JobStatus;
        onMessage(data);
      } catch (error) {
        logger.error('Failed to parse WebSocket message', { error });
      }
    };

    ws.onclose = () => {
      logger.warn('WebSocket closed for job', { jobId });
      connections.current.delete(jobId);
    };

    ws.onerror = (error) => {
      logger.error('WebSocket error', { error, jobId });
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

  return { connectWebSocket, disconnectWebSocket };
};
