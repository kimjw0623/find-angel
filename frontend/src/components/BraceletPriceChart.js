import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Brush } from 'recharts';

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#665191', '#d45087', '#2f4b7c', '#f95d6a'];

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white p-4 border rounded shadow-lg">
        <p className="font-bold">{new Date(label).toLocaleString()}</p>
        
        {payload.map((entry, index) => {
          const pattern = entry.payload[`pattern_${entry.dataKey.split('_')[1]}`];
          
          return (
            <div key={index} className="mt-2">
              <p className="font-semibold" style={{ color: entry.color }}>
                {pattern.grade} {pattern.type} 
                ({pattern.combat_stats ? `${pattern.combat_stats}` : ''})
                {pattern.base_stats ? ` + ${pattern.base_stats}` : ''}
                {pattern.special_effects ? ` + ${pattern.special_effects}` : ''}
              </p>

              <div className="ml-2">
                <p>가격: {entry.value.toLocaleString()}골드</p>
                <p className="text-sm">샘플 수: {pattern.sample_count}개</p>
                <p className="text-sm">고정 {pattern.fixed_option_count}개, 부여 {pattern.extra_option_count}개</p>
              </div>
            </div>
          );
        })}
      </div>
    );
  }
  return null;
};

const BraceletPriceChart = ({ data, selectedPatterns, patterns }) => {
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
        
        // 각 패턴의 데이터를 저장
        timePoint[`price_${pattern}`] = point.price;
        timePoint[`pattern_${pattern}`] = {
          grade: patterns[pattern].grade,
          type: patterns[pattern].type,
          combat_stats: patterns[pattern].combat_stats,
          base_stats: patterns[pattern].base_stats,
          special_effects: patterns[pattern].special_effects,
          fixed_option_count: patterns[pattern].fixed_option_count,
          extra_option_count: patterns[pattern].extra_option_count,
          sample_count: point.sample_count
        };
      });
    });

    // Map을 배열로 변환하고 시간순 정렬
    return Array.from(timeMap.values()).sort((a, b) => a.timestamp - b.timestamp);
  }, [data, selectedPatterns, patterns]);

  return (
    <div className="bg-white p-4 rounded-lg shadow">
      <h2 className="text-xl font-bold mb-4">가격 추이</h2>

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
              tickFormatter={(value) => `${value.toLocaleString()}`}
              domain={[0, dataMax => dataMax * 1.2]}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            {selectedPatterns.map((pattern, index) => (
              <Line
                key={pattern}
                type="monotone"
                dataKey={`price_${pattern}`}
                stroke={COLORS[index % COLORS.length]}
                name={`${patterns[pattern]?.grade} ${patterns[pattern]?.type}`}
                dot={false}
                strokeWidth={2}
              />
            ))}
            <Brush dataKey="timestamp" height={30} stroke="#8884d8" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default BraceletPriceChart;