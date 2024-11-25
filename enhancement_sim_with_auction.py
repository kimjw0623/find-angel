from enhancement_simulator import *
from market_price_cache import MarketPriceCache
from item_checker import ItemEvaluator
from database import DatabaseManager
from collections import defaultdict
from typing import Dict, List, Tuple
from datetime import datetime
import sys, os
import numpy as np

class EnhancementStrategyAnalyzer:
    def __init__(self, db_manager: DatabaseManager, debug: bool = False):
        self.simulator = EnhancementSimulator()
        self.price_cache = MarketPriceCache(db_manager, debug=debug)
        self.evaluator = ItemEvaluator(self.price_cache, debug=debug)
        self.debug = debug

    def analyze_single_option_strategy(self, 
                                     acc_type: AccessoryType,
                                     grade: Grade,
                                     option_name: str,
                                     option_grade: OptionGrade,
                                     quality: int = 90,
                                     trials: int = 10000) -> Dict:
        """단일 옵션에 대한 전략 분석"""
        
        # 초기 프리셋 옵션
        preset_options = [(option_name, option_grade)]
        
        # 1. 현재 상태에서의 판매 가치 계산
        base_value = self._calculate_market_value(
            acc_type, grade, quality, preset_options)
        
        # 2. 2연마까지 진행했을 때의 기대값 계산
        enhance_2_result = self._simulate_enhancement(
            acc_type, grade, preset_options, 2, quality, trials)
        
        # 3. 3연마까지 진행했을 때의 기대값 계산
        enhance_3_result = self._simulate_enhancement(
            acc_type, grade, preset_options, 3, quality, trials)
        
        # 4. 새로 시작했을 때의 기대값 계산 (3연마 완료 기준)
        fresh_start_result = self._simulate_fresh_start(
            acc_type, grade, quality, trials)
        
        # 비용 계산
        costs = self._calculate_costs(grade, preset_options)
        
        return {
            'initial_option': f"{option_name}({option_grade.value})",
            'base_value': base_value,
            'enhance_2': enhance_2_result,
            'enhance_3': enhance_3_result,
            'fresh_start': fresh_start_result,
            'costs': costs
        }

    def _calculate_market_value(self, 
                              acc_type: AccessoryType,
                              grade: Grade,
                              quality: int,
                              options: List[Tuple[str, OptionGrade]]) -> int:
        """현재 상태의 시장 가치 계산"""
        market_item = self._create_market_item(acc_type, grade, quality, options)
        evaluation = self.evaluator.evaluate_item(market_item)
        return evaluation['expected_price'] if evaluation else 0

    def _simulate_enhancement(self,
                            acc_type: AccessoryType,
                            grade: Grade,
                            preset_options: List[Tuple[str, OptionGrade]],
                            target_level: int,
                            quality: int,
                            trials: int) -> Dict:
        """지정된 레벨까지 연마했을 때의 결과 시뮬레이션"""
        values = []
        success_count = 0
        
        for _ in range(trials):
            # 프리셋 옵션을 simulator 형식으로 변환
            preset_acc_options = [
                (AccessoryOption(opt_name, opt_grade), EnhancementCost(0, 0))
                for opt_name, opt_grade in preset_options
            ]
            
            try:
                # simulate_enhancement_with_preset 사용
                remaining = target_level - len(preset_options)
                if remaining <= 0:
                    continue
                    
                result = self.simulator.simulate_enhancement_with_preset(
                    acc_type=acc_type,
                    grade=grade,
                    preset_options=preset_acc_options,
                    remaining_count=remaining
                )
                
                # 시장 가치 평가
                all_options = preset_options + [(opt.name, opt.grade) for opt, _ in result]
                value = self._calculate_market_value(acc_type, grade, quality, all_options)
                
                if value > 0:
                    values.append(value)
                    success_count += 1

            except Exception as e:
                if self.debug:
                    print(f"Simulation failed: {e}")
                continue

        if not values:
            return {
                'avg_value': 0,
                'success_rate': 0,
                'min_value': 0,
                'max_value': 0
            }

        return {
            'avg_value': np.mean(values),
            'success_rate': success_count / trials,
            'min_value': np.min(values),
            'max_value': np.max(values)
        }

    def _simulate_fresh_start(self,
                            acc_type: AccessoryType,
                            grade: Grade,
                            quality: int,
                            trials: int) -> Dict:
        """처음부터 새로 시작했을 때의 결과 시뮬레이션"""
        return self._simulate_enhancement(
            acc_type, grade, [], 3, quality, trials)

    def _calculate_costs(self, 
                        grade: Grade,
                        preset_options: List[Tuple[str, OptionGrade]]) -> Dict[str, Dict]:
        """각 전략별 비용 계산"""
        base_costs = self.simulator.ENHANCEMENT_COSTS[grade]
        current_level = len(preset_options)
        
        costs = {
            'enhance_2': {'gold': 0, 'fragments': 0},
            'enhance_3': {'gold': 0, 'fragments': 0},
            'fresh_start': {
                'gold': sum(cost.gold for cost in base_costs),
                'fragments': sum(cost.fragments for cost in base_costs)
            }
        }
        
        # 2연마까지의 비용
        if current_level < 2:
            for i in range(current_level, 2):
                costs['enhance_2']['gold'] += base_costs[i].gold
                costs['enhance_2']['fragments'] += base_costs[i].fragments
                
        # 3연마까지의 비용
        if current_level < 3:
            for i in range(current_level, 3):
                costs['enhance_3']['gold'] += base_costs[i].gold
                costs['enhance_3']['fragments'] += base_costs[i].fragments
        
        return costs

    def _create_market_item(self,
                           acc_type: AccessoryType,
                           grade: Grade,
                           quality: int,
                           options: List[Tuple[str, OptionGrade]]) -> Dict:
        """시장 가치 평가용 아이템 객체 생성"""
        return {
            "Name": f"{grade.value} {acc_type.value}",
            "Grade": grade.value,
            "GradeQuality": quality,
            "AuctionInfo": {
                "BuyPrice": 1000,
                "TradeAllowCount": 2
            },
            "Options": [
                {
                    "OptionName": opt_name,
                    "Value": self._get_option_value(opt_name, opt_grade),
                    "IsValuePercentage": self._is_percentage_option(opt_name)
                }
                for opt_name, opt_grade in options
            ] + [
                {
                    "OptionName": "깨달음",
                    "Value": len(options) + 8,
                    "IsValuePercentage": False
                }
            ]
        }

    def _get_option_value(self, option_name: str, option_grade: OptionGrade) -> float:
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
        return option_values[option_name][option_grade.value]

    def _is_percentage_option(self, option_name: str) -> bool:
        """해당 옵션이 퍼센트 값인지 여부"""
        percentage_options = {
            "추피", "적주피", "공퍼", "무공퍼", "치적", "치피",
            "아덴게이지", "낙인력", "아군회복", "아군보호막", "아공강", "아피강"
        }
        return option_name in percentage_options

    def analyze_all_strategies(self,
                             acc_type: AccessoryType,
                             grade: Grade,
                             quality: int = 90,
                             trials: int = 1000) -> Dict:
        """모든 가능한 옵션 조합에 대한 전략 분석"""
        results = {}
        
        # 해당 부위의 모든 특수 옵션
        special_options = self.simulator.SPECIAL_OPTIONS[acc_type]
        all_options = special_options + self.simulator.COMMON_OPTIONS
        
        for option in all_options:
            option_results = {}
            for grade_option in [OptionGrade.LOW, OptionGrade.MID, OptionGrade.HIGH]:
                result = self.analyze_single_option_strategy(
                    acc_type, grade, option, grade_option, quality, trials)
                option_results[grade_option.value] = result
            results[option] = option_results
            
        return results
    
    def print_analysis_results(self, results: Dict):
            """분석 결과 출력"""
            print("\n=== 전략 분석 결과 ===")
            
            for option_name, grade_results in results.items():
                print(f"\n[{option_name}]")
                print("-" * 80)
                
                for grade, result in grade_results.items():
                    print(f"\n{result['initial_option']}:")
                    print(f"현재 가치: {result['base_value']:,} 골드")
                    
                    # 2연마 결과
                    enhance_2 = result['enhance_2']
                    costs_2 = result['costs']['enhance_2']
                    print("\n2연마 진행 시:")
                    print(f"  평균 가치: {enhance_2['avg_value']:,.0f} 골드")
                    print(f"  성공률: {enhance_2['success_rate']*100:.1f}%")
                    print(f"  비용: {costs_2['gold']:,} 골드 + {costs_2['fragments']} 조각")
                    if enhance_2['avg_value'] > 0:
                        roi_2 = (enhance_2['avg_value'] - result['base_value'] - costs_2['gold']) / \
                            (costs_2['gold'] + costs_2['fragments'] * 100)
                        print(f"  ROI: {roi_2*100:.1f}%")
                    
                    # 3연마 결과
                    enhance_3 = result['enhance_3']
                    costs_3 = result['costs']['enhance_3']
                    print("\n3연마 진행 시:")
                    print(f"  평균 가치: {enhance_3['avg_value']:,.0f} 골드")
                    print(f"  성공률: {enhance_3['success_rate']*100:.1f}%")
                    print(f"  비용: {costs_3['gold']:,} 골드 + {costs_3['fragments']} 조각")
                    if enhance_3['avg_value'] > 0:
                        roi_3 = (enhance_3['avg_value'] - result['base_value'] - costs_3['gold']) / \
                            (costs_3['gold'] + costs_3['fragments'] * 100)
                        print(f"  ROI: {roi_3*100:.1f}%")
                    
                    # 새로 시작
                    fresh = result['fresh_start']
                    costs_fresh = result['costs']['fresh_start']
                    print("\n새로 시작 시:")
                    print(f"  평균 가치: {fresh['avg_value']:,.0f} 골드")
                    print(f"  성공률: {fresh['success_rate']*100:.1f}%")
                    print(f"  비용: {costs_fresh['gold']:,} 골드 + {costs_fresh['fragments']} 조각")
                    if fresh['avg_value'] > 0:
                        roi_fresh = (fresh['avg_value'] - costs_fresh['gold']) / \
                                (costs_fresh['gold'] + costs_fresh['fragments'] * 100)
                        print(f"  ROI: {roi_fresh*100:.1f}%")
                    
                    # 최적 전략 추천
                    print("\n추천 전략:", end=" ")
                    
                    # ROI 계산 (음수 ROI는 -infinity로 처리)
                    roi_2 = (enhance_2['avg_value'] - result['base_value'] - costs_2['gold']) / \
                        (costs_2['gold'] + costs_2['fragments'] * 100) if enhance_2['avg_value'] > 0 else float('-inf')
                        
                    roi_3 = (enhance_3['avg_value'] - result['base_value'] - costs_3['gold']) / \
                        (costs_3['gold'] + costs_3['fragments'] * 100) if enhance_3['avg_value'] > 0 else float('-inf')
                        
                    roi_fresh = (fresh['avg_value'] - costs_fresh['gold']) / \
                            (costs_fresh['gold'] + costs_fresh['fragments'] * 100) if fresh['avg_value'] > 0 else float('-inf')

                    # 각 선택지의 기대 수익
                    profit_current = result['base_value']
                    profit_2 = enhance_2['avg_value'] - costs_2['gold'] - (costs_2['fragments'] * 100)
                    profit_3 = enhance_3['avg_value'] - costs_3['gold'] - (costs_3['fragments'] * 100)
                    profit_fresh = fresh['avg_value'] - costs_fresh['gold'] - (costs_fresh['fragments'] * 100)

                    # 최적 전략 결정
                    best_profit = max(profit_current, profit_2, profit_3, profit_fresh)
                    
                    if best_profit == profit_current:
                        print("현재 상태에서 판매")
                    elif best_profit == profit_2:
                        print("2연마까지 진행")
                    elif best_profit == profit_3:
                        print("3연마까지 진행")
                    else:
                        print("새로 시작")

                    print(f"  예상 수익: {best_profit:,} 골드")

                    
