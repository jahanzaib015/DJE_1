import axios from 'axios';
import { AnalysisRequest, JobStatus, AnalysisResult } from '../types';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://dje-1-3.onrender.com';

export class AnalysisService {
  static async uploadFile(file: File) {
    console.log('Uploading file to:', `${API_BASE_URL}/api/upload`);
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await axios.post(`${API_BASE_URL}/api/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      
      console.log('Upload response:', response.data);
      return response.data;
    } catch (error) {
      console.error('Upload error:', error);
      throw error;
    }
  }

  static async startAnalysis(request: AnalysisRequest) {
    console.log('Starting analysis with:', request);
    console.log('Analysis URL:', `${API_BASE_URL}/api/analyze`);
    
    try {
      const response = await axios.post(`${API_BASE_URL}/api/analyze`, request);
      console.log('Analysis response:', response.data);
      return response.data;
    } catch (error) {
      console.error('Analysis error:', error);
      throw error;
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
    const response = await axios.get(`${API_BASE_URL}/api/health`);
    return response.data;
  }
}
