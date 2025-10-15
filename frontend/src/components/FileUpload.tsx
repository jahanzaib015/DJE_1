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
  const [isUploading] = useState(false);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (file && file.type === 'application/pdf') {
      onFileUpload(file);
    } else {
      alert('Please select a PDF file');
    }
  }, [onFileUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf']
    },
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
        
        {!uploadedFile ? (
          <div>
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
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
                  {uploadedFile.name}
                </p>
                <p className="text-sm text-gray-500">
                  {formatFileSize(uploadedFile.size)}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRemoveFile();
                }}
                className="text-red-600 hover:text-red-800"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
          </div>
        )}
      </div>

      {uploadedFile && (
        <div className="mt-4">
          <button
            onClick={() => onFileUpload(uploadedFile)}
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

