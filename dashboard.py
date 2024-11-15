import streamlit as st
import pandas as pd
import plotly.express as px
from database import DatabaseManager
from datetime import datetime, timedelta

# streamlit run dashboard.py
def load_data(session, time_range='1d'):
    # 시간 범위에 따른 쿼리 조건 설정
    if time_range == '1d':
        time_limit = datetime.now() - timedelta(days=1)
    elif time_range == '1w':
        time_limit = datetime.now() - timedelta(weeks=1)
    elif time_range == '1m':
        time_limit = datetime.now() - timedelta(days=30)
    else:  # all
        time_limit = datetime(2000, 1, 1)

    query = f"""
    SELECT 
        pr.timestamp,
        pr.grade,
        pr.name,
        pr.part,
        pr.level,
        pr.quality,
        pr.trade_count,
        pr.price,
        GROUP_CONCAT(io.option_name || ' ' || io.option_grade) as options
    FROM price_records pr
    LEFT JOIN item_options io ON pr.id = io.price_record_id
    WHERE pr.timestamp > '{time_limit}'
    GROUP BY pr.id
    """
    df = pd.read_sql(query, session.bind)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def run_dashboard():
    st.title('T4 악세서리 시장 분석')
    
    # 탭 생성
    tab_accessory, tab_bracelet = st.tabs(['악세서리', '팔찌'])
    
    with tab_accessory:
        display_accessory_dashboard()
        
    with tab_bracelet:
        display_bracelet_dashboard()

