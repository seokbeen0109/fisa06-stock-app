# 표준 라이브러리
import datetime
from io import BytesIO
import os

# 서드파티 라이브러리
import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import plotly.graph_objects as go # 캔들차트용
from plotly.subplots import make_subplots # 서브플롯용
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# --- 페이지 설정 ---
st.set_page_config(
    page_title="주식 데이터 대시보드",
    page_icon="📈",
    layout="wide"
)

my_name = os.getenv('MY_NAME', 'Stock Dashboard')
st.title(f"📈 {my_name}")

# --- 유틸리티 함수 ---
@st.cache_data # 데이터 캐싱으로 속도 향상
def get_krx_company_list() -> pd.DataFrame:
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        df_listing = pd.read_html(url, header=0, flavor='bs4', encoding='EUC-KR')[0]
        df_listing = df_listing[['회사명', '종목코드']].copy()
        df_listing['종목코드'] = df_listing['종목코드'].apply(lambda x: f'{x:06}')
        return df_listing
    except Exception as e:
        st.error(f"상장사 명단을 불러오는 데 실패했습니다: {e}")
        return pd.DataFrame(columns=['회사명', '종목코드'])

def get_stock_code_by_company(company_name: str, company_df: pd.DataFrame) -> str:
    if company_name.isdigit() and len(company_name) == 6:
        return company_name
    
    codes = company_df[company_df['회사명'] == company_name]['종목코드'].values
    if len(codes) > 0:
        return codes[0]
    return None

# --- 사이드바 UI ---
with st.sidebar:
    st.header("🔍 검색 옵션")
    
    # 상장사 목록 미리 로드
    df_krx = get_krx_company_list()
    company_list = df_krx['회사명'].tolist()
    
    # 텍스트 입력 대신 검색 가능한 셀렉트박스로 변경 (사용성 개선)
    company_name = st.selectbox(
        '회사를 선택하세요', 
        options=[""] + company_list,
        index=0
    )

    today = datetime.datetime.now()
    start_default = today - datetime.timedelta(days=365) # 기본 1년

    selected_dates = st.date_input(
        '조회 기간',
        (start_default, today),
        format="YYYY-MM-DD",
    )
    
    st.caption("💡 이동평균선 등 보조지표를 보려면 충분한 기간(3개월 이상)을 설정하세요.")
    
    confirm_btn = st.button('조회하기', type="primary")

# --- 메인 로직 ---
if confirm_btn:
    if not company_name:
        st.warning("조회할 회사를 선택해주세요.")
    else:
        try:
            with st.spinner(f'{company_name} 데이터를 분석 중입니다...'):
                stock_code = get_stock_code_by_company(company_name, df_krx)
                
                if len(selected_dates) != 2:
                    st.warning("시작일과 종료일을 모두 선택해주세요.")
                    st.stop()
                    
                start_date = selected_dates[0].strftime("%Y%m%d")
                end_date = selected_dates[1].strftime("%Y%m%d")
                
                # 데이터 수집
                df = fdr.DataReader(stock_code, start_date, end_date)
                
            if df.empty:
                st.info("해당 기간의 데이터가 없습니다.")
            else:
                # --- 데이터 전처리 (이동평균선 계산) ---
                df['MA5'] = df['Close'].rolling(window=5).mean()
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()

                # 최신 데이터 기준 지표 계산
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else latest
                
                diff = latest['Close'] - prev['Close']
                diff_rate = (diff / prev['Close']) * 100
                volume_diff = latest['Volume'] - prev['Volume']

                # --- 1. 핵심 지표 메트릭 (Metrics) ---
                st.subheader(f"{company_name} ({stock_code})")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("현재가", f"{latest['Close']:,}원", f"{diff:,}원 ({diff_rate:.2f}%)")
                with col2:
                    st.metric("거래량", f"{latest['Volume']:,}주", f"{volume_diff:,}주")
                with col3:
                    st.metric("시가", f"{latest['Open']:,}원")
                with col4:
                    st.metric("고가/저가", f"{latest['High']:,} / {latest['Low']:,}")

                st.divider()

                # --- 2. 고급 차트 그리기 (Candlestick + Volume + MA) ---
                # 2줄짜리 서브플롯 생성 (위: 캔들+MA, 아래: 거래량)
                fig = make_subplots(
                    rows=2, cols=1, 
                    shared_xaxes=True, 
                    vertical_spacing=0.03,
                    subplot_titles=(f'{company_name} 주가 차트', '거래량'),
                    row_heights=[0.7, 0.3] # 차트 높이 비율 7:3
                )

                # [상단] 캔들스틱 차트 (한국식 색상: 상승=빨강, 하락=파랑)
                fig.add_trace(go.Candlestick(
                    x=df.index,
                    open=df['Open'], high=df['High'],
                    low=df['Low'], close=df['Close'],
                    name='주가',
                    increasing_line_color='red',  # 상승
                    decreasing_line_color='blue'  # 하락
                ), row=1, col=1)

                # [상단] 이동평균선 추가
                fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='orange', width=1), name='5일 이동평균'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='purple', width=1), name='20일 이동평균'), row=1, col=1)

                # [하단] 거래량 바 차트
                colors = ['red' if row['Open'] - row['Close'] >= 0 else 'blue' for index, row in df.iterrows()]
                fig.add_trace(go.Bar(
                    x=df.index, y=df['Volume'],
                    marker_color=colors,
                    name='거래량'
                ), row=2, col=1)

                # 차트 레이아웃 설정
                fig.update_layout(
                    height=600, # 전체 높이
                    xaxis_rangeslider_visible=False, # 하단 슬라이더 제거 (깔끔하게)
                    hovermode="x unified", # 마우스 오버 시 X축 기준 정보 한꺼번에 표시
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                
                # y축 포맷 (숫자 콤마)
                fig.update_yaxes(tickformat=",", row=1, col=1)
                fig.update_yaxes(tickformat=",", row=2, col=1)

                st.plotly_chart(fig, use_container_width=True)

                # --- 3. 데이터 탭 (Raw Data) ---
                tab1, tab2 = st.tabs(["📊 요약 통계", "📋 원본 데이터"])
                
                with tab1:
                    st.markdown(f"""
                    * **기간 최고가:** {df['High'].max():,}원
                    * **기간 최저가:** {df['Low'].min():,}원
                    * **평균 거래량:** {df['Volume'].mean():,.0f}주
                    """)
                
                with tab2:
                    st.dataframe(df.sort_index(ascending=False), use_container_width=True)
                    
                    # 엑셀 다운로드
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=True)
                    
                    st.download_button(
                        label="📥 엑셀 다운로드",
                        data=output.getvalue(),
                        file_name=f"{company_name}_{start_date}_{end_date}.xlsx",
                        mime="application/vnd.ms-excel"
                    )

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")