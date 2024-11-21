from enhancement_simulator import *
from collections import defaultdict
from itertools import combinations

def analyze_option_patterns(results: List[List[Tuple[AccessoryOption, EnhancementCost]]], 
                          dealer_options: List[str],
                          support_options: List[str],
                          trials: int):
    """딜러/서포터 옵션을 구분하여 패턴 분석"""
    # 유효한 패턴 생성
    valid_patterns = []
    
    # 딜러 옵션 패턴 (1개 또는 2개 조합)
    for r in range(1, min(3, len(dealer_options) + 1)):
        valid_patterns.extend(combinations(dealer_options, r))
    
    # 서포터 옵션 패턴 (1개 또는 2개 조합)
    for r in range(1, min(3, len(support_options) + 1)):
        valid_patterns.extend(combinations(support_options, r))
    
    pattern_stats = {}
    for pattern in valid_patterns:
        # 패턴이 나온 횟수
        pattern_count = 0
        # 패턴의 등급 분포
        grade_distributions = defaultdict(int)
        
        for trial in results:
            trial_options = [option for option, _ in trial]
            trial_option_names = [option.name for option in trial_options]
            
            # 패턴의 모든 옵션이 포함되어 있고,
            # 다른 특수 옵션(같은 역할군의)은 포함되지 않은 경우를 체크
            all_role_options = (dealer_options if pattern[0] in dealer_options 
                              else support_options)
            other_role_options = [opt for opt in all_role_options if opt not in pattern]
            
            if (all(opt in trial_option_names for opt in pattern) and
                not any(opt in trial_option_names for opt in other_role_options)):
                pattern_count += 1
                
                # 해당 옵션들의 등급 조합 기록
                grades = []
                for opt_name in pattern:
                    opt = next(o for o in trial_options if o.name == opt_name)
                    grades.append(opt.grade.value)
                grade_distributions[tuple(sorted(grades))] += 1
        
        if pattern_count > 0:
            pattern_stats[pattern] = {
                'count': pattern_count,
                'percentage': (pattern_count / trials) * 100,
                'is_dealer': pattern[0] in dealer_options,
                'grade_distributions': {
                    grades: {
                        'count': count,
                        'percentage': (count / pattern_count) * 100
                    }
                    for grades, count in grade_distributions.items()
                }
            }
    
    return pattern_stats

def run_detailed_analysis(acc_type: AccessoryType, grade: Grade, trials: int = 1000):
    """상세 분석 실행"""
    simulator = EnhancementSimulator()
    
    print(f"\n=== {grade.value} {acc_type.value} 상세 분석 ({trials:,}회 시도) ===")
    
    # 시뮬레이션 실행
    results = simulator.run_simulation(
        acc_type=acc_type,
        grade=grade,
        trials=trials,
        enhancement_count=3
    )
    
    # 부위별 딜러/서포터 옵션 정의
    options_by_role = {
        AccessoryType.NECKLACE: {
            "dealer": ["추피", "적주피"],
            "support": ["아덴게이지", "낙인력"]
        },
        AccessoryType.EARRING: {
            "dealer": ["공퍼", "무공퍼"],
            "support": ["아군회복", "아군보호막"]
        },
        AccessoryType.RING: {
            "dealer": ["치적", "치피"],
            "support": ["아공강", "아피강"]
        }
    }[acc_type]
    
    # 패턴 분석
    pattern_stats = analyze_option_patterns(
        results, 
        options_by_role["dealer"],
        options_by_role["support"],
        trials
    )
    
    # 결과 출력 (딜러/서포터 구분하여)
    print("\n딜러 옵션 패턴:")
    print("-" * 50)
    # 딜러 패턴 출력 (빈도 내림차순)
    dealer_patterns = sorted(
        [(p, s) for p, s in pattern_stats.items() if s['is_dealer']],
        key=lambda x: (-x[1]['count'], len(x[0]))
    )
    for pattern, stats in dealer_patterns:
        pattern_name = ' + '.join(pattern)
        print(f"\n{pattern_name}:")
        print(f"발생 횟수: {stats['count']:,}회 ({stats['percentage']:.1f}%)")
        
        print("등급 분포:")
        sorted_grades = sorted(
            stats['grade_distributions'].items(),
            key=lambda x: -x[1]['count']
        )
        for grades, grade_stats in sorted_grades:
            grade_pattern = ' + '.join(grades)
            print(f"  {grade_pattern}: {grade_stats['count']:,}회 ({grade_stats['percentage']:.1f}%)")
    
    print("\n서포터 옵션 패턴:")
    print("-" * 50)
    # 서포터 패턴 출력 (빈도 내림차순)
    support_patterns = sorted(
        [(p, s) for p, s in pattern_stats.items() if not s['is_dealer']],
        key=lambda x: (-x[1]['count'], len(x[0]))
    )
    for pattern, stats in support_patterns:
        pattern_name = ' + '.join(pattern)
        print(f"\n{pattern_name}:")
        print(f"발생 횟수: {stats['count']:,}회 ({stats['percentage']:.1f}%)")
        
        print("등급 분포:")
        sorted_grades = sorted(
            stats['grade_distributions'].items(),
            key=lambda x: -x[1]['count']
        )
        for grades, grade_stats in sorted_grades:
            grade_pattern = ' + '.join(grades)
            print(f"  {grade_pattern}: {grade_stats['count']:,}회 ({grade_stats['percentage']:.1f}%)")

if __name__ == "__main__":
    # 유물 목걸이 분석
    run_detailed_analysis(
        acc_type=AccessoryType.NECKLACE,
        grade=Grade.RELIC,
        trials=1000000
    )