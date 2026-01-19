# 표준 라이브러리
import datetime
from io import BytesIO
import os

# 서드파티 라이브러리
import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import plotly.express as px  # Plotly 라이브러리 추가
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()
my_name = os.getenv('MY_NAME')
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

# --- 사이드바 UI ---
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
                
                # 날짜 선택 예외처리 (시작일만 선택된 경우 등)
                if len(selected_dates) != 2:
                    st.warning("시작일과 종료일을 모두 선택해주세요.")
                    st.stop()
                    
                start_date = selected_dates[0].strftime("%Y%m%d")
                end_date = selected_dates[1].strftime("%Y%m%d")
                
                price_df = fdr.DataReader(stock_code, start_date, end_date)
                
            if price_df.empty:
                st.info("해당 기간의 주가 데이터가 없습니다.")
            else:
                st.subheader(f"[{company_name}] 주가 데이터")
                st.dataframe(price_df.tail(10), use_container_width=True)

                # -------------------------------------------------------
                # [수정됨] Plotly를 이용한 인터랙티브 차트 구현
                # -------------------------------------------------------
                # x축은 인덱스(날짜), y축은 Close(종가)
                fig = px.line(
                    price_df, 
                    x=price_df.index, 
                    y='Close', 
                    title=f"{company_name} 종가 추이",
                    labels={'Close': '종가', 'Date': '날짜'}
                )
                
                # 선 색상 설정 (기존 matplotlib의 red와 유사하게)
                fig.update_traces(line_color='red')
                
                # 차트 하단에 기간 조절 슬라이더(Range Slider) 추가
                fig.update_xaxes(rangeslider_visible=True)
                
                # Streamlit에 Plotly 차트 표시
                st.plotly_chart(fig, use_container_width=True)
                # -------------------------------------------------------

                # 엑셀 다운로드 기능
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