import React from 'react';
import { JobStatus } from '../types';

interface ProgressProps {
  jobStatus: JobStatus;
}

export const Progress: React.FC<ProgressProps> = ({ jobStatus }) => {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-gradient-to-r from-green-500 to-green-600';
      case 'failed':
        return 'bg-gradient-to-r from-red-500 to-red-600';
      case 'processing':
        return 'bg-gradient-to-r from-yellow-500 to-yellow-600';
      default:
        return 'bg-gradient-to-r from-gray-500 to-gray-600';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return '✅';
      case 'failed':
        return '❌';
      case 'processing':
        return '🔄';
      default:
        return '⏳';
    }
  };

  return (
    <div className="p-8 bg-white rounded-2xl shadow-xl border-2 border-yellow-200">
      <h3 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
        <span className="mr-3 text-3xl">⚡</span>
        Processing Status
      </h3>
      
      <div className="space-y-6">
        <div className="flex items-center space-x-4">
          <span className="text-4xl">{getStatusIcon(jobStatus.status)}</span>
          <div className="flex-1">
            <div className="flex justify-between text-lg font-semibold text-gray-800 mb-3">
              <span>{jobStatus.message}</span>
              <span className="bg-yellow-100 text-yellow-800 px-3 py-1 rounded-full">{jobStatus.progress}%</span>
            </div>
            <div className="w-full bg-yellow-100 rounded-full h-4 shadow-inner">
              <div
                className={`h-4 rounded-full transition-all duration-500 shadow-lg ${getStatusColor(jobStatus.status)}`}
                style={{ width: `${jobStatus.progress}%` }}
              />
            </div>
          </div>
        </div>
        
        {jobStatus.status === 'failed' && jobStatus.error && (
          <div className="text-red-700 text-lg font-semibold bg-red-100 p-4 rounded-xl border-2 border-red-200">
            <strong>❌ Error:</strong> {jobStatus.error}
          </div>
        )}
        
        {jobStatus.status === 'completed' && (
          <div className="text-green-700 text-lg font-semibold bg-green-100 p-4 rounded-xl border-2 border-green-200">
            <strong>✅ Success:</strong> Analysis completed successfully!
          </div>
        )}
      </div>
    </div>
  );
};
export default Progress