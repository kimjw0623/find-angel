import React, { useState, useEffect } from 'react';
import { Select } from '../components/ui/Select';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';

const SimulationForm = ({ onSimulate }) => {
  const [formState, setFormState] = useState({
    part: '',
    grade: '',
    startLevel: '0',
    targetLevel: '1',
    quality: '90',
    trials: '10000',
    options: []
  });

  const [availableOptions, setAvailableOptions] = useState([]);

  useEffect(() => {
    // 부위에 따른 사용 가능한 옵션 업데이트
    const updateAvailableOptions = () => {
      const options = {
        '목걸이': [
          '추피', '적주피', '아덴게이지', '낙인력',
          '깡공', '깡무공', '최생', '최마'
        ],
        '귀걸이': [
          '공퍼', '무공퍼', '아군회복', '아군보호막',
          '깡공', '깡무공', '최생', '최마'
        ],
        '반지': [
          '치적', '치피', '아공강', '아피강',
          '깡공', '깡무공', '최생', '최마'
        ]
      };

      setAvailableOptions(formState.part ? options[formState.part] : []);
    };

    updateAvailableOptions();
  }, [formState.part]);

  // 옵션 추가/수정 핸들러
  const handleOptionChange = (index, field, value) => {
    const newOptions = [...formState.options];
    if (!newOptions[index]) {
      newOptions[index] = {};
    }
    newOptions[index][field] = value;
    setFormState({ ...formState, options: newOptions });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSimulate(formState);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">부위</label>
          <Select 
            value={formState.part}
            onChange={(value) => setFormState({ ...formState, part: value })}
            placeholder="부위 선택"
          >
            <option value="목걸이">목걸이</option>
            <option value="귀걸이">귀걸이</option>
            <option value="반지">반지</option>
          </Select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">등급</label>
          <Select
            value={formState.grade}
            onChange={(value) => setFormState({ ...formState, grade: value })}
            placeholder="등급 선택"
          >
            <option value="고대">고대</option>
            <option value="유물">유물</option>
          </Select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">품질</label>
          <Input
            type="number"
            min="0"
            max="100"
            value={formState.quality}
            onChange={(e) => setFormState({ ...formState, quality: e.target.value })}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">시작 연마</label>
          <Select
            value={formState.startLevel}
            onChange={(value) => setFormState({ ...formState, startLevel: value })}
            placeholder="시작 연마 선택"
          >
            <option value="0">0연마</option>
            <option value="1">1연마</option>
            <option value="2">2연마</option>
          </Select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">목표 연마</label>
          <Select
            value={formState.targetLevel}
            onChange={(value) => setFormState({ ...formState, targetLevel: value })}
            placeholder="목표 연마 선택"
          >
            {[1, 2, 3].map(level => (
              level > parseInt(formState.startLevel) && (
                <option key={level} value={String(level)}>
                  {level}연마
                </option>
              )
            ))}
          </Select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">시뮬레이션 횟수</label>
          <Input
            type="number"
            min="1000"
            max="1000000"
            value={formState.trials}
            onChange={(e) => setFormState({ ...formState, trials: e.target.value })}
          />
        </div>
      </div>

      {parseInt(formState.startLevel) > 0 && (
        <div className="mt-4">
          <h3 className="text-lg font-medium mb-2">시작 옵션 설정</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...Array(parseInt(formState.startLevel))].map((_, index) => (
              <div key={index} className="space-y-2">
                <Select
                  value={formState.options[index]?.name || ''}
                  onChange={(value) => handleOptionChange(index, 'name', value)}
                  placeholder={`옵션 ${index + 1} 선택`}
                >
                  {availableOptions.map(option => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>

                {formState.options[index]?.name && (
                  <Select
                    value={formState.options[index]?.grade || ''}
                    onChange={(value) => handleOptionChange(index, 'grade', value)}
                    placeholder="등급 선택"
                  >
                    <option value="하옵">하옵</option>
                    <option value="중옵">중옵</option>
                    <option value="상옵">상옵</option>
                  </Select>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <Button type="submit" className="mt-4">
        시뮬레이션 시작
      </Button>
    </form>
  );
};

export default SimulationForm;