import streamlit as st
import anthropic
import time
import json
from datetime import datetime

# ============================================================
# 페이지 기본 설정
# ============================================================
st.set_page_config(
    page_title="🤖 Claude AI 챗봇",
    page_icon="🤖",
    layout="centered",
)

# ============================================================
# 오버워치 감성 CSS
# ============================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');

    /* ====== 전체 배경 - 오버워치 블루/오렌지 ====== */
    .stApp {
        background:
            radial-gradient(ellipse at 10% 20%, rgba(255,152,40,0.12) 0%, transparent 50%),
            radial-gradient(ellipse at 90% 80%, rgba(59,130,246,0.10) 0%, transparent 50%),
            radial-gradient(ellipse at 50% 0%, rgba(255,100,0,0.06) 0%, transparent 40%),
            linear-gradient(180deg,
                #0a1628 0%,
                #0d1f3c 15%,
                #102a4a 30%,
                #0f2844 50%,
                #0d1f3c 70%,
                #0b1a33 85%,
                #091425 100%
            ) !important;
        font-family: 'Noto Sans KR', sans-serif;
    }

    /* ====== 오버워치 HUD 느낌 오버레이 ====== */
    .stApp::before {
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background:
            linear-gradient(90deg, rgba(255,152,40,0.03) 1px, transparent 1px),
            linear-gradient(0deg, rgba(255,152,40,0.03) 1px, transparent 1px);
        background-size: 60px 60px;
        pointer-events: none;
        z-index: 0;
    }

    /* ====== 스캔라인 효과 ====== */
    .stApp::after {
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(0,0,0,0.03) 2px,
            rgba(0,0,0,0.03) 4px
        );
        pointer-events: none;
        z-index: 0;
    }

    /* ====== 헤더 - 오버워치 로고 스타일 ====== */
    .main-header {
        text-align: center;
        padding: 2rem 0 1rem 0;
        position: relative;
    }
    .main-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 120px;
        height: 3px;
        background: linear-gradient(90deg, transparent, #ff9828, #ffb347, #ff9828, transparent);
        border-radius: 2px;
    }
    .main-header h1 {
        font-family: 'Rajdhani', 'Noto Sans KR', sans-serif;
        color: #ffffff;
        font-size: 2.8rem;
        font-weight: 700;
        letter-spacing: 2px;
        text-shadow: 0 0 30px rgba(255,152,40,0.3), 0 0 60px rgba(255,152,40,0.1);
        margin-bottom: 0.2rem;
    }
    .main-header .ow-subtitle {
        font-family: 'Rajdhani', sans-serif;
        color: #ff9828;
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 4px;
        text-transform: uppercase;
    }
    .main-header .ow-desc {
        color: #5a7ca3;
        font-size: 0.85rem;
        margin-top: 0.3rem;
    }

    /* ====== 채팅 메시지 - 유저 (오렌지 계열) ====== */
    .chat-user {
        background: linear-gradient(135deg, rgba(255,152,40,0.15), rgba(255,120,20,0.08));
        border: 1px solid rgba(255,152,40,0.3);
        border-left: 3px solid #ff9828;
        border-radius: 4px 12px 12px 4px;
        padding: 1rem 1.3rem;
        margin: 0.8rem 0;
        color: #fde8c8;
        max-width: 88%;
        margin-left: auto;
        font-size: 0.95rem;
        line-height: 1.6;
        position: relative;
        box-shadow: 0 2px 15px rgba(255,152,40,0.08);
    }
    .chat-user::before {
        content: '';
        position: absolute;
        top: 0; right: 0;
        width: 40px; height: 3px;
        background: linear-gradient(90deg, transparent, #ff9828);
    }

    /* ====== 채팅 메시지 - AI (블루 계열) ====== */
    .chat-ai {
        background: linear-gradient(135deg, rgba(59,130,246,0.10), rgba(37,99,235,0.05));
        border: 1px solid rgba(59,130,246,0.2);
        border-left: 3px solid #3b82f6;
        border-radius: 12px 4px 4px 12px;
        padding: 1rem 1.3rem;
        margin: 0.8rem 0;
        color: #c8dff5;
        max-width: 88%;
        font-size: 0.95rem;
        line-height: 1.7;
        position: relative;
        box-shadow: 0 2px 15px rgba(59,130,246,0.06);
    }
    .chat-ai::before {
        content: '';
        position: absolute;
        top: 0; left: 0;
        width: 40px; height: 3px;
        background: linear-gradient(90deg, #3b82f6, transparent);
    }

    /* ====== 역할 라벨 ====== */
    .chat-role {
        font-family: 'Rajdhani', sans-serif;
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 0.4rem;
    }
    .chat-role-user {
        color: #ff9828;
        text-align: right;
    }
    .chat-role-ai {
        color: #3b82f6;
    }

    /* ====== 모델/페르소나 배지 ====== */
    .model-badge {
        display: inline-block;
        background: rgba(255,152,40,0.12);
        color: #ffb347;
        padding: 0.2rem 0.8rem;
        border-radius: 2px;
        font-family: 'Rajdhani', sans-serif;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 1px;
        border: 1px solid rgba(255,152,40,0.25);
        text-transform: uppercase;
    }
    .persona-badge {
        display: inline-block;
        background: rgba(59,130,246,0.12);
        color: #60a5fa;
        padding: 0.2rem 0.8rem;
        border-radius: 2px;
        font-size: 0.78rem;
        font-weight: 600;
        border: 1px solid rgba(59,130,246,0.25);
    }

    /* ====== 사용량 바 - HUD 스타일 ====== */
    .usage-bar {
        background: rgba(255,152,40,0.04);
        border: 1px solid rgba(255,152,40,0.12);
        border-radius: 4px;
        padding: 0.6rem 1rem;
        margin-top: 0.4rem;
        display: flex;
        justify-content: space-around;
        flex-wrap: wrap;
        gap: 0.5rem;
        position: relative;
    }
    .usage-bar::before {
        content: 'USAGE';
        position: absolute;
        top: -8px;
        left: 10px;
        font-family: 'Rajdhani', sans-serif;
        font-size: 0.6rem;
        font-weight: 700;
        color: #ff9828;
        letter-spacing: 2px;
        background: #0d1f3c;
        padding: 0 5px;
    }
    .usage-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        color: #5a7ca3;
        font-size: 0.76rem;
        font-family: 'Rajdhani', 'Noto Sans KR', sans-serif;
    }
    .usage-chip strong {
        color: #e8dfd0;
        font-weight: 600;
    }

    /* ====== 입력 영역 ====== */
    .stTextArea textarea {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,152,40,0.2) !important;
        color: #e0dcd4 !important;
        border-radius: 4px !important;
        font-size: 0.95rem !important;
        font-family: 'Noto Sans KR', sans-serif !important;
    }
    .stTextArea textarea:focus {
        border-color: #ff9828 !important;
        box-shadow: 0 0 0 1px #ff9828, 0 0 20px rgba(255,152,40,0.15) !important;
    }
    .stTextArea textarea::placeholder {
        color: #3d5a7a !important;
    }

    /* ====== 메인 버튼 - 오버워치 오렌지 ====== */
    .stButton > button {
        font-family: 'Rajdhani', 'Noto Sans KR', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: 1px !important;
        border-radius: 4px !important;
        transition: all 0.3s ease !important;
        text-transform: uppercase !important;
        border: 1px solid rgba(255,152,40,0.4) !important;
        background: linear-gradient(135deg, rgba(255,152,40,0.2), rgba(255,120,20,0.15)) !important;
        color: #ffb347 !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, rgba(255,152,40,0.35), rgba(255,120,20,0.25)) !important;
        border-color: #ff9828 !important;
        box-shadow: 0 0 20px rgba(255,152,40,0.2), inset 0 0 20px rgba(255,152,40,0.05) !important;
        color: #ffffff !important;
    }

    /* ====== 폼 전송 버튼 특별 스타일 ====== */
    .stFormSubmitButton > button {
        font-family: 'Rajdhani', 'Noto Sans KR', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: 1px !important;
        border-radius: 4px !important;
        text-transform: uppercase !important;
    }

    /* ====== 사이드바 - 오버워치 메뉴 ====== */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg,
            #060e1a 0%,
            #091624 30%,
            #0b1a2e 60%,
            #081420 100%
        ) !important;
        border-right: 1px solid rgba(255,152,40,0.1) !important;
    }
    section[data-testid="stSidebar"]::before {
        content: '';
        position: absolute;
        top: 0; right: 0;
        width: 1px; height: 100%;
        background: linear-gradient(180deg, transparent, rgba(255,152,40,0.3), transparent);
    }

    /* ====== 사이드바 타이틀 ====== */
    section[data-testid="stSidebar"] h2 {
        font-family: 'Rajdhani', sans-serif !important;
        color: #ff9828 !important;
        letter-spacing: 2px !important;
        font-weight: 700 !important;
    }
    section[data-testid="stSidebar"] h5 {
        font-family: 'Rajdhani', sans-serif !important;
        color: #ffb347 !important;
        letter-spacing: 2px !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
    }

    /* ====== metric 커스텀 ====== */
    [data-testid="stMetricValue"] {
        font-family: 'Rajdhani', sans-serif !important;
        color: #ffb347 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #5a7ca3 !important;
    }

    /* ====== 라디오 / 셀렉트박스 ====== */
    .stRadio label {
        color: #c0cfe0 !important;
    }
    .stSelectbox label {
        color: #c0cfe0 !important;
    }
    .stRadio > div > label > div:first-child {
        color: #ff9828 !important;
    }

    /* ====== expander ====== */
    .streamlit-expanderHeader {
        background: rgba(255,152,40,0.05) !important;
        border: 1px solid rgba(255,152,40,0.15) !important;
        border-radius: 4px !important;
        color: #ffb347 !important;
        font-family: 'Rajdhani', 'Noto Sans KR', sans-serif !important;
    }

    /* ====== caption ====== */
    .stCaption {
        color: #3d5a7a !important;
    }

    /* ====== hr 구분선 ====== */
    hr {
        border-color: rgba(255,152,40,0.1) !important;
    }

    /* ====== 인포/경고 박스 ====== */
    .stAlert {
        background: rgba(255,152,40,0.05) !important;
        border: 1px solid rgba(255,152,40,0.2) !important;
        color: #c0cfe0 !important;
        border-radius: 4px !important;
    }

    /* ====== 스크롤바 ====== */
    ::-webkit-scrollbar {
        width: 6px;
    }
    ::-webkit-scrollbar-track {
        background: rgba(0,0,0,0.2);
    }
    ::-webkit-scrollbar-thumb {
        background: rgba(255,152,40,0.3);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: rgba(255,152,40,0.5);
    }

    /* ====== 링크 색상 ====== */
    a {
        color: #ff9828 !important;
    }

    /* ====== 다운로드 버튼 ====== */
    .stDownloadButton > button {
        background: rgba(59,130,246,0.15) !important;
        border: 1px solid rgba(59,130,246,0.3) !important;
        color: #60a5fa !important;
        border-radius: 4px !important;
        font-family: 'Rajdhani', sans-serif !important;
        font-weight: 600 !important;
        letter-spacing: 1px !important;
    }
    .stDownloadButton > button:hover {
        background: rgba(59,130,246,0.25) !important;
        border-color: #3b82f6 !important;
        box-shadow: 0 0 15px rgba(59,130,246,0.2) !important;
    }

    /* ====== 차트 배경 ====== */
    .stPlotlyChart, .stBarChart {
        background: rgba(0,0,0,0.2) !important;
        border: 1px solid rgba(255,152,40,0.1) !important;
        border-radius: 4px !important;
        padding: 0.5rem !important;
    }

    /* ====== 인풋 포커스 글로우 제거 깔끔하게 ====== */
    *:focus {
        outline: none !important;
    }

    /* ====== 오버워치 코너 장식 ====== */
    .ow-corner-tl, .ow-corner-br {
        position: fixed;
        width: 60px;
        height: 60px;
        pointer-events: none;
        z-index: 999;
        opacity: 0.15;
    }
    .ow-corner-tl {
        top: 8px; left: 8px;
        border-top: 2px solid #ff9828;
        border-left: 2px solid #ff9828;
    }
    .ow-corner-br {
        bottom: 8px; right: 8px;
        border-bottom: 2px solid #3b82f6;
        border-right: 2px solid #3b82f6;
    }
