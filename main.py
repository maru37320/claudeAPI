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
st.set_page_config(page_title="🤖 Claude AI", page_icon="🤖", layout="wide")

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
# 유저 관리 (Google Sheets)
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
        room.get("persona", "🎓 기본 도우미"), room["created_at"],
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
                "persona": row.get("persona", "🎓 기본 도우미"),
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
        return """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');
            .stApp {
                background: radial-gradient(ellipse at 10% 20%, rgba(255,152,40,0.06) 0%, transparent 50%),
                    radial-gradient(ellipse at 90% 80%, rgba(59,130,246,0.06) 0%, transparent 50%),
                    linear-gradient(180deg, #f0f4f8 0%, #e8ecf1 30%, #f5f7fa 60%, #eef1f5 100%) !important;
                font-family: 'Noto Sans KR', sans-serif;
            }
            .main-header h1 { font-family: 'Rajdhani', sans-serif; color: #1a2a3a; font-size: 2.2rem; font-weight: 700; letter-spacing: 3px; }
            .main-header .ow-subtitle { color: #e0780a; }
            .chat-user {
                background: linear-gradient(135deg, rgba(255,152,40,0.12), rgba(255,120,20,0.06));
                border: 1px solid rgba(255,152,40,0.25); border-left: 3px solid #ff9828;
                border-radius: 4px 12px 12px 4px; padding: 1rem 1.3rem; margin: 0.8rem 0;
                color: #3a2a0a; max-width: 92%; margin-left: auto; font-size: 0.95rem; line-height: 1.6;
            }
            .chat-ai {
                background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(37,99,235,0.04));
                border: 1px solid rgba(59,130,246,0.18); border-left: 3px solid #3b82f6;
                border-radius: 12px 4px 4px 12px; padding: 1rem 1.3rem; margin: 0.8rem 0;
                color: #1a2a3a; max-width: 92%; font-size: 0.95rem; line-height: 1.7;
            }
            .chat-role { font-family: 'Rajdhani', sans-serif; font-size: 0.7rem; font-weight: 700; letter-spacing: 2px; margin-bottom: 0.4rem; text-transform: uppercase; }
            .chat-role-user { color: #e0780a; text-align: right; }
            .chat-role-ai { color: #2563eb; }
            .model-badge { background: rgba(255,152,40,0.1); color: #c06000; padding: 0.2rem 0.8rem; border-radius: 2px; font-family: 'Rajdhani', sans-serif; font-size: 0.78rem; font-weight: 600; border: 1px solid rgba(255,152,40,0.2); }
            .persona-badge { background: rgba(59,130,246,0.1); color: #2563eb; padding: 0.2rem 0.8rem; border-radius: 2px; font-size: 0.78rem; font-weight: 600; border: 1px solid rgba(59,130,246,0.2); }
            .usage-bar { background: rgba(255,152,40,0.04); border: 1px solid rgba(255,152,40,0.12); border-radius: 4px; padding: 0.6rem 1rem; margin-top: 0.4rem; display: flex; justify-content: space-around; flex-wrap: wrap; gap: 0.5rem; position: relative; }
            .usage-bar::before { content: 'USAGE'; position: absolute; top: -8px; left: 10px; font-family: 'Rajdhani', sans-serif; font-size: 0.6rem; font-weight: 700; color: #e0780a; letter-spacing: 2px; background: #f0f4f8; padding: 0 5px; }
            .usage-chip { color: #5a6a7a; font-size: 0.76rem; font-family: 'Rajdhani', sans-serif; }
            .usage-chip strong { color: #1a2a3a; }
            .stTextArea textarea { background: rgba(255,255,255,0.8) !important; border: 1px solid rgba(255,152,40,0.2) !important; color: #1a2a3a !important; border-radius: 4px !important; }
            .stTextArea textarea:focus { border-color: #ff9828 !important; box-shadow: 0 0 0 1px #ff9828 !important; }
            section[data-testid="stSidebar"] { background: linear-gradient(180deg, #e8ecf1, #dde3ea) !important; border-right: 1px solid rgba(255,152,40,0.1) !important; }
            section[data-testid="stSidebar"] h2 { font-family: 'Rajdhani', sans-serif !important; color: #e0780a !important; letter-spacing: 2px !important; }
            section[data-testid="stSidebar"] h5 { font-family: 'Rajdhani', sans-serif !important; color: #c06000 !important; letter-spacing: 2px !important; text-transform: uppercase !important; }
            [data-testid="stMetricValue"] { font-family: 'Rajdhani', sans-serif !important; color: #e0780a !important; }
            [data-testid="stMetricLabel"] { color: #5a6a7a !important; }
            hr { border-color: rgba(0,0,0,0.08) !important; }

            /* ── Canvas 패널 (라이트) ── */
            .canvas-panel {
                background: linear-gradient(180deg, #ffffff, #f8fafc);
                border: 1px solid rgba(59,130,246,0.2);
                border-radius: 12px; padding: 0; overflow: hidden;
                box-shadow: 0 4px 24px rgba(59,130,246,0.08);
                min-height: 80vh;
            }
            .canvas-header {
                background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(37,99,235,0.04));
                border-bottom: 1px solid rgba(59,130,246,0.15);
                padding: 0.8rem 1.2rem; display: flex; align-items: center; gap: 0.6rem;
            }
            .canvas-title { font-family: 'Rajdhani', sans-serif; font-size: 1rem; font-weight: 700; color: #2563eb; letter-spacing: 2px; text-transform: uppercase; }
            .canvas-body { padding: 1.2rem; }
            .canvas-empty { text-align: center; padding: 4rem 2rem; color: #94a3b8; }
            .canvas-empty .icon { font-size: 3rem; margin-bottom: 1rem; }
            .canvas-empty p { font-family: 'Rajdhani', sans-serif; letter-spacing: 2px; font-size: 0.85rem; text-transform: uppercase; }
            .quiz-card { background: rgba(255,255,255,0.9); border: 1px solid rgba(59,130,246,0.15); border-radius: 10px; padding: 1.2rem; margin-bottom: 1rem; }
            .quiz-question { color: #1a2a3a; font-size: 1rem; font-weight: 600; margin-bottom: 0.8rem; line-height: 1.6; }
            .quiz-explanation { background: rgba(255,152,40,0.06); border-left: 3px solid #ff9828; padding: 0.8rem; border-radius: 0 8px 8px 0; margin-top: 0.8rem; color: #3a4a5a; font-size: 0.88rem; line-height: 1.6; }
            .score-box { background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(37,99,235,0.04)); border: 1px solid rgba(59,130,246,0.2); border-radius: 10px; padding: 1.2rem; text-align: center; margin-bottom: 1rem; }

            /* 퀴즈 스타일 */
            .quiz-option-btn { background: rgba(255,255,255,0.9); border: 2px solid rgba(59,130,246,0.25); border-radius: 8px; padding: 0.8rem 1.2rem; margin: 0.4rem 0; color: #1a2a3a; cursor: pointer; width: 100%; text-align: left; font-size: 0.95rem; }
            .quiz-correct { background: rgba(34,197,94,0.12) !important; border-color: #22c55e !important; color: #15803d !important; }
            .quiz-wrong { background: rgba(239,68,68,0.12) !important; border-color: #ef4444 !important; color: #dc2626 !important; }
        </style>
        """
    else:
        return """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');
            .stApp {
                background: radial-gradient(ellipse at 10% 20%, rgba(255,152,40,0.12) 0%, transparent 50%),
                    radial-gradient(ellipse at 90% 80%, rgba(59,130,246,0.10) 0%, transparent 50%),
                    linear-gradient(180deg, #0a1628 0%, #0d1f3c 15%, #102a4a 30%, #0f2844 50%, #0d1f3c 70%, #0b1a33 85%, #091425 100%) !important;
                font-family: 'Noto Sans KR', sans-serif;
            }
            .stApp::before {
                content: ''; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background: linear-gradient(90deg, rgba(255,152,40,0.03) 1px, transparent 1px),
                    linear-gradient(0deg, rgba(255,152,40,0.03) 1px, transparent 1px);
                background-size: 60px 60px; pointer-events: none; z-index: 0;
            }
            .main-header h1 { font-family: 'Rajdhani', sans-serif; color: #ffffff; font-size: 2.2rem; font-weight: 700; letter-spacing: 3px; text-shadow: 0 0 30px rgba(255,152,40,0.3); }
            .main-header .ow-subtitle { color: #ff9828; }
            .chat-user {
                background: linear-gradient(135deg, rgba(255,152,40,0.15), rgba(255,120,20,0.08));
                border: 1px solid rgba(255,152,40,0.3); border-left: 3px solid #ff9828;
                border-radius: 4px 12px 12px 4px; padding: 1rem 1.3rem; margin: 0.8rem 0;
                color: #fde8c8; max-width: 92%; margin-left: auto; font-size: 0.95rem; line-height: 1.6;
            }
            .chat-ai {
                background: linear-gradient(135deg, rgba(59,130,246,0.10), rgba(37,99,235,0.05));
                border: 1px solid rgba(59,130,246,0.2); border-left: 3px solid #3b82f6;
                border-radius: 12px 4px 4px 12px; padding: 1rem 1.3rem; margin: 0.8rem 0;
                color: #c8dff5; max-width: 92%; font-size: 0.95rem; line-height: 1.7;
            }
            .chat-role { font-family: 'Rajdhani', sans-serif; font-size: 0.7rem; font-weight: 700; letter-spacing: 2px; margin-bottom: 0.4rem; text-transform: uppercase; }
            .chat-role-user { color: #ff9828; text-align: right; }
            .chat-role-ai { color: #3b82f6; }
            .model-badge { background: rgba(255,152,40,0.12); color: #ffb347; padding: 0.2rem 0.8rem; border-radius: 2px; font-family: 'Rajdhani', sans-serif; font-size: 0.78rem; font-weight: 600; border: 1px solid rgba(255,152,40,0.25); }
            .persona-badge { background: rgba(59,130,246,0.12); color: #60a5fa; padding: 0.2rem 0.8rem; border-radius: 2px; font-size: 0.78rem; font-weight: 600; border: 1px solid rgba(59,130,246,0.25); }
            .usage-bar { background: rgba(255,152,40,0.04); border: 1px solid rgba(255,152,40,0.12); border-radius: 4px; padding: 0.6rem 1rem; margin-top: 0.4rem; display: flex; justify-content: space-around; flex-wrap: wrap; gap: 0.5rem; position: relative; }
            .usage-bar::before { content: 'USAGE'; position: absolute; top: -8px; left: 10px; font-family: 'Rajdhani', sans-serif; font-size: 0.6rem; font-weight: 700; color: #ff9828; letter-spacing: 2px; background: #0d1f3c; padding: 0 5px; }
            .usage-chip { color: #5a7ca3; font-size: 0.76rem; font-family: 'Rajdhani', sans-serif; }
            .usage-chip strong { color: #e8dfd0; }
            .stTextArea textarea { background: rgba(255,255,255,0.04) !important; border: 1px solid rgba(255,152,40,0.2) !important; color: #e0dcd4 !important; border-radius: 4px !important; }
            .stTextArea textarea:focus { border-color: #ff9828 !important; box-shadow: 0 0 0 1px #ff9828, 0 0 20px rgba(255,152,40,0.15) !important; }
            section[data-testid="stSidebar"] { background: linear-gradient(180deg, #060e1a, #091624, #0b1a2e) !important; border-right: 1px solid rgba(255,152,40,0.1) !important; }
            section[data-testid="stSidebar"] h2 { font-family: 'Rajdhani', sans-serif !important; color: #ff9828 !important; letter-spacing: 2px !important; }
            section[data-testid="stSidebar"] h5 { font-family: 'Rajdhani', sans-serif !important; color: #ffb347 !important; letter-spacing: 2px !important; text-transform: uppercase !important; }
            [data-testid="stMetricValue"] { font-family: 'Rajdhani', sans-serif !important; color: #ffb347 !important; }
            [data-testid="stMetricLabel"] { color: #5a7ca3 !important; }
            hr { border-color: rgba(255,152,40,0.1) !important; }
            ::-webkit-scrollbar { width: 6px; }
            ::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); }
            ::-webkit-scrollbar-thumb { background: rgba(255,152,40,0.3); border-radius: 3px; }

            /* ── Canvas 패널 (다크) ── */
            .canvas-panel {
                background: linear-gradient(180deg, #0b1929, #0d1f3c);
                border: 1px solid rgba(59,130,246,0.25);
                border-radius: 12px; overflow: hidden;
                box-shadow: 0 4px 40px rgba(59,130,246,0.1), inset 0 1px 0 rgba(255,255,255,0.03);
                min-height: 80vh;
            }
            .canvas-header {
                background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(37,99,235,0.08));
                border-bottom: 1px solid rgba(59,130,246,0.2);
                padding: 0.8rem 1.2rem;
            }
            .canvas-title { font-family: 'Rajdhani', sans-serif; font-size: 1rem; font-weight: 700; color: #60a5fa; letter-spacing: 2px; text-transform: uppercase; }
            .canvas-body { padding: 1.2rem; }
            .canvas-empty { text-align: center; padding: 4rem 2rem; color: #3a5a7a; }
            .canvas-empty .icon { font-size: 3rem; margin-bottom: 1rem; opacity: 0.5; }
            .canvas-empty p { font-family: 'Rajdhani', sans-serif; letter-spacing: 2px; font-size: 0.85rem; text-transform: uppercase; }
            .quiz-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(59,130,246,0.15); border-radius: 10px; padding: 1.2rem; margin-bottom: 1rem; }
            .quiz-question { color: #e2e8f0; font-size: 1rem; font-weight: 600; margin-bottom: 0.8rem; line-height: 1.6; }
            .quiz-explanation { background: rgba(255,152,40,0.08); border-left: 3px solid #ff9828; padding: 0.8rem; border-radius: 0 8px 8px 0; margin-top: 0.8rem; color: #c8dff5; font-size: 0.88rem; line-height: 1.6; }
            .score-box { background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.2); border-radius: 10px; padding: 1.2rem; text-align: center; margin-bottom: 1rem; }

            /* 퀴즈 스타일 */
            .quiz-option-btn { background: rgba(255,255,255,0.05); border: 2px solid rgba(59,130,246,0.2); border-radius: 8px; padding: 0.8rem 1.2rem; margin: 0.4rem 0; color: #c8dff5; cursor: pointer; width: 100%; text-align: left; font-size: 0.95rem; }
            .quiz-correct { background: rgba(34,197,94,0.15) !important; border-color: #22c55e !important; color: #86efac !important; }
            .quiz-wrong { background: rgba(239,68,68,0.15) !important; border-color: #ef4444 !important; color: #fca5a5 !important; }
        </style>
        """

