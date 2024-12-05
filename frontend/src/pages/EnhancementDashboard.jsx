import React, { useState } from 'react';
import { Card } from '../components/ui/Card';
import SimulationForm from '../components/SimulationForm';

const EnhancementDashboard = () => {
  const [simulationResults, setSimulationResults] = useState(null);

  const handleSimulate = async (formData) => {
    // TODO: API 호출 및 결과 처리
    console.log('Running simulation with:', formData);
  };

  return (
    <div className="container mx-auto p-4">
      <Card className="mb-4">
        <h2 className="text-2xl font-bold mb-4">연마 시뮬레이터</h2>
        <SimulationForm onSimulate={handleSimulate} />
      </Card>

      {simulationResults && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <h3 className="text-xl font-bold mb-4">딜러 패턴 결과</h3>
            {/* TODO: 딜러 패턴 결과 표시 */}
          </Card>

          <Card>
            <h3 className="text-xl font-bold mb-4">서포터 패턴 결과</h3>
            {/* TODO: 서포터 패턴 결과 표시 */}
          </Card>
        </div>
      )}
    </div>
  );
};

export default EnhancementDashboard;