</style>

<!-- 코너 장식 -->
<div class="ow-corner-tl"></div>
<div class="ow-corner-br"></div>
""", unsafe_allow_html=True)

# ============================================================
# API 키 로드
# ============================================================
try:
    API_KEY = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    st.error("⚠️ `ANTHROPIC_API_KEY`가 설정되지 않았습니다. Streamlit Secrets를 확인해주세요.")
    st.stop()

# ============================================================
# 모델 & 페르소나 정의
# ============================================================
MODELS = {
    "⚡ Sonnet 4": {
        "id": "claude-sonnet-4-20250514",
        "short": "SONNET 4",
        "desc": "빠르고 효율적 — 일반 질문에 적합",
        "input_price": 3.0,
        "output_price": 15.0,
    },
    "🧠 Opus 4": {
        "id": "claude-opus-4-20250514",
        "short": "OPUS 4",
        "desc": "최고 성능 — 복잡한 분석에 적합",
        "input_price": 15.0,
        "output_price": 75.0,
    },
}

PERSONAS = {
    "🎓 기본 도우미": {
        "system": "당신은 당곡고등학교 학생들의 학습을 돕는 친절한 AI 도우미입니다. 이해하기 쉽게 설명하고, 필요하면 예시를 들어줍니다. 한국어로 답변합니다.",
        "greeting": "안녕하세요! 무엇이든 물어보세요 🙂",
    },
    "🔬 과학 선생님": {
        "system": "당신은 열정적인 과학 선생님입니다. 물리, 화학, 생물, 지구과학 개념을 실생활 예시와 함께 재미있게 설명합니다. 실험 이야기도 곁들입니다. 한국어로 답변합니다.",
        "greeting": "과학의 세계에 오신 걸 환영합니다! 🔬",
    },
    "📐 수학 튜터": {
        "system": "당신은 인내심 있는 수학 튜터입니다. 풀이 과정을 단계별로 보여주고, 왜 그렇게 되는지 원리를 설명합니다. 비슷한 연습 문제도 제안합니다. 한국어로 답변합니다.",
        "greeting": "수학 문제 함께 풀어봐요! 📐",
    },
    "📚 역사 해설가": {
        "system": "당신은 흥미진진한 역사 해설가입니다. 역사적 사건을 마치 이야기처럼 생동감 있게 전달하고, 그 사건의 원인과 영향을 분석합니다. 한국어로 답변합니다.",
        "greeting": "역사 속 이야기를 들려드릴게요! 📚",
    },
    "🇬🇧 영어 코치": {
        "system": "당신은 친근한 영어 코치입니다. 문법, 어휘, 독해, 작문을 도와줍니다. 영어 표현을 알려줄 때는 예문과 함께 설명하고, 한국어와 비교해서 이해를 돕습니다. 기본적으로 한국어로 설명하되 영어 예문을 풍부하게 사용합니다.",
        "greeting": "Let's learn English together! 🇬🇧",
    },
    "🏛️ 소크라테스": {
        "system": "당신은 소크라테스입니다. 절대 직접 답을 알려주지 않고, 질문으로 대화합니다. 학생이 스스로 답에 도달하도록 사고를 유도하는 산파술(문답법)을 사용합니다. 한국어로 대화합니다.",
        "greeting": "나는 소크라테스라네. 🏛️ 자네의 생각을 듣고 싶구만...",
    },
    "💻 코딩 멘토": {
        "system": "당신은 경험 많은 프로그래밍 멘토입니다. 코드를 작성할 때 전체 코드와 함께 주석을 달아 설명합니다. 버그를 찾아주고, 더 나은 방법도 제안합니다. Python, JavaScript 등 다양한 언어를 지원합니다. 한국어로 설명합니다.",
        "greeting": "코딩 세계에 오신 걸 환영합니다! 💻",
    },
    "✍️ 논술 코치": {
        "system": "당신은 논술/글쓰기 전문 코치입니다. 학생의 글을 분석하고, 논리 구조, 주장과 근거, 표현력을 개선하도록 도와줍니다. 구체적인 수정 제안과 함께 좋은 글쓰기 원칙도 알려줍니다. 한국어로 답변합니다.",
        "greeting": "글쓰기 실력을 함께 키워봐요! ✍️",
    },
}

# ============================================================
# 세션 상태 초기화
# ============================================================
def init_session():
    if "rooms" not in st.session_state:
        st.session_state.rooms = {}
    if "current_room" not in st.session_state:
        st.session_state.current_room = None
    if "total_input_tokens" not in st.session_state:
        st.session_state.total_input_tokens = 0
    if "total_output_tokens" not in st.session_state:
        st.session_state.total_output_tokens = 0
    if "total_cost" not in st.session_state:
        st.session_state.total_cost = 0.0

init_session()

def create_room(title=None, persona_key="🎓 기본 도우미"):
    room_id = f"room_{int(time.time() * 1000)}"
    room = {
        "id": room_id,
        "title": title or "새 대화",
        "persona": persona_key,
        "messages": [],
        "token_log": [],
        "created_at": datetime.now().strftime("%m/%d %H:%M"),
        "total_input": 0,
        "total_output": 0,
        "total_cost": 0.0,
    }
    st.session_state.rooms[room_id] = room
    st.session_state.current_room = room_id
    return room_id

def get_current_room():
    if st.session_state.current_room and st.session_state.current_room in st.session_state.rooms:
        return st.session_state.rooms[st.session_state.current_room]
    return None

def generate_room_title(question):
    title = question.strip()
    if len(title) > 30:
        title = title[:30] + "..."
    return title

# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.markdown("## ⚡ CLAUDE CHATBOT")
    st.markdown("---")

    if st.button("➕ 새 대화 시작", use_container_width=True):
        create_room()
        st.rerun()

    st.markdown("---")

    # 모델 선택
    st.markdown("##### 🎯 MODEL SELECT")
    model_name = st.radio(
        "모델",
        list(MODELS.keys()),
        label_visibility="collapsed",
    )

    st.markdown("---")

    # 페르소나 선택
    st.markdown("##### 🎭 PERSONA")
    persona_key = st.selectbox(
        "AI 역할",
        list(PERSONAS.keys()),
        label_visibility="collapsed",
    )
    st.caption(PERSONAS[persona_key]["greeting"])

    st.markdown("---")

    # 채팅방 목록
    st.markdown("##### 💬 CONVERSATIONS")

    rooms_sorted = sorted(
        st.session_state.rooms.values(),
        key=lambda r: r["created_at"],
        reverse=True,
    )

    if not rooms_sorted:
        st.info("아직 대화가 없습니다.\n'새 대화 시작'을 눌러보세요!")
    else:
        for room_item in rooms_sorted:
            is_active = (room_item["id"] == st.session_state.current_room)
            msg_count = len([m for m in room_item["messages"] if m["role"] == "user"])
            col_btn, col_del = st.columns([5, 1])
            with col_btn:
                icon = "▶" if is_active else "　"
                label = f"{icon} {room_item['title']}"
                if st.button(label, key=f"room_{room_item['id']}", use_container_width=True):
                    st.session_state.current_room = room_item["id"]
                    st.rerun()
            with col_del:
                if st.button("✕", key=f"del_{room_item['id']}"):
                    st.session_state.total_input_tokens -= room_item["total_input"]
                    st.session_state.total_output_tokens -= room_item["total_output"]
                    st.session_state.total_cost -= room_item["total_cost"]
                    del st.session_state.rooms[room_item["id"]]
                    if st.session_state.current_room == room_item["id"]:
                        remaining = list(st.session_state.rooms.keys())
                        st.session_state.current_room = remaining[0] if remaining else None
                    st.rerun()

            if is_active:
                st.caption(f"  　{room_item['created_at']} · {msg_count}개 · ${room_item['total_cost']:.4f}")

    st.markdown("---")

    # 누적 통계
    st.markdown("##### 📊 TOTAL STATS")
    c1, c2 = st.columns(2)
    c1.metric("입력 토큰", f"{st.session_state.total_input_tokens:,}")
    c2.metric("출력 토큰", f"{st.session_state.total_output_tokens:,}")
    c3, c4 = st.columns(2)
    c3.metric("총 비용", f"${st.session_state.total_cost:.4f}")
    c4.metric("대화방", f"{len(st.session_state.rooms)}개")

    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; color:#2a4060; font-size:0.7rem; font-family:Rajdhani,sans-serif; letter-spacing:2px;'>"
        "DANGGOK HIGH SCHOOL<br>LEARNING ASSISTANT</div>",
        unsafe_allow_html=True,
    )

# ============================================================
# 메인 영역
# ============================================================
st.markdown("""
<div class="main-header">
    <h1>🤖 CLAUDE AI</h1>
    <div class="ow-subtitle">LEARNING ASSISTANT</div>
    <div class="ow-desc">당곡고등학교 학습 도우미 — 이어서 대화할 수 있어요</div>
