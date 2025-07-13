from src.core.enhancement_simulator import *
from src.core.market_price_cache import DBMarketPriceCache
from src.core.item_evaluator import ItemEvaluator
from src.database.raw_database import *
from collections import defaultdict
from typing import Dict, List, Tuple
from datetime import datetime
import sys, os
import numpy as np

class EnhancementStrategyAnalyzer:
    def __init__(self, db_manager: RawDatabaseManager, debug: bool = False):
        self.analyzer = EnhancementAnalyzer(db_manager, debug)
        self.simulator = EnhancementSimulator()
        self.debug = debug

    def analyze_single_enhancement_strategy(self,
                                         acc_type: AccessoryType,
                                         grade: Grade,
                                         quality: int = 90,
                                         trials: int = 10000) -> Dict:
        """0->1 연마 전략 분석"""
        print(f"\n=== {grade.value} {acc_type.value} 0->1 연마 분석 (시도 횟수: {trials:,}) ===")
        
        results = self.simulator.run_simulation(
            acc_type=acc_type,
            grade=grade,
            trials=trials,
            enhancement_count=1
        )
        
        return self.analyzer._analyze_patterns(results, acc_type, grade, quality)

    def analyze_full_enhancement_strategy(self, 
                                       acc_type: AccessoryType,
                                       grade: Grade,
                                       quality: int = 90,
                                       trials: int = 10000) -> Dict:
        """0->3 연마 전략 분석"""
        print(f"\n=== {grade.value} {acc_type.value} 0->3 연마 분석 (시도 횟수: {trials:,}) ===")
        
        results = self.simulator.run_simulation(
            acc_type=acc_type,
            grade=grade,
            trials=trials,
            enhancement_count=3
        )
        
        return self.analyzer._analyze_patterns(results, acc_type, grade, quality)

    def analyze_partial_enhancement_strategy(self,
                                          acc_type: AccessoryType,
                                          grade: Grade,
                                          preset_options: List[Tuple[str, OptionGrade]],
                                          quality: int = 90,
                                          trials: int = 10000) -> Dict:
        """1->3 연마 전략 분석"""
        print(f"\n=== {grade.value} {acc_type.value} 1->3 연마 분석 (프리셋: {preset_options}) ===")

        preset_acc_options = [
            (AccessoryOption(name, grade), EnhancementCost(0, 0))
            for name, grade in preset_options
        ]

        remaining_enhancements = 3 - len(preset_options)
        results = []
        
        for _ in range(trials):
            trial_result = self.simulator.simulate_enhancement_with_preset(
                acc_type=acc_type,
                grade=grade,
                preset_options=preset_acc_options,
                remaining_count=remaining_enhancements
            )
            results.append(preset_acc_options + trial_result)

        return self.analyzer._analyze_patterns(results, acc_type, grade, quality)
    
