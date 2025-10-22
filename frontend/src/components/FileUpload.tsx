import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';

interface FileUploadProps {
  onFileUpload: (file: File) => void;
  uploadedFile: File | null;
  onRemoveFile: () => void;
}

export const FileUpload: React.FC<FileUploadProps> = ({
  onFileUpload,
  uploadedFile,
  onRemoveFile
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading] = useState(false);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
    } else {
      alert('Please select a PDF file');
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: false
  });

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="p-8 bg-white rounded-2xl shadow-xl border-2 border-yellow-200 hover:border-yellow-300 transition-all duration-300">
      <h2 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
        <span className="mr-3 text-3xl">📁</span>
        Upload Document
      </h2>
      
      <div
        {...getRootProps()}
        className={`border-3 border-dashed rounded-2xl p-12 text-center transition-all duration-300 cursor-pointer transform hover:scale-105 ${
          isDragActive
            ? 'border-yellow-400 bg-yellow-50 shadow-lg'
            : 'border-yellow-300 hover:border-yellow-400 hover:bg-yellow-50'
        }`}
      >
        <input {...getInputProps()} />
        {!selectedFile ? (
          <div>
            <p className="mt-4 text-lg font-semibold text-gray-700">
              {isDragActive
                ? '🎯 Drop the PDF here...'
                : '📄 Drag and drop your PDF here, or click to select'}
            </p>
            <p className="mt-2 text-sm text-gray-500">
              Supported format: PDF files only
            </p>
          </div>
        ) : (
          <div className="text-left">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {selectedFile.name}
                </p>
                <p className="text-sm text-gray-500">
                  {formatFileSize(selectedFile.size)}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedFile(null);
                  onRemoveFile();
                }}
                className="text-red-600 hover:text-red-800"
              >
                ✖
              </button>
            </div>
          </div>
        )}
      </div>

      {selectedFile && (
        <div className="mt-4">
          <button
            onClick={() => onFileUpload(selectedFile)}
            disabled={isUploading}
            className="w-full bg-gradient-to-r from-yellow-500 to-yellow-600 text-white py-4 px-6 rounded-xl font-bold text-lg shadow-lg hover:shadow-xl transform hover:scale-105 transition-all duration-300 disabled:opacity-50 disabled:transform-none"
          >
            {isUploading ? '⏳ Uploading...' : '🚀 Upload & Analyze'}
          </button>
        </div>
      )}
    </div>
  );
};

export default FileUpload;