BUTTON_CSS = """
<style>
    .stButton > button, .stFormSubmitButton > button {
        font-family: 'Rajdhani', 'Noto Sans KR', sans-serif !important;
        font-weight: 700 !important; font-size: 0.9rem !important;
        letter-spacing: 1.5px !important; border-radius: 6px !important;
        transition: all 0.3s ease !important; text-transform: uppercase !important;
    }
    .stFormSubmitButton:nth-of-type(1) > button {
        background: linear-gradient(135deg, #ff9828, #ff7b00) !important;
        border: none !important; color: #ffffff !important;
        box-shadow: 0 4px 20px rgba(255,152,40,0.3) !important;
    }
    .stFormSubmitButton:nth-of-type(1) > button:hover {
        background: linear-gradient(135deg, #ffb347, #ff9828) !important;
        box-shadow: 0 6px 30px rgba(255,152,40,0.5) !important; transform: translateY(-1px) !important;
    }
    .stFormSubmitButton:nth-of-type(2) > button {
        background: linear-gradient(135deg, rgba(59,130,246,0.25), rgba(37,99,235,0.15)) !important;
        border: 1px solid rgba(59,130,246,0.4) !important; color: #60a5fa !important;
    }
    .stFormSubmitButton:nth-of-type(3) > button {
        background: linear-gradient(135deg, rgba(239,68,68,0.2), rgba(220,38,38,0.1)) !important;
        border: 1px solid rgba(239,68,68,0.3) !important; color: #f87171 !important;
    }
    section[data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(135deg, rgba(255,152,40,0.08), rgba(255,120,20,0.04)) !important;
        border: 1px solid rgba(255,152,40,0.2) !important; color: #c0a070 !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: linear-gradient(135deg, rgba(255,152,40,0.2), rgba(255,120,20,0.12)) !important;
        border-color: #ff9828 !important; color: #ffb347 !important;
    }
    .stDownloadButton > button {
        background: linear-gradient(135deg, rgba(59,130,246,0.2), rgba(37,99,235,0.1)) !important;
        border: 1px solid rgba(59,130,246,0.35) !important; color: #60a5fa !important;
        border-radius: 6px !important; font-family: 'Rajdhani', sans-serif !important;
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
# 모델 & 페르소나
# ============================================================
MODELS = {
    "⚡ Claude 4.5 Sonnet": {
        "id": "claude-sonnet-4-20250514",
        "short": "CLAUDE 4.5 SONNET",
        "desc": "빠르고 효율적",
        "input_price": 3.0,
        "output_price": 15.0,
    },
    "🧠 Claude 4.5 Opus": {
        "id": "claude-opus-4-20250514",
        "short": "CLAUDE 4.5 OPUS",
        "desc": "최고 성능",
        "input_price": 15.0,
        "output_price": 75.0,
    },
}

PERSONAS = {
    "🎓 기본 도우미": {
        "system": "당신은 당곡고등학교 학생들의 학습을 돕는 친절한 AI 도우미입니다. 한국어로 답변합니다.",
        "greeting": "안녕하세요! 무엇이든 물어보세요 🙂",
        "canvas_type": None,
    },
    "🔬 과학 선생님": {
        "system": "당신은 열정적인 과학 선생님입니다. 실생활 예시와 함께 설명합니다. 한국어로 답변합니다.",
        "greeting": "과학의 세계에 오신 걸 환영합니다! 🔬",
        "canvas_type": "doc",
    },
    "📐 수학 튜터": {
        "system": "당신은 수학 튜터입니다. 단계별로 풀이하고 원리를 설명합니다. 한국어로 답변합니다.",
        "greeting": "수학 문제 함께 풀어봐요! 📐",
        "canvas_type": "doc",
    },
    "📚 역사 해설가": {
        "system": "당신은 역사 해설가입니다. 이야기처럼 생동감 있게 전달합니다. 한국어로 답변합니다.",
        "greeting": "역사 속 이야기를 들려드릴게요! 📚",
        "canvas_type": "doc",
    },
    "🇬🇧 영어 코치": {
        "system": "당신은 영어 코치입니다. 한국어로 설명하되 영어 예문을 풍부하게 사용합니다.",
        "greeting": "Let's learn English together! 🇬🇧",
        "canvas_type": "doc",
    },
    "🏛️ 소크라테스": {
        "system": "당신은 소크라테스입니다. 답을 직접 알려주지 않고 질문으로 사고를 유도합니다. 한국어로 대화합니다.",
        "greeting": "나는 소크라테스라네. 🏛️",
        "canvas_type": None,
    },
    "💻 코딩 멘토": {
        "system": """당신은 프로그래밍 멘토입니다. 코드를 작성할 때는 반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{\"language\": \"python\", \"code\": \"코드 내용\", \"explanation\": \"설명\", \"title\": \"제목\"}
language는 python/javascript/html/css/java/cpp/sql 중 하나. 한국어로 설명합니다.""",
        "greeting": "코딩 세계에 오신 걸 환영합니다! 💻",
        "canvas_type": "code",
    },
    "✍️ 논술 코치": {
        "system": "당신은 논술 코치입니다. 논리 구조와 표현력을 개선하도록 도와줍니다. 한국어로 답변합니다.",
        "greeting": "글쓰기 실력을 함께 키워봐요! ✍️",
        "canvas_type": "doc",
    },
    "🧩 퀴즈 출제자": {
        "system": """당신은 퀴즈 출제자입니다. 주어진 주제에 대해 4지선다 퀴즈를 JSON 형식으로 출제합니다.
반드시 아래 형식의 JSON만 출력하세요. 다른 텍스트 없이 JSON만 출력합니다:
[{\"question\": \"문제\", \"options\": [\"A\", \"B\", \"C\", \"D\"], \"answer\": 0, \"explanation\": \"해설\"}]
answer는 0-3 정수(정답 인덱스)입니다. 한국어로 출제합니다. 최소 3문제 이상 출제하세요.""",
        "greeting": "퀴즈 주제를 알려주세요! 🧩",
        "canvas_type": "quiz",
    },
    "🗺️ 마인드맵 메이커": {
        "system": """당신은 마인드맵 전문가입니다. 주제를 받으면 반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{\"title\": \"중심 주제\", \"nodes\": [{\"id\": \"1\", \"label\": \"가지1\", \"children\": [{\"id\": \"1-1\", \"label\": \"세부1\"}]}, ...]}
최소 4개 이상의 주요 가지와 각 가지에 2-3개 세부항목을 포함하세요. 한국어로 작성합니다.""",
        "greeting": "마인드맵으로 만들고 싶은 주제를 알려주세요! 🗺️",
        "canvas_type": "mindmap",
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
    # Canvas 관련
    "canvas_open": False,
    "canvas_type": None,       # "quiz" | "code" | "doc" | "mindmap"
    "canvas_content": None,    # 실제 데이터
    "canvas_title": "CANVAS",
    # 퀴즈 상태
    "quiz_answers": {}, "quiz_submitted": False,
    # 코드 에디터 상태
    "code_content": "", "code_language": "python", "code_output": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# 테마 적용
# ============================================================
st.markdown(get_theme_css(st.session_state.theme), unsafe_allow_html=True)
st.markdown(BUTTON_CSS, unsafe_allow_html=True)

# ============================================================
# 로그인 / 회원가입 화면
# ============================================================
if not st.session_state.logged_in:
    st.markdown("""
    <div class="main-header" style="text-align:center; padding:3rem 0 1rem 0;">
        <h1 style="font-family:Rajdhani,sans-serif; font-size:2.8rem; font-weight:700; letter-spacing:3px;">🤖 CLAUDE AI</h1>
        <div class="ow-subtitle" style="font-family:Rajdhani,sans-serif; font-size:0.85rem; font-weight:600; letter-spacing:4px; text-transform:uppercase;">LEARNING ASSISTANT</div>
    </div>
    """, unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["🔑 로그인", "📝 회원가입"])

    with tab_login:
        with st.form("login_form"):
            st.markdown("##### 로그인")
            login_id = st.text_input("아이디", key="login_id")
            login_pw = st.text_input("비밀번호", type="password", key="login_pw")
            login_btn = st.form_submit_button("🔓 로그인", use_container_width=True)
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
            st.markdown("##### 회원가입")
            reg_name = st.text_input("이름 (표시용)", key="reg_name")
            reg_id = st.text_input("아이디", key="reg_id")
            reg_pw = st.text_input("비밀번호", type="password", key="reg_pw")
            reg_pw2 = st.text_input("비밀번호 확인", type="password", key="reg_pw2")
            reg_btn = st.form_submit_button("✅ 가입하기", use_container_width=True)
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
                    st.success(msg + " 이제 로그인해주세요!")
                else:
                    st.error(msg)
    st.stop()

# ============================================================
# 로그인 후 — 데이터 로드
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
def create_room(persona_key="🎓 기본 도우미"):
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

def open_canvas(canvas_type, content, title="CANVAS"):
    """Canvas 패널 열기"""
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
    """AI 응답에서 Canvas로 보낼 콘텐츠 자동 감지"""
    persona_info = PERSONAS.get(persona_key, {})
    canvas_type = persona_info.get("canvas_type")

    if canvas_type == "quiz":
        try:
            raw = text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = raw[:-3]
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 0 and "question" in data[0]:
                return "quiz", data
        except:
            pass

    elif canvas_type == "code":
        try:
            raw = text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = raw[:-3]
            data = json.loads(raw)
            if isinstance(data, dict) and "code" in data:
                return "code", data
        except:
            pass
        # 코드 블록이 있으면 추출
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
                return "code", {"code": "\n".join(code_lines), "language": lang,
                                "explanation": "", "title": "코드"}

    elif canvas_type == "mindmap":
        try:
            raw = text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = raw[:-3]
            data = json.loads(raw)
            if isinstance(data, dict) and "nodes" in data:
                return "mindmap", data
        except:
            pass

    elif canvas_type == "doc":
        # 긴 마크다운 응답이면 문서 패널로
        if len(text) > 300:
            return "doc", {"content": text, "title": "문서"}

    return None, None

# ============================================================
# ─────────────────── 사이드바 ───────────────────
# ============================================================
with st.sidebar:
    st.markdown(f"## ⚡ CLAUDE CHATBOT")
    st.caption(f"👋 {st.session_state.display_name}님")

    col_theme, col_logout = st.columns(2)
    with col_theme:
        current_icon = "☀️" if st.session_state.theme == "dark" else "🌙"
        if st.button(f"{current_icon} 테마", use_container_width=True):
            st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
            save_user_stats(st.session_state.username)
            st.rerun()
    with col_logout:
        if st.button("🚪 로그아웃", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    st.markdown("---")

    # ── Canvas 토글 버튼 ──
    canvas_icon = "🎨 Canvas 닫기" if st.session_state.canvas_open else "🎨 Canvas 열기"
    if st.button(canvas_icon, use_container_width=True):
        st.session_state.canvas_open = not st.session_state.canvas_open
        st.rerun()

    st.markdown("---")

    if st.button("➕ 새 대화 시작", use_container_width=True):
        create_room()
        st.rerun()

    st.markdown("---")
    st.markdown("##### 🎯 MODEL")
    model_name = st.radio("모델", list(MODELS.keys()), label_visibility="collapsed")

    st.markdown("---")
    st.markdown("##### 🎭 PERSONA")
    persona_key = st.selectbox("AI 역할", list(PERSONAS.keys()), label_visibility="collapsed")
    st.caption(PERSONAS[persona_key]["greeting"])

    # 페르소나 Canvas 타입 힌트 표시
    p_canvas = PERSONAS[persona_key].get("canvas_type")
    if p_canvas:
        icons = {"quiz": "🧩 퀴즈", "code": "💻 코드", "doc": "📄 문서", "mindmap": "🗺️ 마인드맵"}
        st.caption(f"Canvas: {icons.get(p_canvas, p_canvas)}")

    st.markdown("---")
    st.markdown("##### 💬 CONVERSATIONS")
    rooms_sorted = sorted(st.session_state.rooms.values(), key=lambda r: r["created_at"], reverse=True)

    if not rooms_sorted:
        st.info("대화가 없습니다.\n새 대화를 시작하세요!")
    else:
        for ri in rooms_sorted:
            is_active = (ri["id"] == st.session_state.current_room)
            cb, cd = st.columns([5, 1])
            with cb:
                icon = "▶" if is_active else "　"
                if st.button(f"{icon} {ri['title']}", key=f"r_{ri['id']}", use_container_width=True):
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
    st.markdown("##### 📊 TOTAL STATS")
    c1, c2 = st.columns(2)
    c1.metric("입력", f"{st.session_state.total_input_tokens:,}")
    c2.metric("출력", f"{st.session_state.total_output_tokens:,}")
    c3, c4 = st.columns(2)
    c3.metric("비용", f"${st.session_state.total_cost:.4f}")
    c4.metric("대화방", f"{len(st.session_state.rooms)}개")

# ============================================================
# ─────────────────── 메인 레이아웃 ───────────────────
# Canvas가 열려있으면 좌(채팅):우(Canvas) = 55:45
# 닫혀있으면 채팅 전체 폭
# ============================================================
room = get_current_room()

if st.session_state.canvas_open:
    col_chat, col_canvas = st.columns([55, 45], gap="medium")
else:
    col_chat = st.container()
    col_canvas = None

# ============================================================
# ─────────────────── 채팅 영역 ───────────────────
# ============================================================
with col_chat:
    # 헤더
    st.markdown("""
    <div class="main-header">
        <h1>🤖 CLAUDE AI</h1>
        <div class="ow-subtitle">LEARNING ASSISTANT</div>
    </div>
    """, unsafe_allow_html=True)

    if room is None:
        st.markdown("<div style='text-align:center; padding:4rem 0;'>"
                    "<p style='font-size:3.5rem;'>💬</p>"
                    "<p style='font-family:Rajdhani,sans-serif; font-size:1.3rem; color:#ff9828; letter-spacing:3px;'>START NEW CONVERSATION</p>"
                    "</div>", unsafe_allow_html=True)
        st.stop()

    # 방 정보
    ci1, ci2, ci3 = st.columns([3, 2, 2])
    with ci1:
        st.markdown(f"**💬 {room['title']}**")
    with ci2:
        st.markdown(f"<span class='model-badge'>{MODELS[model_name]['short']}</span>", unsafe_allow_html=True)
    with ci3:
        st.markdown(f"<span class='persona-badge'>{persona_key}</span>", unsafe_allow_html=True)
    st.markdown("---")

    # 대화 내용
    if not room["messages"]:
        greeting = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🎓 기본 도우미"])["greeting"]
        st.markdown(f'<div class="chat-ai"><div class="chat-role chat-role-ai">AI ASSISTANT</div>{greeting}</div>', unsafe_allow_html=True)
    else:
        for i, msg in enumerate(room["messages"]):
            if msg["role"] == "user":
                if msg.get("has_file"):
                    st.markdown(f"""
                    <div class="chat-user">
                        <div class="chat-role chat-role-user">YOU</div>
                        📎 <em>{msg.get('file_name','파일')}</em><br><br>{msg['content']}
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="chat-user">
                        <div class="chat-role chat-role-user">YOU</div>
                        {msg['content']}
                    </div>""", unsafe_allow_html=True)
            else:
                # AI 응답
                active_persona_key = room.get("persona", persona_key)
                c_type, c_data = try_parse_ai_response(msg["content"], active_persona_key)
                is_last_ai = (i == len(room["messages"]) - 1)

                if c_type in ("quiz", "code", "mindmap"):
                    # Canvas로 보낼 수 있는 응답 → 채팅엔 요약 + 버튼
                    type_labels = {"quiz": "🧩 퀴즈", "code": "💻 코드", "mindmap": "🗺️ 마인드맵"}
                    label = type_labels.get(c_type, "Canvas")

                    if c_type == "quiz":
                        preview = f"{len(c_data)}문제 생성됨"
                    elif c_type == "code":
                        lang = c_data.get("language", "")
                        title = c_data.get("title", "코드")
                        preview = f"{lang.upper()} — {title}"
                    elif c_type == "mindmap":
                        preview = f"주제: {c_data.get('title', '')}"

                    st.markdown(f"""
                    <div class="chat-ai">
                        <div class="chat-role chat-role-ai">AI ASSISTANT</div>
                        {label} 준비 완료 — {preview}
                    </div>""", unsafe_allow_html=True)

                    # Canvas로 열기 버튼
                    if st.button(f"🎨 Canvas에서 열기 ({label})", key=f"open_canvas_{i}"):
                        open_canvas(c_type, c_data, f"{label} CANVAS")
                        st.rerun()

                elif c_type == "doc":
                    # 문서: 채팅에도 표시하되 Canvas 버튼도 제공
                    st.markdown(f'<div class="chat-ai"><div class="chat-role chat-role-ai">AI ASSISTANT</div></div>', unsafe_allow_html=True)
                    st.markdown(msg["content"])
                    if st.button(f"📄 Canvas에서 문서 보기", key=f"open_doc_{i}"):
                        open_canvas("doc", c_data, "📄 문서 CANVAS")
                        st.rerun()
                else:
                    # 일반 텍스트
                    st.markdown(f'<div class="chat-ai"><div class="chat-role chat-role-ai">AI ASSISTANT</div></div>', unsafe_allow_html=True)
                    st.markdown(msg["content"])

                # 토큰 사용량
                ai_idx = len([m for m in room["messages"][:i+1] if m["role"] == "assistant"]) - 1
                if ai_idx < len(room["token_log"]):
                    tlog = room["token_log"][ai_idx]
                    st.markdown(f"""
                    <div class="usage-bar">
                        <div class="usage-chip">📥 INPUT <strong>{tlog['input']:,}</strong></div>
                        <div class="usage-chip">📤 OUTPUT <strong>{tlog['output']:,}</strong></div>
                        <div class="usage-chip">💰 <strong>${tlog['cost']:.4f}</strong></div>
                        <div class="usage-chip">⏱ <strong>{tlog.get('elapsed',0):.1f}s</strong></div>
                    </div>""", unsafe_allow_html=True)

    # 파일 업로드
    st.markdown("")
    uploaded_file = st.file_uploader(
        "📎 파일 첨부",
        type=["png", "jpg", "jpeg", "gif", "webp", "txt", "py", "js", "csv", "md"],
        label_visibility="collapsed",
        key="file_upload",
    )

    # 입력 폼
    is_quiz_mode = persona_key == "🧩 퀴즈 출제자" or room.get("persona") == "🧩 퀴즈 출제자"
    is_code_mode = persona_key == "💻 코딩 멘토" or room.get("persona") == "💻 코딩 멘토"
    is_mindmap_mode = persona_key == "🗺️ 마인드맵 메이커" or room.get("persona") == "🗺️ 마인드맵 메이커"

    if is_quiz_mode:
        placeholder_text = "퀴즈 주제를 입력하세요! 예: '한국사 조선시대', '화학 원소 주기율표'"
    elif is_code_mode:
        placeholder_text = "코딩 요청을 입력하세요! 예: '피보나치 수열 출력하는 파이썬 코드'"
    elif is_mindmap_mode:
        placeholder_text = "마인드맵 주제를 입력하세요! 예: '광합성', '한국의 역사'"
    else:
        placeholder_text = "질문을 입력하세요..."

    with st.form("chat_form", clear_on_submit=True):
        user_input = st.text_area(
            "메시지 입력",
            placeholder=placeholder_text,
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
        export_lines.append(f"--- Input: {room['total_input']:,} | Output: {room['total_output']:,} | Cost: ${room['total_cost']:.4f} ---")
        st.download_button(
            label="💾 다운로드 (.txt)",
            data="\n".join(export_lines).encode("utf-8"),
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
        room["total_input"] = room["total_output"] = 0
        room["total_cost"] = 0.0
        room["title"] = "새 대화"
        close_canvas()
        save_room_to_sheet(st.session_state.username, room)
        save_user_stats(st.session_state.username)
        st.rerun()

    # 메시지 전송
    if submitted and user_input.strip():
        if not room["messages"]:
            title = user_input.strip()
            room["title"] = title[:30] + "..." if len(title) > 30 else title
            room["persona"] = persona_key

        # 파일 처리
        file_content_for_api = None
        file_name = None
        file_is_image = False

        if uploaded_file is not None:
            file_name = uploaded_file.name
            file_ext = file_name.split(".")[-1].lower()
            if file_ext in ["png", "jpg", "jpeg", "gif", "webp"]:
                file_is_image = True
                file_bytes = uploaded_file.read()
                file_b64 = base64.b64encode(file_bytes).decode("utf-8")
                media_type_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
                file_content_for_api = {"type": "image", "source": {"type": "base64", "media_type": media_type_map.get(file_ext, "image/png"), "data": file_b64}}
            else:
                try:
                    text_content = uploaded_file.read().decode("utf-8")
                except:
                    text_content = uploaded_file.read().decode("latin-1")
                file_content_for_api = {"type": "text", "text": f"[첨부 파일: {file_name}]\n```\n{text_content[:10000]}\n```"}

        user_msg = {"role": "user", "content": user_input.strip(), "has_file": file_name is not None, "file_name": file_name or ""}
        room["messages"].append(user_msg)

        model_info = MODELS[model_name]
        active_persona = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🎓 기본 도우미"])
        context_messages = room["messages"][-20:]
        api_messages = []

        for m in context_messages:
            if m["role"] == "user":
                if m is context_messages[-1] and file_content_for_api:
                    content_parts = [file_content_for_api, {"type": "text", "text": m["content"]}]
                    api_messages.append({"role": "user", "content": content_parts})
                else:
                    api_messages.append({"role": "user", "content": m["content"]})
            else:
                api_messages.append({"role": "assistant", "content": m["content"]})

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
                room["token_log"].append({"input": input_tokens, "output": output_tokens, "cost": turn_cost, "elapsed": elapsed})
                room["total_input"] += input_tokens
                room["total_output"] += output_tokens
                room["total_cost"] += turn_cost
                st.session_state.total_input_tokens += input_tokens
                st.session_state.total_output_tokens += output_tokens
                st.session_state.total_cost += turn_cost

                # AI 응답에서 Canvas 콘텐츠 자동 감지 → Canvas 자동 열기
                c_type, c_data = try_parse_ai_response(answer, room.get("persona", persona_key))
                if c_type:
                    type_labels = {"quiz": "🧩 퀴즈", "code": "💻 코드", "mindmap": "🗺️ 마인드맵", "doc": "📄 문서"}
                    open_canvas(c_type, c_data, f"{type_labels.get(c_type, 'CANVAS')} CANVAS")

                save_room_to_sheet(st.session_state.username, room)
                save_user_stats(st.session_state.username)
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

    # 토큰 차트
    if room and room["token_log"]:
        st.markdown("---")
        with st.expander("📊 TOKEN USAGE CHART", expanded=False):
            import plotly.graph_objects as go
            turns = [f"Turn {i+1}" for i in range(len(room["token_log"]))]
            inputs = [t["input"] for t in room["token_log"]]
            outputs = [t["output"] for t in room["token_log"]]
            costs = [t["cost"] for t in room["token_log"]]
            bg_color = "rgba(240,244,248,0.8)" if st.session_state.theme == "light" else "rgba(10,22,40,0.8)"
            font_color = "#5a6a7a" if st.session_state.theme == "light" else "#8ba3c4"
            grid_color = "rgba(0,0,0,0.06)" if st.session_state.theme == "light" else "rgba(255,152,40,0.08)"
            fig = go.Figure()
            fig.add_trace(go.Bar(name="📥 Input", x=turns, y=inputs, marker=dict(color="rgba(255,152,40,0.8)"), hovertemplate="Input: %{y:,} tokens<extra></extra>"))
            fig.add_trace(go.Bar(name="📤 Output", x=turns, y=outputs, marker=dict(color="rgba(59,130,246,0.8)"), hovertemplate="Output: %{y:,} tokens<extra></extra>"))
            fig.update_layout(barmode="group", plot_bgcolor=bg_color, paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Rajdhani, sans-serif", color=font_color), title=dict(text="TOKEN USAGE PER TURN", font=dict(size=16, color="#ff9828"), x=0.5), xaxis=dict(gridcolor=grid_color), yaxis=dict(gridcolor=grid_color, title="Tokens"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5), margin=dict(l=40, r=20, t=60, b=40), height=350)
            st.plotly_chart(fig, use_container_width=True)
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=turns, y=costs, mode="lines+markers", name="💰 Cost", line=dict(color="#ff9828", width=2, shape="spline"), marker=dict(size=8, color="#ff9828"), fill="tozeroy", fillcolor="rgba(255,152,40,0.1)", hovertemplate="Cost: $%{y:.4f}<extra></extra>"))
            fig2.update_layout(plot_bgcolor=bg_color, paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Rajdhani, sans-serif", color=font_color), title=dict(text="COST PER TURN ($)", font=dict(size=16, color="#3b82f6"), x=0.5), xaxis=dict(gridcolor=grid_color), yaxis=dict(gridcolor=grid_color, title="USD"), margin=dict(l=40, r=20, t=60, b=40), height=300)
            st.plotly_chart(fig2, use_container_width=True)
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("총 입력", f"{room['total_input']:,}")
            sc2.metric("총 출력", f"{room['total_output']:,}")
            sc3.metric("비용", f"${room['total_cost']:.4f}")
            sc4.metric("원화", f"₩{room['total_cost'] * 1400:.0f}")

# ============================================================
# ─────────────────── Canvas 패널 ───────────────────
# ============================================================
if st.session_state.canvas_open and col_canvas is not None:
    with col_canvas:
        st.markdown("---")

        # Canvas 헤더 + 닫기
        hc1, hc2 = st.columns([4, 1])
        with hc1:
            st.markdown(f"### 🎨 {st.session_state.canvas_title}")
        with hc2:
            if st.button("✕ 닫기", key="close_canvas_btn"):
                close_canvas()
                st.rerun()

        # Canvas 탭 네비게이션
        canvas_tabs = st.tabs(["📝 퀴즈", "💻 코드", "📄 문서", "🗺️ 마인드맵"])

        # ── 퀴즈 탭 ──
        with canvas_tabs[0]:
            if st.session_state.canvas_type == "quiz" and st.session_state.canvas_content:
                quiz_list = st.session_state.canvas_content
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
                        <div style="font-size:2.5rem;">{emoji}</div>
                        <div style="font-family:Rajdhani,sans-serif; font-size:1.8rem; font-weight:700; color:#ff9828;">{score}점</div>
                        <div style="color:#94a3b8; font-size:0.9rem;">{correct_count}/{total_q} 정답</div>
                    </div>""", unsafe_allow_html=True)
                    if st.button("🔄 다시 풀기", use_container_width=True):
                        st.session_state.quiz_answers = {}
                        st.session_state.quiz_submitted = False
                        st.rerun()
                else:
                    st.caption(f"🖊️ {len(st.session_state.quiz_answers)}/{total_q} 문제 선택 완료")

                st.markdown("---")

                for qi, q in enumerate(quiz_list):
                    correct_idx = int(q["answer"])
                    submitted_quiz = st.session_state.quiz_submitted
                    user_ans = st.session_state.quiz_answers.get(qi)
                    option_labels = ["A", "B", "C", "D"]

                    st.markdown(f'<div class="quiz-card"><div class="quiz-question">Q{qi+1}. {q["question"]}</div></div>', unsafe_allow_html=True)

                    for oi, opt in enumerate(q["options"]):
                        label = f"{option_labels[oi]}. {opt}"
                        btn_key = f"cv_quiz_{qi}_{oi}"
                        if submitted_quiz:
                            if oi == correct_idx:
                                st.success(f"✅ {label}")
                            elif oi == user_ans and oi != correct_idx:
                                st.error(f"❌ {label}")
                            else:
                                st.button(label, key=btn_key, disabled=True, use_container_width=True)
                        else:
                            if user_ans == oi:
                                st.button(f"☑️ {label}", key=btn_key, disabled=True, use_container_width=True)
                            else:
                                if st.button(label, key=btn_key, use_container_width=True):
                                    st.session_state.quiz_answers[qi] = oi
                                    st.rerun()

                    if submitted_quiz:
                        st.markdown(f'<div class="quiz-explanation">💡 <strong>해설:</strong> {q["explanation"]}</div>', unsafe_allow_html=True)
                    st.markdown("")

                # 정답 제출 버튼
                if not st.session_state.quiz_submitted:
                    all_answered = len(st.session_state.quiz_answers) == total_q
                    if all_answered:
                        if st.button("📝 정답 확인!", use_container_width=True, key="cv_submit_quiz"):
                            st.session_state.quiz_submitted = True
                            st.rerun()
            else:
                st.markdown("""
                <div class="canvas-empty">
                    <div class="icon">🧩</div>
                    <p>퀴즈 출제자 페르소나로<br>주제를 입력하면<br>여기에 퀴즈가 나타납니다</p>
                </div>""", unsafe_allow_html=True)

        # ── 코드 탭 ──
        with canvas_tabs[1]:
            if st.session_state.canvas_type == "code" and st.session_state.canvas_content:
                code_data = st.session_state.canvas_content
                lang = code_data.get("language", "python")
                title = code_data.get("title", "코드")
                explanation = code_data.get("explanation", "")

                st.markdown(f"**{title}** `{lang.upper()}`")
                if explanation:
                    st.info(explanation)

                # 편집 가능한 코드 에디터
                edited_code = st.text_area(
                    "코드 편집",
                    value=st.session_state.code_content or code_data.get("code", ""),
                    height=350,
                    key="canvas_code_editor",
                    label_visibility="collapsed",
                )
                st.session_state.code_content = edited_code

                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("▶ 실행 (Python)", use_container_width=True, key="run_code_btn"):
                        if lang == "python":
                            import io, contextlib
                            output_buf = io.StringIO()
                            try:
                                with contextlib.redirect_stdout(output_buf):
                                    exec(edited_code, {})
                                st.session_state.code_output = output_buf.getvalue() or "(출력 없음)"
                            except Exception as e:
                                st.session_state.code_output = f"❌ 오류: {str(e)}"
                        else:
                            st.session_state.code_output = f"⚠️ {lang.upper()} 실행은 지원되지 않습니다 (Python만 가능)"
                        st.rerun()
                with cc2:
                    if st.button("📋 복사용 보기", use_container_width=True, key="copy_code_btn"):
                        st.code(edited_code, language=lang)

                if st.session_state.code_output:
                    st.markdown("**실행 결과:**")
                    st.code(st.session_state.code_output, language="text")
            else:
                st.markdown("""
                <div class="canvas-empty">
                    <div class="icon">💻</div>
                    <p>코딩 멘토 페르소나로<br>코드를 요청하면<br>여기서 편집·실행할 수 있습니다</p>
                </div>""", unsafe_allow_html=True)

        # ── 문서 탭 ──
        with canvas_tabs[2]:
            if st.session_state.canvas_type == "doc" and st.session_state.canvas_content:
                doc_data = st.session_state.canvas_content
                doc_title = doc_data.get("title", "문서")
                doc_content = doc_data.get("content", "")

                st.markdown(f"### {doc_title}")
                st.markdown("---")

                # 보기 / 편집 모드
                view_mode = st.toggle("✏️ 편집 모드", value=False, key="doc_edit_toggle")
                if view_mode:
                    edited_doc = st.text_area("문서 편집", value=doc_content, height=500, label_visibility="collapsed")
                    if st.button("💾 저장", key="save_doc_btn"):
                        st.session_state.canvas_content["content"] = edited_doc
                        st.rerun()
                else:
                    st.markdown(doc_content)
            else:
                st.markdown("""
                <div class="canvas-empty">
                    <div class="icon">📄</div>
                    <p>AI의 긴 응답이<br>자동으로 여기에<br>문서로 정리됩니다</p>
                </div>""", unsafe_allow_html=True)

        # ── 마인드맵 탭 ──
        with canvas_tabs[3]:
            if st.session_state.canvas_type == "mindmap" and st.session_state.canvas_content:
                mm_data = st.session_state.canvas_content
                mm_title = mm_data.get("title", "마인드맵")
                mm_nodes = mm_data.get("nodes", [])

                st.markdown(f"### 🗺️ {mm_title}")

                # Plotly로 마인드맵 시각화
                try:
                    import plotly.graph_objects as go
                    import math

                    node_x, node_y, node_text, node_color = [], [], [], []
                    edge_x, edge_y = [], []

                    # 중심 노드
                    cx, cy = 0, 0
                    node_x.append(cx); node_y.append(cy)
                    node_text.append(f"<b>{mm_title}</b>")
                    node_color.append("#ff9828")

                    n_main = len(mm_nodes)
                    for mi, mnode in enumerate(mm_nodes):
                        angle = 2 * math.pi * mi / n_main
                        mx = math.cos(angle) * 2
                        my = math.sin(angle) * 2
                        node_x.append(mx); node_y.append(my)
                        node_text.append(f"<b>{mnode['label']}</b>")
                        node_color.append("#3b82f6")
                        edge_x += [cx, mx, None]; edge_y += [cy, my, None]

                        children = mnode.get("children", [])
                        n_child = len(children)
                        for ci2, child in enumerate(children):
                            spread = 0.6
                            ca = angle + spread * (ci2 - (n_child - 1) / 2) / max(n_child, 1)
                            child_x = mx + math.cos(ca) * 1.3
                            child_y = my + math.sin(ca) * 1.3
                            node_x.append(child_x); node_y.append(child_y)
                            node_text.append(child["label"])
                            node_color.append("#22c55e")
                            edge_x += [mx, child_x, None]; edge_y += [my, child_y, None]

                    is_dark = st.session_state.theme == "dark"
                    bg = "rgba(10,22,40,0.8)" if is_dark else "rgba(248,250,252,0.8)"
                    font_c = "#e2e8f0" if is_dark else "#1a2a3a"

                    fig_mm = go.Figure()
                    fig_mm.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", line=dict(color="rgba(148,163,184,0.4)", width=1.5), hoverinfo="none"))
                    fig_mm.add_trace(go.Scatter(
                        x=node_x, y=node_y, mode="markers+text",
                        marker=dict(size=[30 if i == 0 else 22 if nc == "#3b82f6" else 16 for i, nc in enumerate(node_color)],
                                    color=node_color, line=dict(color="rgba(255,255,255,0.3)", width=1.5)),
                        text=node_text, textposition="middle center",
                        textfont=dict(size=[11 if i > 0 else 13 for i in range(len(node_text))], color=font_c),
                        hoverinfo="text",
                    ))
                    fig_mm.update_layout(
                        showlegend=False,
                        plot_bgcolor=bg, paper_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        margin=dict(l=20, r=20, t=20, b=20),
                        height=480,
                    )
                    st.plotly_chart(fig_mm, use_container_width=True)
                except Exception as e:
                    st.error(f"마인드맵 렌더링 오류: {e}")

                # 텍스트 목차도 함께 표시
                with st.expander("📋 텍스트 목차"):
                    for mnode in mm_nodes:
                        st.markdown(f"**▸ {mnode['label']}**")
                        for child in mnode.get("children", []):
                            st.markdown(f"　　• {child['label']}")
            else:
                st.markdown("""
                <div class="canvas-empty">
                    <div class="icon">🗺️</div>
                    <p>마인드맵 메이커 페르소나로<br>주제를 입력하면<br>여기에 마인드맵이 그려집니다</p>
                </div>""", unsafe_allow_html=True)