class EnhancementAnalyzer:
    def __init__(self, db_manager: DatabaseManager, debug=False):
        self.simulator = EnhancementSimulator()
        price_cache = MarketPriceCache(db_manager, debug=debug)
        self.evaluator = ItemEvaluator(price_cache, debug=debug)

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

    def _is_percentage_option(self, option_name: str) -> bool:
        """해당 옵션이 퍼센트 값인지 여부"""
        percentage_options = {
            "추피", "적주피", "공퍼", "무공퍼", "치적", "치피",
            "아덴게이지", "낙인력", "아군회복", "아군보호막", "아공강", "아피강"
        }
        return option_name in percentage_options

    def analyze_enhancement_value(self,
                                  acc_type: AccessoryType,
                                  grade: Grade,
                                  trials: int = 10000,
                                  quality: int = 80) -> dict:
        """처음부터 시작하는 연마 가치 분석"""
        print(
            f"\n=== {grade.value} {acc_type.value} 연마 가치 분석 (시도 횟수: {trials:,}) ===")
        results = self.simulator.run_simulation(
            acc_type=acc_type,
            grade=grade,
            trials=trials,
            enhancement_count=3
        )

        return self._analyze_patterns(results, acc_type, grade, quality)

    def analyze_enhancement_value_with_preset(self,
                                              acc_type: AccessoryType,
                                              grade: Grade,
                                              preset_options: List[Tuple[str, OptionGrade]],
                                              trials: int = 10000,
                                              quality: int = 80) -> dict:
        """프리셋 옵션으로 시작하는 연마 가치 분석"""
        print(
            f"\n=== {grade.value} {acc_type.value} 연마 가치 분석 (프리셋: {preset_options}) ===")

        # 남은 연마 횟수 계산
        remaining_enhancements = 3 - len(preset_options)
        if remaining_enhancements <= 0:
            raise ValueError("이미 3연마가 완료된 상태입니다")

        # 프리셋 옵션을 AccessoryOption 객체로 변환
        preset_acc_options = [
            (AccessoryOption(name, grade), EnhancementCost(0, 0))
            for name, grade in preset_options
        ]

        results = []
        for _ in range(trials):
            # 프리셋 옵션으로 시작하는 시뮬레이션 실행
            trial_result = self.simulator.simulate_enhancement_with_preset(
                acc_type=acc_type,
                grade=grade,
                preset_options=preset_acc_options,
                remaining_count=remaining_enhancements
            )
            results.append(preset_acc_options + trial_result)

        return self._analyze_patterns(results, acc_type, grade, quality)

    def _analyze_patterns(self, results: List[List[Tuple[AccessoryOption, EnhancementCost]]], 
                            acc_type: AccessoryType,
                            grade: Grade,
                            quality: int) -> dict:
            """특수 옵션 위주로 패턴 분석"""
            dealer_stats = defaultdict(lambda: {
                'values': [],
                'min_item': None,
                'max_item': None,
                'min_value': float('inf'),
                'max_value': -float('inf')
            })
            support_stats = defaultdict(lambda: {
                'values': [],
                'min_item': None,
                'max_item': None,
                'min_value': float('inf'),
                'max_value': -float('inf')
            })
            
            for trial in results:
                # 특수 옵션만 추출
                special_options = [
                    (opt.name, opt.grade.value)
                    for opt, _ in trial
                    if self._is_special_option(opt.name, acc_type)
                ]
                
                # 시장 가격 평가 위한 아이템 생성
                market_item = self.convert_to_market_item(acc_type, grade, quality, trial)
                evaluation = self.evaluator.evaluate_item(market_item)
                if not evaluation:
                    continue
                    
                # 모든 옵션 정보 문자열 생성
                all_options = [
                    f"{opt.name}({opt.grade.value})"
                    for opt, _ in trial
                ]
                
                # 딜러/서포터 구분하여 통계 저장
                pattern_key = tuple(sorted(special_options))
                expected_price = evaluation['expected_price']
                
                if self._is_dealer_pattern(special_options, acc_type):
                    stats = dealer_stats[pattern_key]
                    stats['values'].append(expected_price)
                    
                    # 최소값 업데이트
                    if expected_price < stats['min_value']:
                        stats['min_value'] = expected_price
                        stats['min_item'] = {
                            'options': all_options,
                            'details': evaluation
                        }
                    
                    # 최대값 업데이트
                    if expected_price > stats['max_value']:
                        stats['max_value'] = expected_price
                        stats['max_item'] = {
                            'options': all_options,
                            'details': evaluation
                        }
                        
                elif self._is_support_pattern(special_options, acc_type):
                    stats = support_stats[pattern_key]
                    stats['values'].append(expected_price)
                    
                    # 최소값 업데이트
                    if expected_price < stats['min_value']:
                        stats['min_value'] = expected_price
                        stats['min_item'] = {
                            'options': all_options,
                            'details': evaluation
                        }
                    
                    # 최대값 업데이트
                    if expected_price > stats['max_value']:
                        stats['max_value'] = expected_price
                        stats['max_item'] = {
                            'options': all_options,
                            'details': evaluation
                        }

            # 최종 통계 계산
            return {
                'dealer': self._calculate_pattern_stats(dealer_stats),
                'support': self._calculate_pattern_stats(support_stats)
            }

    def _is_special_option(self, option_name: str, acc_type: AccessoryType) -> bool:
        """특수 옵션인지 확인"""
        special_options = {
            AccessoryType.NECKLACE: ["추피", "적주피", "아덴게이지", "낙인력"],
            AccessoryType.EARRING: ["공퍼", "무공퍼", "아군회복", "아군보호막"],
            AccessoryType.RING: ["치적", "치피", "아공강", "아피강"]
        }
        return option_name in special_options[acc_type]

    def _is_dealer_pattern(self, options: List[Tuple[str, str]], acc_type: AccessoryType) -> bool:
        """딜러 패턴인지 확인"""
        dealer_options = {
            AccessoryType.NECKLACE: ["추피", "적주피"],
            AccessoryType.EARRING: ["공퍼", "무공퍼"],
            AccessoryType.RING: ["치적", "치피"]
        }
        return any(opt[0] in dealer_options[acc_type] for opt in options)

    def _is_support_pattern(self, options: List[Tuple[str, str]], acc_type: AccessoryType) -> bool:
        """서포터 패턴인지 확인"""
        support_options = {
            AccessoryType.NECKLACE: ["아덴게이지", "낙인력"],
            AccessoryType.EARRING: ["무공퍼"],
            AccessoryType.RING: ["아공강", "아피강"]
        }
        return any(opt[0] in support_options[acc_type] for opt in options)

    def _calculate_pattern_stats(self, pattern_stats: Dict[tuple, dict]) -> Dict[tuple, dict]:
        """패턴별 통계 계산"""
        results = {}
        for pattern, stats in pattern_stats.items():
            if stats['values']:
                values = stats['values']
                results[pattern] = {
                    'count': len(values),
                    'avg_value': sum(values) / len(values),
                    'min_value': stats['min_value'],
                    'max_value': stats['max_value'],
                    'std_dev': np.std(values) if len(values) > 1 else 0,
                    'min_item': stats['min_item'],
                    'max_item': stats['max_item']
                }
        return results

    def print_analysis_results(self, results: dict):
        """분석 결과 출력"""
        print("\n=== 연마 가치 분석 결과 ===")
        
        # 딜러 패턴 출력
        if results['dealer']:
            print("\n[딜러 패턴]")
            print("-" * 80)
            sorted_patterns = sorted(
                results['dealer'].items(),
                key=lambda x: x[1]['avg_value'],
                reverse=True
            )
            for pattern, stats in sorted_patterns:
                pattern_str = ' + '.join(f"{opt}({grade})" for opt, grade in pattern)
                print(f"\n패턴: {pattern_str}")
                print(f"발생 횟수: {stats['count']:,}")
                print(f"평균 가치: {stats['avg_value']:,.0f} 골드")
                print(f"가치 범위: {stats['min_value']:,.0f} ~ {stats['max_value']:,.0f} 골드")
                
                # 최소 가치 아이템 정보
                print(f"\n  최소 가치 아이템:")
                print(f"  전체 옵션: {' + '.join(stats['min_item']['options'])}")
                print(f"  예상 가격: {stats['min_item']['details']['expected_price']:,} 골드")
                if 'dealer_price' in stats['min_item']['details']:
                    print(f"  딜러가: {stats['min_item']['details']['dealer_price']:,} 골드")
                if 'support_price' in stats['min_item']['details']:
                    print(f"  서폿가: {stats['min_item']['details']['support_price']:,} 골드")
                
                # 최대 가치 아이템 정보
                print(f"\n  최대 가치 아이템:")
                print(f"  전체 옵션: {' + '.join(stats['max_item']['options'])}")
                print(f"  예상 가격: {stats['max_item']['details']['expected_price']:,} 골드")
                if 'dealer_price' in stats['max_item']['details']:
                    print(f"  딜러가: {stats['max_item']['details']['dealer_price']:,} 골드")
                if 'support_price' in stats['max_item']['details']:
                    print(f"  서폿가: {stats['max_item']['details']['support_price']:,} 골드")
                
        # 서포터 패턴 출력
        if results['support']:
            print("\n[서포터 패턴]")
            print("-" * 80)
            sorted_patterns = sorted(
                results['support'].items(),
                key=lambda x: x[1]['avg_value'],
                reverse=True
            )
            for pattern, stats in sorted_patterns:
                pattern_str = ' + '.join(f"{opt}({grade})" for opt, grade in pattern)
                print(f"\n패턴: {pattern_str}")
                print(f"발생 횟수: {stats['count']:,}")
                print(f"평균 가치: {stats['avg_value']:,.0f} 골드")
                print(f"가치 범위: {stats['min_value']:,.0f} ~ {stats['max_value']:,.0f} 골드")
                
                # 최소 가치 아이템 정보
                print(f"\n  최소 가치 아이템:")
                print(f"  전체 옵션: {' + '.join(stats['min_item']['options'])}")
                print(f"  예상 가격: {stats['min_item']['details']['expected_price']:,} 골드")
                if 'dealer_price' in stats['min_item']['details']:
                    print(f"  딜러가: {stats['min_item']['details']['dealer_price']:,} 골드")
                if 'support_price' in stats['min_item']['details']:
                    print(f"  서폿가: {stats['min_item']['details']['support_price']:,} 골드")
                
                # 최대 가치 아이템 정보
                print(f"\n  최대 가치 아이템:")
                print(f"  전체 옵션: {' + '.join(stats['max_item']['options'])}")
                print(f"  예상 가격: {stats['max_item']['details']['expected_price']:,} 골드")
                if 'dealer_price' in stats['max_item']['details']:
                    print(f"  딜러가: {stats['max_item']['details']['dealer_price']:,} 골드")
                if 'support_price' in stats['max_item']['details']:
                    print(f"  서폿가: {stats['max_item']['details']['support_price']:,} 골드")

        print("\n=== 최종 통계 ===")
        print("-" * 50)
        
        # 모든 시도의 평균 가치 계산
        total_count = sum(stats['count'] for stats in results['dealer'].values()) + \
                    sum(stats['count'] for stats in results['support'].values())
        
        total_value = sum(stats['avg_value'] * stats['count'] for stats in results['dealer'].values()) + \
                    sum(stats['avg_value'] * stats['count'] for stats in results['support'].values())
        
        if total_count > 0:
            avg_value = total_value / total_count
            print(f"시뮬레이션 횟수: {total_count:,}")
            print(f"평균 예상 가치: {avg_value:,.0f} 골드")

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
                "BuyPrice": 1000,  # 가격 평가용이므로 임의의 값
                "TradeAllowCount": 2  # 기본값
            },
            "Options": [
                {
                    "OptionName": option.name,
                    "Value": self._get_option_value(option),
                    "IsValuePercentage": self._is_percentage_option(option.name)
                }
                for option, _ in enhanced_options
            ] +  [
                {
                    "OptionName": "깨달음",
                    "Value": 999.0, 
                    "IsValuePercentage": False
                }
            ]
        }


