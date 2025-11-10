import axios from 'axios';
import { AnalysisRequest, JobStatus, AnalysisResult } from '../types';
import { logger } from '../utils/logger';

// Use environment variable for API URL, fallback to localhost for local development
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export class AnalysisService {
  static async uploadFile(file: File) {
    const startTime = Date.now();
    const requestId = logger.logRequest('POST', `${API_BASE_URL}/api/upload`, {
      filename: file.name,
      size: file.size,
      type: file.type
    });
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await axios.post(`${API_BASE_URL}/api/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          'X-Request-ID': requestId
        },
        timeout: 60000, // 60 second timeout for large files
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            logger.debug(`Upload progress: ${percentCompleted}%`, {}, requestId);
          }
        }
      });
      
      const duration = Date.now() - startTime;
      logger.logResponse('POST', `${API_BASE_URL}/api/upload`, response.status, response.data, duration, requestId);
      return response.data;
    } catch (error: any) {
      const duration = Date.now() - startTime;
      logger.logError('POST', `${API_BASE_URL}/api/upload`, error, requestId);
      if (error.response) {
        // Server responded with error status
        throw new Error(`Upload failed: ${error.response.data?.error || error.response.statusText}`);
      } else if (error.request) {
        // Request was made but no response received
        throw new Error('Upload failed: No response from server. Please check your connection.');
      } else {
        // Something else happened
        throw new Error(`Upload failed: ${error.message}`);
      }
    }
  }

  static async startAnalysis(request: AnalysisRequest) {
    const startTime = Date.now();
    const requestId = logger.logRequest('POST', `${API_BASE_URL}/api/analyze`, request);
    
    try {
      const response = await axios.post(`${API_BASE_URL}/api/analyze`, request, {
        timeout: 120000, // 120 second timeout (2 minutes) - analysis starts async, but backend may be slow to respond
        headers: {
          'Content-Type': 'application/json',
          'X-Request-ID': requestId
        }
      });
      const duration = Date.now() - startTime;
      logger.logResponse('POST', `${API_BASE_URL}/api/analyze`, response.status, response.data, duration, requestId);
      return response.data;
    } catch (error: any) {
      const duration = Date.now() - startTime;
      logger.logError('POST', `${API_BASE_URL}/api/analyze`, error, requestId);
      if (error.response) {
        throw new Error(`Analysis failed: ${error.response.data?.error || error.response.statusText}`);
      } else if (error.request) {
        throw new Error('Analysis failed: No response from server. Please check your connection.');
      } else {
        throw new Error(`Analysis failed: ${error.message}`);
      }
    }
  }

  static async getJobStatus(jobId: string): Promise<JobStatus> {
    const startTime = Date.now();
    const requestId = logger.logRequest('GET', `${API_BASE_URL}/api/jobs/${jobId}/status`);
    
    try {
      const response = await axios.get(`${API_BASE_URL}/api/jobs/${jobId}/status`, {
        headers: { 'X-Request-ID': requestId },
        timeout: 10000
      });
      const duration = Date.now() - startTime;
      logger.debug(`Job status: ${response.data.status}`, { jobId, status: response.data.status }, requestId);
      return response.data;
    } catch (error: any) {
      const duration = Date.now() - startTime;
      logger.logError('GET', `${API_BASE_URL}/api/jobs/${jobId}/status`, error, requestId);
      throw error;
    }
  }

  static async getResults(jobId: string): Promise<AnalysisResult> {
    const startTime = Date.now();
    const requestId = logger.logRequest('GET', `${API_BASE_URL}/api/jobs/${jobId}/results`);
    
    try {
      const response = await axios.get(`${API_BASE_URL}/api/jobs/${jobId}/results`, {
        headers: { 'X-Request-ID': requestId },
        timeout: 30000
      });
      const duration = Date.now() - startTime;
      logger.logResponse('GET', `${API_BASE_URL}/api/jobs/${jobId}/results`, response.status, 
        { resultSize: JSON.stringify(response.data).length }, duration, requestId);
      return response.data;
    } catch (error: any) {
      const duration = Date.now() - startTime;
      logger.logError('GET', `${API_BASE_URL}/api/jobs/${jobId}/results`, error, requestId);
      throw error;
    }
  }

  static async exportExcel(jobId: string) {
    const response = await axios.get(`${API_BASE_URL}/api/jobs/${jobId}/export/excel`, {
      responseType: 'blob'
    });
    
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'ocrd_results.xlsx');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }

  static async exportJson(results: AnalysisResult) {
    const blob = new Blob([JSON.stringify(results, null, 2)], { 
      type: 'application/json' 
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'ocrd_results.json');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }

  static async getAvailableModels() {
    const response = await axios.get(`${API_BASE_URL}/api/models`);
    return response.data;
  }

  static async testConnection() {
    const startTime = Date.now();
    const requestId = logger.logRequest('GET', `${API_BASE_URL}/api/health`);
    
    try {
      // Test Node.js backend only - this is sufficient for the app to work
      // Increased timeout for Render free tier cold starts (can take 30+ seconds)
      const nodeResponse = await axios.get(`${API_BASE_URL}/api/health`, {
        headers: { 'X-Request-ID': requestId },
        timeout: 30000 // 30 seconds to allow for Render cold start
      });
      const duration = Date.now() - startTime;
      logger.logResponse('GET', `${API_BASE_URL}/api/health`, nodeResponse.status, nodeResponse.data, duration, requestId);
      
      return {
        status: 'connected',
        message: 'Backend is healthy and ready for analysis'
      };
    } catch (error: any) {
      const duration = Date.now() - startTime;
      logger.logError('GET', `${API_BASE_URL}/api/health`, error, requestId);
      throw new Error(`Connection test failed: ${error.response?.data?.error || error.message}`);
    }
  }

  static async listJobs() {
    const startTime = Date.now();
    const requestId = logger.logRequest('GET', `${API_BASE_URL}/api/jobs`);
    
    try {
      const response = await axios.get(`${API_BASE_URL}/api/jobs`, {
        headers: { 'X-Request-ID': requestId },
        timeout: 10000
      });
      const duration = Date.now() - startTime;
      logger.logResponse('GET', `${API_BASE_URL}/api/jobs`, response.status, 
        { totalJobs: response.data.total_jobs }, duration, requestId);
      return response.data;
    } catch (error: any) {
      const duration = Date.now() - startTime;
      logger.logError('GET', `${API_BASE_URL}/api/jobs`, error, requestId);
      throw new Error(`Failed to list jobs: ${error.response?.data?.error || error.message}`);
    }
  }
}