def display_accessory_dashboard():
    # 기존 악세서리 대시보드 코드
    st.header('악세서리 시장 분석')
    db = DatabaseManager()
    
    # 사이드바 필터
    st.sidebar.header('필터')
    time_range = st.sidebar.selectbox(
        '시간 범위',
        ['1d', '1w', '1m', 'all'],
        format_func=lambda x: {
            '1d': '1일',
            '1w': '1주일',
            '1m': '1개월',
            'all': '전체'
        }[x]
    )
    
    with db.get_read_session() as session:
        df = load_data(session, time_range)
        
        if df.empty:
            st.warning('선택한 기간에 데이터가 없습니다.')
            return
            
        # 사이드바 필터
        st.sidebar.header('필터')

        # 기본 필터
        col1, col2 = st.sidebar.columns(2)
        selected_grade = col1.multiselect('등급', df['grade'].unique(), default=df['grade'].unique())
        selected_part = col2.multiselect('부위', df['part'].unique(), default=df['part'].unique())

        # 품질 범위 필터
        quality_range = st.sidebar.slider('품질', 
            min_value=0, max_value=100, 
            value=(67, 100))  # 기본값 67-100

        # 거래 가능 횟수 필터
        trade_counts = sorted(df['trade_count'].unique())
        selected_trade_count = st.sidebar.multiselect('거래 가능 횟수', 
            trade_counts, 
            default=trade_counts)

        # 옵션 필터 (최대 3개)
        st.sidebar.subheader('옵션 필터')
        available_options = ['없음', '공퍼', '무공퍼', '치적', '치피', '추피', '적주피', 
                            '아덴게이지', '낙인력', '아군회복', '아군보호막', '아공강', '아피강', '최생', '최마', '깡공', '깡무공']
        grade_map = {'하옵': '1', '중옵': '2', '상옵': '3'}

        option_filters = []
        for i in range(3):
            col1, col2 = st.sidebar.columns(2)
            selected_option = col1.selectbox(f'옵션 {i+1}', available_options, key=f'opt_{i}')
            
            if selected_option != '없음':
                option_grade = col2.selectbox('등급', ['전체', '하옵', '중옵', '상옵'], key=f'grade_{i}')
                option_filters.append((selected_option, option_grade))

        # 필터 적용
        filtered_df = df[
            (df['grade'].isin(selected_grade)) &
            (df['part'].isin(selected_part)) &
            (df['quality'].between(quality_range[0], quality_range[1])) &
            (df['trade_count'].isin(selected_trade_count))
        ]

        # 옵션 필터 적용
        for option, grade in option_filters:
            option_pattern = option
            if grade != '전체':
                option_pattern = f"{option} {grade_map[grade]}"
            filtered_df = filtered_df[filtered_df['options'].str.contains(option_pattern, na=False)]
        
        # 메인 대시보드
        st.header('📊 시장 분석')

        # 최저가 추이 차트
        st.subheader('선택한 옵션 조합의 최저가 추이')
        min_price_df = (filtered_df
            .groupby('timestamp')['price']
            .min()
            .reset_index()
        )

        if not min_price_df.empty:
            fig = px.line(min_price_df,
                x='timestamp',
                y='price',
                title='최저가 추이')
            
            fig.update_layout(
                xaxis_title="시간",
                yaxis_title="가격",
                yaxis_tickformat=',',  # 가격에 천단위 콤마 추가
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info('선택한 조건에 맞는 데이터가 없습니다.')

        # 기본 통계는 남겨둘까요?
        col1, col2, col3 = st.columns(3)
        col1.metric("현재 최저가", f"{int(filtered_df['price'].min()):,}" if not filtered_df.empty else "-")
        col2.metric("평균 가격", f"{int(filtered_df['price'].mean()):,}" if not filtered_df.empty else "-")
        col3.metric("데이터 수", f"{len(filtered_df):,}")

        # 최근 거래 데이터 표시
        st.subheader('최근 거래 데이터')
        recent_data = filtered_df.sort_values('timestamp', ascending=False).head(100)

        # 데이터프레임 표시 형식
        def format_row(row):
            options_str = row['options'].replace(',', ' / ') if pd.notna(row['options']) else ''
            return (f"{row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"{row['grade']} {row['name']} | "
                    f"연마 {row['level']}단계 | "
                    f"품질 {row['quality']} | "
                    f"거래 {row['trade_count']}회 | "
                    f"{row['price']:,}골드 | "
                    f"옵션: {options_str}")

        for idx, row in recent_data.iterrows():
            st.text(format_row(row))

def display_bracelet_dashboard():
    """팔찌 시장 분석 대시보드"""
    st.header('팔찌 시장 분석')
    db = DatabaseManager()
    
    # 사이드바 필터
    st.sidebar.header('팔찌 필터')
    time_range = st.sidebar.selectbox(
        '시간 범위',
        ['1d', '1w', '1m', 'all'],
        format_func=lambda x: {
            '1d': '1일',
            '1w': '1주일',
            '1m': '1개월',
            'all': '전체'
        }[x],
        key='bracelet_time_range'  # 고유한 key 추가
    )

    # 시간 범위에 따른 쿼리 조건 설정
    if time_range == '1d':
        time_limit = datetime.now() - timedelta(days=1)
    elif time_range == '1w':
        time_limit = datetime.now() - timedelta(weeks=1)
    elif time_range == '1m':
        time_limit = datetime.now() - timedelta(days=30)
    else:  # all
        time_limit = datetime(2000, 1, 1)

    with db.get_read_session() as session:
        query = f"""
        SELECT 
            b.timestamp,
            b.grade,
            b.name,
            b.price,
            b.fixed_option_count,
            b.extra_option_count,
            GROUP_CONCAT(DISTINCT cs.stat_type || ' ' || cs.value) as combat_stats,
            GROUP_CONCAT(DISTINCT bs.stat_type || ' ' || bs.value) as base_stats,
            GROUP_CONCAT(DISTINCT se.effect_type) as special_effects
        FROM bracelet_price_records b
        LEFT JOIN bracelet_combat_stats cs ON b.id = cs.bracelet_id
        LEFT JOIN bracelet_base_stats bs ON b.id = bs.bracelet_id
        LEFT JOIN bracelet_special_effects se ON b.id = se.bracelet_id
        WHERE b.timestamp > '{time_limit}'
        GROUP BY b.id
        """
        df = pd.read_sql(query, session.bind)
        
        if df.empty:
            st.warning('선택한 기간에 데이터가 없습니다.')
            return

        # timestamp 컬럼을 datetime으로 변환
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # 기본 필터
        col1, col2 = st.sidebar.columns(2)
        selected_grade = col1.multiselect('등급', 
                                        df['grade'].unique(), 
                                        default=df['grade'].unique(),
                                        key='bracelet_grade')  # 고유한 key 추가
        
        # 고정 효과 개수 필터
        fixed_counts = sorted(df['fixed_option_count'].unique())
        selected_fixed_count = col2.multiselect('고정 효과 개수', 
            fixed_counts, 
            default=fixed_counts,
            key='bracelet_fixed_count')  # 고유한 key 추가

        # 전투특성 필터
        st.sidebar.subheader('전투특성 필터')
        combat_stats = ["특화", "치명", "신속"]
        selected_combat_stats = st.sidebar.multiselect('전투특성', 
                                                     combat_stats,
                                                     key='bracelet_combat_stats')  # 고유한 key 추가
        
        if selected_combat_stats:
            min_value, max_value = st.sidebar.slider('전투특성 수치', 
                min_value=40, max_value=110, 
                value=(40, 110),
                key='bracelet_stat_range')  # 고유한 key 추가

        # 필터 적용
        filtered_df = df[
            (df['grade'].isin(selected_grade)) &
            (df['fixed_option_count'].isin(selected_fixed_count))
        ]

        # 전투특성 필터 적용
        if selected_combat_stats:
            for stat in selected_combat_stats:
                filtered_df = filtered_df[
                    filtered_df['combat_stats'].str.contains(
                        f"{stat} [{min_value}-{max_value}]", 
                        regex=True, 
                        na=False
                    )
                ]

        # 메인 대시보드
        st.header('📊 시장 분석')

        # 최저가 추이 차트
        st.subheader('선택한 옵션 조합의 최저가 추이')
        min_price_df = (filtered_df
            .groupby('timestamp')['price']
            .min()
            .reset_index()
        )

        if not min_price_df.empty:
            fig = px.line(min_price_df,
                x='timestamp',
                y='price',
                title='최저가 추이')
            
            fig.update_layout(
                xaxis_title="시간",
                yaxis_title="가격",
                yaxis_tickformat=',',
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info('선택한 조건에 맞는 데이터가 없습니다.')

        # 기본 통계
        col1, col2, col3 = st.columns(3)
        col1.metric("현재 최저가", f"{int(filtered_df['price'].min()):,}" if not filtered_df.empty else "-")
        col2.metric("평균 가격", f"{int(filtered_df['price'].mean()):,}" if not filtered_df.empty else "-")
        col3.metric("데이터 수", f"{len(filtered_df):,}")

        # 최근 거래 데이터 표시
        st.subheader('최근 거래 데이터')
        recent_data = filtered_df.sort_values('timestamp', ascending=False).head(100)

        # 데이터프레임 표시 형식
        def format_row(row):
            combat_stats_str = row['combat_stats'].replace(',', ' / ') if pd.notna(row['combat_stats']) else ''
            base_stats_str = row['base_stats'].replace(',', ' / ') if pd.notna(row['base_stats']) else ''
            special_effects_str = row['special_effects'].replace(',', ' / ') if pd.notna(row['special_effects']) else ''
            
            return (f"{row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | "
                   f"{row['grade']} | "
                   f"고정 {row['fixed_option_count']}개, 부여 {row['extra_option_count']}개 | "
                   f"{row['price']:,}골드 | "
                   f"전투특성: {combat_stats_str} | "
                   f"기본스탯: {base_stats_str} | "
                   f"특수효과: {special_effects_str}")

        # 최근 거래 데이터 표시
        st.subheader('최근 거래 데이터')
        recent_data = filtered_df.sort_values('timestamp', ascending=False).head(100)

        for idx, row in recent_data.iterrows():
            st.text(format_row(row))



if __name__ == '__main__':
    run_dashboard()