def run_simulation_test():
    db_manager = DatabaseManager()
    analyzer = EnhancementAnalyzer(db_manager, debug=False)

    # 테스트할 설정들
    test_cases = [
        # 목걸이 프리셋 테스트
        {
            'type': AccessoryType.NECKLACE,
            'grade': Grade.ANCIENT,
            'preset': [("추피", OptionGrade.LOW)],
            'desc': "고대 목걸이 (추피 하옵 시작)"
        },
        {
            'type': AccessoryType.NECKLACE,
            'grade': Grade.ANCIENT,
            'preset': [("아덴게이지", OptionGrade.MID)],
            'desc': "고대 목걸이 (아덴 중옵 시작)"
        },
        # 귀걸이 프리셋 테스트
        {
            'type': AccessoryType.EARRING,
            'grade': Grade.ANCIENT,
            'preset': [("공퍼", OptionGrade.HIGH)],
            'desc': "고대 귀걸이 (공퍼 상옵 시작)"
        },
        # 반지 프리셋 테스트
        {
            'type': AccessoryType.RING,
            'grade': Grade.ANCIENT,
            'preset': [("치적", OptionGrade.MID)],
            'desc': "고대 반지 (치적 중옵 시작)"
        },
    ]

    # 각 테스트 케이스 실행
    for case in test_cases:
        print(f"\n{'='*80}")
        print(f"테스트 케이스: {case['desc']}")
        print(f"{'='*80}")

        try:
            results = analyzer.analyze_enhancement_value_with_preset(
                acc_type=case['type'],
                grade=case['grade'],
                preset_options=case['preset'],
                trials=10000,
                quality=90
            )

            analyzer.print_analysis_results(results)

            # 결과를 파일로도 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sim_result/preset_analysis_{case['grade'].value}_{case['type'].value}_{timestamp}.txt"

            with open(filename, 'w', encoding='utf-8') as f:
                # 원래 stdout을 저장
                original_stdout = sys.stdout
                # stdout을 파일로 변경
                sys.stdout = f

                print(f"\n=== {case['desc']} 분석 결과 ===")
                print(f"분석 시간: {datetime.now()}")
                print(f"시뮬레이션 횟수: 10,000")
                analyzer.print_analysis_results(results)

                # stdout 복구
                sys.stdout = original_stdout

            print(f"\n분석 결과가 {filename}에 저장되었습니다.")

        except Exception as e:
            print(f"오류 발생: {e}")
            continue


