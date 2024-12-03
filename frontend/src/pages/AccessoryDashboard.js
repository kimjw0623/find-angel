import React, { useState, useEffect } from 'react';
import api from '../services/api';
import AccessoryPriceChart from '../components/AccessoryPriceChart';
import AccessoryPatternList from '../components/AccessoryPatternList';

const AccessoryDashboard = ({ timeRange }) => {
  const [priceData, setPriceData] = useState({});
  const [patterns, setPatterns] = useState({ dealer: {}, support: {} });
  const [selectedRole, setSelectedRole] = useState('dealer');
  const [selectedPatterns, setSelectedPatterns] = useState(new Set());

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [trendsData, patternsData] = await Promise.all([
          api.getPriceTrends({ role: selectedRole, timeRange }),
          api.getAllPatterns()
        ]);
        setPriceData(trendsData);
        setPatterns(patternsData);
      } catch (error) {
        console.error('데이터 로딩 실패:', error);
      }
    };

    fetchData();
  }, [selectedRole, timeRange]);

  const handlePatternSelect = (patternKey) => {
    setSelectedPatterns(prev => {
      const newSet = new Set(prev);
      if (newSet.has(patternKey)) {
        newSet.delete(patternKey);
      } else {
        newSet.add(patternKey);
      }
      return newSet;
    });
  };

  const handleClearSelection = () => {
    setSelectedPatterns(new Set());
  };

  return (
    <div>
      <div className="mb-4 flex space-x-4">
        <select
          className="p-2 border rounded"
          value={selectedRole}
          onChange={(e) => {
            setSelectedRole(e.target.value);
            setSelectedPatterns(new Set());
          }}
        >
          <option value="dealer">딜러</option>
          <option value="support">서포터</option>
        </select>

        {selectedPatterns.size > 0 && (
          <button
            onClick={handleClearSelection}
            className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600"
          >
            선택 초기화
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          {selectedPatterns.size > 0 && (
            <AccessoryPriceChart
              data={priceData}
              selectedPatterns={Array.from(selectedPatterns)}
              patterns={patterns[selectedRole]}
            />
          )}
        </div>
        <div>
          <AccessoryPatternList
            patterns={patterns[selectedRole]}
            selectedPatterns={selectedPatterns}
            onPatternSelect={handlePatternSelect}
          />
        </div>
      </div>
    </div>
  );
};

export default AccessoryDashboard;