from enhancement_simulator import *
from item_checker import ItemEvaluator
from database import DatabaseManager
from collections import defaultdict

class EnhancementAnalyzer:
    def __init__(self, db_manager: DatabaseManager):
        self.simulator = EnhancementSimulator()
        self.evaluator = ItemEvaluator(db_manager)
        
    def convert_to_market_item(self, 
                             acc_type: AccessoryType,
                             grade: Grade,
                             quality: int,
                             enhanced_options: List[Tuple[AccessoryOption, EnhancementCost]]) -> dict:
        """시뮬레이션 결과를 가격 평가 시스템용 형식으로 변환"""
        return {
            "Name": f"{grade.value} {acc_type.value}",
            "Grade": grade.value,
            "GradeQuality": quality,
            "AuctionInfo": {
                "BuyPrice": 1000,  # 가격 평가용이므로 0으로 설정
                "TradeAllowCount": 2  # 기본값
            },
            "Options": [
                {
                    "OptionName": option.name,
                    "Value": self._get_option_value(option),
                    "IsValuePercentage": self._is_percentage_option(option.name)
                }
                for option, _ in enhanced_options
            ]
        }
    
    def _is_percentage_option(self, option_name: str) -> bool:
        """해당 옵션이 퍼센트 값인지 여부"""
        percentage_options = {
            "추피", "적주피", "공퍼", "무공퍼", "치적", "치피",
            "아덴게이지", "낙인력", "아군회복", "아군보호막", "아공강", "아피강"
        }
        return option_name in percentage_options
    
    def _get_option_value(self, option: AccessoryOption) -> float:
        """옵션 등급에 따른 수치 반환"""
        option_values = {
            "추피": {"하옵": 0.7, "중옵": 1.6, "상옵": 2.6},
            "적주피": {"하옵": 0.55, "중옵": 1.2, "상옵": 2.0},
            "공퍼": {"하옵": 0.4, "중옵": 0.95, "상옵": 1.55},
            "무공퍼": {"하옵": 0.8, "중옵": 1.8, "상옵": 3.0},
            "치적": {"하옵": 0.4, "중옵": 0.95, "상옵": 1.55},
            "치피": {"하옵": 1.1, "중옵": 2.4, "상옵": 4.0},
            "아덴게이지": {"하옵": 1.6, "중옵": 3.6, "상옵": 6.0},
            "낙인력": {"하옵": 2.15, "중옵": 4.8, "상옵": 8.0},
            "아군회복": {"하옵": 0.95, "중옵": 2.1, "상옵": 3.5},
            "아군보호막": {"하옵": 0.95, "중옵": 2.1, "상옵": 3.5},
            "아공강": {"하옵": 1.35, "중옵": 3.0, "상옵": 5.0},
            "아피강": {"하옵": 2.0, "중옵": 4.5, "상옵": 7.5},
            "깡공": {"하옵": 80, "중옵": 195, "상옵": 390},
            "깡무공": {"하옵": 195, "중옵": 480, "상옵": 960},
            "최생": {"하옵": 1300, "중옵": 3250, "상옵": 6500},
            "최마": {"하옵": 6, "중옵": 15, "상옵": 30},
            "상태이상공격지속시간": {"하옵": 0.2, "중옵": 0.5, "상옵": 1.0},
            "전투중생회": {"하옵": 10, "중옵": 25, "상옵": 50}
        }
        return option_values[option.name][option.grade.value]

    def analyze_enhancement_value(self,
                                acc_type: AccessoryType,
                                grade: Grade,
                                trials: int = 10000,
                                quality: int = 80) -> dict:
        """연마 가치 분석"""
        print(f"\n=== {grade.value} {acc_type.value} 연마 가치 분석 (시도 횟수: {trials:,}) ===")
        results = self.simulator.run_simulation(
            acc_type=acc_type,
            grade=grade,
            trials=trials,
            enhancement_count=3
        )
        
        # 패턴별 가치 분석
        pattern_values = defaultdict(lambda: {
            'count': 0,
            'total_value': 0,
            'min_value': float('inf'),
            'max_value': 0,
            'costs': {'gold': 0, 'fragments': 0},
            'values': []  # 모든 값을 저장
        })
        
        valid_count = 0  # 유효한 평가 횟수
        
        for trial_idx, trial in enumerate(results, 1):
            if trial_idx % 1000 == 0:
                print(f"진행 중... {trial_idx:,}/{trials:,}")
                
            # 시뮬레이션 결과를 가격 평가 형식으로 변환
            market_item = self.convert_to_market_item(
                acc_type=acc_type,
                grade=grade,
                quality=quality,
                enhanced_options=trial
            )
            
            # 가격 평가
            evaluation = self.evaluator.evaluate_item(market_item)
            if not evaluation:  # 평가 실패
                continue
                
            valid_count += 1
            value = evaluation['expected_price']
            
            # 패턴 식별 및 가치 기록
            pattern = self._identify_pattern(trial)
            stats = pattern_values[pattern]
            
            stats['count'] += 1
            stats['total_value'] += value
            stats['min_value'] = min(stats['min_value'], value)
            stats['max_value'] = max(stats['max_value'], value)
            stats['values'].append(value)
            
            # 비용 계산 - 매번 덮어써도 됨 (같은 패턴은 비용이 동일)
            total_gold = sum(cost.gold for _, cost in trial)
            total_fragments = sum(cost.fragments for _, cost in trial)
            stats['costs']['gold'] = total_gold
            stats['costs']['fragments'] = total_fragments
        
        print(f"\n유효한 평가 횟수: {valid_count:,}/{trials:,}")
        
        # 통계 계산 및 결과 정리
        analysis_results = {}
        for pattern, stats in pattern_values.items():
            if stats['count'] > 0:  # 0으로 나누기 방지
                avg_value = stats['total_value'] / stats['count']
                roi = (avg_value - stats['costs']['gold']) / stats['costs']['gold']
                
                analysis_results[pattern] = {
                    'count': stats['count'],  # 이 부분 추가
                    'occurrence_rate': (stats['count'] / valid_count) * 100,
                    'avg_value': avg_value,
                    'min_value': stats['min_value'],
                    'max_value': stats['max_value'],
                    'values': stats['values'],  # 필요한 경우 모든 값들도 저장
                    'costs': stats['costs'],
                    'roi': roi
                }
        
        return analysis_results
    
    def _identify_pattern(self, trial: List[Tuple[AccessoryOption, EnhancementCost]]) -> str:
        """시뮬레이션 결과의 패턴 식별"""
        # 딜러/서포터 옵션 분류
        dealer_options = []
        support_options = []
        other_options = []
        
        for option, _ in trial:
            if self._is_dealer_option(option.name):
                dealer_options.append((option.name, option.grade.value))
            elif self._is_support_option(option.name):
                support_options.append((option.name, option.grade.value))
            else:
                other_options.append((option.name, option.grade.value))
        
        # 딜러 또는 서포터 옵션이 있는 경우만 해당 패턴으로 분류
        if dealer_options:
            pattern_type = "딜러"
            main_options = dealer_options
        elif support_options:
            pattern_type = "서폿"
            main_options = support_options
        else:
            pattern_type = "기타"
            main_options = []
        
        # 메인 옵션(딜러/서폿)은 정렬하여 일관된 순서로 표시
        main_pattern = ' + '.join(f"{opt}({grade})" 
                                for opt, grade in sorted(main_options))
        
        # 부가 옵션은 있는 경우만 표시
        if other_options:
            other_pattern = ' + '.join(f"{opt}({grade})" 
                                    for opt, grade in sorted(other_options))
            return f"{pattern_type}({main_pattern}) + {other_pattern}"
        else:
            return f"{pattern_type}({main_pattern})"

    def _is_dealer_option(self, option_name: str) -> bool:
        """딜러 전용 옵션인지 확인"""
        dealer_options = {
            "추피", "적주피",  # 목걸이
            "공퍼", "무공퍼",  # 귀걸이
            "치적", "치피",    # 반지
        }
        return option_name in dealer_options

    def _is_support_option(self, option_name: str) -> bool:
        """서포터 전용 옵션인지 확인"""
        support_options = {
            "아덴게이지", "낙인력",  # 목걸이
            "아군회복", "아군보호막",  # 귀걸이
            "아공강", "아피강",      # 반지
        }
        return option_name in support_options

    def print_analysis_results(self, results: dict):
        """분석 결과 출력 - 패턴별 결과와 전체 요약 포함"""
        print("\n=== 연마 가치 분석 결과 ===")
        
        # 전체 통계 계산
        total_trials = sum(stats['count'] for stats in results.values())
        total_value = sum(stats['avg_value'] * stats['count'] for stats in results.values())
        total_gold = sum(stats['costs']['gold'] * stats['count'] for stats in results.values())
        total_fragments = sum(stats['costs']['fragments'] * stats['count'] for stats in results.values())
        
        # 딜러/서폿 패턴 분류
        dealer_patterns = {k: v for k, v in results.items() if k.startswith('딜러')}
        support_patterns = {k: v for k, v in results.items() if k.startswith('서폿')}
        
        # 딜러 패턴 출력
        if dealer_patterns:
            print("\n[딜러 패턴]")
            print("-" * 50)
            sorted_patterns = sorted(
                dealer_patterns.items(),
                key=lambda x: x[1]['roi'],
                reverse=True
            )
            for pattern, stats in sorted_patterns:
                self._print_pattern_stats(pattern, stats)
        
        # 서폿 패턴 출력
        if support_patterns:
            print("\n[서포터 패턴]")
            print("-" * 50)
            sorted_patterns = sorted(
                support_patterns.items(),
                key=lambda x: x[1]['roi'],
                reverse=True
            )
            # for pattern, stats in sorted_patterns:
            #     self._print_pattern_stats(pattern, stats)
        
        # 전체 요약 통계
        print("\n=== 전체 요약 ===")
        print("-" * 50)
        
        # 기본 통계
        print(f"총 시뮬레이션 횟수: {total_trials:,}회")
        print(f"평균 기대 가치: {total_value/total_trials:,.0f} 골드")
        print(f"평균 소요 비용: {total_gold/total_trials:,.0f} 골드, {total_fragments/total_trials:.1f} 조각")
        
        if total_gold > 0:  # 0으로 나누기 방지
            overall_roi = ((total_value - total_gold) / total_gold) * 100
            print(f"전체 평균 ROI: {overall_roi:.1f}%")
        
        # 딜러/서폿 패턴 비율
        dealer_count = sum(stats['count'] for stats in dealer_patterns.values())
        support_count = sum(stats['count'] for stats in support_patterns.values())
        print(f"\n딜러 패턴 비율: {dealer_count/total_trials*100:.1f}%")
        print(f"서폿 패턴 비율: {support_count/total_trials*100:.1f}%")
        
        # 최고 수익 패턴
        if results:  # 결과가 있는 경우만
            best_roi_pattern = max(results.items(), key=lambda x: x[1]['roi'])
            print(f"\n최고 수익률 패턴: {best_roi_pattern[0]}")
            print(f"- ROI: {best_roi_pattern[1]['roi']*100:.1f}%")
            print(f"- 평균 가치: {best_roi_pattern[1]['avg_value']:,.0f} 골드")
            print(f"- 발생 확률: {best_roi_pattern[1]['occurrence_rate']:.2f}%")
            
            # 최고 가치 패턴
            best_value_pattern = max(results.items(), key=lambda x: x[1]['avg_value'])
            print(f"\n최고 가치 패턴: {best_value_pattern[0]}")
            print(f"- 평균 가치: {best_value_pattern[1]['avg_value']:,.0f} 골드")
            print(f"- ROI: {best_value_pattern[1]['roi']*100:.1f}%")
            print(f"- 발생 확률: {best_value_pattern[1]['occurrence_rate']:.2f}%")

    def _print_pattern_stats(self, pattern: str, stats: dict):
        """개별 패턴의 통계 출력"""
        print(f"\n패턴: {pattern}")
        print(f"발생 확률: {stats['occurrence_rate']:.2f}%")
        print(f"평균 가치: {stats['avg_value']:,.0f} 골드")
        print(f"가치 범위: {stats['min_value']:,.0f} ~ {stats['max_value']:,.0f} 골드")
        print(f"비용: {stats['costs']['gold']:,} 골드, {stats['costs']['fragments']} 조각")
        print(f"ROI: {stats['roi']*100:.1f}%")

    def run_comprehensive_analysis(self, trials: int = 50000):
        """모든 경우의 수에 대한 종합 분석 실행"""
        grades = [Grade.ANCIENT, Grade.RELIC]
        acc_types = [AccessoryType.NECKLACE, AccessoryType.EARRING, AccessoryType.RING]
        qualities = [70, 80, 90]

        for grade in grades:
            print(f"\n{'='*80}")
            print(f"=== {grade.value} 등급 분석 ===")
            print(f"{'='*80}")
            
            for acc_type in acc_types:
                print(f"\n{'#'*60}")
                print(f"### {acc_type.value} 분석 ###")
                print(f"{'#'*60}")
                
                for quality in qualities:
                    print(f"\n{'-'*40}")
                    print(f"품질 {quality} 분석")
                    print(f"{'-'*40}")
                    
                    try:
                        results = self.analyze_enhancement_value(
                            acc_type=acc_type,
                            grade=grade,
                            trials=trials,
                            quality=quality
                        )
                        
                        self.print_analysis_results(results)
                        
                        # 파일로도 저장
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"sim_result/analysis_{grade.value}_{acc_type.value}_품질{quality}_{timestamp}.txt"
                        
                        with open(filename, 'w', encoding='utf-8') as f:
                            # 원래 stdout을 저장
                            original_stdout = sys.stdout
                            # stdout을 파일로 변경
                            sys.stdout = f
                            
                            print(f"\n=== {grade.value} {acc_type.value} (품질 {quality}) 분석 결과 ===")
                            print(f"분석 시간: {datetime.now()}")
                            print(f"시뮬레이션 횟수: {trials:,}")
                            self.print_analysis_results(results)
                            
                            # stdout 복구
                            sys.stdout = original_stdout
                        
                        print(f"\n분석 결과가 {filename}에 저장되었습니다.")
                        
                    except Exception as e:
                        print(f"오류 발생: {e}")
                        continue

if __name__ == "__main__":
    import sys
    from datetime import datetime
    
    db_manager = DatabaseManager()
    analyzer = EnhancementAnalyzer(db_manager)
    
    # 전체 분석 실행
    analyzer.run_comprehensive_analysis(trials=10000)