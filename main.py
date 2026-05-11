import streamlit as st
import anthropic
import time
import json
import hashlib
import base64
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
    row_data = [
        username, room["id"], room["title"],
        room.get("persona", "🔬 학습 도우미"), room["created_at"],
        json.dumps(room["messages"], ensure_ascii=False),
        json.dumps(room["token_log"], ensure_ascii=False),
        room["total_input"], room["total_output"], room["total_cost"],
    ]
    if row_idx:
        sheet.update(f"A{row_idx}:J{row_idx}", [row_data])
    else:
        sheet.append_row(row_data)

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
# 테마 CSS — 완전 재작성
# ============================================================
def get_theme_css(theme):
    if theme == "light":
        return """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

* { box-sizing: border-box; }

.stApp {
    background: #f5f4ef !important;
    font-family: 'Inter', -apple-system, sans-serif;
    color: #1a1a1a !important;
}

/* ── 사이드바 ── */
section[data-testid="stSidebar"] {
    background: #eeede8 !important;
    border-right: 1px solid rgba(0,0,0,0.08) !important;
}
section[data-testid="stSidebar"] * { color: #1a1a1a !important; }
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaption { color: #555 !important; }
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4,
section[data-testid="stSidebar"] h5 { color: #1a1a1a !important; }

/* ── 메인 텍스트 ── */
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown h1,
.stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
    color: #1a1a1a !important;
}
p, span, div, label { color: #1a1a1a; }
[data-testid="stMetricValue"] { color: #1a1a1a !important; font-weight: 600 !important; }
[data-testid="stMetricLabel"] { color: #666 !important; }
.stCaption, small { color: #666 !important; }

/* ── 입력창 — Claude 스타일 ── */
.stTextArea textarea {
    background: #ffffff !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    border-radius: 14px !important;
    color: #1a1a1a !important;
    font-size: 0.95rem !important;
    line-height: 1.6 !important;
    padding: 14px 16px !important;
    resize: none !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
}
.stTextArea textarea:focus {
    border-color: rgba(0,0,0,0.25) !important;
    box-shadow: 0 0 0 3px rgba(0,0,0,0.06), 0 1px 4px rgba(0,0,0,0.06) !important;
    outline: none !important;
}
.stTextArea textarea::placeholder { color: #aaa !important; }

/* ── 텍스트 입력 ── */
.stTextInput input {
    background: #ffffff !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    border-radius: 10px !important;
    color: #1a1a1a !important;
    font-size: 0.9rem !important;
}
.stTextInput input:focus {
    border-color: rgba(0,0,0,0.3) !important;
    box-shadow: 0 0 0 3px rgba(0,0,0,0.06) !important;
}

/* ── 버튼 전역 초기화 ── */
.stButton > button,
.stFormSubmitButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    border-radius: 8px !important;
    transition: all 0.18s ease !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
}

/* 기본 버튼 */
.stButton > button {
    background: rgba(0,0,0,0.05) !important;
    border: 1px solid rgba(0,0,0,0.1) !important;
    color: #333 !important;
}
.stButton > button:hover {
    background: rgba(0,0,0,0.1) !important;
    border-color: rgba(0,0,0,0.2) !important;
    color: #1a1a1a !important;
}

/* 폼 버튼 */
.stFormSubmitButton > button {
    background: rgba(0,0,0,0.06) !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    color: #444 !important;
}
.stFormSubmitButton > button:hover {
    background: rgba(0,0,0,0.12) !important;
    color: #1a1a1a !important;
}
/* 다운로드 버튼 */
.stDownloadButton > button {
    background: rgba(0,0,0,0.06) !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    color: #444 !important;
    border-radius: 8px !important;
}

/* ── 라디오 / 셀렉트 ── */
.stRadio label, .stSelectbox label { color: #1a1a1a !important; }
.stSelectbox > div > div {
    background: #ffffff !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    color: #1a1a1a !important;
    border-radius: 8px !important;
}

/* ── 채팅 버블 ── */
.msg-user {
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 18px 18px 4px 18px;
    padding: 12px 16px;
    margin: 6px 0 6px auto;
    max-width: 88%;
    color: #1a1a1a;
    font-size: 0.93rem;
    line-height: 1.65;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.msg-ai {
    background: transparent;
    border-radius: 4px;
    padding: 4px 0;
    margin: 6px 0;
    max-width: 92%;
    color: #1a1a1a;
    font-size: 0.93rem;
    line-height: 1.7;
}
.msg-role {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    margin-bottom: 4px;
    text-transform: uppercase;
    color: #888;
}
.msg-role-user { text-align: right; color: #888; }
.msg-role-ai { color: #888; }

/* ── 토큰 바 ── */
.token-bar {
    display: flex; gap: 12px; flex-wrap: wrap;
    padding: 6px 0; margin-top: 4px;
    font-size: 0.72rem; color: #999;
}
.token-bar strong { color: #555; }

/* ── Canvas 패널 (fixed) ── */
.canvas-fixed {
    position: fixed;
    top: 0; right: 0;
    width: 42vw;
    height: 100vh;
    background: #f9f8f4;
    border-left: 1px solid rgba(0,0,0,0.1);
    z-index: 1000;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
.canvas-header-bar {
    padding: 14px 18px;
    border-bottom: 1px solid rgba(0,0,0,0.08);
    display: flex; align-items: center; justify-content: space-between;
    background: #f9f8f4;
    flex-shrink: 0;
}
.canvas-header-title {
    font-size: 0.8rem; font-weight: 600; color: #888;
    letter-spacing: 0.08em; text-transform: uppercase;
}
.canvas-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 18px;
}
.canvas-scroll::-webkit-scrollbar { width: 4px; }
.canvas-scroll::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 2px; }

/* ── 채팅 영역 (Canvas 열릴때 오른쪽 여백) ── */
.chat-area-shifted { margin-right: 43vw; }

/* ── 퀴즈 ── */
.quiz-q { font-weight: 600; color: #1a1a1a; margin-bottom: 10px; line-height: 1.6; }
.quiz-exp { background: rgba(0,0,0,0.04); border-left: 3px solid #999; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-top: 10px; font-size: 0.86rem; color: #555; line-height: 1.6; }
.score-box { background: #fff; border: 1px solid rgba(0,0,0,0.1); border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 16px; }
.score-num { font-size: 2.4rem; font-weight: 700; color: #1a1a1a; }

/* ── PASTED 칩 ── */
.pasted-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(0,0,0,0.06); border: 1px solid rgba(0,0,0,0.1);
    border-radius: 8px; padding: 6px 12px; cursor: pointer;
    font-size: 0.8rem; font-weight: 500; color: #555;
    margin-bottom: 6px; transition: all 0.15s;
}
.pasted-chip:hover { background: rgba(0,0,0,0.1); }

/* ── 이미지 썸네일 ── */
.img-thumb-wrap {
    position: relative; display: inline-block;
    cursor: pointer; border-radius: 10px; overflow: hidden;
    border: 1px solid rgba(0,0,0,0.1); margin-bottom: 6px;
}
.img-thumb-wrap img { width: 80px; height: 60px; object-fit: cover; display: block; }
.img-thumb-overlay {
    position: absolute; inset: 0;
    background: rgba(0,0,0,0.3); opacity: 0;
    display: flex; align-items: center; justify-content: center;
    color: white; font-size: 1.2rem; transition: opacity 0.2s;
}
.img-thumb-wrap:hover .img-thumb-overlay { opacity: 1; }

/* ── expander ── */
.streamlit-expanderHeader { color: #1a1a1a !important; }

hr { border-color: rgba(0,0,0,0.08) !important; }
</style>
"""
    else:  # dark
        return """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

* { box-sizing: border-box; }

.stApp {
    background: #1c1c1e !important;
    font-family: 'Inter', -apple-system, sans-serif;
    color: #e8e6e1 !important;
}

/* ── 사이드바 ── */
section[data-testid="stSidebar"] {
    background: #161618 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
section[data-testid="stSidebar"] * { color: #e8e6e1 !important; }
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaption { color: #888 !important; }
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4,
section[data-testid="stSidebar"] h5 { color: #e8e6e1 !important; }

/* ── 메인 텍스트 ── */
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown h1,
.stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
    color: #e8e6e1 !important;
}
p, span, div, label { color: #e8e6e1; }
[data-testid="stMetricValue"] { color: #e8e6e1 !important; font-weight: 600 !important; }
[data-testid="stMetricLabel"] { color: #777 !important; }
.stCaption, small { color: #666 !important; }
.stInfo { color: #e8e6e1 !important; background: rgba(255,255,255,0.06) !important; }

/* ── 입력창 — Claude 스타일 ── */
.stTextArea textarea {
    background: #2a2a2d !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 14px !important;
    color: #e8e6e1 !important;
    font-size: 0.95rem !important;
    line-height: 1.6 !important;
    padding: 14px 16px !important;
    resize: none !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.2) !important;
    caret-color: #e8e6e1 !important;
}
.stTextArea textarea:focus {
    border-color: rgba(255,255,255,0.25) !important;
    box-shadow: 0 0 0 3px rgba(255,255,255,0.05), 0 1px 4px rgba(0,0,0,0.2) !important;
    outline: none !important;
}
.stTextArea textarea::placeholder { color: #555 !important; }

/* ── 텍스트 입력 ── */
.stTextInput input {
    background: #2a2a2d !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
    color: #e8e6e1 !important;
    font-size: 0.9rem !important;
    caret-color: #e8e6e1 !important;
}
.stTextInput input:focus {
    border-color: rgba(255,255,255,0.25) !important;
    box-shadow: 0 0 0 3px rgba(255,255,255,0.05) !important;
}

/* ── 버튼 전역 ── */
.stButton > button,
.stFormSubmitButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    border-radius: 8px !important;
    transition: all 0.18s ease !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
}

.stButton > button {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #ccc !important;
}
.stButton > button:hover {
    background: rgba(255,255,255,0.12) !important;
    border-color: rgba(255,255,255,0.2) !important;
    color: #e8e6e1 !important;
}

.stFormSubmitButton > button {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #ccc !important;
}
.stFormSubmitButton > button:hover {
    background: rgba(255,255,255,0.13) !important;
    color: #e8e6e1 !important;
}

.stDownloadButton > button {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #ccc !important;
    border-radius: 8px !important;
}

/* ── 라디오 / 셀렉트 ── */
.stRadio label { color: #e8e6e1 !important; }
.stSelectbox label { color: #e8e6e1 !important; }
.stSelectbox > div > div {
    background: #2a2a2d !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #e8e6e1 !important;
    border-radius: 8px !important;
}
.stSelectbox svg { fill: #888 !important; }

/* ── 채팅 버블 ── */
.msg-user {
    background: #2a2a2d;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px 18px 4px 18px;
    padding: 12px 16px;
    margin: 6px 0 6px auto;
    max-width: 88%;
    color: #e8e6e1;
    font-size: 0.93rem;
    line-height: 1.65;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.msg-ai {
    background: transparent;
    border-radius: 4px;
    padding: 4px 0;
    margin: 6px 0;
    max-width: 92%;
    color: #e8e6e1;
    font-size: 0.93rem;
    line-height: 1.7;
}
.msg-role {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    margin-bottom: 4px;
    text-transform: uppercase;
    color: #555;
}
.msg-role-user { text-align: right; color: #555; }
.msg-role-ai { color: #555; }

/* ── 토큰 바 ── */
.token-bar {
    display: flex; gap: 12px; flex-wrap: wrap;
    padding: 6px 0; margin-top: 4px;
    font-size: 0.72rem; color: #555;
}
.token-bar strong { color: #888; }

/* ── Canvas 패널 (fixed) ── */
.canvas-fixed {
    position: fixed;
    top: 0; right: 0;
    width: 42vw;
    height: 100vh;
    background: #161618;
    border-left: 1px solid rgba(255,255,255,0.07);
    z-index: 1000;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
.canvas-header-bar {
    padding: 14px 18px;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    display: flex; align-items: center; justify-content: space-between;
    background: #161618;
    flex-shrink: 0;
}
.canvas-header-title {
    font-size: 0.75rem; font-weight: 600; color: #555;
    letter-spacing: 0.1em; text-transform: uppercase;
}
.canvas-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 18px;
}
.canvas-scroll::-webkit-scrollbar { width: 4px; }
.canvas-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

/* ── 채팅 영역 오른쪽 여백 ── */
.chat-area-shifted { margin-right: 43vw; }

/* ── 퀴즈 ── */
.quiz-q { font-weight: 600; color: #e8e6e1; margin-bottom: 10px; line-height: 1.6; }
.quiz-exp { background: rgba(255,255,255,0.04); border-left: 3px solid #555; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-top: 10px; font-size: 0.86rem; color: #aaa; line-height: 1.6; }
.score-box { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 16px; }
.score-num { font-size: 2.4rem; font-weight: 700; color: #e8e6e1; }

/* ── PASTED 칩 ── */
.pasted-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px; padding: 6px 12px; cursor: pointer;
    font-size: 0.8rem; font-weight: 500; color: #aaa;
    margin-bottom: 6px; transition: all 0.15s;
}
.pasted-chip:hover { background: rgba(255,255,255,0.12); }

/* ── 이미지 썸네일 ── */
.img-thumb-wrap {
    position: relative; display: inline-block;
    cursor: pointer; border-radius: 10px; overflow: hidden;
    border: 1px solid rgba(255,255,255,0.1); margin-bottom: 6px;
}
.img-thumb-wrap img { width: 80px; height: 60px; object-fit: cover; display: block; }
.img-thumb-overlay {
    position: absolute; inset: 0;
    background: rgba(0,0,0,0.4); opacity: 0;
    display: flex; align-items: center; justify-content: center;
    color: white; font-size: 1.2rem; transition: opacity 0.2s;
}
.img-thumb-wrap:hover .img-thumb-overlay { opacity: 1; }

/* ── expander ── */
.streamlit-expanderHeader { color: #e8e6e1 !important; }
.streamlit-expanderContent { color: #e8e6e1 !important; }

/* ── 코드 블록 ── */
.stCodeBlock { border-radius: 10px !important; }

hr { border-color: rgba(255,255,255,0.06) !important; }

::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 3px; }
</style>
"""

