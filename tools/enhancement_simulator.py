import random
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from enum import Enum

class AccessoryType(Enum):
    NECKLACE = "목걸이"
    EARRING = "귀걸이"
    RING = "반지"

class Grade(Enum):
    ANCIENT = "고대"
    RELIC = "유물"

class OptionGrade(Enum):
    LOW = "하옵"     # 63%
    MID = "중옵"     # 30%
    HIGH = "상옵"    # 7%

@dataclass
class EnhancementCost:
    gold: int
    fragments: int

class AccessoryOption:
    def __init__(self, name: str, grade: OptionGrade = None):
        self.name = name
        self.grade = grade

    def __str__(self) -> str:
        return f"{self.name}({self.grade.value if self.grade else 'None'})"

class EnhancementSimulator:
    def __init__(self):
        # 각 부위별 특수 옵션
        self.SPECIAL_OPTIONS = {
            AccessoryType.NECKLACE: ["추피", "적주피", "낙인력", "아덴게이지"],
            AccessoryType.EARRING: ["공퍼", "무공퍼", "아군회복", "아군보호막"],
            AccessoryType.RING: ["치적", "치피", "아공강", "아피강"]
        }
        
        # 공통 옵션
        self.COMMON_OPTIONS = [
            "최생", "최마", "깡공", "깡무공", 
            "상태이상공격지속시간", "전투중생회"
        ]
        
        # 등급별 비용
        self.ENHANCEMENT_COSTS = {
            Grade.RELIC: [
                EnhancementCost(600, 10),
                EnhancementCost(600, 20),
                EnhancementCost(600, 30)
            ],
            Grade.ANCIENT: [
                EnhancementCost(1200, 75),
                EnhancementCost(1200, 150),
                EnhancementCost(1200, 225)
            ]
        }

        # 옵션 등급 확률
        self.GRADE_PROBABILITIES = {
            OptionGrade.LOW: 0.63,
            OptionGrade.MID: 0.30,
            OptionGrade.HIGH: 0.07
        }

    def _get_random_option_grade(self) -> OptionGrade:
        """옵션 등급 랜덤 선택 (하옵 63%, 중옵 30%, 상옵 7%)"""
        rand = random.random()
        cumulative = 0
        for grade, prob in self.GRADE_PROBABILITIES.items():
            cumulative += prob
            if rand <= cumulative:
                return grade
        return OptionGrade.LOW  # 안전장치

    def _get_available_options(self, acc_type: AccessoryType, 
                             enhanced_options: List[AccessoryOption]) -> List[str]:
        """남은 사용 가능한 옵션 목록 반환"""
        # 현재 적용된 옵션 이름들
        used_options = [opt.name for opt in enhanced_options]
        
        # 해당 부위의 특수 옵션 + 공통 옵션
        all_options = self.SPECIAL_OPTIONS[acc_type] + self.COMMON_OPTIONS
        
        # 아직 사용되지 않은 옵션만 반환
        return [opt for opt in all_options if opt not in used_options]

    def enhance_once(self, acc_type: AccessoryType, 
                    current_options: List[AccessoryOption]) -> Tuple[AccessoryOption, EnhancementCost]:
        """한 번의 연마 시도"""
        # 사용 가능한 옵션들 가져오기
        available_options = self._get_available_options(acc_type, current_options)
        if not available_options:
            raise ValueError("No available options for enhancement")

        # 랜덤하게 옵션 선택
        selected_option = random.choice(available_options)
        
        # 옵션 등급 결정
        option_grade = self._get_random_option_grade()
        
        return AccessoryOption(selected_option, option_grade)

    def simulate_enhancement(self, 
                           acc_type: AccessoryType,
                           grade: Grade,
                           enhancement_count: int = 3) -> List[Tuple[AccessoryOption, EnhancementCost]]:
        """지정된 횟수만큼 연마 시도"""
        if enhancement_count > 3:
            raise ValueError("Maximum enhancement count is 3")

        results = []
        current_options = []

        for i in range(enhancement_count):
            # 연마 시도
            new_option = self.enhance_once(acc_type, current_options)
            current_options.append(new_option)
            
            # 비용 계산
            cost = self.ENHANCEMENT_COSTS[grade][i]
            
            results.append((new_option, cost))

        return results

    def simulate_enhancement_with_preset(self, 
                                    acc_type: AccessoryType,
                                    grade: Grade,
                                    preset_options: List[Tuple[AccessoryOption, EnhancementCost]],
                                    remaining_count: int) -> List[Tuple[AccessoryOption, EnhancementCost]]:
        """프리셋 옵션으로 시작하는 연마 시뮬레이션"""
        if remaining_count <= 0:
            return []

        results = []
        current_options = [opt for opt, _ in preset_options]

        for i in range(remaining_count):
            # 연마 시도
            new_option = self.enhance_once(acc_type, current_options)
            current_options.append(new_option)
            
            # 비용 계산 - 프리셋 이후부터의 비용만 계산
            cost = self.ENHANCEMENT_COSTS[grade][len(preset_options) + i]
            
            results.append((new_option, cost))

        return results

    def run_simulation(self, 
                      acc_type: AccessoryType,
                      grade: Grade,
                      trials: int = 1000,
                      enhancement_count: int = 3) -> List[List[Tuple[AccessoryOption, EnhancementCost]]]:
        """여러 번의 시뮬레이션 실행"""
        results = []
        for _ in range(trials):
            trial_result = self.simulate_enhancement(acc_type, grade, enhancement_count)
            results.append(trial_result)
        return results