</div>
""", unsafe_allow_html=True)

# 현재 채팅방 없으면 생성 유도
room = get_current_room()
if room is None:
    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; padding:4rem 0; color:#3d5a7a;'>"
        "<p style='font-size:3.5rem; margin-bottom:0.5rem;'>💬</p>"
        "<p style='font-family:Rajdhani,sans-serif; font-size:1.3rem; color:#ff9828; letter-spacing:3px; font-weight:600;'>START NEW CONVERSATION</p>"
        "<p style='font-size:0.9rem; margin-top:0.5rem;'>왼쪽 사이드바의 <strong style=\"color:#ffb347;\">➕ 새 대화 시작</strong> 버튼을 눌러주세요</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# 현재 채팅방 정보 표시
col_info1, col_info2, col_info3 = st.columns([3, 2, 2])
with col_info1:
    st.markdown(f"**💬 {room['title']}**")
with col_info2:
    st.markdown(f"<span class='model-badge'>{MODELS[model_name]['short']}</span>", unsafe_allow_html=True)
with col_info3:
    st.markdown(f"<span class='persona-badge'>{persona_key}</span>", unsafe_allow_html=True)

st.markdown("---")

# ============================================================
# 대화 내용 표시
# ============================================================
chat_container = st.container()

with chat_container:
    if not room["messages"]:
        greeting = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🎓 기본 도우미"])["greeting"]
        st.markdown(f"""
        <div class="chat-ai">
            <div class="chat-role chat-role-ai">AI ASSISTANT</div>
            {greeting}
        </div>
        """, unsafe_allow_html=True)
    else:
        for i, msg in enumerate(room["messages"]):
            if msg["role"] == "user":
                st.markdown(f"""
                <div class="chat-user">
                    <div class="chat-role chat-role-user">YOU</div>
                    {msg['content']}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-ai">
                    <div class="chat-role chat-role-ai">AI ASSISTANT</div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(msg["content"])

                token_idx = len([m for m in room["messages"][:i+1] if m["role"] == "assistant"]) - 1
                if token_idx < len(room["token_log"]):
                    tlog = room["token_log"][token_idx]
                    st.markdown(f"""
                    <div class="usage-bar">
                        <div class="usage-chip">📥 INPUT <strong>{tlog['input']:,}</strong></div>
                        <div class="usage-chip">📤 OUTPUT <strong>{tlog['output']:,}</strong></div>
                        <div class="usage-chip">💰 COST <strong>${tlog['cost']:.4f}</strong></div>
                        <div class="usage-chip">⏱ <strong>{tlog.get('elapsed', 0):.1f}s</strong></div>
                    </div>
                    """, unsafe_allow_html=True)

