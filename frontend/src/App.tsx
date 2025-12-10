import React, { useState, useEffect } from 'react';
import FileUpload from './components/FileUpload';
import Settings from './components/Settings';
import Progress from './components/Progress';
import Results from './components/Results';
import Header from './components/Header';
import TraceViewer from './components/TraceViewer';
import { usePolling } from './hooks/usePolling';
import { AnalysisService } from './services/AnalysisService';
import { JobStatus, AnalysisResult, Settings as SettingsType } from './types';
import { logger } from './utils/logger';

function App() {
  const [showSettings, setShowSettings] = useState(true);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [currentJob, setCurrentJob] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [results, setResults] = useState<AnalysisResult | null>(null);
  const [showTraceViewer, setShowTraceViewer] = useState(false);
  const [currentTraceId, setCurrentTraceId] = useState<string | null>(null);
  const [settings, setSettings] = useState<SettingsType>({
    analysisMethod: 'llm',
    llmProvider: 'openai',
    model: 'gpt-5.1',
    fundId: '5800'
  });

  // ✅ Test backend connectivity on app load
  useEffect(() => {
    const test = async () => {
      try {
        await AnalysisService.testConnection();
        logger.info('Initial connection test successful');
      } catch (error) {
        logger.error('Initial connection test failed:', { error: (error as Error).message });
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
      logger.info(`Results fetched successfully for job ${jobId}`);
    } catch (error) {
      logger.error('Failed to fetch results:', { error: (error as Error).message, jobId });
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
      logger.error('Upload failed:', { error: (error as Error).message });
      alert('Upload failed: ' + (error as Error).message);
    }
  };

  const handleExportExcel = async () => {
    if (!currentJob) return;
    
    try {
      await AnalysisService.exportExcel(currentJob);
    } catch (error) {
      logger.error('Export failed:', { error: (error as Error).message, jobId: currentJob });
      alert('Export failed: ' + (error as Error).message);
    }
  };

  const handleExportJson = async () => {
    if (!results) return;
    
    try {
      await AnalysisService.exportJson(results);
    } catch (error) {
      logger.error('Export failed:', { error: (error as Error).message, jobId: currentJob });
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
                {/* Trace Viewer Button */}
                {results.trace_id && (
                  <div className="p-4 border-t">
                    <button
                      onClick={() => {
                        setCurrentTraceId(results.trace_id!);
                        setShowTraceViewer(true);
                      }}
                      className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium"
                    >
                      🔍 View Trace Details
                    </button>
                    <p className="text-xs text-gray-500 mt-1">
                      Trace ID: {results.trace_id}
                    </p>
                  </div>
                )}
              </div>
            )}
        </div>
      </div>

      {/* Trace Viewer Modal */}
      {showTraceViewer && (
        <TraceViewer
          traceId={currentTraceId || undefined}
          onClose={() => {
            setShowTraceViewer(false);
            setCurrentTraceId(null);
          }}
        />
      )}
    </div>
  );
}

export default App;
