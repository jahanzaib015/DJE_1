import { useEffect, useRef } from 'react';
import { AnalysisService } from '../services/AnalysisService';
import { JobStatus } from '../types';
import { logger } from '../utils/logger';

export const usePolling = (jobId: string | null, onUpdate: (status: JobStatus) => void) => {
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const onUpdateRef = useRef(onUpdate);

  // Keep onUpdate ref current without causing re-renders
  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  useEffect(() => {
    if (!jobId) return;

    // clear any existing interval
    if (intervalRef.current) clearInterval(intervalRef.current);

    const fetchStatus = async () => {
      try {
        const status = await AnalysisService.getJobStatus(jobId);
        // Use ref to avoid dependency issues
        onUpdateRef.current(status);
        
        // CRITICAL: Stop polling when job is completed or failed to prevent infinite requests
        if (status.status === 'completed' || status.status === 'failed') {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
            logger.info(`Polling stopped for job ${jobId}: status=${status.status}`);
          }
        }
      } catch (error: any) {
        logger.error('Polling error:', {
          message: error.message,
          status: error.response?.status,
          data: error.response?.data
        }, jobId);
        
        // Stop polling on any error (404, 500, network error, etc.)
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
          logger.warn(`Polling stopped for job ${jobId} due to error`);
        }
      }
    };

    // run immediately and every 3 seconds
    fetchStatus();
    intervalRef.current = setInterval(fetchStatus, 3000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [jobId]); // Removed onUpdate from dependencies to prevent infinite loop
};

