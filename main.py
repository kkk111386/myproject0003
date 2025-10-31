# Streamlit 앱: 대중교통현황조사(시도별 대중교통 접근수단) 시각화
# 파일 경로: /mnt/data/대중교통현황조사 시도별 대중교통 접근수단.csv
# 사용법: 이 파일을 깃허브에 올리고 main.py로 저장한 뒤
#        Streamlit에서 `streamlit run main.py` 로 실행하세요.

import streamlit as st
import pandas as pd
import altair as alt
import io
import re

st.set_page_config(page_title="대중교통 접근수단 시각화", layout="wide")

DATA_PATH = "/mnt/data/대중교통현황조사 시도별 대중교통 접근수단.csv"

@st.cache_data
def load_data(path):
    # 파일 인코딩 자동 시도 (cp949 -> utf-8)
    for enc in ("cp949", "euc-kr", "utf-8", "utf-8-sig"):
        try:
            df = pd.read_csv(path, encoding=enc)
            return df
        except Exception:
            pass
    raise ValueError("CSV 파일을 읽을 수 없습니다. 인코딩을 확인해 주세요.")


def clean_columns(df):
    # 컬럼명 정리: 공백 제거, 소문자화, 괄호 등 제거
    new_cols = []
    for c in df.columns:
        nc = c.strip()
        nc = re.sub(r"\s+", "_", nc)
        new_cols.append(nc)
    df.columns = new_cols
    return df


def guess_columns(df):
    # 흔히 쓰이는 한글 컬럼명(시도, 연도 등)을 찾아보고 키 이름 반환
    cols = {"region": None, "year": None, "value_cols": []}
    for c in df.columns:
        low = c.lower()
        if any(k in low for k in ["시도", "지역", "도"]):
            cols["region"] = c
        if any(k in low for k in ["년", "연도", "year"]):
            cols["year"] = c
    # value 컬럼은 숫자형 컬럼 또는 나머지
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if numeric_cols:
        cols["value_cols"] = numeric_cols
    else:
        # 숫자형 컬럼이 없으면, 연도나 지역을 제외한 나머지 컬럼들을 후보로 둠
        cols["value_cols"] = [c for c in df.columns if c not in (cols["region"], cols["year"]) and c is not None]
    return cols


# ---------- 데이터 로드 ----------
try:
    df_raw = load_data(DATA_PATH)
except Exception as e:
    st.error(f"데이터를 불러오지 못했습니다: {e}")
    st.stop()

# 컬럼 정리
df = clean_columns(df_raw.copy())
col_info = guess_columns(df)

# 앱 레이아웃
st.title("대중교통 접근수단 (시도별) — 시각화")
st.markdown("업로드한 CSV를 기반으로 여러 상호작용형 차트(시계열, 막대그래프 등)를 제공합니다.")

with st.expander("원본 데이터 확인 / 다운로드"):
    st.dataframe(df.head(100))
    # CSV 다운로드
    csv_buf = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("CSV로 다운로드 (UTF-8)", data=csv_buf, file_name="transport_by_region.csv", mime='text/csv')

# 사이드바: 필터
st.sidebar.header("필터")
region_col = col_info['region']
year_col = col_info['year']
value_cols = col_info['value_cols']

if region_col is None and year_col is None:
    st.warning("데이터에서 '시도' 또는 '연도' 관련된 컬럼을 자동으로 찾지 못했습니다. 컬럼명을 확인하세요.")

# 지역 선택
regions = df[region_col].unique().tolist() if region_col in df.columns else []
sel_regions = st.sidebar.multiselect("시도 선택", options=regions, default=regions[:5] if regions else [])
if sel_regions:
    df = df[df[region_col].isin(sel_regions)]

