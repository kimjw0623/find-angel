import React, { useState, useEffect } from 'react';
import api from '../services/api';
import BraceletPriceChart from '../components/BraceletPriceChart';
import BraceletPatternList from '../components/BraceletPatternList';

const BraceletDashboard = ({ timeRange }) => {
  const [grade, setGrade] = useState('고대');
  const [fixedCount, setFixedCount] = useState('all');
  const [extraCount, setExtraCount] = useState('all');
  const [selectedPatterns, setSelectedPatterns] = useState(new Set());
  const [braceletData, setBraceletData] = useState({});
  const [priceData, setPriceData] = useState({});

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [trendsData, patternsData] = await Promise.all([
          api.getBraceletTrends({ grade, timeRange }),
          api.getBraceletPatterns({ grade })
        ]);
        setPriceData(trendsData);
        setBraceletData(patternsData);
      } catch (error) {
        console.error('팔찌 데이터 로딩 실패:', error);
      }
    };

    fetchData();
  }, [grade, timeRange]);

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

  return (
    <div>
      <div className="mb-4 flex space-x-4">
        <select
          className="p-2 border rounded"
          value={grade}
          onChange={(e) => setGrade(e.target.value)}
        >
          <option value="고대">고대</option>
          <option value="유물">유물</option>
        </select>

        <select
          className="p-2 border rounded"
          value={fixedCount}
          onChange={(e) => setFixedCount(e.target.value)}
        >
          <option value="all">고정 전체</option>
          <option value="1">고정 1개</option>
          <option value="2">고정 2개</option>
        </select>

        <select
          className="p-2 border rounded"
          value={extraCount}
          onChange={(e) => setExtraCount(e.target.value)}
        >
          {grade === '고대' ? (
            <>
              <option value="all">부여 전체</option>
              <option value="2">부여 2개</option>
              <option value="3">부여 3개</option>
            </>
          ) : (
            <>
              <option value="all">부여 전체</option>
              <option value="1">부여 1개</option>
              <option value="2">부여 2개</option>
            </>
          )}
        </select>

        {selectedPatterns.size > 0 && (
          <button
            onClick={() => setSelectedPatterns(new Set())}
            className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600"
          >
            선택 초기화
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          {selectedPatterns.size > 0 && (
            <BraceletPriceChart
              data={priceData}
              selectedPatterns={Array.from(selectedPatterns)}
              patterns={braceletData}
            />
          )}
        </div>
        <div>
          <BraceletPatternList
            patterns={braceletData}
            selectedPatterns={selectedPatterns}
            onPatternSelect={handlePatternSelect}
            filters={{ grade, fixedCount, extraCount }}
          />
        </div>
      </div>
    </div>
  );
};

export default BraceletDashboard;