class EnhancementAnalyzer:
    def __init__(self, db_manager: RawDatabaseManager, debug: bool = False):
        self.debug = debug
        self.price_cache = DBMarketPriceCache(db_manager, debug=debug)
        self.evaluator = ItemEvaluator(self.price_cache, debug=debug)

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

    def print_analysis_results(self, results: Dict):
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
                
                print(f"\n  최소 가치 아이템:")
                print(f"  전체 옵션: {' + '.join(stats['min_item']['options'])}")
                print(f"  예상 가격: {stats['min_item']['details']['expected_price']:,} 골드")
                if 'dealer_price' in stats['min_item']['details']:
                    print(f"  딜러가: {stats['min_item']['details']['dealer_price']:,} 골드")
                if 'support_price' in stats['min_item']['details']:
                    print(f"  서폿가: {stats['min_item']['details']['support_price']:,} 골드")
                
                print(f"\n  최대 가치 아이템:")
                print(f"  전체 옵션: {' + '.join(stats['max_item']['options'])}")
                print(f"  예상 가격: {stats['max_item']['details']['expected_price']:,} 골드")
                if 'dealer_price' in stats['max_item']['details']:
                    print(f"  딜러가: {stats['max_item']['details']['dealer_price']:,} 골드")
                if 'support_price' in stats['max_item']['details']:
                    print(f"  서폿가: {stats['max_item']['details']['support_price']:,} 골드")
        
        # 서포터 패턴 출력 (위와 동일한 형식)
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
                
                print(f"\n  최소 가치 아이템:")
                print(f"  전체 옵션: {' + '.join(stats['min_item']['options'])}")
                print(f"  예상 가격: {stats['min_item']['details']['expected_price']:,} 골드")
                if 'dealer_price' in stats['min_item']['details']:
                    print(f"  딜러가: {stats['min_item']['details']['dealer_price']:,} 골드")
                if 'support_price' in stats['min_item']['details']:
                    print(f"  서폿가: {stats['min_item']['details']['support_price']:,} 골드")
                
                print(f"\n  최대 가치 아이템:")
                print(f"  전체 옵션: {' + '.join(stats['max_item']['options'])}")
                print(f"  예상 가격: {stats['max_item']['details']['expected_price']:,} 골드")
                if 'dealer_price' in stats['max_item']['details']:
                    print(f"  딜러가: {stats['max_item']['details']['dealer_price']:,} 골드")
                if 'support_price' in stats['max_item']['details']:
                    print(f"  서폿가: {stats['max_item']['details']['support_price']:,} 골드")

        # 최종 통계
        print("\n=== 최종 통계 ===")
        print("-" * 50)
        
        total_count = sum(stats['count'] for stats in results['dealer'].values()) + \
                     sum(stats['count'] for stats in results['support'].values())
        
        total_value = sum(stats['avg_value'] * stats['count'] for stats in results['dealer'].values()) + \
                     sum(stats['avg_value'] * stats['count'] for stats in results['support'].values())
        
        if total_count > 0:
            avg_value = total_value / total_count
            print(f"시뮬레이션 횟수: {total_count:,}")
            print(f"평균 예상 가치: {avg_value:,.0f} 골드")

    def _analyze_patterns(self, results: List[List[Tuple[AccessoryOption, EnhancementCost]]], 
                        acc_type: AccessoryType,
                        grade: Grade,
                        quality: int) -> Dict:
        """
        모든 연마 결과를 분석하고, 패턴별로 분류
        """
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
            # 모든 옵션을 패턴 키로 사용
            pattern_key = tuple(sorted(
                (opt.name, opt.grade.value)
                for opt, _ in trial
            ))
            
            # 시장 가격 평가를 위한 아이템 생성
            market_item = self.convert_to_market_item(acc_type, grade, quality, trial)
            evaluation = self.evaluator.evaluate_item(market_item)
            if not evaluation:
                continue
                
            # 모든 옵션 정보 문자열 생성
            all_options = [
                f"{opt.name}({opt.grade.value})"
                for opt, _ in trial
            ]
            
            expected_price = evaluation['expected_price']
            
            # 딜러/서포터 구분하여 통계 저장
            has_dealer_options = any(self._is_special_option(opt.name, acc_type) and 
                                self._is_dealer_pattern([(opt.name, opt.grade.value)], acc_type)
                                for opt, _ in trial)
            has_support_options = any(self._is_special_option(opt.name, acc_type) and 
                                    self._is_support_pattern([(opt.name, opt.grade.value)], acc_type)
                                    for opt, _ in trial)
            
            if has_dealer_options or (not has_dealer_options and not has_support_options):
                stats = dealer_stats[pattern_key]
                stats['values'].append(expected_price)
                
                if expected_price < stats['min_value']:
                    stats['min_value'] = expected_price
                    stats['min_item'] = {
                        'options': all_options,
                        'details': evaluation
                    }
                
                if expected_price > stats['max_value']:
                    stats['max_value'] = expected_price
                    stats['max_item'] = {
                        'options': all_options,
                        'details': evaluation
                    }
                    
            elif has_support_options:
                stats = support_stats[pattern_key]
                stats['values'].append(expected_price)
                
                if expected_price < stats['min_value']:
                    stats['min_value'] = expected_price
                    stats['min_item'] = {
                        'options': all_options,
                        'details': evaluation
                    }
                
                if expected_price > stats['max_value']:
                    stats['max_value'] = expected_price
                    stats['max_item'] = {
                        'options': all_options,
                        'details': evaluation
                    }

        return {
            'dealer': self._calculate_pattern_stats(dealer_stats),
            'support': self._calculate_pattern_stats(support_stats)
        }

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

    def convert_to_market_item(self,
                                acc_type: AccessoryType,
                                grade: Grade,
                                quality: int,
                                enhanced_options: List[Tuple[AccessoryOption, EnhancementCost]]) -> Dict:
            """시뮬레이션 결과를 가격 평가 시스템용 형식으로 변환"""
            return {
                "Name": f"{grade.value} {acc_type.value}",
                "Grade": grade.value,
                "GradeQuality": quality,
                "AuctionInfo": {
                    "BuyPrice": 1,  # 가격 평가용이므로 임의의 값
                    "TradeAllowCount": 2  # 기본값
                },
                "Options": [
                    {
                        "OptionName": option.name,
                        "Value": self._get_option_value(option.name, option.grade),
                        "IsValuePercentage": self._is_percentage_option(option.name)
                    }
                    for option, _ in enhanced_options
                ] + [
                    {
                        "OptionName": "깨달음",
                        "Value": len(enhanced_options) + 8,  # 기본값 8에 옵션 개수를 더함
                        "IsValuePercentage": False
                    }
                ]
            }

