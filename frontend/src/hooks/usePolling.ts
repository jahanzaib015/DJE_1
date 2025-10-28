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
      } catch (error: any) {
        console.error('Polling error:', error);
        console.error('Error details:', {
          message: error.message,
          status: error.response?.status,
          data: error.response?.data
        });
        
        // If it's a 404 error, the job might not exist anymore
        if (error.response?.status === 404) {
          console.error(`Job ${jobId} not found on server`);
          // Stop polling for this job
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
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

