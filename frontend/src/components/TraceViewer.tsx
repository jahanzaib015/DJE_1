import React, { useState, useEffect } from 'react';

interface TraceFile {
  filename: string;
  size: number;
}

interface Trace {
  trace_id: string;
  trace_dir: string;
  files: string[];
  created_at: string;
  file_sizes: Record<string, number>;
}

interface TraceViewerProps {
  traceId?: string;
  onClose?: () => void;
}

const TraceViewer: React.FC<TraceViewerProps> = ({ traceId, onClose }) => {
  const [traces, setTraces] = useState<Trace[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTraces();
    if (traceId) {
      fetchTrace(traceId);
    }
  }, [traceId]);

  const fetchTraces = async () => {
    try {
      const response = await fetch('/api/traces');
      const data = await response.json();
      setTraces(data.traces || []);
    } catch (err) {
      setError('Failed to fetch traces');
    }
  };

  const fetchTrace = async (id: string) => {
    setLoading(true);
    try {
      const response = await fetch(`/api/traces/${id}`);
      const data = await response.json();
      setSelectedTrace(data);
    } catch (err) {
      setError('Failed to fetch trace details');
    } finally {
      setLoading(false);
    }
  };

  const fetchFileContent = async (traceId: string, filename: string) => {
    setLoading(true);
    try {
      const response = await fetch(`/api/traces/${traceId}/files/${filename}`);
      const data = await response.json();
      setFileContent(data);
      setSelectedFile(filename);
    } catch (err) {
      setError('Failed to fetch file content');
    } finally {
      setLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleString();
  };

  const renderFileContent = () => {
    if (!fileContent) return null;

    if (selectedFile?.endsWith('.json')) {
      return (
        <pre className="bg-gray-100 p-4 rounded text-sm overflow-auto max-h-96">
          {JSON.stringify(fileContent, null, 2)}
        </pre>
      );
    } else if (selectedFile?.endsWith('.jsonl')) {
      return (
        <div className="space-y-2">
          {fileContent.lines?.map((line: any, index: number) => (
            <div key={index} className="bg-gray-100 p-2 rounded text-sm">
              <pre>{JSON.stringify(line, null, 2)}</pre>
            </div>
          ))}
        </div>
      );
    } else {
      return (
        <pre className="bg-gray-100 p-4 rounded text-sm overflow-auto max-h-96 whitespace-pre-wrap">
          {fileContent.content || JSON.stringify(fileContent, null, 2)}
        </pre>
      );
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-11/12 h-5/6 flex flex-col">
        <div className="flex justify-between items-center p-4 border-b">
          <h2 className="text-xl font-bold">Trace Viewer</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-2xl"
          >
            ×
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left sidebar - Trace list */}
          <div className="w-1/3 border-r overflow-y-auto">
            <div className="p-4">
              <h3 className="font-semibold mb-2">Available Traces</h3>
              <div className="space-y-2">
                {traces.map((trace) => (
                  <div
                    key={trace.trace_id}
                    className={`p-2 rounded cursor-pointer ${
                      selectedTrace?.trace_id === trace.trace_id
                        ? 'bg-blue-100 border-blue-300'
                        : 'bg-gray-50 hover:bg-gray-100'
                    }`}
                    onClick={() => fetchTrace(trace.trace_id)}
                  >
                    <div className="font-mono text-sm">{trace.trace_id}</div>
                    <div className="text-xs text-gray-500">
                      {formatDate(trace.created_at)}
                    </div>
                    <div className="text-xs text-gray-500">
                      {trace.files.length} files
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Middle - File list */}
          <div className="w-1/3 border-r overflow-y-auto">
            {selectedTrace && (
              <div className="p-4">
                <h3 className="font-semibold mb-2">Files</h3>
                <div className="space-y-1">
                  {selectedTrace.files.map((filename) => (
                    <div
                      key={filename}
                      className={`p-2 rounded cursor-pointer text-sm ${
                        selectedFile === filename
                          ? 'bg-blue-100 border-blue-300'
                          : 'bg-gray-50 hover:bg-gray-100'
                      }`}
                      onClick={() => fetchFileContent(selectedTrace.trace_id, filename)}
                    >
                      <div className="font-mono">{filename}</div>
                      <div className="text-xs text-gray-500">
                        {formatFileSize(selectedTrace.file_sizes[filename] || 0)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right - File content */}
          <div className="flex-1 overflow-y-auto">
            {selectedFile && (
              <div className="p-4">
                <h3 className="font-semibold mb-2">{selectedFile}</h3>
                {loading ? (
                  <div className="flex items-center justify-center h-32">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                  </div>
                ) : (
                  renderFileContent()
                )}
              </div>
            )}
          </div>
        </div>

        {error && (
          <div className="p-4 bg-red-100 text-red-700 border-t">
            {error}
          </div>
        )}
      </div>
    </div>
  );
};

export default TraceViewer;
