import React, { useState, useEffect } from 'react';
import FileUpload from './components/FileUpload';
import Settings from './components/Settings';
import Progress from './components/Progress';
import Results from './components/Results';
import Header from './components/Header';
import { usePolling } from './hooks/usePolling';
import { AnalysisService } from './services/AnalysisService';
import { JobStatus, AnalysisResult, Settings as SettingsType } from './types';

function App() {
  const [showSettings, setShowSettings] = useState(true);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [currentJob, setCurrentJob] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [results, setResults] = useState<AnalysisResult | null>(null);
  const [settings, setSettings] = useState<SettingsType>({
    analysisMethod: 'llm_with_fallback',
    llmProvider: 'openai',
    model: 'gpt-4o-mini',
    fundId: '5800'
  });

  // ✅ Test backend connectivity on app load
  useEffect(() => {
    const test = async () => {
      try {
        await AnalysisService.testConnection();
        console.log('Initial connection test successful');
      } catch (error) {
        console.error('Initial connection test failed:', error);
        alert('Connection test failed: ' + (error as Error).message);
      }
    };
    test();
  }, []);

  // ✅ Polling instead of WebSocket
  usePolling(currentJob, (status) => {
    setJobStatus(status);
    if (status.status === 'completed') {
      fetchResults(currentJob!);
    }
  });

  const fetchResults = async (jobId: string) => {
    try {
      const response = await AnalysisService.getResults(jobId);
      setResults(response);
    } catch (error) {
      console.error('Failed to fetch results:', error);
    }
  };

  const handleFileUpload = async (file: File) => {
    setUploadedFile(file);
    
    try {
      // Upload file
      const uploadResponse = await AnalysisService.uploadFile(file);
      
      // Start analysis
      const analysisResponse = await AnalysisService.startAnalysis({
        file_path: uploadResponse.file_path,
        analysis_method: settings.analysisMethod,
        llm_provider: settings.llmProvider,
        model: settings.model,
        fund_id: settings.fundId
      });
      
      setCurrentJob(analysisResponse.job_id);
      setJobStatus({ job_id: analysisResponse.job_id, status: 'queued', progress: 0, message: 'Queued' });
      setResults(null);
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Upload failed: ' + (error as Error).message);
    }
  };

  const handleExportExcel = async () => {
    if (!currentJob) return;
    
    try {
      await AnalysisService.exportExcel(currentJob);
    } catch (error) {
      console.error('Export failed:', error);
      alert('Export failed: ' + (error as Error).message);
    }
  };

  const handleExportJson = async () => {
    if (!results) return;
    
    try {
      await AnalysisService.exportJson(results);
    } catch (error) {
      console.error('Export failed:', error);
      alert('Export failed: ' + (error as Error).message);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-yellow-50 via-white to-yellow-100">
      <Header 
        onToggleSettings={() => setShowSettings(!showSettings)}
        showSettings={showSettings}
      />
      
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Settings at Top */}
        {showSettings && (
          <div className="mb-8">
            <Settings
              settings={settings}
              onSettingsChange={setSettings}
            />
          </div>
        )}

        {/* Main Content */}
        <div className="w-full">
            {/* File Upload */}
            <div className="bg-white rounded-lg shadow mb-8">
              <FileUpload
                onFileUpload={handleFileUpload}
                uploadedFile={uploadedFile}
                onRemoveFile={() => setUploadedFile(null)}
              />
            </div>

            {/* Progress */}
            {currentJob && jobStatus && (
              <div className="bg-white rounded-lg shadow mb-8">
                <Progress jobStatus={jobStatus} />
              </div>
            )}

            {/* Results */}
            {results && (
              <div className="bg-white rounded-lg shadow">
                <Results
                  results={results}
                  onExportExcel={handleExportExcel}
                  onExportJson={handleExportJson}
                />
              </div>
            )}
        </div>
      </div>
    </div>
  );
}

export default App;
