import React, { useState } from 'react';

const PatternList = ({ patterns, selectedPatterns, onPatternSelect }) => {
  const [gradeFilter, setGradeFilter] = useState('all');
  const [partFilter, setPartFilter] = useState('all');
  const [levelFilter, setLevelFilter] = useState('all');

  if (!patterns || Object.keys(patterns).length === 0) {
    return (
      <div className="bg-white p-4 rounded-lg shadow">
        <h2 className="text-xl font-bold mb-4">패턴 목록</h2>
        <p className="text-gray-500">데이터가 없습니다.</p>
      </div>
    );
  }

  const sortedPatterns = Object.entries(patterns)
    .map(([key, pattern]) => ({
      ...pattern,
      key
    }))
    .filter(pattern => 
      (gradeFilter === 'all' || pattern.grade === gradeFilter) &&
      (partFilter === 'all' || pattern.part === partFilter) &&
      (levelFilter === 'all' || pattern.level === parseInt(levelFilter))
    )
    .sort((a, b) => b.base_price - a.base_price);

  return (
    <div className="bg-white p-4 rounded-lg shadow">
      <h2 className="text-xl font-bold mb-4">패턴 목록</h2>
      
      <div className="grid grid-cols-3 gap-2 mb-4">
        <select 
          className="p-2 border rounded"
          value={gradeFilter}
          onChange={(e) => setGradeFilter(e.target.value)}
        >
          <option value="all">등급: 전체</option>
          <option value="고대">고대</option>
          <option value="유물">유물</option>
        </select>

        <select 
          className="p-2 border rounded"
          value={partFilter}
          onChange={(e) => setPartFilter(e.target.value)}
        >
          <option value="all">부위: 전체</option>
          <option value="목걸이">목걸이</option>
          <option value="귀걸이">귀걸이</option>
          <option value="반지">반지</option>
        </select>

        <select 
          className="p-2 border rounded"
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
        >
          <option value="all">연마: 전체</option>
          <option value="0">0연마</option>
          <option value="1">1연마</option>
          <option value="2">2연마</option>
          <option value="3">3연마</option>
        </select>
      </div>

      <div className="space-y-2 max-h-[600px] overflow-y-auto">
        {sortedPatterns.map((pattern) => {
          const fullKey = `${pattern.grade}:${pattern.part}:${pattern.level}:${pattern.pattern}`;
          return (
            <div
              key={pattern.key}
              onClick={() => onPatternSelect(fullKey)}
              className={`p-4 border rounded cursor-pointer transition-colors ${
                selectedPatterns.has(fullKey) ? 'bg-blue-50 border-blue-500' : 'hover:bg-gray-50'
              }`}
            >
              <div className="flex justify-between items-center">
                <div className="flex flex-col">
                  <span className="font-medium">
                    {pattern.grade} {pattern.part} ({pattern.level}연마)
                  </span>
                  <span className="text-sm text-gray-600">{pattern.pattern}</span>
                </div>
                <div className="text-right">
                  <div className="font-medium">
                    {pattern.base_price.toLocaleString()}골드
                  </div>
                  <div className="text-sm text-gray-500">
                    거래량: {pattern.sample_count}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PatternList;