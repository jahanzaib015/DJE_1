import { useEffect, useRef } from 'react';
import { AnalysisService } from '../services/AnalysisService';
import { JobStatus } from '../types';

export const usePolling = (jobId: string | null, onUpdate: (status: JobStatus) => void) => {
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!jobId) return;

    // clear any existing interval
    if (intervalRef.current) clearInterval(intervalRef.current);

    const fetchStatus = async () => {
      try {
        const status = await AnalysisService.getJobStatus(jobId);
        onUpdate(status);
      } catch (error) {
        console.error('Polling error:', error);
      }
    };

    // run immediately and every 3 seconds
    fetchStatus();
    intervalRef.current = setInterval(fetchStatus, 3000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [jobId, onUpdate]);
};

