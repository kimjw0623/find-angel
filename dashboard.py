import streamlit as st
import pandas as pd
import plotly.express as px
from database import DatabaseManager
from datetime import datetime, timedelta
from sqlalchemy import text


# streamlit run dashboard.py
def load_accessory_data(session, time_range="1d"):
    # 시간 범위에 따른 쿼리 조건 설정
    if time_range == "1d":
        time_limit = datetime.now() - timedelta(days=1)
    elif time_range == "1w":
        time_limit = datetime.now() - timedelta(weeks=1)
    elif time_range == "1m":
        time_limit = datetime.now() - timedelta(days=30)
    else:  # all
        time_limit = datetime(2000, 1, 1)

    query = f"""
    SELECT 
        pr.timestamp,
        pr.search_cycle_id,
        pr.grade,
        pr.name,
        pr.part,
        pr.level,
        pr.quality,
        pr.trade_count,
        pr.price,
        pr.end_time,
        GROUP_CONCAT(io.option_name || ' ' || io.option_grade) as options
    FROM price_records pr
    LEFT JOIN item_options io ON pr.id = io.price_record_id
    WHERE pr.timestamp > '{time_limit}'
    GROUP BY pr.id
    """
    df = pd.read_sql(query, session.bind)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["end_time"] = pd.to_datetime(df["end_time"])  # end_time도 datetime으로 변환
    return df


def load_bracelet_data(session, time_range="1d"):
    """팔찌 데이터 로드"""
    # 시간 범위에 따른 쿼리 조건 설정
    if time_range == "1d":
        time_limit = datetime.now() - timedelta(days=1)
    elif time_range == "1w":
        time_limit = datetime.now() - timedelta(weeks=1)
    elif time_range == "1m":
        time_limit = datetime.now() - timedelta(days=30)
    else:  # all
        time_limit = datetime(2000, 1, 1)

    query = f"""
    SELECT 
        b.timestamp,
        b.search_cycle_id,
        b.grade,
        b.name,
        b.price,
        b.fixed_option_count,
        b.extra_option_count,
        GROUP_CONCAT(DISTINCT 
            CASE WHEN cs.stat_type IS NOT NULL 
            THEN cs.stat_type || ' ' || cs.value 
            END
        ) as combat_stats,
        GROUP_CONCAT(DISTINCT 
            CASE WHEN bs.stat_type IS NOT NULL 
            THEN bs.stat_type || ' ' || bs.value 
            END
        ) as base_stats,
        GROUP_CONCAT(DISTINCT 
            CASE WHEN se.effect_type IS NOT NULL 
            THEN se.effect_type || COALESCE(' ' || se.value, '')
            END
        ) as special_effects
    FROM bracelet_price_records b
    LEFT JOIN bracelet_combat_stats cs ON b.id = cs.bracelet_id
    LEFT JOIN bracelet_base_stats bs ON b.id = bs.bracelet_id
    LEFT JOIN bracelet_special_effects se ON b.id = se.bracelet_id
    WHERE b.timestamp > '{time_limit}'
    GROUP BY b.id, b.timestamp, b.grade, b.name, b.price, b.fixed_option_count, b.extra_option_count, b.search_cycle_id
    ORDER BY b.timestamp DESC
    """

    df = pd.read_sql(query, session.bind)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def run_dashboard():
    st.title("T4 악세서리 경매장 분석")

    # 현재 선택된 탭 추적을 위한 radio 버튼
    current_tab = st.sidebar.radio("분석 대상 선택", ["악세서리", "팔찌"])

    if current_tab == "악세서리":
        display_accessory_dashboard()
    else:
        display_bracelet_dashboard()


