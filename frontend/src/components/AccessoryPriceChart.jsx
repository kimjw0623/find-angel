import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Brush } from 'recharts';

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#665191', '#d45087', '#2f4b7c', '#f95d6a'];

const CustomTooltip = ({ active, payload, label, patterns }) => {
  if (active && payload && payload.length) {
    // payload를 가격 기준으로 내림차순 정렬
    const sortedPayload = [...payload].sort((a, b) => (b.value || 0) - (a.value || 0));

    return (
      <div className="bg-white p-4 border rounded shadow-lg">
        <p className="font-bold">{new Date(label).toLocaleString()}</p>
        
        {sortedPayload.map((entry, index) => {
          const patternKey = entry.dataKey.split('_')[1];
          const patternData = entry.payload[`data_${patternKey}`];
          
          return (
            <div key={index} className="mt-2">
              <p className="font-semibold" style={{ color: entry.color }}>
                {patterns[patternKey]?.grade} {patterns[patternKey]?.part} {patterns[patternKey]?.level}연마 ({patterns[patternKey]?.pattern})
              </p>

              <div className="ml-2">
                {/* 품질별 가격 정보 */}
                <p>가격: {entry.value?.toLocaleString()}골드</p>
                <p className="text-sm">샘플 수: {patternData?.sample_count}개</p>

                {/* Common 옵션 가치 정보 */}
                {patternData?.common_option_values && 
                 Object.keys(patternData.common_option_values).length > 0 && (
                  <div className="mt-1">
                    <p className="text-sm font-medium">부가 옵션 가치:</p>
                    {Object.entries(patternData.common_option_values).map(([option, values]) => (
                      <div key={option} className="ml-2">
                        <p className="text-sm">{option}:</p>
                        {Object.entries(values).map(([value, price]) => (
                          <p key={value} className="text-xs ml-2">
                            {value}: +{price.toLocaleString()}골드
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  }
  return null;
};

const PriceChart = ({ data, selectedPatterns, patterns }) => {
  const [qualityFilter, setQualityFilter] = useState('90');

  // 모든 선택된 패턴의 데이터를 통합
  const chartData = React.useMemo(() => {
    const timeMap = new Map();

    // 각 패턴의 데이터를 시간별로 통합
    selectedPatterns.forEach(pattern => {
      const patternData = data[pattern];
      if (!patternData) return;

      patternData.forEach(point => {
        if (!timeMap.has(point.timestamp)) {
          timeMap.set(point.timestamp, {
            timestamp: point.timestamp
          });
        }
        const timePoint = timeMap.get(point.timestamp);
        
        // 각 패턴의 데이터를 저장 - 0인 경우 undefined로 설정
        const price = point.quality_prices[qualityFilter] || undefined;
        if (price !== undefined) {
          timePoint[`price_${pattern}`] = price;
          timePoint[`data_${pattern}`] = {
            quality_prices: point.quality_prices,
            common_option_values: point.common_option_values,
            sample_count: point.sample_count
          };
        }
      });
    });

    // Map을 배열로 변환하고 시간순 정렬
    return Array.from(timeMap.values()).sort((a, b) => a.timestamp - b.timestamp);
  }, [data, selectedPatterns, qualityFilter]);

  return (
    <div className="bg-white p-4 rounded-lg shadow">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">가격 추이</h2>
        <select
          className="p-2 border rounded"
          value={qualityFilter}
          onChange={(e) => setQualityFilter(e.target.value)}
        >
          <option value="60">품질: 60+</option>
          <option value="70">품질: 70+</option>
          <option value="80">품질: 80+</option>
          <option value="90">품질: 90+</option>
        </select>
      </div>

      <div className="h-[600px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={chartData}
            margin={{ top: 10, right: 50, left: 60, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="timestamp"
              type="number"
              domain={['auto', 'auto']}
              tickFormatter={(timestamp) => new Date(timestamp).toLocaleDateString()}
              scale="time"
            />
            <YAxis
              tickFormatter={(value) => `${value?.toLocaleString()}`}
            />
            <Tooltip content={<CustomTooltip patterns={patterns} />} />
            <Legend />
            {selectedPatterns.map((pattern, index) => (
              <Line
                key={pattern}
                type="monotone"
                dataKey={`price_${pattern}`}
                stroke={COLORS[index % COLORS.length]}
                name={`${patterns[pattern]?.grade} ${patterns[pattern]?.part} ${patterns[pattern]?.level}연마 (${patterns[pattern]?.pattern})`}
                dot={false}
                strokeWidth={2}
                connectNulls={true}
              />
            ))}
            <Brush dataKey="timestamp" height={30} stroke="#8884d8" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default PriceChart;