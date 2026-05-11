import streamlit as st
import anthropic
import time
import json
import hashlib
import base64
import math
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(page_title="Claude AI", page_icon="✦", layout="wide")

# ============================================================
# Google Sheets 연결
# ============================================================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def get_gsheet_connection():
    gcp_info = {
        "type": st.secrets["type"],
        "project_id": st.secrets["project_id"],
        "private_key_id": st.secrets["private_key_id"],
        "private_key": st.secrets["private_key"],
        "client_email": st.secrets["client_email"],
        "client_id": st.secrets["client_id"],
        "auth_uri": st.secrets["auth_uri"],
        "token_uri": st.secrets["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["client_x509_cert_url"],
        "universe_domain": st.secrets["universe_domain"],
    }
    credentials = Credentials.from_service_account_info(gcp_info, scopes=SCOPES)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_url(st.secrets["SPREADSHEET_URL"])
    return spreadsheet

def get_sheet(sheet_name):
    spreadsheet = get_gsheet_connection()
    return spreadsheet.worksheet(sheet_name)

# ============================================================
# 유저 관리
# ============================================================
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def register_user(username, password, display_name):
    sheet = get_sheet("users")
    all_users = sheet.col_values(1)
    if username in all_users:
        return False, "이미 존재하는 아이디입니다."
    sheet.append_row([
        username,
        hash_password(password),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        display_name,
    ])
    stats_sheet = get_sheet("stats")
    stats_sheet.append_row([username, 0, 0, 0.0, "", "dark"])
    return True, "회원가입 성공!"

def login_user(username, password):
    sheet = get_sheet("users")
    all_data = sheet.get_all_records()
    for row in all_data:
        if row["username"] == username and row["password_hash"] == hash_password(password):
            return True, row.get("display_name", username)
    return False, ""

# ============================================================
# 구글시트 50000자 제한 우회 — 긴 텍스트 분할 저장
# ============================================================
MAX_CELL_CHARS = 45000  # 안전 마진 포함

def truncate_for_sheet(text: str) -> str:
    """셀 저장 전 길이 초과 시 잘라냄"""
    if len(text) > MAX_CELL_CHARS:
        return text[:MAX_CELL_CHARS] + "\n...[truncated]"
    return text

def safe_json_for_sheet(obj) -> str:
    """메시지 리스트를 JSON으로 변환하되, 각 content를 45000자 이내로 제한"""
    if isinstance(obj, list):
        safe_list = []
        for item in obj:
            if isinstance(item, dict) and "content" in item:
                safe_item = dict(item)
                safe_item["content"] = truncate_for_sheet(str(item["content"]))
                safe_list.append(safe_item)
            else:
                safe_list.append(item)
        raw = json.dumps(safe_list, ensure_ascii=False)
    else:
        raw = json.dumps(obj, ensure_ascii=False)
    # 최종 JSON 자체도 45000자 제한
    return truncate_for_sheet(raw) if len(raw) > MAX_CELL_CHARS else raw

# ============================================================
# 대화 저장/불러오기
# ============================================================
def save_room_to_sheet(username, room):
    sheet = get_sheet("conversations")
    all_data = sheet.get_all_records()
    row_idx = None
    for i, row in enumerate(all_data):
        if row["username"] == username and row["room_id"] == room["id"]:
            row_idx = i + 2
            break

    messages_json = safe_json_for_sheet(room["messages"])
    token_json = safe_json_for_sheet(room["token_log"])

    row_data = [
        username, room["id"], room["title"],
        room.get("persona", "🔬 학습 도우미"), room["created_at"],
        messages_json,
        token_json,
        room["total_input"], room["total_output"], room["total_cost"],
    ]
    try:
        if row_idx:
            sheet.update(f"A{row_idx}:J{row_idx}", [row_data])
        else:
            sheet.append_row(row_data)
    except Exception as e:
        # 저장 실패 시 메시지 수를 줄여서 재시도
        st.warning(f"시트 저장 중 오류 (최근 메시지만 보존): {e}")
        trimmed_messages = room["messages"][-10:]
        row_data[5] = safe_json_for_sheet(trimmed_messages)
        try:
            if row_idx:
                sheet.update(f"A{row_idx}:J{row_idx}", [row_data])
            else:
                sheet.append_row(row_data)
        except Exception as e2:
            st.error(f"시트 저장 실패: {e2}")

def delete_room_from_sheet(username, room_id):
    sheet = get_sheet("conversations")
    all_data = sheet.get_all_records()
    for i, row in enumerate(all_data):
        if row["username"] == username and row["room_id"] == room_id:
            sheet.delete_rows(i + 2)
            break

def load_rooms_from_sheet(username):
    sheet = get_sheet("conversations")
    all_data = sheet.get_all_records()
    rooms = {}
    for row in all_data:
        if row["username"] == username:
            room_id = row["room_id"]
            try:
                messages = json.loads(row["messages_json"]) if row["messages_json"] else []
            except:
                messages = []
            try:
                token_log = json.loads(row["token_log_json"]) if row["token_log_json"] else []
            except:
                token_log = []
            rooms[room_id] = {
                "id": room_id, "title": row["room_title"],
                "persona": row.get("persona", "🔬 학습 도우미"),
                "messages": messages, "token_log": token_log,
                "created_at": row["created_at"],
                "total_input": int(row.get("total_input", 0)),
                "total_output": int(row.get("total_output", 0)),
                "total_cost": float(row.get("total_cost", 0.0)),
            }
    return rooms

def save_user_stats(username):
    sheet = get_sheet("stats")
    all_data = sheet.get_all_records()
    row_idx = None
    for i, row in enumerate(all_data):
        if row["username"] == username:
            row_idx = i + 2
            break
    theme = st.session_state.get("theme", "dark")
    row_data = [
        username,
        st.session_state.get("total_input_tokens", 0),
        st.session_state.get("total_output_tokens", 0),
        st.session_state.get("total_cost", 0.0),
        st.session_state.get("current_room", ""),
        theme,
    ]
    if row_idx:
        sheet.update(f"A{row_idx}:F{row_idx}", [row_data])
    else:
        sheet.append_row(row_data)

def load_user_stats(username):
    sheet = get_sheet("stats")
    all_data = sheet.get_all_records()
    for row in all_data:
        if row["username"] == username:
            st.session_state.total_input_tokens = int(row.get("total_input_tokens", 0))
            st.session_state.total_output_tokens = int(row.get("total_output_tokens", 0))
            st.session_state.total_cost = float(row.get("total_cost", 0.0))
            st.session_state.current_room = row.get("current_room", "")
            st.session_state.theme = row.get("theme", "dark")
            return
    st.session_state.total_input_tokens = 0
    st.session_state.total_output_tokens = 0
    st.session_state.total_cost = 0.0
    st.session_state.current_room = ""
    st.session_state.theme = "dark"

# ============================================================
# 테마 CSS
# ============================================================
def get_theme_css(theme):
    if theme == "light":
        select_bg = "#ffffff"
        select_text = "#1a1a1a"
        select_hover = "#f0efea"
        persona_scroll_bg = "#e8e7e2"
        persona_scroll_border = "rgba(0,0,0,0.1)"
        btn_send_bg = "#1a1a1a"
        btn_send_color = "#ffffff"
        btn_icon_bg = "#e0dfd9"
        btn_icon_color = "#333333"
        btn_icon_border = "rgba(0,0,0,0.18)"
        return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
* {{ box-sizing: border-box; }}
.stApp {{ background: #f5f4ef !important; font-family: 'Inter', -apple-system, sans-serif; color: #1a1a1a !important; }}

section[data-testid="stSidebar"] {{ background: #eeede8 !important; border-right: 1px solid rgba(0,0,0,0.08) !important; }}
section[data-testid="stSidebar"] * {{ color: #1a1a1a !important; }}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaption {{ color: #555 !important; }}

/* 셀렉트박스 — 라이트 모드 */
.stSelectbox > div > div {{
    background: {select_bg} !important;
    border: 1px solid rgba(0,0,0,0.15) !important;
    color: {select_text} !important;
    border-radius: 8px !important;
}}
.stSelectbox > div > div > div {{ color: {select_text} !important; }}
[data-baseweb="popover"] {{ background: {select_bg} !important; }}
[data-baseweb="menu"] {{ background: {select_bg} !important; }}
[data-baseweb="option"] {{ background: {select_bg} !important; color: {select_text} !important; }}
[data-baseweb="option"]:hover {{ background: {select_hover} !important; }}

/* 페르소나 스크롤 영역 — 라이트 모드 배경 반전 */
.persona-scroll-area {{
    background: {persona_scroll_bg} !important;
    border: 1px solid {persona_scroll_border} !important;
    border-radius: 10px !important;
    padding: 6px !important;
    max-height: 220px !important;
    overflow-y: auto !important;
}}
.persona-scroll-area * {{ color: {select_text} !important; }}

.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown h1,
.stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {{ color: #1a1a1a !important; }}
[data-testid="stMetricValue"] {{ color: #1a1a1a !important; font-weight: 600 !important; }}
[data-testid="stMetricLabel"] {{ color: #666 !important; }}
.stCaption, small {{ color: #666 !important; }}

.stTextArea textarea {{
    background: #ffffff !important; border: 1px solid rgba(0,0,0,0.12) !important;
    border-radius: 14px !important; color: #1a1a1a !important;
    font-size: 0.95rem !important; line-height: 1.6 !important;
    padding: 14px 16px !important; resize: none !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
}}
.stTextArea textarea:focus {{
    border-color: rgba(0,0,0,0.3) !important;
    box-shadow: 0 0 0 3px rgba(0,0,0,0.06) !important; outline: none !important;
}}
.stTextArea textarea::placeholder {{ color: #aaa !important; }}
.stTextInput input {{
    background: #ffffff !important; border: 1px solid rgba(0,0,0,0.12) !important;
    border-radius: 10px !important; color: #1a1a1a !important;
}}

/* 버튼 기본 */
.stButton > button {{
    font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
    font-size: 0.82rem !important; border-radius: 8px !important;
    transition: all 0.18s ease !important;
    background: {btn_icon_bg} !important;
    border: 1px solid {btn_icon_border} !important;
    color: {btn_icon_color} !important;
}}
.stButton > button:hover {{ background: #d0cec8 !important; color: #1a1a1a !important; }}

/* Send 버튼 */
button[data-testid="send_btn"] {{
    background: {btn_send_bg} !important;
    color: {btn_send_color} !important;
    border: none !important;
    border-radius: 50% !important;
    width: 40px !important; height: 40px !important;
    padding: 0 !important; font-size: 1.1rem !important;
}}

/* 아이콘 버튼들 (canvas, export, clear) */
button[data-testid="canvas_btn"],
button[data-testid="export_btn"],
button[data-testid="clear_btn"] {{
    background: {btn_icon_bg} !important;
    border: 1px solid {btn_icon_border} !important;
    color: {btn_icon_color} !important;
    border-radius: 8px !important;
    width: 40px !important; height: 40px !important;
    padding: 0 !important; font-size: 0.95rem !important;
}}
button[data-testid="canvas_btn"]:hover {{ background: #d0cec8 !important; }}
button[data-testid="clear_btn"]:hover {{ background: rgba(220,60,60,0.15) !important; color: #c03030 !important; border-color: rgba(200,50,50,0.4) !important; }}

.msg-user {{
    background: #ffffff; border: 1px solid rgba(0,0,0,0.08);
    border-radius: 18px 18px 4px 18px; padding: 12px 16px;
    margin: 6px 0 6px auto; max-width: 88%; color: #1a1a1a;
    font-size: 0.93rem; line-height: 1.65; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}}
.msg-ai {{ background: transparent; padding: 4px 0; margin: 6px 0; max-width: 92%; color: #1a1a1a; font-size: 0.93rem; line-height: 1.7; }}
.msg-role {{ font-size: 0.7rem; font-weight: 600; letter-spacing: 0.04em; margin-bottom: 4px; text-transform: uppercase; }}
.msg-role-user {{ text-align: right; color: #888; }}
.msg-role-ai {{ color: #888; }}
.token-bar {{ display: flex; gap: 12px; flex-wrap: wrap; padding: 6px 0; font-size: 0.72rem; color: #999; }}
.token-bar strong {{ color: #555; }}

.quiz-q {{ font-weight: 600; color: #1a1a1a; margin-bottom: 10px; line-height: 1.6; }}
.quiz-exp {{ background: rgba(0,0,0,0.04); border-left: 3px solid #999; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-top: 10px; font-size: 0.86rem; color: #555; line-height: 1.6; }}
.score-box {{ background: #fff; border: 1px solid rgba(0,0,0,0.1); border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 16px; }}
.score-num {{ font-size: 2.4rem; font-weight: 700; color: #1a1a1a; }}

.pasted-chip {{
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(0,0,0,0.07); border: 1px solid rgba(0,0,0,0.14);
    border-radius: 8px; padding: 5px 10px;
    font-size: 0.8rem; font-weight: 500; color: #444; margin: 2px 4px 2px 0;
    cursor: pointer;
}}
.img-thumb {{
    width: 72px; height: 54px; object-fit: cover;
    border-radius: 8px; border: 1px solid rgba(0,0,0,0.12);
    cursor: pointer; margin: 2px 4px 2px 0; display: inline-block;
    transition: opacity 0.15s; vertical-align: middle;
}}
.img-thumb:hover {{ opacity: 0.8; }}

hr {{ border-color: rgba(0,0,0,0.08) !important; }}
.streamlit-expanderHeader {{ color: #1a1a1a !important; }}

/* 팝업 */
.popup-overlay {{
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    z-index: 9999; display: flex; align-items: center; justify-content: center;
}}
.popup-box {{
    background: #ffffff; border-radius: 14px; padding: 24px;
    max-width: 80vw; max-height: 85vh; overflow: auto;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}}
</style>
"""
    else:  # dark
        return """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
* { box-sizing: border-box; }
.stApp { background: #1c1c1e !important; font-family: 'Inter', -apple-system, sans-serif; color: #e8e6e1 !important; }

section[data-testid="stSidebar"] { background: #161618 !important; border-right: 1px solid rgba(255,255,255,0.06) !important; }
section[data-testid="stSidebar"] * { color: #e8e6e1 !important; }
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaption { color: #888 !important; }

.stSelectbox > div > div {
    background: #2a2a2d !important; border: 1px solid rgba(255,255,255,0.1) !important;
    color: #e8e6e1 !important; border-radius: 8px !important;
}
.stSelectbox > div > div > div { color: #e8e6e1 !important; }
[data-baseweb="popover"] { background: #2a2a2d !important; }
[data-baseweb="menu"] { background: #2a2a2d !important; }
[data-baseweb="option"] { background: #2a2a2d !important; color: #e8e6e1 !important; }
[data-baseweb="option"]:hover { background: #3a3a3d !important; }
.stSelectbox svg { fill: #888 !important; }

/* 페르소나 스크롤 영역 — 다크 모드 */
.persona-scroll-area {
    background: #222224 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important;
    padding: 6px !important;
    max-height: 220px !important;
    overflow-y: auto !important;
}
.persona-scroll-area * { color: #e8e6e1 !important; }

.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown h1,
.stMarkdown h2, .stMarkdown h3, .stMarkdown h4 { color: #e8e6e1 !important; }
[data-testid="stMetricValue"] { color: #e8e6e1 !important; font-weight: 600 !important; }
[data-testid="stMetricLabel"] { color: #777 !important; }
.stCaption, small { color: #666 !important; }
.stInfo { color: #e8e6e1 !important; background: rgba(255,255,255,0.06) !important; }

.stTextArea textarea {
    background: #2a2a2d !important; border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 14px !important; color: #e8e6e1 !important;
    font-size: 0.95rem !important; line-height: 1.6 !important;
    padding: 14px 16px !important; resize: none !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.2) !important; caret-color: #e8e6e1 !important;
}
.stTextArea textarea:focus {
    border-color: rgba(255,255,255,0.25) !important;
    box-shadow: 0 0 0 3px rgba(255,255,255,0.05) !important; outline: none !important;
}
.stTextArea textarea::placeholder { color: #555 !important; }
.stTextInput input {
    background: #2a2a2d !important; border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important; color: #e8e6e1 !important; caret-color: #e8e6e1 !important;
}
.stTextInput input:focus { border-color: rgba(255,255,255,0.25) !important; }

/* 버튼 기본 — 다크에서 잘 보이게 */
.stButton > button {
    font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
    font-size: 0.82rem !important; border-radius: 8px !important;
    transition: all 0.18s ease !important;
    background: rgba(255,255,255,0.12) !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
    color: #e8e6e1 !important;
}
.stButton > button:hover {
    background: rgba(255,255,255,0.22) !important;
    border-color: rgba(255,255,255,0.35) !important; color: #fff !important;
}

.msg-user {
    background: #2a2a2d; border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px 18px 4px 18px; padding: 12px 16px;
    margin: 6px 0 6px auto; max-width: 88%; color: #e8e6e1;
    font-size: 0.93rem; line-height: 1.65; box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.msg-ai { background: transparent; padding: 4px 0; margin: 6px 0; max-width: 92%; color: #e8e6e1; font-size: 0.93rem; line-height: 1.7; }
.msg-role { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.04em; margin-bottom: 4px; text-transform: uppercase; }
.msg-role-user { text-align: right; color: #555; }
.msg-role-ai { color: #555; }
.token-bar { display: flex; gap: 12px; flex-wrap: wrap; padding: 6px 0; font-size: 0.72rem; color: #555; }
.token-bar strong { color: #888; }

.quiz-q { font-weight: 600; color: #e8e6e1; margin-bottom: 10px; line-height: 1.6; }
.quiz-exp { background: rgba(255,255,255,0.04); border-left: 3px solid #555; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-top: 10px; font-size: 0.86rem; color: #aaa; line-height: 1.6; }
.score-box { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 16px; }
.score-num { font-size: 2.4rem; font-weight: 700; color: #e8e6e1; }

.pasted-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(255,255,255,0.09); border: 1px solid rgba(255,255,255,0.16);
    border-radius: 8px; padding: 5px 10px;
    font-size: 0.8rem; font-weight: 500; color: #bbb; margin: 2px 4px 2px 0;
    cursor: pointer;
}
.img-thumb {
    width: 72px; height: 54px; object-fit: cover;
    border-radius: 8px; border: 1px solid rgba(255,255,255,0.12);
    cursor: pointer; margin: 2px 4px 2px 0; display: inline-block;
    transition: opacity 0.15s; vertical-align: middle;
}
.img-thumb:hover { opacity: 0.75; }

hr { border-color: rgba(255,255,255,0.06) !important; }
.streamlit-expanderHeader { color: #e8e6e1 !important; }
.streamlit-expanderContent { color: #e8e6e1 !important; }
.stCodeBlock { border-radius: 10px !important; }
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 3px; }

.popup-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.75);
    z-index: 9999; display: flex; align-items: center; justify-content: center;
}
.popup-box {
    background: #2a2a2d; border-radius: 14px; padding: 24px;
    max-width: 80vw; max-height: 85vh; overflow: auto;
    box-shadow: 0 24px 64px rgba(0,0,0,0.6);
}
</style>
"""

# ============================================================
# API 키
# ============================================================
try:
    API_KEY = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    st.error("⚠️ `ANTHROPIC_API_KEY`가 설정되지 않았습니다.")
    st.stop()

# ============================================================
# 모델
# ============================================================
MODELS = {
    "Sonnet 4.5": {
        "id": "claude-sonnet-4-20250514",
        "input_price": 3.0,
        "output_price": 15.0,
    },
    "Opus 4.5": {
        "id": "claude-opus-4-20250514",
        "input_price": 15.0,
        "output_price": 75.0,
    },
}

# ============================================================
# 페르소나 — 유용한 기능 중심으로만
# ============================================================
PERSONAS = {
    "🔬 학습 도우미": {
        "system": "당신은 당곡고등학교 학생들의 학습을 돕는 AI 도우미입니다. 핵심만 간결하게, 이해하기 쉽게 설명합니다. 한국어로 답변합니다.",
        "greeting": "무엇이든 물어보세요.",
        "canvas_type": None,
    },
    "📐 수학 · 과학 튜터": {
        "system": "당신은 수학/과학 튜터입니다. 단계별 풀이와 직관적 설명을 제공합니다. 수식은 명확하게 표현합니다. 한국어로 답변합니다.",
        "greeting": "수학·과학 문제를 입력하세요.",
        "canvas_type": "doc",
    },
    "🗺️ 마인드맵 메이커": {
        "system": """당신은 마인드맵 전문가입니다. 주제를 받으면 반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{"title": "중심 주제", "nodes": [{"id": "1", "label": "가지1", "children": [{"id": "1-1", "label": "세부1"}]}, ...]}
최소 4개 이상의 주요 가지와 각 가지에 2-3개 세부항목을 포함하세요. 한국어로 작성합니다.""",
        "greeting": "마인드맵으로 만들 주제를 알려주세요.",
        "canvas_type": "mindmap",
    },
    "🧩 퀴즈 출제자": {
        "system": """당신은 퀴즈 출제자입니다. 주어진 주제에 대해 4지선다 퀴즈를 JSON 형식으로 출제합니다.
반드시 아래 형식의 순수한 JSON만 출력하세요 (코드블록 없이, 설명 없이):
[{"question": "문제", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "해설"}]
answer는 0-3 정수(정답 옵션의 인덱스). 한국어로 최소 3문제 이상 출제합니다. JSON 외 다른 텍스트를 절대 포함하지 마세요.""",
        "greeting": "퀴즈 주제를 알려주세요.",
        "canvas_type": "quiz",
    },
    "💻 코딩 멘토": {
        "system": """당신은 프로그래밍 멘토입니다. 코드를 작성할 때는 반드시 아래 JSON 형식으로만 응답하세요 (코드블록 없이):
{"language": "python", "code": "코드 내용", "explanation": "설명", "title": "제목"}
language는 python/javascript/html/css/java/cpp/sql 중 하나. 한국어로 설명합니다.""",
        "greeting": "어떤 코드가 필요한가요?",
        "canvas_type": "code",
    },
    "✍️ 글쓰기 · 논술 코치": {
        "system": "당신은 글쓰기 코치입니다. 논리 구조, 표현력, 문장력을 체계적으로 개선합니다. 첨삭 시 구체적인 수정안을 제시합니다. 한국어로 답변합니다.",
        "greeting": "글이나 주제를 입력하면 첨삭·개선해드립니다.",
        "canvas_type": "doc",
    },
    "📊 데이터 분석가": {
        "system": """당신은 데이터 분석 전문가입니다. 데이터를 분석하고 인사이트를 도출합니다.
분석 코드가 필요하면 반드시 아래 JSON 형식으로만 응답하세요:
{"language": "python", "code": "코드 내용", "explanation": "설명", "title": "분석 코드"}
한국어로 답변합니다.""",
        "greeting": "데이터나 분석 요청을 입력하세요.",
        "canvas_type": "code",
    },
    "🌐 번역 · 영어 코치": {
        "system": "당신은 영어 전문가입니다. 번역, 문법 교정, 표현 개선을 제공합니다. 번역은 자연스러운 표현을 우선시하고, 영어 학습에 도움이 되는 설명을 덧붙입니다. 한국어로 설명합니다.",
        "greeting": "번역하거나 교정할 텍스트를 입력하세요.",
        "canvas_type": "doc",
    },
    "🧠 비판적 사고 코치": {
        "system": """당신은 비판적 사고 코치입니다. 어떤 주제나 주장에 대해:
1. 핵심 전제 분석
2. 논리적 오류 검토
3. 다양한 관점 제시
4. 반론 구성
을 체계적으로 수행합니다. 한국어로 답변합니다.""",
        "greeting": "분석할 주제나 주장을 입력하세요.",
        "canvas_type": "doc",
    },
    "📅 플래너 · 스케줄러": {
        "system": """당신은 계획 전문가입니다. 목표나 과제를 입력받으면 구체적이고 실행 가능한 계획을 세워줍니다.
계획은 아래 구조로 문서로 정리합니다:
- 전체 목표 요약
- 단계별 세부 계획 (날짜/기간 포함)
- 주의사항 및 팁
한국어로 답변합니다.""",
        "greeting": "달성하고 싶은 목표나 과제를 알려주세요.",
        "canvas_type": "doc",
    },
    "🎯 면접 · 자소서 코치": {
        "system": """당신은 취업/입시 컨설턴트입니다. 자기소개서 첨삭, 면접 답변 준비, 포트폴리오 조언을 제공합니다.
피드백은 구체적이고 실용적으로 제시합니다. 한국어로 답변합니다.""",
        "greeting": "자소서 내용이나 면접 질문을 입력하세요.",
        "canvas_type": "doc",
    },
}

# ============================================================
# 세션 초기화
# ============================================================
defaults = {
    "logged_in": False, "username": "", "display_name": "",
    "rooms": {}, "current_room": "",
    "total_input_tokens": 0, "total_output_tokens": 0, "total_cost": 0.0,
    "theme": "dark", "data_loaded": False,
    # Canvas 상태
    "canvas_open": False,
    "canvas_type": None,
    "canvas_content": None,
    "canvas_title": "Canvas",
    "quiz_answers": {}, "quiz_submitted": False,
    "code_content": "", "code_language": "python", "code_output": "",
    # 팝업
    "popup_type": None,
    "popup_content": None,
    "popup_label": "",
    # 파일 첨부 대기
    "pending_file_b64": None,
    "pending_file_type": None,
    "pending_file_name": None,
    "pending_file_is_image": False,
    "pending_file_api": None,
    # 스트리밍 중 임시 저장
    "streaming_answer": "",
    "is_streaming": False,
    # 액션 플래그 (폼 외부 버튼용)
    "_action": None,
    "_action_data": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# CSS 적용
# ============================================================
st.markdown(get_theme_css(st.session_state.theme), unsafe_allow_html=True)

# ============================================================
# 로그인 / 회원가입
# ============================================================
if not st.session_state.logged_in:
    st.markdown("""
    <div style="text-align:center; padding:4rem 0 2rem 0;">
        <div style="font-size:1.8rem; font-weight:300; letter-spacing:-0.02em; margin-bottom:6px;">✦ Claude AI</div>
        <div style="font-size:0.8rem; color:#888; letter-spacing:0.1em; text-transform:uppercase;">Learning Assistant</div>
    </div>
    """, unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["로그인", "회원가입"])

    with tab_login:
        with st.form("login_form"):
            login_id = st.text_input("아이디", key="login_id")
            login_pw = st.text_input("비밀번호", type="password", key="login_pw")
            login_btn = st.form_submit_button("로그인", use_container_width=True)
        if login_btn:
            if login_id and login_pw:
                ok, dname = login_user(login_id, login_pw)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.username = login_id
                    st.session_state.display_name = dname
                    st.session_state.data_loaded = False
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 틀렸습니다.")
            else:
                st.warning("아이디와 비밀번호를 입력하세요.")

    with tab_register:
        with st.form("register_form"):
            reg_name = st.text_input("이름", key="reg_name")
            reg_id = st.text_input("아이디", key="reg_id")
            reg_pw = st.text_input("비밀번호", type="password", key="reg_pw")
            reg_pw2 = st.text_input("비밀번호 확인", type="password", key="reg_pw2")
            reg_btn = st.form_submit_button("가입하기", use_container_width=True)
        if reg_btn:
            if not all([reg_name, reg_id, reg_pw, reg_pw2]):
                st.warning("모든 항목을 입력하세요.")
            elif reg_pw != reg_pw2:
                st.error("비밀번호가 일치하지 않습니다.")
            elif len(reg_pw) < 4:
                st.error("비밀번호는 4자 이상이어야 합니다.")
            else:
                ok, msg = register_user(reg_id, reg_pw, reg_name)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
    st.stop()

# ============================================================
# 데이터 로드
# ============================================================
if not st.session_state.data_loaded:
    load_user_stats(st.session_state.username)
    st.session_state.rooms = load_rooms_from_sheet(st.session_state.username)
    if st.session_state.current_room not in st.session_state.rooms:
        keys = list(st.session_state.rooms.keys())
        st.session_state.current_room = keys[0] if keys else ""
    st.session_state.data_loaded = True

# ============================================================
# 헬퍼 함수
# ============================================================
def create_room(persona_key="🔬 학습 도우미"):
    room_id = f"room_{int(time.time() * 1000)}"
    room = {
        "id": room_id, "title": "새 대화", "persona": persona_key,
        "messages": [], "token_log": [],
        "created_at": datetime.now().strftime("%m/%d %H:%M"),
        "total_input": 0, "total_output": 0, "total_cost": 0.0,
    }
    st.session_state.rooms[room_id] = room
    st.session_state.current_room = room_id
    save_room_to_sheet(st.session_state.username, room)
    save_user_stats(st.session_state.username)
    return room_id

def get_current_room():
    rid = st.session_state.current_room
    if rid and rid in st.session_state.rooms:
        return st.session_state.rooms[rid]
    return None

def open_canvas(canvas_type, content, title="Canvas"):
    st.session_state.canvas_open = True
    st.session_state.canvas_type = canvas_type
    st.session_state.canvas_content = content
    st.session_state.canvas_title = title
    if canvas_type == "quiz":
        st.session_state.quiz_answers = {}
        st.session_state.quiz_submitted = False
    elif canvas_type == "code":
        st.session_state.code_content = content.get("code", "")
        st.session_state.code_language = content.get("language", "python")
        st.session_state.code_output = ""

def close_canvas():
    st.session_state.canvas_open = False
    st.session_state.canvas_type = None
    st.session_state.canvas_content = None

def try_parse_ai_response(text, persona_key):
    """AI 응답에서 Canvas 콘텐츠 파싱"""
    persona_info = PERSONAS.get(persona_key, {})
    canvas_type = persona_info.get("canvas_type")

    if not canvas_type:
        return None, None

    # JSON 추출 (코드블록 제거)
    def extract_json(t):
        t = t.strip()
        # ```json ... ``` 또는 ``` ... ``` 제거
        if t.startswith("```"):
            lines = t.split("\n")
            # 첫 줄(```json 등)과 마지막 줄(```) 제거
            inner = []
            started = False
            for line in lines:
                if not started and line.startswith("```"):
                    started = True
                    continue
                if started and line.strip() == "```":
                    break
                if started:
                    inner.append(line)
            t = "\n".join(inner).strip()
        return t

    if canvas_type == "quiz":
        try:
            raw = extract_json(text)
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 0 and "question" in data[0]:
                return "quiz", data
        except:
            pass

    elif canvas_type == "code":
        try:
            raw = extract_json(text)
            data = json.loads(raw)
            if isinstance(data, dict) and "code" in data:
                return "code", data
        except:
            pass
        # 코드블록 fallback
        if "```" in text:
            lines = text.split("\n")
            code_lines = []
            in_block = False
            lang = "python"
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    lang_hint = line[3:].strip()
                    if lang_hint:
                        lang = lang_hint
                elif line.startswith("```") and in_block:
                    in_block = False
                elif in_block:
                    code_lines.append(line)
            if code_lines:
                return "code", {"code": "\n".join(code_lines), "language": lang, "explanation": "", "title": "코드"}

    elif canvas_type == "mindmap":
        try:
            raw = extract_json(text)
            data = json.loads(raw)
            if isinstance(data, dict) and "nodes" in data:
                return "mindmap", data
        except:
            pass

    elif canvas_type == "doc":
        if len(text) > 300:
            return "doc", {"content": text, "title": "문서"}

    return None, None

def is_likely_code_paste(text):
    """긴 코드 붙여넣기 판별"""
    if len(text) < 150:
        return False
    code_signals = [
        "def ", "class ", "import ", "function ", "const ", "var ", "let ",
        "#include", "public class", "SELECT ", "CREATE TABLE", "<?php",
        "async def", "export default", "return (", "@app.route",
        "for (", "while (", "if (", "} else {", "=> {",
    ]
    signal_count = sum(1 for sig in code_signals if sig in text)
    return signal_count >= 2

# ============================================================
# 액션 처리 (폼 외부 버튼 → session_state 플래그)
# ============================================================
def handle_pending_action():
    action = st.session_state.get("_action")
    if not action:
        return
    data = st.session_state.get("_action_data", {})
    st.session_state._action = None
    st.session_state._action_data = None

    if action == "open_canvas":
        open_canvas(data["type"], data["content"], data["title"])
        st.rerun()
    elif action == "open_popup":
        st.session_state.popup_type = data["ptype"]
        st.session_state.popup_content = data["content"]
        st.session_state.popup_label = data["label"]
        st.rerun()
    elif action == "close_popup":
        st.session_state.popup_type = None
        st.session_state.popup_content = None
        st.rerun()

handle_pending_action()

# ============================================================
# 팝업 모달
# ============================================================
if st.session_state.popup_type == "image" and st.session_state.popup_content:
    b64 = st.session_state.popup_content
    fname = st.session_state.popup_label
    is_dark = st.session_state.theme == "dark"
    box_bg = "#2a2a2d" if is_dark else "#ffffff"
    text_c = "#ccc" if is_dark else "#555"
    st.markdown(f"""
    <div style="position:fixed;inset:0;background:rgba(0,0,0,0.78);z-index:9999;
                display:flex;align-items:center;justify-content:center;">
        <div style="background:{box_bg};border-radius:16px;padding:20px;
                    max-width:82vw;max-height:88vh;overflow:auto;
                    box-shadow:0 24px 64px rgba(0,0,0,0.6);">
            <div style="font-size:0.75rem;color:{text_c};margin-bottom:10px;">{fname}</div>
            <img src="data:image/png;base64,{b64}"
                 style="max-width:100%;max-height:70vh;border-radius:8px;display:block;" />
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("✕ 이미지 닫기", key="close_img_modal"):
        st.session_state.popup_type = None
        st.session_state.popup_content = None
        st.rerun()

elif st.session_state.popup_type == "pasted" and st.session_state.popup_content:
    code_text = st.session_state.popup_content
    fname = st.session_state.popup_label
    is_dark = st.session_state.theme == "dark"
    box_bg = "#2a2a2d" if is_dark else "#ffffff"
    text_c = "#e8e6e1" if is_dark else "#1a1a1a"
    sub_c = "#888" if is_dark else "#555"
    st.markdown(f"""
    <div style="position:fixed;inset:0;background:rgba(0,0,0,0.78);z-index:9999;
                display:flex;align-items:center;justify-content:center;">
        <div style="background:{box_bg};border-radius:16px;padding:24px;
                    max-width:80vw;max-height:85vh;overflow:auto;
                    box-shadow:0 24px 64px rgba(0,0,0,0.6);min-width:400px;">
            <div style="font-size:0.78rem;color:{sub_c};margin-bottom:12px;">📋 {fname}</div>
    """, unsafe_allow_html=True)
    st.code(code_text[:5000] + ("\n...(이하 생략)" if len(code_text) > 5000 else ""))
    st.markdown("</div></div>", unsafe_allow_html=True)
    if st.button("✕ 닫기", key="close_pasted_modal"):
        st.session_state.popup_type = None
        st.session_state.popup_content = None
        st.rerun()

# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.markdown(f"**✦ Claude AI**")
    st.caption(f"{st.session_state.display_name}")

    col_theme, col_logout = st.columns(2)
    with col_theme:
        icon = "☀️" if st.session_state.theme == "dark" else "🌙"
        if st.button(f"{icon} 테마", use_container_width=True, key="theme_btn"):
            st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
            save_user_stats(st.session_state.username)
            st.rerun()
    with col_logout:
        if st.button("로그아웃", use_container_width=True, key="logout_btn"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    st.markdown("---")

    if st.button("＋ 새 대화", use_container_width=True, key="new_chat_btn"):
        create_room()
        st.rerun()

    st.markdown("---")
    st.caption("MODEL")
    model_name = st.radio("모델", list(MODELS.keys()), label_visibility="collapsed", key="model_radio")

    st.markdown("---")
    st.caption("PERSONA")
    persona_key = st.selectbox(
        "페르소나",
        list(PERSONAS.keys()),
        label_visibility="collapsed",
        key="persona_select",
    )
    st.caption(PERSONAS[persona_key]["greeting"])

    st.markdown("---")
    st.caption("CONVERSATIONS")
    rooms_sorted = sorted(st.session_state.rooms.values(), key=lambda r: r["created_at"], reverse=True)

    if not rooms_sorted:
        st.caption("대화가 없습니다.")
    else:
        for ri in rooms_sorted:
            is_active = (ri["id"] == st.session_state.current_room)
            cb, cd = st.columns([5, 1])
            with cb:
                prefix = "▸ " if is_active else "  "
                label_text = ri["title"][:22] + "…" if len(ri["title"]) > 22 else ri["title"]
                if st.button(f"{prefix}{label_text}", key=f"r_{ri['id']}", use_container_width=True):
                    st.session_state.current_room = ri["id"]
                    close_canvas()
                    save_user_stats(st.session_state.username)
                    st.rerun()
            with cd:
                if st.button("✕", key=f"d_{ri['id']}"):
                    st.session_state.total_input_tokens -= ri["total_input"]
                    st.session_state.total_output_tokens -= ri["total_output"]
                    st.session_state.total_cost -= ri["total_cost"]
                    del st.session_state.rooms[ri["id"]]
                    delete_room_from_sheet(st.session_state.username, ri["id"])
                    if st.session_state.current_room == ri["id"]:
                        keys = list(st.session_state.rooms.keys())
                        st.session_state.current_room = keys[0] if keys else ""
                    close_canvas()
                    save_user_stats(st.session_state.username)
                    st.rerun()

    st.markdown("---")
    st.caption("STATS")
    c1, c2 = st.columns(2)
    c1.metric("입력", f"{st.session_state.total_input_tokens:,}")
    c2.metric("출력", f"{st.session_state.total_output_tokens:,}")
    c3, c4 = st.columns(2)
    c3.metric("비용", f"${st.session_state.total_cost:.4f}")
    c4.metric("대화", f"{len(st.session_state.rooms)}")

# ============================================================
# 메인 영역 레이아웃
# ============================================================
room = get_current_room()

if st.session_state.canvas_open and st.session_state.canvas_content is not None:
    main_col, canvas_col = st.columns([1, 1], gap="medium")
else:
    main_col = st.container()
    canvas_col = None

# ============================================================
# 메인 채팅 영역
# ============================================================
with main_col:
    col_h1, col_h2 = st.columns([3, 2])
    with col_h1:
        st.markdown("#### ✦ Claude AI")
    with col_h2:
        if room:
            model_display = MODELS[model_name]["id"].split("-")[1].upper()
            st.caption(f"**{model_display}** · {room.get('persona','')}")

    if room is None:
        st.markdown("<div style='text-align:center;padding:6rem 0;color:#555;'>새 대화를 시작하세요</div>", unsafe_allow_html=True)
        st.stop()

    st.markdown("---")

    # ── 대화 히스토리 렌더링 ──
    chat_container = st.container()
    with chat_container:
        if not room["messages"]:
            greeting = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🔬 학습 도우미"])["greeting"]
            st.markdown(f'<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div>{greeting}</div>', unsafe_allow_html=True)
        else:
            ai_turn_idx = 0
            for i, msg in enumerate(room["messages"]):
                if msg["role"] == "user":
                    # 첨부파일/코드 표시
                    if msg.get("has_file"):
                        fname = msg.get("file_name", "파일")
                        is_img = msg.get("file_is_image", False)
                        fkey = msg.get("file_key", "")

                        if is_img and fkey:
                            st.markdown(
                                f'<img src="data:image/png;base64,{fkey}" class="img-thumb" title="{fname}" />',
                                unsafe_allow_html=True
                            )
                            if st.button(f"🔍 {fname}", key=f"img_thumb_{i}"):
                                st.session_state.popup_type = "image"
                                st.session_state.popup_content = fkey
                                st.session_state.popup_label = fname
                                st.rerun()
                        elif not is_img and fkey:
                            char_count = len(fkey)
                            st.markdown(
                                f'<span class="pasted-chip">📋 PASTED · {fname} · {char_count:,}자</span>',
                                unsafe_allow_html=True
                            )
                            if st.button(f"📋 {fname}", key=f"pasted_chip_{i}"):
                                st.session_state.popup_type = "pasted"
                                st.session_state.popup_content = fkey
                                st.session_state.popup_label = fname
                                st.rerun()

                    display_text = msg.get("display", msg["content"])
                    st.markdown(f"""
                    <div class="msg-user">
                        <div class="msg-role msg-role-user">You</div>
                        {display_text}
                    </div>""", unsafe_allow_html=True)

                else:
                    active_persona = room.get("persona", persona_key)
                    c_type, c_data = try_parse_ai_response(msg["content"], active_persona)

                    if c_type in ("quiz", "code", "mindmap"):
                        type_labels = {"quiz": "퀴즈", "code": "코드", "mindmap": "마인드맵"}
                        label = type_labels.get(c_type, "Canvas")
                        if c_type == "quiz":
                            preview = f"{len(c_data)}문제"
                        elif c_type == "code":
                            preview = f"{c_data.get('language','').upper()} — {c_data.get('title','')}"
                        else:
                            preview = c_data.get("title", "")

                        st.markdown(f"""
                        <div class="msg-ai">
                            <div class="msg-role msg-role-ai">Claude</div>
                            {label} 준비 완료 — {preview}
                        </div>""", unsafe_allow_html=True)
                        if st.button(f"▶ Canvas에서 열기", key=f"open_canvas_{i}"):
                            open_canvas(c_type, c_data, label)
                            st.rerun()

                    elif c_type == "doc":
                        st.markdown('<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div></div>', unsafe_allow_html=True)
                        st.markdown(msg["content"])
                        if st.button("📄 문서로 보기 →", key=f"open_doc_{i}"):
                            open_canvas("doc", c_data, "문서")
                            st.rerun()
                    else:
                        st.markdown('<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div></div>', unsafe_allow_html=True)
                        st.markdown(msg["content"])

                    # 토큰 정보
                    if ai_turn_idx < len(room["token_log"]):
                        tlog = room["token_log"][ai_turn_idx]
                        st.markdown(f"""
                        <div class="token-bar">
                            <span>↑ {tlog['input']:,}</span>
                            <span>↓ {tlog['output']:,}</span>
                            <span>${tlog['cost']:.4f}</span>
                            <span>{tlog.get('elapsed',0):.1f}s</span>
                        </div>""", unsafe_allow_html=True)
                    ai_turn_idx += 1

    # ── 스트리밍 중일 때 여기에 실시간 표시 ──
    streaming_area = st.container()

    # ── 파일 업로더 ──
    st.markdown("")
    uploaded_file = st.file_uploader(
        "파일 첨부",
        type=["png", "jpg", "jpeg", "gif", "webp", "txt", "py", "js", "ts", "csv", "md", "json"],
        label_visibility="collapsed",
        key="file_upload",
    )

    if uploaded_file is not None:
        fname = uploaded_file.name
        fext = fname.split(".")[-1].lower()
        if fext in ["png", "jpg", "jpeg", "gif", "webp"]:
            file_bytes = uploaded_file.read()
            fb64 = base64.b64encode(file_bytes).decode("utf-8")
            mtype_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
            mtype = mtype_map.get(fext, "image/png")
            st.session_state.pending_file_b64 = fb64
            st.session_state.pending_file_type = mtype
            st.session_state.pending_file_name = fname
            st.session_state.pending_file_is_image = True
            st.session_state.pending_file_api = {"type": "image", "source": {"type": "base64", "media_type": mtype, "data": fb64}}
            # 썸네일
            st.markdown(f'<img src="data:image/png;base64,{fb64}" class="img-thumb" title="{fname}" style="margin-bottom:4px;" />', unsafe_allow_html=True)
            if st.button(f"🔍 미리보기: {fname}", key="preview_pending_img"):
                st.session_state.popup_type = "image"
                st.session_state.popup_content = fb64
                st.session_state.popup_label = fname
                st.rerun()
        else:
            try:
                text_content = uploaded_file.read().decode("utf-8")
            except:
                text_content = uploaded_file.read().decode("latin-1")
            fb64_text = text_content[:10000]
            st.session_state.pending_file_b64 = fb64_text
            st.session_state.pending_file_type = "text"
            st.session_state.pending_file_name = fname
            st.session_state.pending_file_is_image = False
            st.session_state.pending_file_api = {"type": "text", "text": f"[첨부 파일: {fname}]\n```\n{fb64_text}\n```"}
            st.markdown(f'<span class="pasted-chip">📋 PASTED · {fname} · {len(fb64_text):,}자</span>', unsafe_allow_html=True)
            if st.button(f"📋 미리보기: {fname}", key="preview_pending_file"):
                st.session_state.popup_type = "pasted"
                st.session_state.popup_content = fb64_text
                st.session_state.popup_label = fname
                st.rerun()

    # ── 입력 폼 ──
    # !! 핵심 수정: 폼 안에는 textarea + send 버튼만, 나머지 버튼은 폼 밖으로 !!
    is_quiz_mode = persona_key == "🧩 퀴즈 출제자"
    is_mindmap_mode = persona_key == "🗺️ 마인드맵 메이커"
    if is_quiz_mode:
        ph = "퀴즈 주제를 입력하세요  ex) 한국사 조선시대"
    elif is_mindmap_mode:
        ph = "마인드맵 주제를 입력하세요  ex) 광합성"
    else:
        ph = "메시지 입력..."

    # 폼: textarea + 전송만
    with st.form("chat_form", clear_on_submit=True):
        user_input = st.text_area(
            "메시지",
            placeholder=ph,
            height=100,
            label_visibility="collapsed",
            key="user_input",
        )
        # 전송 버튼 (폼 제출)
        col_send, col_spacer = st.columns([1, 9])
        with col_send:
            submitted = st.form_submit_button("↑", help="전송 (Ctrl+Enter)")

    # 폼 외부 버튼들 (Canvas, Export, Clear)
    btn_cols = st.columns([1, 1, 1, 7])
    with btn_cols[0]:
        canvas_label = "⊟ Canvas" if st.session_state.canvas_open else "⊞ Canvas"
        if st.button(canvas_label, key="canvas_toggle_btn", help="Canvas 패널 열기/닫기"):
            st.session_state.canvas_open = not st.session_state.canvas_open
            st.rerun()
    with btn_cols[1]:
        if st.button("↓ 저장", key="export_btn_outer", help="대화 내보내기"):
            if room["messages"]:
                lines = [f"=== {room['title']} ===", f"{room['created_at']}", ""]
                for m in room["messages"]:
                    role = "나" if m["role"] == "user" else "Claude"
                    lines += [f"[{role}]", m["content"], ""]
                lines.append(f"Input: {room['total_input']:,} · Output: {room['total_output']:,} · ${room['total_cost']:.4f}")
                st.download_button(
                    "💾 다운로드",
                    data="\n".join(lines).encode("utf-8"),
                    file_name=f"chat_{room['id']}.txt",
                    mime="text/plain",
                    key="dl_btn_real",
                )
    with btn_cols[2]:
        if st.button("✕ 초기화", key="clear_btn_outer", help="현재 대화 초기화"):
            st.session_state.total_input_tokens -= room["total_input"]
            st.session_state.total_output_tokens -= room["total_output"]
            st.session_state.total_cost -= room["total_cost"]
            room["messages"] = []
            room["token_log"] = []
            room["total_input"] = room["total_output"] = 0
            room["total_cost"] = 0.0
            room["title"] = "새 대화"
            close_canvas()
            st.session_state.pending_file_b64 = None
            st.session_state.pending_file_api = None
            st.session_state.pending_file_name = None
            save_room_to_sheet(st.session_state.username, room)
            save_user_stats(st.session_state.username)
            st.rerun()

    # ── 메시지 전송 + 스트리밍 ──
    if submitted and user_input.strip():
        if not room["messages"]:
            title = user_input.strip()
            room["title"] = title[:28] + "…" if len(title) > 28 else title
            room["persona"] = persona_key

        # 파일 처리
        file_content_for_api = st.session_state.get("pending_file_api")
        file_name = st.session_state.get("pending_file_name")
        file_is_image = st.session_state.get("pending_file_is_image", False)
        file_key = st.session_state.get("pending_file_b64", "")

        # 긴 코드 붙여넣기 감지
        display_input = user_input.strip()
        if is_likely_code_paste(user_input.strip()) and not file_name:
            file_name = "붙여넣은 코드"
            file_is_image = False
            file_key = user_input.strip()
            file_content_for_api = {"type": "text", "text": f"[붙여넣은 코드]\n```\n{user_input.strip()}\n```"}
            display_input = "(코드 첨부됨)"

        user_msg = {
            "role": "user",
            "content": user_input.strip(),
            "display": display_input,
            "has_file": file_name is not None,
            "file_name": file_name or "",
            "file_is_image": file_is_image,
            "file_key": file_key,
        }
        room["messages"].append(user_msg)

        model_info = MODELS[model_name]
        active_persona = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🔬 학습 도우미"])
        context_messages = room["messages"][-20:]
        api_messages = []

        for m in context_messages:
            if m["role"] == "user":
                if m is context_messages[-1] and file_content_for_api:
                    parts = [file_content_for_api, {"type": "text", "text": m["content"]}]
                    api_messages.append({"role": "user", "content": parts})
                else:
                    api_messages.append({"role": "user", "content": m["content"]})
            else:
                api_messages.append({"role": "assistant", "content": m["content"]})

        # ── 스트리밍: streaming_area에 표시 (대화 목록 바로 아래) ──
        with streaming_area:
            st.markdown(
                '<div class="msg-user"><div class="msg-role msg-role-user">You</div>'
                + display_input + '</div>',
                unsafe_allow_html=True
            )
            st.markdown('<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div></div>', unsafe_allow_html=True)
            stream_placeholder = st.empty()

        client = anthropic.Anthropic(api_key=API_KEY)
        start_time = time.time()
        full_answer = ""

        try:
            with client.messages.stream(
                model=model_info["id"],
                max_tokens=4096,
                system=active_persona["system"],
                messages=api_messages,
            ) as stream:
                for text_chunk in stream.text_stream:
                    full_answer += text_chunk
                    with streaming_area:
                        stream_placeholder.markdown(full_answer + " ▌")

            with streaming_area:
                stream_placeholder.empty()

            elapsed = time.time() - start_time
            final_msg = stream.get_final_message()
            input_tokens = final_msg.usage.input_tokens
            output_tokens = final_msg.usage.output_tokens
            input_cost = (input_tokens / 1_000_000) * model_info["input_price"]
            output_cost = (output_tokens / 1_000_000) * model_info["output_price"]
            turn_cost = input_cost + output_cost

            room["messages"].append({"role": "assistant", "content": full_answer})
            room["token_log"].append({
                "input": input_tokens, "output": output_tokens,
                "cost": turn_cost, "elapsed": elapsed,
            })
            room["total_input"] += input_tokens
            room["total_output"] += output_tokens
            room["total_cost"] += turn_cost
            st.session_state.total_input_tokens += input_tokens
            st.session_state.total_output_tokens += output_tokens
            st.session_state.total_cost += turn_cost

            # Canvas 자동 열기
            c_type, c_data = try_parse_ai_response(full_answer, room.get("persona", persona_key))
            if c_type:
                labels = {"quiz": "퀴즈", "code": "코드", "mindmap": "마인드맵", "doc": "문서"}
                open_canvas(c_type, c_data, labels.get(c_type, "Canvas"))

            # 파일 상태 초기화
            st.session_state.pending_file_api = None
            st.session_state.pending_file_b64 = None
            st.session_state.pending_file_name = None
            st.session_state.pending_file_is_image = False

            save_room_to_sheet(st.session_state.username, room)
            save_user_stats(st.session_state.username)
            st.rerun()

        except anthropic.AuthenticationError:
            st.error("API 키가 유효하지 않습니다.")
            room["messages"].pop()
        except anthropic.RateLimitError:
            st.error("요청 한도 초과. 잠시 후 다시 시도하세요.")
            room["messages"].pop()
        except Exception as e:
            st.error(f"오류: {str(e)}")
            if room["messages"] and room["messages"][-1]["role"] == "user":
                room["messages"].pop()

    # ── 토큰 차트 ──
    if room and room["token_log"]:
        with st.expander("토큰 사용량", expanded=False):
            import plotly.graph_objects as go
            turns = [f"#{i+1}" for i in range(len(room["token_log"]))]
            inputs = [t["input"] for t in room["token_log"]]
            outputs = [t["output"] for t in room["token_log"]]

            is_dark = st.session_state.theme == "dark"
            bg = "rgba(0,0,0,0)"
            fc = "#888"
            gc = "rgba(255,255,255,0.05)" if is_dark else "rgba(0,0,0,0.05)"

            fig = go.Figure()
            fig.add_trace(go.Bar(name="입력", x=turns, y=inputs, marker_color="rgba(150,150,150,0.6)"))
            fig.add_trace(go.Bar(name="출력", x=turns, y=outputs, marker_color="rgba(100,100,100,0.8)"))
            fig.update_layout(
                barmode="group", plot_bgcolor=bg, paper_bgcolor=bg,
                font=dict(family="Inter", color=fc, size=11),
                xaxis=dict(gridcolor=gc), yaxis=dict(gridcolor=gc),
                margin=dict(l=30, r=10, t=20, b=30), height=240,
                legend=dict(orientation="h", y=1.1)
            )
            st.plotly_chart(fig, use_container_width=True)

            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("총 입력", f"{room['total_input']:,}")
            sc2.metric("총 출력", f"{room['total_output']:,}")
            sc3.metric("비용", f"${room['total_cost']:.4f}")
            sc4.metric("₩", f"{int(room['total_cost'] * 1400):,}")

# ============================================================
# Canvas 패널 (오른쪽 컬럼)
# ============================================================
if canvas_col is not None and st.session_state.canvas_content is not None:
    with canvas_col:
        ct = st.session_state.canvas_type
        cc = st.session_state.canvas_content
        th = st.session_state.theme
        text_col = "#e8e6e1" if th == "dark" else "#1a1a1a"
        sub_col = "#555" if th == "dark" else "#888"

        ch1, ch2 = st.columns([4, 1])
        with ch1:
            st.markdown(f"**{st.session_state.canvas_title}**")
        with ch2:
            if st.button("✕", key="close_canvas_btn"):
                close_canvas()
                st.rerun()
        st.markdown("---")

        # ── 퀴즈 ──
        if ct == "quiz":
            quiz_list = cc
            total_q = len(quiz_list)

            if st.session_state.quiz_submitted:
                correct_count = sum(
                    1 for qi, q in enumerate(quiz_list)
                    if st.session_state.quiz_answers.get(qi) == int(q["answer"])
                )
                score = int(correct_count / total_q * 100)
                emoji = "🏆" if score == 100 else "👏" if score >= 70 else "💪" if score >= 40 else "📖"
                st.markdown(f"""
                <div class="score-box">
                    <div style="font-size:2.2rem;">{emoji}</div>
                    <div class="score-num">{score}점</div>
                    <div style="font-size:0.85rem;color:{sub_col};">{correct_count}/{total_q} 정답</div>
                </div>""", unsafe_allow_html=True)
                if st.button("다시 풀기", use_container_width=True, key="retake_quiz"):
                    st.session_state.quiz_answers = {}
                    st.session_state.quiz_submitted = False
                    st.rerun()
            else:
                st.caption(f"{len(st.session_state.quiz_answers)}/{total_q} 선택 완료")

            for qi, q in enumerate(quiz_list):
                correct_idx = int(q["answer"])
                user_ans = st.session_state.quiz_answers.get(qi)
                submitted_quiz = st.session_state.quiz_submitted
                option_labels = ["A", "B", "C", "D"]

                st.markdown(f'<div class="quiz-q">Q{qi+1}. {q["question"]}</div>', unsafe_allow_html=True)

                for oi, opt in enumerate(q["options"]):
                    label = f"{option_labels[oi]}. {opt}"
                    btn_key = f"cv_q_{qi}_{oi}"
                    if submitted_quiz:
                        if oi == correct_idx:
                            st.success(f"✅ {label}")
                        elif oi == user_ans and oi != correct_idx:
                            st.error(f"❌ {label}")
                        else:
                            st.button(label, key=btn_key, disabled=True, use_container_width=True)
                    else:
                        prefix = "● " if user_ans == oi else "  "
                        if st.button(f"{prefix}{label}", key=btn_key, use_container_width=True):
                            st.session_state.quiz_answers[qi] = oi
                            st.rerun()

                if submitted_quiz:
                    st.markdown(f'<div class="quiz-exp">💡 {q["explanation"]}</div>', unsafe_allow_html=True)
                st.markdown("")

            if not st.session_state.quiz_submitted:
                if len(st.session_state.quiz_answers) == total_q:
                    if st.button("정답 확인", use_container_width=True, key="submit_quiz_cv"):
                        st.session_state.quiz_submitted = True
                        st.rerun()

        # ── 코드 ──
        elif ct == "code":
            code_data = cc
            lang = code_data.get("language", "python")
            title = code_data.get("title", "코드")
            explanation = code_data.get("explanation", "")

            st.markdown(f"**{title}** · `{lang.upper()}`")
            if explanation:
                st.info(explanation)

            edited_code = st.text_area(
                "코드",
                value=st.session_state.code_content or code_data.get("code", ""),
                height=320,
                key="canvas_code_editor",
                label_visibility="collapsed",
            )
            st.session_state.code_content = edited_code

            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                if st.button("▶ 실행", use_container_width=True, key="run_code_cv"):
                    if lang == "python":
                        import io, contextlib
                        buf = io.StringIO()
                        try:
                            with contextlib.redirect_stdout(buf):
                                exec(edited_code, {})
                            st.session_state.code_output = buf.getvalue() or "(출력 없음)"
                        except Exception as e:
                            st.session_state.code_output = f"오류: {str(e)}"
                    else:
                        st.session_state.code_output = f"{lang.upper()} 실행은 Python만 지원됩니다"
                    st.rerun()
            with cc2:
                st.download_button("↓ 저장", data=edited_code.encode(),
                                   file_name=f"code.{lang}", mime="text/plain", key="dl_code_cv")
            with cc3:
                if st.button("📋 복사", use_container_width=True, key="copy_code_cv"):
                    st.toast("클립보드 복사는 브라우저에서 직접 선택 후 복사하세요")

            if st.session_state.code_output:
                st.markdown("**실행 결과**")
                st.code(st.session_state.code_output, language="text")

            with st.expander("전체 코드 보기"):
                st.code(edited_code, language=lang)

        # ── 문서 ──
        elif ct == "doc":
            doc_content = cc.get("content", "")
            doc_title = cc.get("title", "문서")
            st.markdown(f"### {doc_title}")
            st.markdown("---")

            edit_mode = st.toggle("편집 모드", key="doc_edit_cv")
            if edit_mode:
                edited_doc = st.text_area("", value=doc_content, height=480,
                                          label_visibility="collapsed", key="doc_edit_area")
                if st.button("저장", key="save_doc_cv"):
                    st.session_state.canvas_content["content"] = edited_doc
                    st.rerun()
            else:
                st.markdown(doc_content)

            st.download_button(
                "↓ 문서 저장",
                data=doc_content.encode("utf-8"),
                file_name=f"{doc_title}.md",
                mime="text/markdown",
                key="dl_doc_cv",
            )

        # ── 마인드맵 ──
        elif ct == "mindmap":
            import plotly.graph_objects as go

            mm_title = cc.get("title", "마인드맵")
            mm_nodes = cc.get("nodes", [])
            st.markdown(f"**{mm_title}**")

            node_x, node_y, node_text, node_color, node_size = [], [], [], [], []
            edge_x, edge_y = [], []

            node_x.append(0); node_y.append(0)
            node_text.append(f"<b>{mm_title}</b>")
            node_color.append("#e8e6e1" if th == "dark" else "#1a1a1a")
            node_size.append(34)

            n_main = len(mm_nodes)
            for mi, mnode in enumerate(mm_nodes):
                angle = 2 * math.pi * mi / n_main - math.pi / 2
                mx = math.cos(angle) * 2.2
                my = math.sin(angle) * 2.2
                node_x.append(mx); node_y.append(my)
                node_text.append(f"<b>{mnode['label']}</b>")
                node_color.append("#888")
                node_size.append(24)
                edge_x += [0, mx, None]; edge_y += [0, my, None]

                children = mnode.get("children", [])
                nc = len(children)
                for ci2, child in enumerate(children):
                    sp = 0.55
                    ca = angle + sp * (ci2 - (nc - 1) / 2) / max(nc, 1)
                    cx2 = mx + math.cos(ca) * 1.4
                    cy2 = my + math.sin(ca) * 1.4
                    node_x.append(cx2); node_y.append(cy2)
                    node_text.append(child["label"])
                    node_color.append("#555" if th == "dark" else "#777")
                    node_size.append(16)
                    edge_x += [mx, cx2, None]; edge_y += [my, cy2, None]

            fig_mm = go.Figure()
            fig_mm.add_trace(go.Scatter(
                x=edge_x, y=edge_y, mode="lines",
                line=dict(color="rgba(128,128,128,0.3)", width=1.5), hoverinfo="none"
            ))
            fig_mm.add_trace(go.Scatter(
                x=node_x, y=node_y, mode="markers+text",
                marker=dict(size=node_size, color=node_color,
                            line=dict(color="rgba(128,128,128,0.2)", width=1)),
                text=node_text,
                textposition="middle center",
                textfont=dict(size=9, color=text_col),
                hoverinfo="text",
            ))
            fig_mm.update_layout(
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                margin=dict(l=10, r=10, t=10, b=10), height=440,
            )
            st.plotly_chart(fig_mm, use_container_width=True)

            with st.expander("목차"):
                for mn in mm_nodes:
                    st.markdown(f"**{mn['label']}**")
                    for ch in mn.get("children", []):
                        st.markdown(f"　• {ch['label']}")