# ============================================================
# 아이콘 버튼 CSS (Send / Export / Reset)
# ============================================================
ICON_BTN_CSS = """
<style>
/* ── 아이콘 전용 버튼 (폼 submit) ── */
div[data-testid="stFormSubmitButton"]:nth-of-type(1) > button {
    background: #e8e6e1 !important;
    color: #1c1c1e !important;
    border: none !important;
    border-radius: 50% !important;
    width: 40px !important; height: 40px !important;
    padding: 0 !important;
    font-size: 1rem !important;
    display: flex !important; align-items: center !important; justify-content: center !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.15) !important;
}
div[data-testid="stFormSubmitButton"]:nth-of-type(1) > button:hover {
    background: #d0cec8 !important;
    transform: scale(1.05) !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2) !important;
}
div[data-testid="stFormSubmitButton"]:nth-of-type(2) > button {
    background: transparent !important;
    border: 1px solid rgba(128,128,128,0.3) !important;
    border-radius: 8px !important;
    width: 38px !important; height: 38px !important;
    padding: 0 !important;
    font-size: 0.95rem !important;
    color: #888 !important;
}
div[data-testid="stFormSubmitButton"]:nth-of-type(2) > button:hover {
    background: rgba(128,128,128,0.1) !important;
    color: #aaa !important;
    border-color: rgba(128,128,128,0.5) !important;
}
div[data-testid="stFormSubmitButton"]:nth-of-type(3) > button {
    background: transparent !important;
    border: 1px solid rgba(128,128,128,0.3) !important;
    border-radius: 8px !important;
    width: 38px !important; height: 38px !important;
    padding: 0 !important;
    font-size: 0.95rem !important;
    color: #888 !important;
}
div[data-testid="stFormSubmitButton"]:nth-of-type(3) > button:hover {
    background: rgba(220,80,80,0.12) !important;
    border-color: rgba(220,80,80,0.4) !important;
    color: #e07070 !important;
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
# 페르소나 — 유용한 것만
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
반드시 아래 형식의 JSON만 출력하세요:
[{"question": "문제", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "해설"}]
answer는 0-3 정수. 한국어로 최소 3문제 이상 출제합니다.""",
        "greeting": "퀴즈 주제를 알려주세요.",
        "canvas_type": "quiz",
    },
    "💻 코딩 멘토": {
        "system": """당신은 프로그래밍 멘토입니다. 코드를 작성할 때는 반드시 아래 JSON 형식으로만 응답하세요:
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
분석 결과는 명확한 구조로 정리하고, 시각화 코드가 필요하면 아래 JSON 형식으로 제공합니다:
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
을 체계적으로 수행합니다. 단순한 답이 아닌 깊은 사고를 유도합니다. 한국어로 답변합니다.""",
        "greeting": "분석할 주제나 주장을 입력하세요.",
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
    "canvas_open": False,
    "canvas_type": None,
    "canvas_content": None,
    "canvas_title": "Canvas",
    "quiz_answers": {}, "quiz_submitted": False,
    "code_content": "", "code_language": "python", "code_output": "",
    # 팝업 관련
    "popup_type": None,   # "pasted" | "image"
    "popup_content": None,
    "popup_label": "",
    # 파일 미리보기 캐시
    "pending_file_b64": None,
    "pending_file_type": None,
    "pending_file_name": None,
    "pending_file_is_image": False,
    "pending_file_api": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# CSS 적용
# ============================================================
st.markdown(get_theme_css(st.session_state.theme), unsafe_allow_html=True)
st.markdown(ICON_BTN_CSS, unsafe_allow_html=True)

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
    persona_info = PERSONAS.get(persona_key, {})
    canvas_type = persona_info.get("canvas_type")

    if canvas_type == "quiz":
        try:
            raw = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 0 and "question" in data[0]:
                return "quiz", data
        except:
            pass

    elif canvas_type == "code":
        try:
            raw = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(raw)
            if isinstance(data, dict) and "code" in data:
                return "code", data
        except:
            pass
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
            raw = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
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
    """긴 코드 블록인지 판별"""
    if len(text) < 200:
        return False
    code_signals = ["def ", "class ", "import ", "function ", "const ", "var ", "let ",
                    "#include", "public class", "SELECT ", "CREATE TABLE", "<?php"]
    return any(sig in text for sig in code_signals)

# ============================================================
# 팝업 처리 (PASTED / Image preview)
# ============================================================
if st.session_state.popup_type == "pasted":
    with st.expander(f"📋 {st.session_state.popup_label}", expanded=True):
        st.code(st.session_state.popup_content, language="python")
        if st.button("닫기", key="close_pasted_popup"):
            st.session_state.popup_type = None
            st.session_state.popup_content = None
            st.rerun()

elif st.session_state.popup_type == "image":
    with st.expander(f"🖼 {st.session_state.popup_label}", expanded=True):
        b64 = st.session_state.popup_content
        st.markdown(f'<img src="data:image/png;base64,{b64}" style="max-width:100%; border-radius:10px;">', unsafe_allow_html=True)
        if st.button("닫기", key="close_img_popup"):
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
        if st.button(f"{icon}", use_container_width=True, key="theme_btn"):
            st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
            save_user_stats(st.session_state.username)
            st.rerun()
    with col_logout:
        if st.button("로그아웃", use_container_width=True, key="logout_btn"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    st.markdown("---")

    canvas_label = "Canvas 닫기" if st.session_state.canvas_open else "Canvas"
    if st.button(canvas_label, use_container_width=True, key="canvas_toggle_btn"):
        st.session_state.canvas_open = not st.session_state.canvas_open
        st.rerun()

    if st.button("＋ 새 대화", use_container_width=True, key="new_chat_btn"):
        create_room()
        st.rerun()

    st.markdown("---")
    st.caption("MODEL")
    model_name = st.radio("모델", list(MODELS.keys()), label_visibility="collapsed", key="model_radio")

    st.markdown("---")
    st.caption("PERSONA")
    persona_key = st.selectbox("페르소나", list(PERSONAS.keys()), label_visibility="collapsed", key="persona_select")
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
# 메인 영역
# ============================================================
room = get_current_room()

# Canvas가 열려있으면 채팅에 오른쪽 여백 추가
if st.session_state.canvas_open:
    st.markdown('<div class="chat-area-shifted">', unsafe_allow_html=True)

# ── 헤더 ──
col_h1, col_h2, col_h3 = st.columns([3, 2, 2])
with col_h1:
    st.markdown("#### ✦ Claude AI")
with col_h2:
    if room:
        st.caption(f"**{MODELS[model_name]['id'].split('-')[1].upper()}** · {room.get('persona','')}")
with col_h3:
    pass

if room is None:
    st.markdown("<div style='text-align:center; padding:6rem 0; color:#555;'>새 대화를 시작하세요</div>", unsafe_allow_html=True)
    if st.session_state.canvas_open:
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

st.markdown("---")

# ── 대화 내용 ──
if not room["messages"]:
    greeting = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🔬 학습 도우미"])["greeting"]
    st.markdown(f'<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div>{greeting}</div>', unsafe_allow_html=True)
else:
    ai_turn_idx = 0
    for i, msg in enumerate(room["messages"]):
        if msg["role"] == "user":
            # PASTED 칩 / 이미지 썸네일 표시
            file_html = ""
            if msg.get("has_file"):
                fname = msg.get("file_name", "파일")
                is_img = msg.get("file_is_image", False)
                fkey = msg.get("file_key", "")
                if is_img and fkey:
                    # 이미지 썸네일 (클릭 가능)
                    btn_key = f"img_popup_{i}"
                    file_html = f"""
                    <div class="img-thumb-wrap" title="{fname}" onclick="">
                        <img src="data:image/png;base64,{fkey}" />
                        <div class="img-thumb-overlay">🔍</div>
                    </div><br>"""
                    # Streamlit 버튼으로 팝업 트리거
                    if st.button(f"🖼 {fname}", key=btn_key):
                        st.session_state.popup_type = "image"
                        st.session_state.popup_content = fkey
                        st.session_state.popup_label = fname
                        st.rerun()
                elif not is_img and fkey:
                    # PASTED 칩
                    btn_key = f"pasted_popup_{i}"
                    if st.button(f"📋 PASTED · {fname}", key=btn_key):
                        st.session_state.popup_type = "pasted"
                        st.session_state.popup_content = fkey
                        st.session_state.popup_label = fname
                        st.rerun()

            st.markdown(f"""
            <div class="msg-user">
                <div class="msg-role msg-role-user">You</div>
                {msg['content']}
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
                if st.button(f"Canvas에서 열기 →", key=f"open_canvas_{i}"):
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

# ── 파일 업로더 ──
st.markdown("")
uploaded_file = st.file_uploader(
    "파일 첨부",
    type=["png", "jpg", "jpeg", "gif", "webp", "txt", "py", "js", "ts", "csv", "md", "json"],
    label_visibility="collapsed",
    key="file_upload",
)

# 파일 업로드 미리보기 처리
if uploaded_file is not None:
    fname = uploaded_file.name
    fext = fname.split(".")[-1].lower()
    if fext in ["png", "jpg", "jpeg", "gif", "webp"]:
        file_bytes = uploaded_file.read()
        fb64 = base64.b64encode(file_bytes).decode("utf-8")
        mtype_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
        st.session_state.pending_file_b64 = fb64
        st.session_state.pending_file_type = mtype_map.get(fext, "image/png")
        st.session_state.pending_file_name = fname
        st.session_state.pending_file_is_image = True
        st.session_state.pending_file_api = {"type": "image", "source": {"type": "base64", "media_type": mtype_map.get(fext, "image/png"), "data": fb64}}
        # 썸네일 미리보기
        st.markdown(f'<img src="data:image/png;base64,{fb64}" style="max-height:80px; border-radius:8px; margin-bottom:6px;">', unsafe_allow_html=True)
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
        # PASTED 칩 미리보기
        st.markdown(f'<div class="pasted-chip">📋 {fname} · {len(fb64_text):,}자</div>', unsafe_allow_html=True)

# ── 입력 폼 ──
is_quiz_mode = persona_key == "🧩 퀴즈 출제자"
is_mindmap_mode = persona_key == "🗺️ 마인드맵 메이커"
if is_quiz_mode:
    ph = "퀴즈 주제를 입력하세요  ex) 한국사 조선시대"
elif is_mindmap_mode:
    ph = "마인드맵 주제를 입력하세요  ex) 광합성"
else:
    ph = "메시지 입력..."

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_area(
        "메시지",
        placeholder=ph,
        height=100,
        label_visibility="collapsed",
        key="user_input",
    )
    col_send, col_export, col_reset, col_spacer = st.columns([1, 1, 1, 8])
    with col_send:
        submitted = st.form_submit_button("↑")
    with col_export:
        download_btn = st.form_submit_button("↓")
    with col_reset:
        clear_btn = st.form_submit_button("✕")

# ── 내보내기 ──
if download_btn and room["messages"]:
    lines = [f"=== {room['title']} ===", f"{room['created_at']}", ""]
    for m in room["messages"]:
        role = "나" if m["role"] == "user" else "Claude"
        lines += [f"[{role}]", m["content"], ""]
    lines.append(f"Input: {room['total_input']:,} · Output: {room['total_output']:,} · ${room['total_cost']:.4f}")
    st.download_button("💾 다운로드", data="\n".join(lines).encode("utf-8"),
                       file_name=f"chat_{room['id']}.txt", mime="text/plain")

# ── 초기화 ──
if clear_btn:
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
    save_room_to_sheet(st.session_state.username, room)
    save_user_stats(st.session_state.username)
    st.rerun()

# ── 메시지 전송 (스트리밍) ──
if submitted and user_input.strip():
    if not room["messages"]:
        title = user_input.strip()
        room["title"] = title[:28] + "…" if len(title) > 28 else title
        room["persona"] = persona_key

    # 파일 처리
    file_content_for_api = st.session_state.get("pending_file_api")
    file_name = st.session_state.get("pending_file_name")
    file_is_image = st.session_state.get("pending_file_is_image", False)
    file_key = st.session_state.get("pending_file_b64", "")  # b64 or text preview

    # 긴 코드 붙여넣기 감지
    pasted_code = None
    display_input = user_input.strip()
    if is_likely_code_paste(user_input.strip()):
        pasted_code = user_input.strip()
        display_input = "(코드 첨부됨)"

    user_msg = {
        "role": "user",
        "content": user_input.strip(),
        "display": display_input,
        "has_file": file_name is not None,
        "file_name": file_name or "",
        "file_is_image": file_is_image,
        "file_key": file_key if not file_is_image else (file_key[:200] if file_key else ""),
        # 이미지는 b64 저장 (썸네일용)
        "img_b64": file_key if file_is_image else "",
    }

    # 이미지 b64는 너무 크니까 썸네일 분리
    if file_is_image:
        user_msg["file_key"] = file_key  # full b64 for popup

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

    # 스트리밍 응답
    client = anthropic.Anthropic(api_key=API_KEY)
    start_time = time.time()

    stream_placeholder = st.empty()
    full_answer = ""
    error_occurred = False

    try:
        stream_placeholder.markdown('<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div><span style="color:#888;">▌</span></div>', unsafe_allow_html=True)

        with client.messages.stream(
            model=model_info["id"],
            max_tokens=4096,
            system=active_persona["system"],
            messages=api_messages,
        ) as stream:
            for text_chunk in stream.text_stream:
                full_answer += text_chunk
                # 스트리밍 중 화면에 표시
                stream_placeholder.markdown(f'<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div></div>', unsafe_allow_html=True)
                stream_placeholder.markdown(full_answer + " ▌")

        # 스트리밍 완료
        stream_placeholder.empty()

        elapsed = time.time() - start_time
        final_msg = stream.get_final_message()
        input_tokens = final_msg.usage.input_tokens
        output_tokens = final_msg.usage.output_tokens
        input_cost = (input_tokens / 1_000_000) * model_info["input_price"]
        output_cost = (output_tokens / 1_000_000) * model_info["output_price"]
        turn_cost = input_cost + output_cost

        room["messages"].append({"role": "assistant", "content": full_answer})
        room["token_log"].append({"input": input_tokens, "output": output_tokens, "cost": turn_cost, "elapsed": elapsed})
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
        error_occurred = True
    except anthropic.RateLimitError:
        st.error("요청 한도 초과. 잠시 후 다시 시도하세요.")
        room["messages"].pop()
        error_occurred = True
    except Exception as e:
        st.error(f"오류: {str(e)}")
        if room["messages"] and room["messages"][-1]["role"] == "user":
            room["messages"].pop()
        error_occurred = True

# ── 토큰 차트 ──
if room and room["token_log"]:
    with st.expander("토큰 사용량", expanded=False):
        import plotly.graph_objects as go
        turns = [f"#{i+1}" for i in range(len(room["token_log"]))]
        inputs = [t["input"] for t in room["token_log"]]
        outputs = [t["output"] for t in room["token_log"]]
        costs = [t["cost"] for t in room["token_log"]]

        is_dark = st.session_state.theme == "dark"
        bg = "rgba(0,0,0,0)"
        fc = "#888"
        gc = "rgba(255,255,255,0.05)" if is_dark else "rgba(0,0,0,0.05)"

        fig = go.Figure()
        fig.add_trace(go.Bar(name="입력", x=turns, y=inputs, marker_color="rgba(150,150,150,0.6)"))
        fig.add_trace(go.Bar(name="출력", x=turns, y=outputs, marker_color="rgba(100,100,100,0.8)"))
        fig.update_layout(barmode="group", plot_bgcolor=bg, paper_bgcolor=bg,
                          font=dict(family="Inter", color=fc, size=11),
                          xaxis=dict(gridcolor=gc), yaxis=dict(gridcolor=gc),
                          margin=dict(l=30, r=10, t=20, b=30), height=240,
                          legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("총 입력", f"{room['total_input']:,}")
        sc2.metric("총 출력", f"{room['total_output']:,}")
        sc3.metric("비용", f"${room['total_cost']:.4f}")
        sc4.metric("₩", f"{int(room['total_cost'] * 1400):,}")

if st.session_state.canvas_open:
    st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# Canvas 패널 — position:fixed 오버레이로 구현
# ============================================================
if st.session_state.canvas_open and st.session_state.canvas_content is not None:

    # CSS로 fixed 패널 구현 (Streamlit 컬럼 대신 HTML overlay)
    # 실제 컨텐츠는 st.columns 안에 넣되, 위치를 CSS로 강제
    # → Streamlit 한계상 fixed overlay는 JS 없이 완벽하지 않으므로
    #   우측 컬럼을 sticky하게 만드는 방식으로 구현

    # JavaScript로 Canvas 패널을 body에 fixed 위치로 이동
    canvas_js = """
    <script>
    (function() {
        function moveCanvas() {
            const sidebar = document.querySelector('[data-testid="stSidebar"]');
            const sidebarW = sidebar ? sidebar.offsetWidth : 240;
            const canvasEl = document.getElementById('canvas-panel-root');
            if (canvasEl) {
                canvasEl.style.position = 'fixed';
                canvasEl.style.top = '0';
                canvasEl.style.right = '0';
                canvasEl.style.width = '42vw';
                canvasEl.style.height = '100vh';
                canvasEl.style.zIndex = '999';
                canvasEl.style.overflowY = 'auto';
            }
        }
        setTimeout(moveCanvas, 300);
    })();
    </script>
    """

    # Canvas 패널 직접 렌더링 (st.columns 사용)
    # canvas_open이면 오른쪽에 별도 컬럼으로 배치
    pass

# Canvas를 별도 컬럼으로 렌더링
if st.session_state.canvas_open:
    # 빈 div로 간격 확보 후 컬럼으로 오른쪽에 패널 배치
    # Streamlit에서 진짜 fixed panel은 experimental_fragment 혹은 custom component 필요
    # 현실적 대안: 항상 2-컬럼 레이아웃, 오른쪽 컬럼을 Canvas로 사용

    st.markdown("""
    <style>
    /* Canvas 컨테이너를 sticky top으로 */
    div[data-testid="column"]:last-child {
        position: sticky !important;
        top: 0 !important;
        max-height: 100vh !important;
        overflow-y: auto !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ─── 실제 Canvas 렌더링을 별도 세로 공간에 ───
# Canvas가 열릴 때 전체 레이아웃을 2-컬럼으로 재구성하기 위해
# 페이지 상단에서 처리해야 하므로, 여기서는 사이드 패널 CSS + 컨테이너 방식
# 위의 chat_area_shifted div와 함께 작동

if st.session_state.canvas_open and st.session_state.canvas_content is not None:
    ct = st.session_state.canvas_type
    cc = st.session_state.canvas_content

    # fixed panel HTML 직접 삽입
    th = st.session_state.theme
    panel_bg = "#161618" if th == "dark" else "#f9f8f4"
    panel_border = "rgba(255,255,255,0.07)" if th == "dark" else "rgba(0,0,0,0.1)"
    text_col = "#e8e6e1" if th == "dark" else "#1a1a1a"
    sub_col = "#555" if th == "dark" else "#888"

    # Canvas 닫기 버튼 (Streamlit 버튼을 패널 바깥에 배치)
    close_col1, close_col2 = st.columns([1, 1])
    with close_col2:
        if st.button("✕ Canvas 닫기", key="close_canvas_main"):
            close_canvas()
            st.rerun()

    # ── Canvas 탭 ──
    tab_names = []
    if ct == "quiz":
        tab_names = ["🧩 퀴즈"]
    elif ct == "code":
        tab_names = ["💻 코드"]
    elif ct == "doc":
        tab_names = ["📄 문서"]
    elif ct == "mindmap":
        tab_names = ["🗺️ 마인드맵"]

    st.markdown(f"**{st.session_state.canvas_title}**")
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
                <div style="font-size:0.85rem; color:{sub_col};">{correct_count}/{total_q} 정답</div>
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
            # 복사 (클립보드)
            escaped = edited_code.replace("`", "\\`").replace("\\", "\\\\")
            st.markdown(f"""
            <button onclick="navigator.clipboard.writeText(`{escaped}`).then(()=>this.textContent='✓ 복사됨').catch(()=>this.textContent='실패')"
                style="width:100%; padding:6px 10px; background:rgba(128,128,128,0.12);
                       border:1px solid rgba(128,128,128,0.2); border-radius:8px;
                       cursor:pointer; color:{text_col}; font-size:0.82rem;">
                📋 복사
            </button>""", unsafe_allow_html=True)
        with cc3:
            st.download_button("↓ 저장", data=edited_code.encode(),
                               file_name=f"code.{lang}", mime="text/plain", key="dl_code_cv")

        if st.session_state.code_output:
            st.markdown("**실행 결과**")
            st.code(st.session_state.code_output, language="text")

        # 전체 코드 보기
        with st.expander("코드 전체 보기"):
            st.code(edited_code, language=lang)

    # ── 문서 ──
    elif ct == "doc":
        doc_content = cc.get("content", "")
        doc_title = cc.get("title", "문서")
        st.markdown(f"### {doc_title}")
        st.markdown("---")

        edit_mode = st.toggle("편집 모드", key="doc_edit_cv")
        if edit_mode:
            edited_doc = st.text_area("", value=doc_content, height=480, label_visibility="collapsed", key="doc_edit_area")
            if st.button("저장", key="save_doc_cv"):
                st.session_state.canvas_content["content"] = edited_doc
                st.rerun()
        else:
            st.markdown(doc_content)

        # 복사 버튼
        escaped_doc = doc_content.replace("`", "\\`").replace("\\", "\\\\")
        st.markdown(f"""
        <button onclick="navigator.clipboard.writeText(`{escaped_doc}`).then(()=>this.textContent='✓ 복사됨')"
            style="padding:6px 14px; background:rgba(128,128,128,0.12);
                   border:1px solid rgba(128,128,128,0.2); border-radius:8px;
                   cursor:pointer; color:{text_col}; font-size:0.82rem; margin-top:8px;">
            📋 전체 복사
        </button>""", unsafe_allow_html=True)

    # ── 마인드맵 ──
    elif ct == "mindmap":
        import math
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