def run_default_simulation_test():
    """프리셋 없이 처음부터 시작하는 시뮬레이션"""
    db_manager = DatabaseManager()
    analyzer = EnhancementAnalyzer(db_manager)

    test_cases = [
        {
            'type': AccessoryType.NECKLACE,
            'grade': Grade.ANCIENT,
            'desc': "고대 목걸이 (기본)"
        },
        {
            'type': AccessoryType.EARRING,
            'grade': Grade.ANCIENT,
            'desc': "고대 귀걸이 (기본)"
        },
        {
            'type': AccessoryType.RING,
            'grade': Grade.ANCIENT,
            'desc': "고대 반지 (기본)"
        },
    ]

    for case in test_cases:
        print(f"\n{'='*80}")
        print(f"테스트 케이스: {case['desc']}")
        print(f"{'='*80}")

        try:
            results = analyzer.analyze_enhancement_value(
                acc_type=case['type'],
                grade=case['grade'],
                trials=10000,
                quality=90
            )

            analyzer.print_analysis_results(results)

            # 결과를 파일로도 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sim_result/default_analysis_{case['grade'].value}_{case['type'].value}_{timestamp}.txt"

            with open(filename, 'w', encoding='utf-8') as f:
                original_stdout = sys.stdout
                sys.stdout = f

                print(f"\n=== {case['desc']} 분석 결과 ===")
                print(f"분석 시간: {datetime.now()}")
                print(f"시뮬레이션 횟수: 10,000")
                analyzer.print_analysis_results(results)

                sys.stdout = original_stdout

            print(f"\n분석 결과가 {filename}에 저장되었습니다.")

        except Exception as e:
            print(f"오류 발생: {e}")
            continue