# ============================================================
# 입력 영역
# ============================================================
st.markdown("")

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_area(
        "메시지 입력",
        placeholder="질문을 입력하세요... (Ctrl+Enter로 전송)",
        height=100,
        label_visibility="collapsed",
        key="user_input",
    )

    col_send, col_download, col_clear = st.columns([3, 1.5, 1.5])
    with col_send:
        submitted = st.form_submit_button("🚀 SEND", use_container_width=True)
    with col_download:
        download_btn = st.form_submit_button("📥 EXPORT", use_container_width=True)
    with col_clear:
        clear_btn = st.form_submit_button("🧹 RESET", use_container_width=True)

# 내보내기
if download_btn and room["messages"]:
    export_lines = [f"=== {room['title']} ===", f"Created: {room['created_at']}", ""]
    for msg in room["messages"]:
        role = "나" if msg["role"] == "user" else "AI"
        export_lines.append(f"[{role}]")
        export_lines.append(msg["content"])
        export_lines.append("")
    export_lines.append(
        f"--- Input: {room['total_input']:,} | Output: {room['total_output']:,} | Cost: ${room['total_cost']:.4f} ---"
    )
    export_text = "\n".join(export_lines)
    st.download_button(
        label="💾 다운로드 (.txt)",
        data=export_text.encode("utf-8"),
        file_name=f"chat_{room['id']}.txt",
        mime="text/plain",
    )

