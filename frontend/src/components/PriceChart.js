import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Brush } from 'recharts';

// 차트 색상 배열
const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#665191', '#d45087', '#2f4b7c', '#f95d6a'];

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white p-4 border rounded shadow-lg">
        <p className="font-bold">{new Date(label).toLocaleString()}</p>
        {payload.filter(p => p.dataKey.startsWith('price_')).map((p, idx) => (
          <p key={idx} style={{ color: p.color }}>
            {p.name}: {p.value.toLocaleString()}골드
          </p>
        ))}
        {payload.filter(p => p.dataKey.startsWith('volume_')).map((p, idx) => (
          <p key={idx} style={{ color: p.color }}>
            {p.name} 거래량: {p.value}개
          </p>
        ))}
      </div>
    );
  }
  return null;
};

const PriceChart = ({ data, selectedPatterns, patterns }) => {
  // 데이터 재구성
  const chartData = data[selectedPatterns[0]]?.map(point => {
    const newPoint = { timestamp: point.timestamp };
    selectedPatterns.forEach((pattern, idx) => {
      const patternData = data[pattern]?.find(d => d.timestamp === point.timestamp);
      if (patternData) {
        newPoint[`price_${idx}`] = patternData.base_price;
        newPoint[`volume_${idx}`] = patternData.sample_count;
      }
    });
    return newPoint;
  }) || [];

  return (
    <div className="bg-white p-4 rounded-lg shadow">
      <h2 className="text-xl font-bold mb-4">가격 추이</h2>
      <div className="h-[400px]">
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
              yAxisId="price"
              name="가격"
              tickFormatter={(value) => `${value.toLocaleString()}`}
            />
            <YAxis
              yAxisId="volume"
              orientation="right"
              name="거래량"
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            {selectedPatterns.map((pattern, idx) => (
              <React.Fragment key={pattern}>
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey={`price_${idx}`}
                  stroke={COLORS[idx % COLORS.length]}
                  name={`${patterns[pattern]?.grade} ${patterns[pattern]?.part} ${patterns[pattern]?.level}연마 (${patterns[pattern]?.pattern})`}
                  dot={false}
                  strokeWidth={2}
                />
              </React.Fragment>
            ))}
            <Brush dataKey="timestamp" height={30} stroke="#8884d8" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default PriceChart;