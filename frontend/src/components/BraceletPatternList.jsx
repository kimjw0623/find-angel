import React, { useState, useMemo } from 'react';

const BraceletPatternList = ({ patterns, selectedPatterns, onPatternSelect, filters }) => {
  const [sortBy, setSortBy] = useState('price');
  const [statFilter, setStatFilter] = useState('all');

  const filteredAndSortedPatterns = useMemo(() => {
    if (!patterns || Object.keys(patterns).length === 0) {
      return [];
    }

    let filtered = Object.entries(patterns).map(([key, pattern]) => ({
      ...pattern,
      key
    })).filter(pattern => {
      // 등급 필터
      if (pattern.grade !== filters.grade) return false;

      // 고정 효과 수 필터
      if (filters.fixedCount !== 'all' && 
          pattern.fixed_option_count !== parseInt(filters.fixedCount)) {
        return false;
      }

      // 부여 효과 수 필터
      if (filters.extraCount !== 'all' && 
          pattern.extra_option_count !== parseInt(filters.extraCount)) {
        return false;
      }

      // 전투특성 필터
      if (statFilter !== 'all') {
        if (!pattern.combat_stats || !pattern.combat_stats.includes(statFilter)) {
          return false;
        }
      }

      return true;
    });

    // 정렬
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'price':
          return b.current_price - a.current_price;
        case 'samples':
          return b.sample_count - a.sample_count;
        default:
          return b.current_price - a.current_price;
      }
    });

    return filtered;
  }, [patterns, filters, sortBy, statFilter]);

  return (
    <div className="bg-white p-4 rounded-lg shadow">
      <h2 className="text-xl font-bold mb-4">패턴 목록</h2>
      
      <div className="grid grid-cols-2 gap-2 mb-4">
        <select
          className="p-2 border rounded"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
        >
          <option value="price">가격순</option>
          <option value="samples">거래량순</option>
        </select>

        <select
          className="p-2 border rounded"
          value={statFilter}
          onChange={(e) => setStatFilter(e.target.value)}
        >
          <option value="all">모든 특성</option>
          <option value="특화">특화</option>
          <option value="치명">치명</option>
          <option value="신속">신속</option>
        </select>
      </div>

      <div className="space-y-2 max-h-[600px] overflow-y-auto">
        {filteredAndSortedPatterns.map((pattern) => (
          <div
            key={pattern.key}
            onClick={() => onPatternSelect(pattern.key)}
            className={`p-4 border rounded cursor-pointer transition-colors ${
              selectedPatterns.has(pattern.key) 
                ? 'bg-blue-50 border-blue-500' 
                : 'hover:bg-gray-50'
            }`}
          >
            <div className="flex justify-between items-center">
              <div className="flex flex-col">
                <span className="font-medium">
                  {pattern.grade} {pattern.type}
                </span>
                <span className="text-sm text-gray-600">
                  {pattern.combat_stats && <span>{pattern.combat_stats}</span>}
                  {pattern.base_stats && <span> + {pattern.base_stats}</span>}
                  {pattern.special_effects && <span> + {pattern.special_effects}</span>}
                </span>
                <span className="text-sm text-gray-500">
                  고정 {pattern.fixed_option_count}개, 부여 {pattern.extra_option_count}개
                </span>
              </div>
              <div className="text-right">
                <div className="font-medium">
                  {pattern.current_price.toLocaleString()}골드
                </div>
                <div className="text-sm text-gray-500">
                  거래량: {pattern.sample_count}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default BraceletPatternList;