# 대화 초기화
if clear_btn:
    st.session_state.total_input_tokens -= room["total_input"]
    st.session_state.total_output_tokens -= room["total_output"]
    st.session_state.total_cost -= room["total_cost"]
    room["messages"] = []
    room["token_log"] = []
    room["total_input"] = 0
    room["total_output"] = 0
    room["total_cost"] = 0.0
    room["title"] = "새 대화"
    st.rerun()

# 메시지 전송
if submitted and user_input.strip():
    if not room["messages"]:
        room["title"] = generate_room_title(user_input)
        room["persona"] = persona_key

    room["messages"].append({"role": "user", "content": user_input.strip()})

    model_info = MODELS[model_name]
    active_persona = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🎓 기본 도우미"])

    context_messages = room["messages"][-20:]
    api_messages = [{"role": m["role"], "content": m["content"]} for m in context_messages]

    with st.spinner("🤔 Claude가 생각하고 있어요..."):
        try:
            client = anthropic.Anthropic(api_key=API_KEY)
            start_time = time.time()

            response = client.messages.create(
                model=model_info["id"],
                max_tokens=4096,
                system=active_persona["system"],
                messages=api_messages,
            )

            elapsed = time.time() - start_time

            answer = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            input_cost = (input_tokens / 1_000_000) * model_info["input_price"]
            output_cost = (output_tokens / 1_000_000) * model_info["output_price"]
            turn_cost = input_cost + output_cost

            room["messages"].append({"role": "assistant", "content": answer})
            room["token_log"].append({
                "input": input_tokens,
                "output": output_tokens,
                "cost": turn_cost,
                "elapsed": elapsed,
            })

            room["total_input"] += input_tokens
            room["total_output"] += output_tokens
            room["total_cost"] += turn_cost

            st.session_state.total_input_tokens += input_tokens
            st.session_state.total_output_tokens += output_tokens
            st.session_state.total_cost += turn_cost

            st.rerun()

        except anthropic.AuthenticationError:
            st.error("❌ API 키가 유효하지 않습니다.")
            room["messages"].pop()
        except anthropic.RateLimitError:
            st.error("⏳ 요청 한도 초과. 잠시 후 다시 시도해주세요.")
            room["messages"].pop()
        except Exception as e:
            st.error(f"❌ 오류: {str(e)}")
            room["messages"].pop()

# ============================================================
# 토큰 차트
# ============================================================
if room["token_log"]:
    st.markdown("---")
    with st.expander("📊 TOKEN USAGE CHART", expanded=False):
        import pandas as pd
        df = pd.DataFrame(room["token_log"])
        df.index = [f"Turn {i+1}" for i in range(len(df))]
        df_chart = df[["input", "output"]].rename(columns={"input": "Input Tokens", "output": "Output Tokens"})
        st.bar_chart(df_chart, color=["#ff9828", "#3b82f6"])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 입력", f"{room['total_input']:,}")
        c2.metric("총 출력", f"{room['total_output']:,}")
        c3.metric("비용", f"${room['total_cost']:.4f}")
        c4.metric("원화", f"₩{room['total_cost'] * 1400:.0f}")