def main():
    db_manager = DatabaseManager()
    analyzer = EnhancementStrategyAnalyzer(db_manager, debug=False)

    test_cases = [
        (AccessoryType.NECKLACE, Grade.ANCIENT, "고대 목걸이"),
        (AccessoryType.EARRING, Grade.ANCIENT, "고대 귀걸이"),
        (AccessoryType.RING, Grade.ANCIENT, "고대 반지"),
        (AccessoryType.NECKLACE, Grade.RELIC, "유물 목걸이"),
        (AccessoryType.EARRING, Grade.RELIC, "유물 귀걸이"),
        (AccessoryType.RING, Grade.RELIC, "유물 반지"),
    ]

    while True:
        print("\n=== 연마 전략 분석기 ===")
        print("1. 고대 목걸이 분석")
        print("2. 고대 귀걸이 분석")
        print("3. 고대 반지 분석")
        print("4. 유물 목걸이 분석")
        print("5. 유물 귀걸이 분석")
        print("6. 유물 반지 분석")
        print("7. 종료")

        choice = input("\n분석할 아이템을 선택하세요 (1-7): ")
        if choice == "7":
            break

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(test_cases):
                acc_type, grade, desc = test_cases[idx]
                
                print(f"\n{desc} 분석을 시작합니다...")
                print("(기본 품질 90, 시뮬레이션 10000회 기준)")
                
                # 분석 실행
                results = analyzer.analyze_all_strategies(
                    acc_type=acc_type,
                    grade=grade,
                    quality=90,
                    trials=10000
                )

                # 결과 출력
                analyzer.print_analysis_results(results)

                # 파일로도 저장
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"enhancement_analysis_{grade.value}_{acc_type.value}_{timestamp}.txt"

                with open(filename, 'w', encoding='utf-8') as f:
                    original_stdout = sys.stdout
                    sys.stdout = f

                    print(f"\n=== {desc} 분석 결과 ===")
                    print(f"분석 시간: {datetime.now()}")
                    print(f"시뮬레이션 횟수: 1,000")
                    analyzer.print_analysis_results(results)

                    sys.stdout = original_stdout

                print(f"\n분석 결과가 {filename}에 저장되었습니다.")

            else:
                print("잘못된 선택입니다.")

        except Exception as e:
            print(f"분석 중 오류 발생: {e}")
            if analyzer.debug:
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    main()