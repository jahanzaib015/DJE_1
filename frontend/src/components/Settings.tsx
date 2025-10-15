import React, { useState, useEffect } from 'react';
import { Settings as SettingsType } from '../types';
import { AnalysisService } from '../services/AnalysisService';

interface SettingsProps {
  settings: SettingsType;
  onSettingsChange: (settings: SettingsType) => void;
}

export const Settings: React.FC<SettingsProps> = ({ settings, onSettingsChange }) => {
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const models = await AnalysisService.getAvailableModels();
        setAvailableModels(models.openai_models || ['gpt-4', 'gpt-3.5-turbo']);
      } catch (error) {
        console.error('Failed to fetch models:', error);
        setAvailableModels(['gpt-4', 'gpt-3.5-turbo']);
      }
    };

    fetchModels();
  }, []);

  const handleTestConnection = async () => {
    setTesting(true);
    try {
      await AnalysisService.testConnection();
      alert('Connection successful!');
    } catch (error) {
      alert('Connection failed: ' + (error as Error).message);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl border-2 border-yellow-200 p-6">
      <h3 className="text-2xl font-bold text-gray-800 mb-6 flex items-center">
        <span className="mr-3 text-3xl">⚙️</span>
        Settings
      </h3>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      
        {/* Analysis Method */}
        <div>
          <label className="block text-lg font-semibold text-gray-800 mb-3">
            🔍 Analysis Method
          </label>
          <select
            value={settings.analysisMethod}
            onChange={(e) => onSettingsChange({
              ...settings,
              analysisMethod: e.target.value as SettingsType['analysisMethod']
            })}
            className="w-full border-2 border-yellow-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-yellow-500 bg-yellow-50 text-gray-800 font-medium"
          >
            {/* <option value="keywords">⚡ Fast Keywords</option> COMMENTED OUT: Only using OpenAI for now */}
            <option value="llm">🤖 OpenAI Analysis</option>
            {/* <option value="llm_with_fallback">🔄 LLM with Fallback</option> COMMENTED OUT: Only using OpenAI for now */}
          </select>
        </div>

        {/* LLM Provider */}
        {settings.analysisMethod !== 'keywords' && (
          <div>
            <label className="block text-lg font-semibold text-gray-800 mb-3">
              🤖 LLM Provider
            </label>
            <select
              value={settings.llmProvider}
              onChange={(e) => onSettingsChange({
                ...settings,
                llmProvider: e.target.value as SettingsType['llmProvider']
              })}
              className="w-full border-2 border-yellow-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-yellow-500 bg-yellow-50 text-gray-800 font-medium"
            >
              <option value="openai">OpenAI (ChatGPT)</option>
              {/* <option value="ollama">Ollama (Local)</option> COMMENTED OUT: Only using OpenAI for now */}
            </select>
          </div>
        )}

        {/* Model Selection */}
        {settings.analysisMethod !== 'keywords' && (
          <div>
            <label className="block text-lg font-semibold text-gray-800 mb-3">
              🧠 Model
            </label>
            <select
              value={settings.model}
              onChange={(e) => onSettingsChange({
                ...settings,
                model: e.target.value
              })}
              className="w-full border-2 border-yellow-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-yellow-500 bg-yellow-50 text-gray-800 font-medium"
            >
              {availableModels.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Fund ID */}
        <div>
          <label className="block text-lg font-semibold text-gray-800 mb-3">
            🏦 Fund ID
          </label>
          <input
            type="text"
            value={settings.fundId}
            onChange={(e) => onSettingsChange({
              ...settings,
              fundId: e.target.value
            })}
            className="w-full border-2 border-yellow-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-yellow-500 bg-yellow-50 text-gray-800 font-medium"
            placeholder="5800"
          />
        </div>

        {/* Test Connection */}
        {settings.analysisMethod !== 'keywords' && (
          <div>
            <label className="block text-lg font-semibold text-gray-800 mb-3">
              🔗 Test
            </label>
            <button
              onClick={handleTestConnection}
              disabled={testing}
              className="w-full bg-gradient-to-r from-green-500 to-green-600 text-white py-3 px-6 rounded-xl font-bold shadow-lg hover:shadow-xl transform hover:scale-105 transition-all duration-300 disabled:opacity-50 disabled:transform-none"
            >
              {testing ? '⏳ Testing...' : '🔗 Test Connection'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
export default Settings