# 연도 선택(있으면)
if year_col in df.columns:
    try:
        # 연도 칼럼이 숫자/문자일 수 있으니 안전하게 변환
        df[year_col] = pd.to_numeric(df[year_col], errors='coerce')
        years = sorted(df[year_col].dropna().unique().astype(int).tolist())
        if years:
            sel_years = st.sidebar.multiselect("연도 선택", options=years, default=[years[-1]])
            if sel_years:
                df = df[df[year_col].isin(sel_years)]
    except Exception:
        pass

# 지표 선택
metrics = value_cols
if not metrics:
    st.error("시각화할 수치형(또는 비율) 컬럼을 찾지 못했습니다. CSV 구조를 확인해 주세요.")
    st.stop()
sel_metrics = st.sidebar.multiselect("표시할 지표 선택", options=metrics, default=metrics[:3])

# ---------- 시각화 영역 ----------
st.header("차트")

# 1) 연도별(시계열) 라인 차트: year_col이 있을 경우
if year_col in df.columns and sel_metrics:
    st.subheader("연도별 추이 (라인 차트)")
    # 시계열용 데이터 전처리
    df_ts = df.copy()
    # 선택된 지표들만 fold하여 long format으로 변환
    id_vars = [c for c in [region_col, year_col] if c in df_ts.columns]
    df_long = df_ts.melt(id_vars=id_vars, value_vars=sel_metrics, var_name='metric', value_name='value')
    # dropna
    df_long = df_long.dropna(subset=['value'])

    line = alt.Chart(df_long).mark_line(point=True).encode(
        x=alt.X(f"{year_col}:O", title="연도"),
        y=alt.Y('value:Q', title='값'),
        color=alt.Color('metric:N', title='지표'),
        strokeDash=alt.Color('metric:N'),
        tooltip=[region_col, year_col, 'metric', alt.Tooltip('value:Q')]
    ).interactive()

    st.altair_chart(line, use_container_width=True)

# 2) 최신 연도(또는 선택된 연도)의 막대 차트 (지표 비교)
if sel_metrics:
    st.subheader("지표 비교 — 막대그래프")
    # 최신 연도 선택
    if year_col in df.columns:
        latest = df[year_col].max()
        df_latest = df[df[year_col] == latest]
        subtitle = f"연도: {int(latest)} (최신)" if pd.notna(latest) else ""
    else:
        df_latest = df
        subtitle = ""

    # 집계: 지역별 지표 합계/평균 선택
    agg_mode = st.selectbox("집계 방식", options=["sum", "mean"], index=1)
    if agg_mode == 'sum':
        df_agg = df_latest.groupby(region_col)[sel_metrics].sum().reset_index()
    else:
        df_agg = df_latest.groupby(region_col)[sel_metrics].mean().reset_index()

    st.caption(subtitle)
    # long format
    df_bar = df_agg.melt(id_vars=[region_col], value_vars=sel_metrics, var_name='metric', value_name='value')

    bar = alt.Chart(df_bar).mark_bar().encode(
        x=alt.X('value:Q', title='값'),
        y=alt.Y(f'{region_col}:N', sort='-x', title='시도'),
        color='metric:N',
        tooltip=[region_col, 'metric', alt.Tooltip('value:Q')]
    ).interactive()

    st.altair_chart(bar, use_container_width=True)

# 3) 테이블 및 다운로드
st.header("표로 보기 및 다운로드")
st.dataframe(df.reset_index(drop=True))

buffer = io.StringIO()
df.to_csv(buffer, index=False)
st.download_button("현재 필터 데이터 다운로드 (CSV)", data=buffer.getvalue().encode('utf-8-sig'), file_name='filtered_transport.csv', mime='text/csv')

# 4) 간단한 통계
st.header("요약 통계")
try:
    st.write(df[sel_metrics].describe())
except Exception:
    st.write("선택된 지표에 대해 통계량을 계산할 수 없습니다.")

# 끝
st.markdown("---")
st.caption("앱 생성: main.py — 이 파일을 깃허브 레포에 넣고 Streamlit에서 실행하세요.")
