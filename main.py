import streamlit as st
import anthropic
import time

# ============================================================
# 페이지 기본 설정
# ============================================================
st.set_page_config(
    page_title="🤖 Claude AI 질문하기",
    page_icon="🤖",
    layout="centered",
)

# ============================================================
# 커스텀 CSS - 깔끔한 디자인
# ============================================================
st.markdown("""
<style>
    /* 전체 배경 */
    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    }

    /* 메인 헤더 */
    .main-header {
        text-align: center;
        padding: 2rem 0 1rem 0;
    }
    .main-header h1 {
        color: #ffffff;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }
    .main-header p {
        color: #a0aec0;
        font-size: 1.1rem;
    }

    /* 모델 선택 카드 */
    .model-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 1rem 1.5rem;
        margin-bottom: 1.5rem;
    }

    /* 사용량 박스 */
    .usage-box {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.15);
        border-radius: 12px;
        padding: 1.2rem;
        margin-top: 1rem;
    }
    .usage-title {
        color: #a78bfa;
        font-size: 0.9rem;
        font-weight: 600;
        margin-bottom: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .usage-grid {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 1rem;
    }
    .usage-item {
        text-align: center;
        background: rgba(255,255,255,0.05);
        border-radius: 8px;
        padding: 0.8rem;
    }
    .usage-label {
        color: #94a3b8;
        font-size: 0.75rem;
        margin-bottom: 0.3rem;
    }
    .usage-value {
        color: #e2e8f0;
        font-size: 1.3rem;
        font-weight: 700;
    }
    .usage-sub {
        color: #64748b;
        font-size: 0.7rem;
        margin-top: 0.2rem;
    }

    /* 답변 영역 */
    .answer-box {
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(167,139,250,0.3);
        border-radius: 12px;
        padding: 1.5rem;
        margin-top: 1rem;
        color: #e2e8f0;
        line-height: 1.8;
        font-size: 1rem;
    }
    .answer-label {
        color: #a78bfa;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    /* 경과 시간 */
    .time-badge {
        display: inline-block;
        background: rgba(167,139,250,0.15);
        color: #c4b5fd;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        margin-top: 0.5rem;
    }

    /* 대화 기록 */
    .history-item {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .history-question {
        color: #93c5fd;
        font-weight: 600;
        margin-bottom: 0.5rem;
        font-size: 0.95rem;
    }
    .history-answer {
        color: #cbd5e1;
        font-size: 0.9rem;
        line-height: 1.6;
    }
    .history-meta {
        color: #64748b;
        font-size: 0.75rem;
        margin-top: 0.5rem;
        display: flex;
        gap: 1rem;
    }

    /* Streamlit 기본 요소 커스터마이징 */
    .stTextArea textarea {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        color: #e2e8f0 !important;
        border-radius: 10px !important;
        font-size: 1rem !important;
    }
    .stTextArea textarea:focus {
        border-color: #a78bfa !important;
        box-shadow: 0 0 0 1px #a78bfa !important;
    }
    .stTextArea textarea::placeholder {
        color: #64748b !important;
    }

    /* 버튼 */
    .stButton > button {
        background: linear-gradient(135deg, #7c3aed, #a78bfa) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.6rem 2rem !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        width: 100% !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #6d28d9, #8b5cf6) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 15px rgba(124,58,237,0.4) !important;
    }

    /* 라디오 버튼 */
    .stRadio > div {
        display: flex;
        gap: 1rem;
    }
    .stRadio label {
        color: #e2e8f0 !important;
    }

    /* 사이드바 */
    section[data-testid="stSidebar"] {
        background: rgba(15, 12, 41, 0.95) !important;
    }

    /* 구분선 */
    hr {
        border-color: rgba(255,255,255,0.1) !important;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# API 키 로드 (Streamlit Secrets)
# ============================================================
try:
    API_KEY = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    st.error("⚠️ API 키가 설정되지 않았습니다. Streamlit Cloud의 Secrets에 `ANTHROPIC_API_KEY`를 등록해주세요.")
    st.stop()

# ============================================================
# 모델 정보 정의
# ============================================================
MODELS = {
    "Claude Sonnet 4 (최신)": {
        "id": "claude-sonnet-4-20250514",
        "description": "⚡ 빠르고 효율적 — 일반 질문, 요약, 코딩에 적합",
        "icon": "⚡",
        "input_price": 3.0,    # $3 per 1M input tokens
        "output_price": 15.0,  # $15 per 1M output tokens
    },
    "Claude Opus 4 (최신)": {
        "id": "claude-opus-4-20250514",
        "description": "🧠 최고 성능 — 복잡한 분석, 논술, 심화 질문에 적합",
        "icon": "🧠",
        "input_price": 15.0,   # $15 per 1M input tokens
        "output_price": 75.0,  # $75 per 1M output tokens
    },
}

# ============================================================
# 세션 상태 초기화
# ============================================================
if "history" not in st.session_state:
    st.session_state.history = []
if "total_input_tokens" not in st.session_state:
    st.session_state.total_input_tokens = 0
if "total_output_tokens" not in st.session_state:
    st.session_state.total_output_tokens = 0

# ============================================================
# 헤더
# ============================================================
st.markdown("""
<div class="main-header">
    <h1>🤖 Claude AI에게 질문하기</h1>
    <p>당곡고등학교 학습 도우미 — Claude API 기반</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 모델 선택
# ============================================================
st.markdown("#### 🎯 모델 선택")
model_name = st.radio(
    label="사용할 모델을 선택하세요",
    options=list(MODELS.keys()),
    horizontal=True,
    label_visibility="collapsed",
)
model_info = MODELS[model_name]

st.markdown(f"""
<div class="model-card">
    <span style="font-size:1.2rem;">{model_info['icon']}</span>
    <strong style="color:#e2e8f0;"> {model_name}</strong><br>
    <span style="color:#94a3b8; font-size:0.9rem;">{model_info['description']}</span><br>
    <span style="color:#64748b; font-size:0.8rem;">모델 ID: <code>{model_info['id']}</code></span>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 질문 입력
# ============================================================
st.markdown("#### 💬 질문 입력")
user_question = st.text_area(
    label="질문을 입력하세요",
    placeholder="궁금한 것을 자유롭게 질문해 보세요! 예: '광합성 과정을 쉽게 설명해줘'",
    height=130,
    label_visibility="collapsed",
)

# ============================================================
# 질문 전송
# ============================================================
if st.button("🚀 질문하기", use_container_width=True):
    if not user_question.strip():
        st.warning("질문을 입력해주세요!")
    else:
        with st.spinner("🤔 Claude가 생각하고 있어요..."):
            try:
                client = anthropic.Anthropic(api_key=API_KEY)

                start_time = time.time()

                # API 호출
                response = client.messages.create(
                    model=model_info["id"],
                    max_tokens=4096,
                    system="당신은 당곡고등학교 학생들의 학습을 돕는 친절한 AI 도우미입니다. "
                           "학생들이 이해하기 쉽도록 명확하고 자세하게 설명해주세요. "
                           "한국어로 답변하며, 필요하면 예시를 들어 설명합니다.",
                    messages=[
                        {"role": "user", "content": user_question}
                    ],
                )

                elapsed = time.time() - start_time

                # 응답 파싱
                answer = response.content[0].text
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                total_tokens = input_tokens + output_tokens

                # 비용 계산
                input_cost = (input_tokens / 1_000_000) * model_info["input_price"]
                output_cost = (output_tokens / 1_000_000) * model_info["output_price"]
                total_cost = input_cost + output_cost

                # 누적 토큰 업데이트
                st.session_state.total_input_tokens += input_tokens
                st.session_state.total_output_tokens += output_tokens

                # ---------- 답변 표시 ----------
                st.markdown("""
                <div class="answer-label">
                    <span>✨</span> Claude의 답변
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f'<div class="answer-box">{answer}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="time-badge">⏱️ 응답 시간: {elapsed:.1f}초</div>', unsafe_allow_html=True)

                # ---------- 이번 질문 사용량 ----------
                st.markdown("""
                <div class="usage-box">
                    <div class="usage-title">📊 이번 질문 사용량</div>
                    <div class="usage-grid">
                        <div class="usage-item">
                            <div class="usage-label">입력 토큰</div>
                            <div class="usage-value">{:,}</div>
                            <div class="usage-sub">${:.4f}</div>
                        </div>
                        <div class="usage-item">
                            <div class="usage-label">출력 토큰</div>
                            <div class="usage-value">{:,}</div>
                            <div class="usage-sub">${:.4f}</div>
                        </div>
                        <div class="usage-item">
                            <div class="usage-label">총 비용</div>
                            <div class="usage-value" style="color:#a78bfa;">${:.4f}</div>
                            <div class="usage-sub">≈ ₩{:.1f}</div>
                        </div>
                    </div>
                </div>
                """.format(
                    input_tokens, input_cost,
                    output_tokens, output_cost,
                    total_cost, total_cost * 1400,
                ), unsafe_allow_html=True)

                # ---------- 대화 기록 저장 ----------
                st.session_state.history.insert(0, {
                    "question": user_question,
                    "answer": answer,
                    "model": model_name,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": total_cost,
                    "elapsed": elapsed,
                })

            except anthropic.AuthenticationError:
                st.error("❌ API 키가 유효하지 않습니다. Secrets 설정을 확인해주세요.")
            except anthropic.RateLimitError:
                st.error("⏳ API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
            except Exception as e:
                st.error(f"❌ 오류가 발생했습니다: {str(e)}")

# ============================================================
# 사이드바 - 누적 사용량 & 대화 기록
# ============================================================
with st.sidebar:
    st.markdown("## 📈 누적 사용량")

    total_input = st.session_state.total_input_tokens
    total_output = st.session_state.total_output_tokens
    total_all = total_input + total_output

    col1, col2 = st.columns(2)
    col1.metric("입력 토큰", f"{total_input:,}")
    col2.metric("출력 토큰", f"{total_output:,}")

    st.metric("총 토큰", f"{total_all:,}")
    st.metric("총 질문 수", f"{len(st.session_state.history)}회")

    st.markdown("---")

    # 대화 기록
    st.markdown("## 📝 대화 기록")

    if st.session_state.history:
        if st.button("🗑️ 기록 전체 삭제"):
            st.session_state.history = []
            st.session_state.total_input_tokens = 0
            st.session_state.total_output_tokens = 0
            st.rerun()

        for i, item in enumerate(st.session_state.history):
            # 질문 미리보기 (50자까지)
            preview = item["question"][:50] + ("..." if len(item["question"]) > 50 else "")

            with st.expander(f"💬 {preview}", expanded=(i == 0)):
                st.markdown(f"**모델:** {item['model']}")
                st.markdown(f"**질문:** {item['question']}")
                st.markdown(f"**답변:** {item['answer'][:300]}{'...' if len(item['answer']) > 300 else ''}")
                st.caption(
                    f"입력: {item['input_tokens']:,} · "
                    f"출력: {item['output_tokens']:,} · "
                    f"비용: ${item['cost']:.4f} · "
                    f"시간: {item['elapsed']:.1f}초"
                )
    else:
        st.info("아직 대화 기록이 없습니다.\n질문을 해보세요! 🙂")

    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; color:#64748b; font-size:0.75rem;'>"
        "당곡고등학교 학습 도우미<br>Powered by Claude API</div>",
        unsafe_allow_html=True,
    )
