import React, { useState, useEffect } from 'react';
import api from '../services/api';
import PriceChart from '../components/PriceChart';
import PatternList from '../components/PatternList';

const Dashboard = () => {
  const [priceData, setPriceData] = useState({});
  const [patterns, setPatterns] = useState({ dealer: {}, support: {} });
  const [selectedRole, setSelectedRole] = useState('dealer');
  const [selectedPatterns, setSelectedPatterns] = useState(new Set());
  const [timeRange, setTimeRange] = useState('1d');  // 기본값 1일

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
  }, [selectedRole, timeRange]);  // timeRange를 의존성 배열에 추가

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
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-6">로스트아크 시장 분석</h1>
      
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
            <PriceChart
              data={priceData}
              selectedPatterns={Array.from(selectedPatterns)}
              patterns={patterns[selectedRole]}
            />
          )}
        </div>
        <div>
          <PatternList
            patterns={patterns[selectedRole]}
            selectedPatterns={selectedPatterns}
            onPatternSelect={handlePatternSelect}
          />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;