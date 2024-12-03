import React, { useState } from 'react';
import AccessoryDashboard from './pages/AccessoryDashboard';
import BraceletDashboard from './pages/BraceletDashboard';

const App = () => {
  const [activeTab, setActiveTab] = useState('accessory');
  const [timeRange, setTimeRange] = useState('1d');

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-6">로스트아크 시장 분석</h1>
      
      <div className="flex justify-between items-center mb-4">
        <div className="flex space-x-4 border-b">
          <button
            className={`py-2 px-4 ${activeTab === 'accessory' 
              ? 'border-b-2 border-blue-500 text-blue-500' 
              : 'text-gray-500'}`}
            onClick={() => setActiveTab('accessory')}
          >
            악세서리
          </button>
          <button
            className={`py-2 px-4 ${activeTab === 'bracelet' 
              ? 'border-b-2 border-blue-500 text-blue-500' 
              : 'text-gray-500'}`}
            onClick={() => setActiveTab('bracelet')}
          >
            팔찌
          </button>
        </div>

        <select
          className="p-2 border rounded"
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value)}
        >
          <option value="1d">1일</option>
          <option value="1w">1주일</option>
          <option value="1m">1개월</option>
          <option value="3m">3개월</option>
        </select>
      </div>

      {activeTab === 'accessory' ? (
        <AccessoryDashboard timeRange={timeRange} />
      ) : (
        <BraceletDashboard timeRange={timeRange} />
      )}
    </div>
  );
};

export default App;