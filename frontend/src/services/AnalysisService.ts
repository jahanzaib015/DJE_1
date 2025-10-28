import axios from 'axios';
import { AnalysisRequest, JobStatus, AnalysisResult } from '../types';

const API_BASE_URL = 'https://dje-1-3.onrender.com';

export class AnalysisService {
  static async uploadFile(file: File) {
    console.log('Uploading file to:', `${API_BASE_URL}/api/upload`);
    console.log('File details:', { name: file.name, size: file.size, type: file.type });
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await axios.post(`${API_BASE_URL}/api/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        timeout: 60000, // 60 second timeout for large files
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            console.log(`Upload progress: ${percentCompleted}%`);
          }
        }
      });
      
      console.log('Upload response:', response.data);
      return response.data;
    } catch (error: any) {
      console.error('Upload error:', error);
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
    console.log('Starting analysis with:', request);
    console.log('Analysis URL:', `${API_BASE_URL}/api/analyze`);
    
    try {
      const response = await axios.post(`${API_BASE_URL}/api/analyze`, request, {
        timeout: 30000, // 30 second timeout
        headers: {
          'Content-Type': 'application/json'
        }
      });
      console.log('Analysis response:', response.data);
      return response.data;
    } catch (error: any) {
      console.error('Analysis error:', error);
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
    const response = await axios.get(`${API_BASE_URL}/api/jobs/${jobId}/status`);
    return response.data;
  }

  static async getResults(jobId: string): Promise<AnalysisResult> {
    const response = await axios.get(`${API_BASE_URL}/api/jobs/${jobId}/results`);
    return response.data;
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
    try {
      // Test Node.js backend only - this is sufficient for the app to work
      const nodeResponse = await axios.get(`${API_BASE_URL}/api/health`);
      console.log('Backend health:', nodeResponse.data);
      
      return {
        status: 'connected',
        message: 'Backend is healthy and ready for analysis'
      };
    } catch (error: any) {
      console.error('Connection test failed:', error);
      throw new Error(`Connection test failed: ${error.response?.data?.error || error.message}`);
    }
  }

  static async listJobs() {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/jobs`);
      console.log('Available jobs:', response.data);
      return response.data;
    } catch (error: any) {
      console.error('Failed to list jobs:', error);
      throw new Error(`Failed to list jobs: ${error.response?.data?.error || error.message}`);
    }
  }
}