def display_accessory_dashboard():
    st.header("악세서리 경매장 분석")
    db = DatabaseManager()

    # 시간 범위 선택
    time_range = st.sidebar.selectbox(
        "시간 범위",
        ["1d", "1w", "1m", "all"],
        format_func=lambda x: {
            "1d": "1일",
            "1w": "1주일",
            "1m": "1개월",
            "all": "전체",
        }[x],
    )

    with db.get_read_session() as session:
        df = load_accessory_data(session, time_range)

        if df.empty:
            st.warning("선택한 기간에 데이터가 없습니다.")
            return

        # 기본 필터
        grades = df["grade"].unique().tolist()
        parts = df["part"].unique().tolist()
        trade_counts = sorted(df["trade_count"].unique().tolist())

        col1, col2 = st.sidebar.columns(2)
        selected_grade = col1.multiselect("등급", options=grades, default=grades)
        selected_part = col2.multiselect("부위", options=parts, default=parts)

        # 품질 범위 필터
        quality_range = st.sidebar.slider(
            "품질", min_value=0, max_value=100, value=(67, 100)
        )

        # 연마 단계 필터 추가
        levels = sorted(df["level"].unique().tolist())
        selected_levels = st.sidebar.multiselect(
            "연마 단계", options=levels, default=levels
        )

        # 거래 가능 횟수 필터
        selected_trade_count = st.sidebar.multiselect(
            "거래 가능 횟수", options=trade_counts, default=trade_counts
        )

        # 옵션 필터
        st.sidebar.subheader("옵션 필터")
        available_options = [
            "없음",
            "공퍼",
            "무공퍼",
            "치적",
            "치피",
            "추피",
            "적주피",
            "아덴게이지",
            "낙인력",
            "아군회복",
            "아군보호막",
            "아공강",
            "아피강",
            "최생",
            "최마",
            "깡공",
            "깡무공",
        ]
        grade_options = ["없음", "하옵", "중옵", "상옵"]
        grade_map = {"하옵": "1", "중옵": "2", "상옵": "3"}

        # 1. 기본 필터 먼저 적용
        filtered_df = df[
            df["grade"].isin(selected_grade)
            & df["part"].isin(selected_part)
            & df["level"].isin(selected_levels)
            & df["quality"].between(quality_range[0], quality_range[1])
            & df["trade_count"].isin(selected_trade_count)
        ]

        # 2. 포함할 옵션 필터 적용
        st.sidebar.subheader("포함할 옵션")
        for i in range(3):
            col1, col2 = st.sidebar.columns(2)
            selected_option = col1.selectbox(
                f"포함할 옵션 {i+1}", available_options, key=f"include_opt_{i}"
            )
            selected_grade = col2.selectbox(
                "등급", grade_options, key=f"include_grade_{i}"
            )

            if selected_option != "없음":
                if selected_grade == "없음":
                    filtered_df = filtered_df[
                        filtered_df["options"].apply(
                            lambda x: (
                                any(
                                    selected_option in opt.strip()
                                    for opt in x.split(",")
                                )
                                if pd.notna(x)
                                else False
                            )
                        )
                    ]
                else:
                    option_pattern = f"{selected_option} {grade_map[selected_grade]}"
                    filtered_df = filtered_df[
                        filtered_df["options"].apply(
                            lambda x: (
                                option_pattern in [opt.strip() for opt in x.split(",")]
                                if pd.notna(x)
                                else False
                            )
                        )
                    ]

        # 제외할 옵션 필터를 멀티셀렉트로 변경
        st.sidebar.subheader("제외할 옵션")

        # 옵션 이름만으로 제외할 옵션 리스트 생성
        exclude_options = available_options[1:]  # '없음' 제외

        selected_excludes = st.sidebar.multiselect(
            "제외할 옵션 선택", options=exclude_options, default=[]
        )

        # 선택된 제외 옵션 적용 - 정확한 옵션명 매칭을 위해 수정
        if selected_excludes:
            filtered_df = filtered_df[
                ~filtered_df["options"].apply(
                    lambda x: (
                        any(
                            exclude_opt == opt.split()[0]
                            for exclude_opt in selected_excludes
                            for opt in x.split(",")
                        )
                        if pd.notna(x)
                        else False
                    )
                )
            ]

        # 차트 및 통계
        st.header("📊 경매장 분석")

        # 최저가 추이
        st.subheader("선택한 옵션 조합의 최저가 추이")
        if not filtered_df.empty:
            # search_cycle_id로 그룹화하여 각 사이클당 최저가 항목 선택
            min_price_indices = filtered_df.groupby("search_cycle_id")["price"].idxmin()
            min_price_df = filtered_df.loc[
                min_price_indices,
                ["timestamp", "price", "quality", "name", "grade", "options"],
            ]

            if not min_price_df.empty:
                # 악세서리용 hover template
                fig = px.line(
                    min_price_df,
                    x="timestamp",
                    y="price",
                    title="최저가 추이",
                    custom_data=[
                        "quality",
                        "name",
                        "grade",
                        "options",
                    ],  # 악세서리 데이터
                )

                fig.update_layout(
                    xaxis_title="시간",
                    yaxis_title="가격",
                    yaxis_tickformat=",",
                )

                fig.update_traces(
                    hovertemplate="<br>".join(
                        [
                            "시간: %{x}",
                            "가격: %{y:,}골드",
                            "품질: %{customdata[0]}",
                            "이름: %{customdata[1]}",
                            "등급: %{customdata[2]}",
                            "옵션: %{customdata[3]}",
                        ]
                    )
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("선택한 조건에 맞는 데이터가 없습니다.")

        # 최근 매물 데이터 표시 부분 수정
        st.subheader("최근 매물 데이터")
        recent_data = filtered_df.sort_values("timestamp", ascending=False).head(100)

        current_time = datetime.now()

        for _, row in recent_data.iterrows():
            options_str = (
                row["options"].replace(",", " / ") if pd.notna(row["options"]) else ""
            )
            remaining_time = row["end_time"] - current_time

            if remaining_time.total_seconds() > 0:
                days = remaining_time.days
                hours, remainder = divmod(remaining_time.seconds, 3600)
                minutes, _ = divmod(remainder, 60)

                if days > 0:
                    remaining_str = f"{days}일 {hours}시간"
                else:
                    remaining_str = f"{hours}시간 {minutes}분"
            else:
                remaining_str = "만료됨"

            display_text = (
                f"{row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | "
                f"{row['grade']} {row['name']} | "
                f"연마 {row['level']}단계 | "
                f"품질 {row['quality']} | "
                f"거래 {row['trade_count']}회 | "
                f"{row['price']:,}골드 | "
                f"남은시간: {remaining_str} | "
                f"옵션: {options_str}"
            )
            st.text(display_text)


def display_bracelet_dashboard():
    """팔찌 대시보드 표시"""
    st.header("팔찌 경매장 분석")
    db = DatabaseManager()

    # 시간 범위 선택
    time_range = st.sidebar.selectbox(
        "시간 범위",
        ["1d", "1w", "1m", "all"],
        format_func=lambda x: {
            "1d": "1일",
            "1w": "1주일",
            "1m": "1개월",
            "all": "전체",
        }[x],
        key="bracelet_time_range",
    )

    with db.get_read_session() as session:
        df = load_bracelet_data(session, time_range)

        if df.empty:
            st.warning("선택한 기간에 데이터가 없습니다.")
            return

        # timestamp 컬럼을 datetime으로 변환
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        st.sidebar.header("팔찌 필터")
        # 1. 기본 필터 (등급, 고정 효과)
        col1, col2 = st.sidebar.columns(2)
        selected_grade = col1.multiselect(
            "등급", df["grade"].unique(), default=df["grade"].unique()
        )

        # 고정 효과 개수 필터
        fixed_counts = sorted(df["fixed_option_count"].unique())
        selected_fixed_count = col2.multiselect(
            "고정 효과 개수", fixed_counts, default=fixed_counts
        )

        # 2. 부여 효과 개수 필터
        extra_counts = sorted(df["extra_option_count"].unique())
        selected_extra_count = st.sidebar.multiselect(
            "부여 효과 개수", extra_counts, default=extra_counts
        )

        # 3. 전투특성 필터 (개별적으로)
        st.sidebar.subheader("전투특성 필터 (선택사항)")
        combat_stats = ["특화", "치명", "신속"]

        # 각 전투특성별 필터
        combat_stat_filters = {}
        for stat in combat_stats:
            col1, col2 = st.sidebar.columns(2)
            use_filter = col1.checkbox(f"{stat} 필터 사용")
            if use_filter:
                stat_range = col2.slider(
                    f"{stat} 수치",
                    min_value=40,
                    max_value=120,
                    value=(40, 120),
                    key=f"stat_range_{stat}",
                )
                combat_stat_filters[stat] = stat_range

        # 4. 기본 스탯 필터 (하나만 선택)
        st.sidebar.subheader("기본 스탯 필터 (선택사항)")
        base_stats = ["힘", "민첩", "지능"]
        selected_base_stat = st.sidebar.selectbox(
            "기본 스탯 선택", ["없음"] + base_stats
        )

        if selected_base_stat != "없음":
            base_stat_range = st.sidebar.slider(
                f"{selected_base_stat} 수치",
                min_value=6400,
                max_value=12800,
                value=(6400, 12800),
            )

        # 필터 적용
        filtered_df = df[
            (df["grade"].isin(selected_grade))
            & (df["fixed_option_count"].isin(selected_fixed_count))
            & (df["extra_option_count"].isin(selected_extra_count))
        ]

        # 전투특성 필터 적용
        for stat, (min_val, max_val) in combat_stat_filters.items():
            filtered_df = filtered_df[
                filtered_df["combat_stats"].apply(
                    lambda x: any(
                        stat in cs and min_val <= float(cs.split()[-1]) <= max_val
                        for cs in str(x).split(",")
                        if stat in cs
                    )
                )
            ]

        # 기본 스탯 필터 적용
        if selected_base_stat != "없음":
            min_val, max_val = base_stat_range
            filtered_df = filtered_df[
                filtered_df["base_stats"].apply(
                    lambda x: any(
                        selected_base_stat in bs
                        and min_val <= float(bs.split()[-1]) <= max_val
                        for bs in str(x).split(",")
                        if selected_base_stat in bs
                    )
                )
            ]

        # 메인 대시보드
        st.header("📊 경매장 분석")

        # 최저가 추이 차트
        st.subheader("선택한 옵션 조합의 최저가 추이")

        # 최저가 추이 차트
        if not filtered_df.empty:
            # search_cycle_id로 그룹화하여 각 사이클당 최저가 항목 선택
            min_price_indices = filtered_df.groupby("search_cycle_id")["price"].idxmin()
            min_price_df = filtered_df.loc[
                min_price_indices,
                [
                    "timestamp",
                    "price",
                    "fixed_option_count",
                    "extra_option_count",
                    "combat_stats",
                    "base_stats",
                    "special_effects",
                ],
            ]

            if not min_price_df.empty:
                fig = px.line(
                    min_price_df,
                    x="timestamp",
                    y="price",
                    title="최저가 추이",
                    custom_data=[
                        "fixed_option_count",
                        "extra_option_count",
                        "combat_stats",
                        "base_stats",
                        "special_effects",
                    ],
                )

                fig.update_layout(
                    xaxis_title="시간",
                    yaxis_title="가격",
                    yaxis_tickformat=",",
                )

                # custom hover template
                def custom_hover_template(data):
                    base_template = (
                        "시간: %{x}<br>"
                        + "가격: %{y:,}골드<br>"
                        + "고정효과: %{customdata[0]}개<br>"
                        + "부여효과: %{customdata[1]}개<br>"
                        + "전투특성: %{customdata[2]}"
                    )

                    # 기본스탯이 있는 경우에만 추가
                    if pd.notna(data["base_stats"]):
                        base_template += f"<br>기본스탯: {data['base_stats']}"

                    # 특수효과가 있는 경우에만 추가
                    if pd.notna(data["special_effects"]):
                        base_template += f"<br>특수효과: {data['special_effects']}"

                    return base_template + "<extra></extra>"

                fig.update_traces(
                    hovertemplate=custom_hover_template(min_price_df.iloc[0])
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("선택한 조건에 맞는 데이터가 없습니다.")

        # 기본 통계
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "현재 최저가",
            f"{int(filtered_df['price'].min()):,}" if not filtered_df.empty else "-",
        )
        col2.metric(
            "평균 가격",
            f"{int(filtered_df['price'].mean()):,}" if not filtered_df.empty else "-",
        )
        col3.metric("데이터 수", f"{len(filtered_df):,}")

        # 최근 거래 데이터 표시
        st.subheader("최근 거래 데이터")
        recent_data = filtered_df.sort_values("timestamp", ascending=False).head(100)

        # 데이터프레임 표시 형식
        def format_row(row):
            combat_stats_str = (
                row["combat_stats"].replace(",", " / ")
                if pd.notna(row["combat_stats"])
                else ""
            )
            base_stats_str = (
                row["base_stats"].replace(",", " / ")
                if pd.notna(row["base_stats"])
                else ""
            )
            special_effects_str = (
                row["special_effects"].replace(",", " / ")
                if pd.notna(row["special_effects"])
                else ""
            )

            return (
                f"{row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | "
                f"{row['grade']} | "
                f"고정 {row['fixed_option_count']}개, 부여 {row['extra_option_count']}개 | "
                f"{row['price']:,}골드 | "
                f"전투특성: {combat_stats_str} | "
                f"기본스탯: {base_stats_str} | "
                f"특수효과: {special_effects_str}"
            )

        # 최근 거래 데이터 표시
        st.subheader("최근 거래 데이터")
        recent_data = filtered_df.sort_values("timestamp", ascending=False).head(100)

        for idx, row in recent_data.iterrows():
            st.text(format_row(row))


if __name__ == "__main__":
    run_dashboard()
