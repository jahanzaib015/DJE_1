import React from 'react';
import { AnalysisResult, InstrumentData } from '../types';

interface ResultsProps {
  results: AnalysisResult;
  onExportExcel: () => void;
  onExportJson: () => void;
}

export const Results: React.FC<ResultsProps> = ({ results, onExportExcel, onExportJson }) => {
  const formatEvidence = (evidence: { text: string; page?: number }) => {
    if (!evidence.text) return 'No evidence found';
    return evidence.text.length > 100 
      ? `${evidence.text.substring(0, 100)}...` 
      : evidence.text;
  };

  const getStatusBadge = (allowed: boolean | null) => {
    if (allowed === true) {
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-bold bg-green-100 text-green-800 border-2 border-green-300">
          ✅ Allowed
        </span>
      );
    } else if (allowed === false) {
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-bold bg-red-100 text-red-800 border-2 border-red-300">
          ❌ Not Allowed
        </span>
      );
    } else {
      // null = manual approval required
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-bold bg-yellow-100 text-yellow-800 border-2 border-yellow-300">
          ⚠️ Manual Approval Required
        </span>
      );
    }
  };

  return (
    <div className="p-8 bg-white rounded-2xl shadow-xl border-2 border-yellow-200">
      <div className="flex justify-between items-center mb-8">
        <h3 className="text-2xl font-bold text-gray-800 flex items-center">
          <span className="mr-3 text-3xl">📊</span>
          Analysis Results
        </h3>
        <div className="flex space-x-3">
          <button
            onClick={onExportExcel}
            className="bg-gradient-to-r from-green-500 to-green-600 text-white px-6 py-3 rounded-xl font-bold shadow-lg hover:shadow-xl transform hover:scale-105 transition-all duration-300"
          >
            📊 Export Excel
          </button>
          <button
            onClick={onExportJson}
            className="bg-gradient-to-r from-blue-500 to-blue-600 text-white px-6 py-3 rounded-xl font-bold shadow-lg hover:shadow-xl transform hover:scale-105 transition-all duration-300"
          >
            📄 Export JSON
          </button>
        </div>
      </div>

      {/* Confidence Score Banner */}
      <div className="mb-6 p-6 bg-gradient-to-r from-yellow-400 via-orange-400 to-pink-400 rounded-xl shadow-lg border-4 border-yellow-300">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <span className="text-5xl">🤖</span>
            <div>
              <div className="text-lg font-semibold text-gray-800 mb-1">
                Model Confidence Score
              </div>
              <div className="text-sm text-gray-700">
                I am <span className="font-bold text-2xl text-gray-900">{results.confidence_score || 0}%</span> confident that the results generated are correct.
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold text-white drop-shadow-lg">
              {results.confidence_score || 0}%
            </div>
            <div className="text-xs text-gray-800 font-semibold mt-1">
              Confidence Level
            </div>
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-gray-50 p-4 rounded-lg">
          <div className="text-2xl font-bold text-gray-900">
            {results.total_instruments}
          </div>
          <div className="text-sm text-gray-600">Total Instruments</div>
        </div>
        <div className="bg-green-50 p-4 rounded-lg">
          <div className="text-2xl font-bold text-green-600">
            {results.allowed_instruments}
          </div>
          <div className="text-sm text-gray-600">Allowed</div>
        </div>
        <div className="bg-blue-50 p-4 rounded-lg">
          <div className="text-2xl font-bold text-blue-600">
            {results.evidence_coverage}%
          </div>
          <div className="text-sm text-gray-600">Evidence Coverage</div>
        </div>
        <div className="bg-purple-50 p-4 rounded-lg">
          <div className="text-2xl font-bold text-purple-600">
            {results.processing_time}s
          </div>
          <div className="text-sm text-gray-600">Processing Time</div>
        </div>
      </div>


      {/* Results Table */}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Section
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Instrument
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Allowed
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Note
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Evidence
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {Object.entries(results.sections).map(([section, items]) => {
              // All sections are now flat (future, option, warrant are top-level, no parent "derivatives" category)
              if (typeof items !== 'object' || items === null) {
                return null;
              }
              
              return Object.entries(items)
                .filter(([key]) => key !== 'special_other_restrictions')
                .map(([key, value]) => {
                  // Type guard
                  if (typeof value !== 'object' || value === null || !('allowed' in value)) {
                    return null;
                  }
                  
                  // Type assertion after type guard
                  const instrumentData = value as InstrumentData;
                  
                  return (
                    <tr key={`${section}-${key}`} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {section}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex flex-col gap-1">
                          {getStatusBadge(instrumentData.allowed)}
                          {instrumentData.confidence !== null && instrumentData.confidence !== undefined && (
                            <span className="text-xs text-gray-500 mt-1">
                              Confidence: {(instrumentData.confidence * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900">
                        {instrumentData.note || '-'}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900 max-w-xs">
                        <div className="truncate" title={instrumentData.evidence?.text || ''}>
                          {formatEvidence(instrumentData.evidence || { text: '' })}
                        </div>
                      </td>
                    </tr>
                  );
                })
                .filter((item): item is JSX.Element => item !== null); // Remove null entries with proper type guard
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
export default Results