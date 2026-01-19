# 표준 라이브러리
import datetime
from io import BytesIO
import os

# 서드파티 라이브러리
import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
# import matplotlib.pyplot as plt  <-- 삭제 (Plotly로 대체)
# import koreanize_matplotlib      <-- 삭제 (Plotly는 한글 자동 지원)
import plotly.graph_objects as go  # 추가: 캔들차트용
from plotly.subplots import make_subplots  # 추가: 차트 레이아웃 분할용
from dotenv import load_dotenv

load_dotenv() # .env의 환경변수를 읽어옴

my_name = os.getenv('MY_NAME', 'Stock Dashboard') # 값이 없을 경우 기본값 설정
st.header(my_name)

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

def get_stock_code_by_company(company_name: str) -> str:
    if company_name.isdigit() and len(company_name) == 6:
        return company_name
    
    company_df = get_krx_company_list()
    codes = company_df[company_df['회사명'] == company_name]['종목코드'].values
    if len(codes) > 0:
        return codes[0]
    else:
        raise ValueError(f"'{company_name}'을 찾을 수 없습니다. 종목코드 6자리를 직접 입력해보세요.")

# --- 사이드바 입력 부분 (기존 유지) ---
company_name = st.sidebar.text_input('조회할 회사를 입력하세요')

today = datetime.datetime.now()
jan_1 = datetime.date(today.year, 1, 1)

selected_dates = st.sidebar.date_input(
    '조회 기간 설정',
    (jan_1, today),
    format="MM.DD.YYYY",
)

confirm_btn = st.sidebar.button('조회하기') 

# --- 메인 로직 ---
if confirm_btn:
    if not company_name: 
        st.warning("조회할 회사 이름을 입력하세요.")
    else:
        try:
            with st.spinner('데이터를 수집하는 중...'):
                stock_code = get_stock_code_by_company(company_name)
                
                # 날짜 선택 예외처리
                if len(selected_dates) != 2:
                    st.warning("시작일과 종료일을 모두 선택해주세요.")
                    st.stop()

                start_date = selected_dates[0].strftime("%Y%m%d")
                end_date = selected_dates[1].strftime("%Y%m%d")
                
                price_df = fdr.DataReader(stock_code, start_date, end_date)
                
            if price_df.empty:
                st.info("해당 기간의 주가 데이터가 없습니다.")
            else:
                # -----------------------------------------------------------
                # [추가된 부분] 데이터 분석 및 지표 계산
                # -----------------------------------------------------------
                # 이동평균선 계산
                price_df['MA5'] = price_df['Close'].rolling(window=5).mean()
                price_df['MA20'] = price_df['Close'].rolling(window=20).mean()

                # 최신 데이터 및 등락폭 계산
                latest = price_df.iloc[-1]
                prev = price_df.iloc[-2] if len(price_df) > 1 else latest
                diff = latest['Close'] - prev['Close']
                diff_rate = (diff / prev['Close']) * 100 if prev['Close'] != 0 else 0

                st.subheader(f"[{company_name}] 주가 데이터 ({stock_code})")

                # 1. 핵심 지표 보여주기 (Metrics)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("현재가", f"{latest['Close']:,}원", f"{diff:,}원 ({diff_rate:.2f}%)")
                with col2:
                    st.metric("거래량", f"{latest['Volume']:,}주")
                with col3:
                    st.metric("시가", f"{latest['Open']:,}원")
                with col4:
                    st.metric("고가/저가", f"{latest['High']:,} / {latest['Low']:,}")
                
                st.divider()

                # -----------------------------------------------------------
                # [수정된 부분] Plotly를 이용한 전문적인 캔들스틱 차트
                # -----------------------------------------------------------
                # 2줄짜리 차트 생성 (위: 주가+이동평균선, 아래: 거래량) 
                fig = make_subplots(
                    rows=2, cols=1, 
                    shared_xaxes=True, 
                    vertical_spacing=0.03,
                    subplot_titles=(f'{company_name} 주가 흐름', '거래량'),
                    row_heights=[0.7, 0.3]
                )

                # [상단] 캔들스틱 차트 추가 (한국식: 상승=빨강, 하락=파랑)
                fig.add_trace(go.Candlestick(
                    x=price_df.index,
                    open=price_df['Open'], high=price_df['High'],
                    low=price_df['Low'], close=price_df['Close'],
                    name='주가',
                    increasing_line_color='red', decreasing_line_color='blue'
                ), row=1, col=1)

                # [상단] 이동평균선 추가
                fig.add_trace(go.Scatter(x=price_df.index, y=price_df['MA5'], line=dict(color='orange', width=1), name='5일 이동평균'), row=1, col=1)
                fig.add_trace(go.Scatter(x=price_df.index, y=price_df['MA20'], line=dict(color='purple', width=1), name='20일 이동평균'), row=1, col=1)

                # [하단] 거래량 바 차트 추가
                colors = ['red' if row['Open'] - row['Close'] >= 0 else 'blue' for index, row in price_df.iterrows()]
                fig.add_trace(go.Bar(
                    x=price_df.index, y=price_df['Volume'],
                    marker_color=colors,
                    name='거래량'
                ), row=2, col=1)

                # 차트 레이아웃 꾸미기
                fig.update_layout(
                    height=600, 
                    xaxis_rangeslider_visible=False, # 하단 슬라이더 제거 (깔끔하게)
                    hovermode="x unified", # 마우스 오버시 X축 정보 통합 표시
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                
                # Y축 숫자 포맷 (천 단위 콤마)
                fig.update_yaxes(tickformat=",", row=1, col=1)
                fig.update_yaxes(tickformat=",", row=2, col=1)

                st.plotly_chart(fig, use_container_width=True)
                # -----------------------------------------------------------

                st.dataframe(price_df.tail(10), use_container_width=True)

                # 엑셀 다운로드 기능 (기존 유지)
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    price_df.to_excel(writer, index=True, sheet_name='Sheet1')
                st.download_button(
                    label="📥 엑셀 파일 다운로드",
                    data=output.getvalue(),
                    file_name=f"{company_name}_주가.xlsx",
                    mime="application/vnd.ms-excel"
                )
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")