def test_enhancement_simulator():
    simulator = EnhancementSimulator()

    def print_options(options):
        """옵션 출력 헬퍼 함수"""
        for option, cost in options:
            print(f"옵션: {option.name} ({option.grade.value}), "
                  f"비용: {cost.gold} 골드, {cost.fragments} 조각")
        print()

    # 기본 연마 테스트
    print("\n=== 기본 연마 테스트 ===")
    print("고대 목걸이 3연마 시도:")
    result = simulator.simulate_enhancement(
        acc_type=AccessoryType.NECKLACE,
        grade=Grade.ANCIENT,
        enhancement_count=3
    )
    print_options(result)

    # 프리셋 연마 테스트
    print("\n=== 프리셋 연마 테스트 ===")
    # 추피 상옵으로 시작하는 테스트
    preset_options = [(AccessoryOption("추피", OptionGrade.HIGH), 
                      EnhancementCost(0, 0))]
    print("고대 목걸이 프리셋(추피 상옵) + 2연마 시도:")
    result = simulator.simulate_enhancement_with_preset(
        acc_type=AccessoryType.NECKLACE,
        grade=Grade.ANCIENT,
        preset_options=preset_options,
        remaining_count=2
    )
    print("프리셋 옵션:")
    print_options(preset_options)
    print("추가된 옵션:")
    print_options(result)

    # 여러 번의 시도 결과 확인
    print("\n=== 여러 번의 시도 결과 ===")
    print("고대 목걸이 10번 시도 결과:")
    for i in range(10):
        print(f"\n시도 {i+1}:")
        result = simulator.simulate_enhancement(
            acc_type=AccessoryType.NECKLACE,
            grade=Grade.ANCIENT,
            enhancement_count=3
        )
        print_options(result)

    # 옵션 출현 빈도 테스트
    print("\n=== 옵션 출현 빈도 테스트 (1000회) ===")
    option_counts = {}
    grade_counts = {
        OptionGrade.LOW: 0,
        OptionGrade.MID: 0,
        OptionGrade.HIGH: 0
    }

    for _ in range(1000):
        result = simulator.enhance_once(
            acc_type=AccessoryType.NECKLACE,
            current_options=[]
        )
        option_counts[result.name] = option_counts.get(result.name, 0) + 1
        grade_counts[result.grade] += 1

    print("\n옵션별 출현 횟수:")
    for option, count in sorted(option_counts.items()):
        print(f"{option}: {count}회 ({count/1000*100:.1f}%)")

    print("\n등급별 출현 횟수:")
    for grade, count in grade_counts.items():
        print(f"{grade.value}: {count}회 ({count/1000*100:.1f}%)")

if __name__ == "__main__":
    test_enhancement_simulator()