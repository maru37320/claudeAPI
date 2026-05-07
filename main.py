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
# CSS
# ============================================================
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(160deg, #0f0c29 0%, #1a1145 40%, #302b63 70%, #24243e 100%);
    }

    /* 헤더 */
    .main-header {
        text-align: center;
        padding: 1.5rem 0 0.5rem 0;
    }
    .main-header h1 {
        color: #ffffff;
        font-size: 2.2rem;
        font-weight: 700;
    }
    .main-header p {
        color: #8b92a8;
        font-size: 0.95rem;
    }

    /* 채팅 메시지 */
    .chat-user {
        background: linear-gradient(135deg, #3b2f7b, #4c3f91);
        border: 1px solid rgba(167,139,250,0.25);
        border-radius: 16px 16px 4px 16px;
        padding: 1rem 1.3rem;
        margin: 0.6rem 0;
        color: #e8e0ff;
        max-width: 85%;
        margin-left: auto;
        font-size: 0.95rem;
        line-height: 1.6;
    }
    .chat-ai {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 16px 16px 16px 4px;
        padding: 1rem 1.3rem;
        margin: 0.6rem 0;
        color: #dde2ee;
        max-width: 85%;
        font-size: 0.95rem;
        line-height: 1.7;
    }
    .chat-role {
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.4rem;
    }
    .chat-role-user {
        color: #c4b5fd;
        text-align: right;
    }
    .chat-role-ai {
        color: #6ee7b7;
    }
    .chat-meta {
        font-size: 0.7rem;
        color: #4a5074;
        margin-top: 0.3rem;
    }
    .chat-meta-user {
        text-align: right;
    }

    /* 모델 배지 */
    .model-badge {
        display: inline-block;
        background: rgba(167,139,250,0.15);
        color: #c4b5fd;
        padding: 0.2rem 0.7rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* 사용량 바 */
    .usage-bar {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 0.7rem 1rem;
        margin-top: 0.5rem;
        display: flex;
        justify-content: space-around;
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    .usage-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        color: #94a3b8;
        font-size: 0.78rem;
    }
    .usage-chip strong {
        color: #e2e8f0;
    }

    /* 페르소나 카드 */
    .persona-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        gap: 0.5rem;
        margin: 0.5rem 0;
    }
    .persona-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 0.6rem;
        text-align: center;
        cursor: pointer;
        transition: all 0.2s;
    }
    .persona-card:hover {
        border-color: #a78bfa;
        background: rgba(167,139,250,0.1);
    }
    .persona-icon {
        font-size: 1.5rem;
    }
    .persona-name {
        color: #e2e8f0;
        font-size: 0.8rem;
        font-weight: 600;
        margin-top: 0.2rem;
    }

    /* 사이드바 채팅방 리스트 */
    .room-item {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        padding: 0.6rem 0.8rem;
        margin-bottom: 0.4rem;
        cursor: pointer;
        transition: all 0.2s;
    }
    .room-item:hover {
        background: rgba(167,139,250,0.1);
        border-color: rgba(167,139,250,0.3);
    }
    .room-active {
        background: rgba(167,139,250,0.15) !important;
        border-color: #a78bfa !important;
    }
    .room-title {
        color: #e2e8f0;
        font-size: 0.85rem;
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .room-meta {
        color: #4a5074;
        font-size: 0.7rem;
        margin-top: 0.15rem;
    }

    /* 채팅 입력 영역 */
    .stTextArea textarea {
        background: rgba(255,255,255,0.06) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        color: #e2e8f0 !important;
        border-radius: 12px !important;
        font-size: 0.95rem !important;
    }
    .stTextArea textarea:focus {
        border-color: #a78bfa !important;
        box-shadow: 0 0 0 1px #a78bfa !important;
    }

    /* 버튼 */
    .stButton > button {
        background: linear-gradient(135deg, #7c3aed, #a78bfa) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        transition: all 0.3s !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #6d28d9, #8b5cf6) !important;
        box-shadow: 0 4px 15px rgba(124,58,237,0.4) !important;
    }

    /* 사이드바 */
    section[data-testid="stSidebar"] {
        background: rgba(10, 8, 30, 0.97) !important;
    }

    /* selectbox / radio 커스텀 */
    .stRadio label, .stSelectbox label {
        color: #c4b5fd !important;
    }

    /* 통계 카드 */
    .stat-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 0.8rem;
        text-align: center;
    }
    .stat-value {
        color: #e2e8f0;
        font-size: 1.5rem;
        font-weight: 700;
    }
    .stat-label {
        color: #64748b;
        font-size: 0.75rem;
        margin-top: 0.2rem;
    }
</style>
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
        "short": "Sonnet 4",
        "desc": "빠르고 효율적 — 일반 질문에 적합",
        "input_price": 3.0,
        "output_price": 15.0,
    },
    "🧠 Opus 4": {
        "id": "claude-opus-4-20250514",
        "short": "Opus 4",
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
        "greeting": "과학의 세계에 오신 걸 환영합니다! 🔬 어떤 과학 궁금증이 있나요?",
    },
    "📐 수학 튜터": {
        "system": "당신은 인내심 있는 수학 튜터입니다. 풀이 과정을 단계별로 보여주고, 왜 그렇게 되는지 원리를 설명합니다. 비슷한 연습 문제도 제안합니다. 한국어로 답변합니다.",
        "greeting": "수학 문제 함께 풀어봐요! 📐 어떤 문제가 어렵나요?",
    },
    "📚 역사 해설가": {
        "system": "당신은 흥미진진한 역사 해설가입니다. 역사적 사건을 마치 이야기처럼 생동감 있게 전달하고, 그 사건의 원인과 영향을 분석합니다. 한국어로 답변합니다.",
        "greeting": "역사 속 이야기를 들려드릴게요! 📚 어떤 시대가 궁금하세요?",
    },
    "🇬🇧 영어 코치": {
        "system": "당신은 친근한 영어 코치입니다. 문법, 어휘, 독해, 작문을 도와줍니다. 영어 표현을 알려줄 때는 예문과 함께 설명하고, 한국어와 비교해서 이해를 돕습니다. 기본적으로 한국어로 설명하되 영어 예문을 풍부하게 사용합니다.",
        "greeting": "Let's learn English together! 🇬🇧 영어 질문 환영합니다!",
    },
    "🏛️ 소크라테스": {
        "system": "당신은 소크라테스입니다. 절대 직접 답을 알려주지 않고, 질문으로 대화합니다. 학생이 스스로 답에 도달하도록 사고를 유도하는 산파술(문답법)을 사용합니다. 한국어로 대화합니다.",
        "greeting": "나는 소크라테스라네. 🏛️ 자네의 생각을 듣고 싶구만... 무엇이 궁금한가?",
    },
    "💻 코딩 멘토": {
        "system": "당신은 경험 많은 프로그래밍 멘토입니다. 코드를 작성할 때 전체 코드와 함께 주석을 달아 설명합니다. 버그를 찾아주고, 더 나은 방법도 제안합니다. Python, JavaScript 등 다양한 언어를 지원합니다. 한국어로 설명합니다.",
        "greeting": "코딩 세계에 오신 걸 환영합니다! 💻 어떤 프로그램을 만들어볼까요?",
    },
    "✍️ 논술 코치": {
        "system": "당신은 논술/글쓰기 전문 코치입니다. 학생의 글을 분석하고, 논리 구조, 주장과 근거, 표현력을 개선하도록 도와줍니다. 구체적인 수정 제안과 함께 좋은 글쓰기 원칙도 알려줍니다. 한국어로 답변합니다.",
        "greeting": "글쓰기 실력을 함께 키워봐요! ✍️ 글을 보여주시거나 주제를 알려주세요!",
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
    """새 채팅방 생성"""
    room_id = f"room_{int(time.time() * 1000)}"
    room = {
        "id": room_id,
        "title": title or f"새 대화",
        "persona": persona_key,
        "messages": [],  # [{"role": "user"/"assistant", "content": "..."}]
        "token_log": [],  # [{"input": n, "output": n, "cost": f}]
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
    """첫 질문 기반으로 채팅방 제목 생성"""
    title = question.strip()
    if len(title) > 30:
        title = title[:30] + "..."
    return title

# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.markdown("## 🤖 Claude 챗봇")
    st.markdown("---")

    # ---- 새 채팅 버튼 ----
    if st.button("➕ 새 대화 시작", use_container_width=True):
        create_room()
        st.rerun()

    st.markdown("---")

    # ---- 모델 선택 ----
    st.markdown("##### 🎯 모델 선택")
    model_name = st.radio(
        "모델",
        list(MODELS.keys()),
        label_visibility="collapsed",
    )

    st.markdown("---")

    # ---- 페르소나 선택 ----
    st.markdown("##### 🎭 페르소나")
    persona_key = st.selectbox(
        "AI 역할",
        list(PERSONAS.keys()),
        label_visibility="collapsed",
    )
    st.caption(PERSONAS[persona_key]["greeting"])

    st.markdown("---")

    # ---- 채팅방 목록 ----
    st.markdown("##### 💬 대화 목록")

    rooms_sorted = sorted(
        st.session_state.rooms.values(),
        key=lambda r: r["created_at"],
        reverse=True,
    )

    if not rooms_sorted:
        st.info("아직 대화가 없습니다.\n'새 대화 시작'을 눌러보세요!")
    else:
        for room in rooms_sorted:
            is_active = (room["id"] == st.session_state.current_room)
            msg_count = len([m for m in room["messages"] if m["role"] == "user"])
            col_btn, col_del = st.columns([5, 1])
            with col_btn:
                label = f"{'🟢' if is_active else '💬'} {room['title']}"
                if st.button(
                    label,
                    key=f"room_{room['id']}",
                    use_container_width=True,
                ):
                    st.session_state.current_room = room["id"]
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del_{room['id']}"):
                    # 토큰 통계 차감
                    st.session_state.total_input_tokens -= room["total_input"]
                    st.session_state.total_output_tokens -= room["total_output"]
                    st.session_state.total_cost -= room["total_cost"]
                    del st.session_state.rooms[room["id"]]
                    if st.session_state.current_room == room["id"]:
                        remaining = list(st.session_state.rooms.keys())
                        st.session_state.current_room = remaining[0] if remaining else None
                    st.rerun()

            if is_active:
                st.caption(f"  　{room['created_at']} · {msg_count}개 질문 · ${room['total_cost']:.4f}")

    st.markdown("---")

    # ---- 누적 통계 ----
    st.markdown("##### 📊 전체 통계")
    c1, c2 = st.columns(2)
    c1.metric("총 입력", f"{st.session_state.total_input_tokens:,}")
    c2.metric("총 출력", f"{st.session_state.total_output_tokens:,}")
    c3, c4 = st.columns(2)
    c3.metric("총 비용", f"${st.session_state.total_cost:.4f}")
    c4.metric("대화방 수", f"{len(st.session_state.rooms)}개")

    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; color:#4a5074; font-size:0.7rem;'>"
        "당곡고등학교 학습 도우미<br>Powered by Claude API</div>",
        unsafe_allow_html=True,
    )

# ============================================================
# 메인 영역
# ============================================================
st.markdown("""
<div class="main-header">
    <h1>🤖 Claude AI 챗봇</h1>
    <p>당곡고등학교 학습 도우미 — 이어서 대화할 수 있어요</p>
</div>
""", unsafe_allow_html=True)

# ---- 현재 채팅방이 없으면 생성 유도 ----
room = get_current_room()
if room is None:
    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; padding:3rem; color:#8b92a8;'>"
        "<p style='font-size:3rem;'>💬</p>"
        "<p style='font-size:1.2rem;'>새 대화를 시작해보세요!</p>"
        "<p>왼쪽 사이드바의 <strong>➕ 새 대화 시작</strong> 버튼을 눌러주세요</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# ---- 현재 채팅방 정보 표시 ----
col_info1, col_info2, col_info3 = st.columns([3, 2, 2])
with col_info1:
    st.markdown(f"**💬 {room['title']}**")
with col_info2:
    st.markdown(f"<span class='model-badge'>{MODELS[model_name]['short']}</span>", unsafe_allow_html=True)
with col_info3:
    persona_icon = persona_key.split(" ")[0]
    st.markdown(f"<span class='model-badge'>{persona_key}</span>", unsafe_allow_html=True)

st.markdown("---")

# ============================================================
# 대화 내용 표시
# ============================================================
chat_container = st.container()

with chat_container:
    if not room["messages"]:
        # 페르소나 인사말
        greeting = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🎓 기본 도우미"])["greeting"]
        st.markdown(f"""
        <div class="chat-ai">
            <div class="chat-role chat-role-ai">AI</div>
            {greeting}
        </div>
        """, unsafe_allow_html=True)
    else:
        for i, msg in enumerate(room["messages"]):
            if msg["role"] == "user":
                st.markdown(f"""
                <div class="chat-user">
                    <div class="chat-role chat-role-user">나</div>
                    {msg['content']}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-ai">
                    <div class="chat-role chat-role-ai">AI</div>
                </div>
                """, unsafe_allow_html=True)
                # 마크다운 렌더링 (코드블록, 수식 등 지원)
                st.markdown(msg["content"])

                # 해당 턴의 사용량 표시
                token_idx = len([m for m in room["messages"][:i+1] if m["role"] == "assistant"]) - 1
                if token_idx < len(room["token_log"]):
                    tlog = room["token_log"][token_idx]
                    st.markdown(f"""
                    <div class="usage-bar">
                        <div class="usage-chip">📥 입력 <strong>{tlog['input']:,}</strong></div>
                        <div class="usage-chip">📤 출력 <strong>{tlog['output']:,}</strong></div>
                        <div class="usage-chip">💰 <strong>${tlog['cost']:.4f}</strong></div>
                        <div class="usage-chip">⏱️ <strong>{tlog.get('elapsed', 0):.1f}s</strong></div>
                    </div>
                    """, unsafe_allow_html=True)

# ============================================================
# 입력 영역
# ============================================================
st.markdown("")  # 여백

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
        submitted = st.form_submit_button("🚀 전송", use_container_width=True)
    with col_download:
        download_btn = st.form_submit_button("📥 내보내기", use_container_width=True)
    with col_clear:
        clear_btn = st.form_submit_button("🧹 대화 초기화", use_container_width=True)

# ---- 대화 내보내기 ----
if download_btn and room["messages"]:
    export_lines = [f"=== {room['title']} ===", f"생성: {room['created_at']}", ""]
    for msg in room["messages"]:
        role = "나" if msg["role"] == "user" else "AI"
        export_lines.append(f"[{role}]")
        export_lines.append(msg["content"])
        export_lines.append("")
    export_lines.append(f"--- 총 입력 토큰: {room['total_input']:,} | 출력 토큰: {room['total_output']:,} | 비용: ${room['total_cost']:.4f} ---")
    export_text = "\n".join(export_lines)

    st.download_button(
        label="💾 텍스트 파일 다운로드",
        data=export_text.encode("utf-8"),
        file_name=f"chat_{room['id']}.txt",
        mime="text/plain",
    )

# ---- 대화 초기화 ----
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

# ---- 메시지 전송 ----
if submitted and user_input.strip():
    # 첫 메시지면 제목 자동 생성 & 페르소나 저장
    if not room["messages"]:
        room["title"] = generate_room_title(user_input)
        room["persona"] = persona_key

    # 유저 메시지 추가
    room["messages"].append({"role": "user", "content": user_input.strip()})

    # API 호출 준비 - 전체 대화 맥락 전송
    model_info = MODELS[model_name]
    active_persona = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🎓 기본 도우미"])

    # 대화 맥락 (토큰 절약을 위해 최근 20개 메시지만)
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

            # 응답 처리
            answer = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            input_cost = (input_tokens / 1_000_000) * model_info["input_price"]
            output_cost = (output_tokens / 1_000_000) * model_info["output_price"]
            turn_cost = input_cost + output_cost

            # AI 메시지 추가
            room["messages"].append({"role": "assistant", "content": answer})
            room["token_log"].append({
                "input": input_tokens,
                "output": output_tokens,
                "cost": turn_cost,
                "elapsed": elapsed,
            })

            # 채팅방 통계 업데이트
            room["total_input"] += input_tokens
            room["total_output"] += output_tokens
            room["total_cost"] += turn_cost

            # 전체 통계 업데이트
            st.session_state.total_input_tokens += input_tokens
            st.session_state.total_output_tokens += output_tokens
            st.session_state.total_cost += turn_cost

            st.rerun()

        except anthropic.AuthenticationError:
            st.error("❌ API 키가 유효하지 않습니다.")
            room["messages"].pop()  # 유저 메시지 롤백
        except anthropic.RateLimitError:
            st.error("⏳ 요청 한도 초과. 잠시 후 다시 시도해주세요.")
            room["messages"].pop()
        except Exception as e:
            st.error(f"❌ 오류: {str(e)}")
            room["messages"].pop()

# ============================================================
# 하단 - 현재 채팅방 누적 사용량 차트
# ============================================================
if room["token_log"]:
    st.markdown("---")

    with st.expander("📊 이 대화의 토큰 사용량 그래프", expanded=False):
        import pandas as pd

        df = pd.DataFrame(room["token_log"])
        df.index = [f"턴 {i+1}" for i in range(len(df))]
        df_chart = df[["input", "output"]].rename(columns={"input": "입력 토큰", "output": "출력 토큰"})

        st.bar_chart(df_chart, color=["#7c3aed", "#6ee7b7"])

        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        col_s1.metric("총 입력", f"{room['total_input']:,}")
        col_s2.metric("총 출력", f"{room['total_output']:,}")
        col_s3.metric("총 비용", f"${room['total_cost']:.4f}")
        col_s4.metric("원화 환산", f"₩{room['total_cost'] * 1400:.0f}")