def main():
    db_manager = RawDatabaseManager()
    analyzer = EnhancementStrategyAnalyzer(db_manager, debug=False)

    test_cases = [
        # 0->1 연마 분석 케이스
        [(AccessoryType.NECKLACE, Grade.ANCIENT, None, "고대 목걸이 (0->1)"),
         (AccessoryType.EARRING, Grade.ANCIENT, None, "고대 귀걸이 (0->1)"),
         (AccessoryType.RING, Grade.ANCIENT, None, "고대 반지 (0->1)"),
         (AccessoryType.NECKLACE, Grade.RELIC, None, "유물 목걸이 (0->1)"),
         (AccessoryType.EARRING, Grade.RELIC, None, "유물 귀걸이 (0->1)"),
         (AccessoryType.RING, Grade.RELIC, None, "유물 반지 (0->1)")],
         
        # 0->3 연마 분석 케이스
        [(AccessoryType.NECKLACE, Grade.ANCIENT, None, "고대 목걸이 (0->3)"),
         (AccessoryType.EARRING, Grade.ANCIENT, None, "고대 귀걸이 (0->3)"),
         (AccessoryType.RING, Grade.ANCIENT, None, "고대 반지 (0->3)"),
         (AccessoryType.NECKLACE, Grade.RELIC, None, "유물 목걸이 (0->3)"),
         (AccessoryType.EARRING, Grade.RELIC, None, "유물 귀걸이 (0->3)"),
         (AccessoryType.RING, Grade.RELIC, None, "유물 반지 (0->3)")],
         
        # 1->3 연마 분석 케이스 (프리셋 필요)
        [(AccessoryType.NECKLACE, Grade.ANCIENT, [("추피", OptionGrade.HIGH)], "고대 목걸이 (1->3)"),
         (AccessoryType.EARRING, Grade.ANCIENT, [("공퍼", OptionGrade.LOW)], "고대 귀걸이 (1->3)"),
         (AccessoryType.RING, Grade.ANCIENT, [("치적", OptionGrade.LOW)], "고대 반지 (1->3)"),
         (AccessoryType.NECKLACE, Grade.RELIC, [("추피", OptionGrade.LOW)], "유물 목걸이 (1->3)"),
         (AccessoryType.EARRING, Grade.RELIC, [("공퍼", OptionGrade.LOW)], "유물 귀걸이 (1->3)"),
         (AccessoryType.RING, Grade.RELIC, [("치적", OptionGrade.LOW)], "유물 반지 (1->3)")]
    ]

    while True:
        print("\n=== 연마 전략 분석기 ===")
        print("\n[0->1 연마 분석]")
        for i in range(6):
            print(f"{i+1}. {test_cases[0][i][3]}")
            
        print("\n[0->3 연마 분석]")
        for i in range(6):
            print(f"{i+7}. {test_cases[1][i][3]}")
            
        print("\n[1->3 연마 분석]")
        for i in range(6):
            print(f"{i+13}. {test_cases[2][i][3]}")
            
        print("\n19. 종료")

        choice = input("\n분석할 아이템을 선택하세요 (1-19): ")
        if choice == "19":
            break

        try:
            idx = int(choice) - 1
            category = idx // 6  # 0: 0->1, 1: 0->3, 2: 1->3
            item_idx = idx % 6
            
            if 0 <= idx < 18:
                acc_type, grade, preset, desc = test_cases[category][item_idx]
                
                print(f"\n{desc} 분석을 시작합니다...")
                print("(기본 품질 90, 시뮬레이션 10000회 기준)")
                
                # 분석 방법 선택
                if category == 0:  # 0->1 연마
                    results = analyzer.analyze_single_enhancement_strategy(
                        acc_type=acc_type,
                        grade=grade,
                        quality=90,
                        trials=10000
                    )
                elif category == 1:  # 0->3 연마
                    results = analyzer.analyze_full_enhancement_strategy(
                        acc_type=acc_type,
                        grade=grade,
                        quality=90,
                        trials=10000
                    )
                else:  # 1->3 연마
                    results = analyzer.analyze_partial_enhancement_strategy(
                        acc_type=acc_type,
                        grade=grade,
                        preset_options=preset,
                        quality=90,
                        trials=10000
                    )

                # 결과 출력
                analyzer.analyzer.print_analysis_results(results)

                # 파일로 저장
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                enhancement_type = ["0to1", "0to3", "1to3"][category]
                filename = f"sim_result/enhancement_analysis_{enhancement_type}_{grade.value}_{acc_type.value}_{timestamp}.txt"

                with open(filename, 'w', encoding='utf-8') as f:
                    original_stdout = sys.stdout
                    sys.stdout = f

                    print(f"\n=== {desc} 분석 결과 ===")
                    print(f"분석 시간: {datetime.now()}")
                    print(f"시뮬레이션 횟수: 10,000")
                    analyzer.analyzer.print_analysis_results(results)

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