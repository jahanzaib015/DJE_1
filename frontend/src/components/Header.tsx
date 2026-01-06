import React from 'react';

interface HeaderProps {
  onToggleSettings: () => void;
  showSettings: boolean;
}

export const Header: React.FC<HeaderProps> = ({ onToggleSettings, showSettings }) => {
  return (
    <header className="bg-gradient-to-r from-yellow-400 via-yellow-300 to-yellow-400 shadow-lg border-b-4 border-yellow-500">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center py-6">
          <div className="flex items-center">
            {/* DJE Logo */}
            <div className="flex items-center mr-6">
              <div className="flex items-center">
                {/* DJE Text */}
                <span className="text-4xl font-bold text-black italic mr-4">DJE</span>
                {/* Golden Orange Graphic Element */}
                <svg width="40" height="30" viewBox="0 0 40 30" className="flex-shrink-0">
                  <defs>
                    <linearGradient id="goldenGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#FF8C00" />
                      <stop offset="100%" stopColor="#FFA500" />
                    </linearGradient>
                  </defs>
                  {/* Back sail (largest) */}
                  <path d="M5 25 Q15 5 25 15 Q20 25 5 25 Z" fill="url(#goldenGradient)" />
                  {/* Middle sail */}
                  <path d="M10 20 Q18 8 26 18 Q22 25 10 20 Z" fill="url(#goldenGradient)" />
                  {/* Front sail (smallest) */}
                  <path d="M15 15 Q22 10 30 20 Q26 25 15 15 Z" fill="url(#goldenGradient)" />
                </svg>
              </div>
            </div>
            
            <div className="flex items-center">
              <h1 className="text-3xl font-bold text-white drop-shadow-lg">📄 Rules Extractor for DJE SA</h1>
              <span className="ml-3 px-3 py-1 text-sm bg-white text-yellow-600 rounded-full shadow-md font-semibold">
                Modern
              </span>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            <button
              onClick={onToggleSettings}
              className="p-3 bg-white text-yellow-600 hover:bg-yellow-50 hover:text-yellow-700 rounded-full shadow-lg transition-all duration-300 hover:scale-110"
              title={showSettings ? 'Hide Settings' : 'Show Settings'}
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
export default Header;