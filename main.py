# 어제의 박스오피스 — KOBIS 일별 박스오피스 API
# 스트림릿 클라우드 배포용 main.py

import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")

# 인증키는 비밀 금고(secrets)에서 불러온다 — 코드에 직접 쓰지 않는다
# 스트림릿 클라우드 대시보드 > 앱 설정 > Secrets 에 아래처럼 넣어 두면 된다.
#   KOBIS_KEY = "발급받은_인증키"
if "KOBIS_KEY" not in st.secrets:
    st.error("secrets에 KOBIS_KEY가 없습니다. 앱 설정 > Secrets에 KOBIS_KEY를 추가해 주세요.")
    st.stop()

API_KEY = st.secrets["KOBIS_KEY"]
URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# '어제'를 한국 시간(KST) 기준으로 계산한다 — 배포 서버의 시계는 한국 시간이 아닐 수 있다
KST = datetime.timezone(datetime.timedelta(hours=9))
yesterday = datetime.datetime.now(KST).date() - datetime.timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")


@st.cache_data(ttl=3600)  # 같은 날짜는 한 시간 동안 기억해 두고 API를 다시 부르지 않는다
def fetch_boxoffice(date_str):
    """KOBIS API에서 해당 날짜의 일별 박스오피스를 받아 온다."""
    params = {"key": API_KEY, "targetDt": date_str}
    res = requests.get(URL, params=params, timeout=10)
    res.raise_for_status()
    return res.json()


st.title("🎬 어제의 박스오피스")
st.caption(f"조회 날짜: {yesterday} (한국 시간 기준 어제)")

# 1) 네트워크 요청 자체가 실패한 경우 (연결 끊김, 타임아웃 등)
try:
    data = fetch_boxoffice(target_dt)
except requests.RequestException:
    st.error("서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 잠시 뒤 새로고침해 주세요.")
    st.stop()

# 2) 응답이 200이지만 JSON이 아닌 경우 (예: 점검 중 안내 HTML 페이지)
try:
    data = data if isinstance(data, dict) else {}
except Exception:
    st.error("서버 응답을 해석하지 못했습니다. 잠시 뒤 다시 시도해 주세요.")
    st.stop()

# 3) 인증키가 틀리면 상태코드는 200이지만 faultInfo 상자가 온다
if "faultInfo" in data:
    st.error(f"API가 오류를 돌려주었습니다: {data['faultInfo'].get('message', '알 수 없는 오류')}")
    st.info("secrets의 KOBIS_KEY 값이 올바른지, 인증키가 만료되지 않았는지 확인해 주세요.")
    st.stop()

movies = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])

# 4) 영화 목록이 비어서 오면 — 아직 집계 전인 날짜일 가능성이 높다
if not movies:
    st.warning(
        "영화 목록이 비어 있습니다. 어제 날짜(집계 기준)가 아직 집계 전이거나, "
        "targetDt 형식(yyyymmdd)에 문제가 없는지 확인해 주세요."
    )
    st.stop()

df = pd.DataFrame(movies)

# 숫자가 전부 문자열로 오므로 숫자로 바꿔야 정렬과 그래프에 쓸 수 있다
# errors="coerce": 혹시 빈 문자열 등 이상한 값이 오더라도 앱이 죽지 않고 NaN으로 처리한다
num_cols = ["rank", "audiCnt", "audiAcc", "scrnCnt"]
for col in num_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# 숫자 변환에 실패한 행(예외적인 데이터)은 표/그래프 계산에서 제외
df = df.dropna(subset=num_cols)
if df.empty:
    st.warning("받아온 데이터의 숫자 값이 올바르지 않아 표시할 수 없습니다. 잠시 뒤 다시 시도해 주세요.")
    st.stop()

for col in num_cols:
    df[col] = df[col].astype(int)

# 신작 여부 뱃지 (rankOldAndNew: "NEW"면 신규 진입작)
if "rankOldAndNew" in df.columns:
    df["신작여부"] = df["rankOldAndNew"].apply(lambda v: "🆕 신작" if v == "NEW" else "")
else:
    df["신작여부"] = ""

# 1위 영화는 지표 카드 세 장으로 크게
top = df.sort_values("rank").iloc[0]
badge = " 🆕" if top["신작여부"] else ""
st.subheader(f"🥇 1위 — {top['movieNm']}{badge}")
c1, c2, c3 = st.columns(3)
c1.metric("어제 관객수", f"{top['audiCnt']:,}명")
c2.metric("누적 관객수", f"{top['audiAcc']:,}명")
c3.metric("스크린수", f"{top['scrnCnt']:,}개")

# 전체 순위표
st.subheader("📋 어제의 순위표")
table = df.sort_values("rank")[
    ["rank", "movieNm", "신작여부", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
]
table.columns = ["순위", "영화명", "신작", "개봉일", "관객수", "누적관객", "스크린수"]
st.dataframe(table, hide_index=True, use_container_width=True)

# 관객수 상위 5편은 막대그래프로
st.subheader("📊 관객수 상위 5편")
top5 = df.sort_values("audiCnt", ascending=False).head(5)
fig = px.bar(
    top5,
    x="movieNm",
    y="audiCnt",
    labels={"movieNm": "영화명", "audiCnt": "어제 관객수"},
)
st.plotly_chart(fig, use_container_width=True)
