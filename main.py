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
st.set_page_config(page_title="🤖 Claude AI", page_icon="🤖", layout="centered")

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
    # stats 초기 행
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
# 대화 저장/불러오기 (Google Sheets)
# ============================================================
def save_room_to_sheet(username, room):
    sheet = get_sheet("conversations")
    all_data = sheet.get_all_records()
    row_idx = None
    for i, row in enumerate(all_data):
        if row["username"] == username and row["room_id"] == room["id"]:
            row_idx = i + 2  # 헤더 + 0-indexed
            break

    row_data = [
        username,
        room["id"],
        room["title"],
        room.get("persona", "🎓 기본 도우미"),
        room["created_at"],
        json.dumps(room["messages"], ensure_ascii=False),
        json.dumps(room["token_log"], ensure_ascii=False),
        room["total_input"],
        room["total_output"],
        room["total_cost"],
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
                "id": room_id,
                "title": row["room_title"],
                "persona": row.get("persona", "🎓 기본 도우미"),
                "messages": messages,
                "token_log": token_log,
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
                background:
                    radial-gradient(ellipse at 10% 20%, rgba(255,152,40,0.06) 0%, transparent 50%),
                    radial-gradient(ellipse at 90% 80%, rgba(59,130,246,0.06) 0%, transparent 50%),
                    linear-gradient(180deg, #f0f4f8 0%, #e8ecf1 30%, #f5f7fa 60%, #eef1f5 100%) !important;
                font-family: 'Noto Sans KR', sans-serif;
            }
            .stApp::before {
                content: '';
                position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background:
                    linear-gradient(90deg, rgba(255,152,40,0.02) 1px, transparent 1px),
                    linear-gradient(0deg, rgba(255,152,40,0.02) 1px, transparent 1px);
                background-size: 60px 60px;
                pointer-events: none; z-index: 0;
            }
            .stApp::after { display: none; }

            .main-header h1 {
                font-family: 'Rajdhani', sans-serif;
                color: #1a2a3a; font-size: 2.8rem; font-weight: 700; letter-spacing: 3px;
                text-shadow: 0 0 20px rgba(255,152,40,0.15);
            }
            .main-header .ow-subtitle { color: #e0780a; }

            .chat-user {
                background: linear-gradient(135deg, rgba(255,152,40,0.12), rgba(255,120,20,0.06));
                border: 1px solid rgba(255,152,40,0.25); border-left: 3px solid #ff9828;
                border-radius: 4px 12px 12px 4px; padding: 1rem 1.3rem; margin: 0.8rem 0;
                color: #3a2a0a; max-width: 88%; margin-left: auto; font-size: 0.95rem; line-height: 1.6;
                box-shadow: 0 2px 10px rgba(255,152,40,0.06);
            }
            .chat-ai {
                background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(37,99,235,0.04));
                border: 1px solid rgba(59,130,246,0.18); border-left: 3px solid #3b82f6;
                border-radius: 12px 4px 4px 12px; padding: 1rem 1.3rem; margin: 0.8rem 0;
                color: #1a2a3a; max-width: 88%; font-size: 0.95rem; line-height: 1.7;
                box-shadow: 0 2px 10px rgba(59,130,246,0.04);
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

            section[data-testid="stSidebar"] { background: linear-gradient(180deg, #e8ecf1, #dde3ea, #e0e6ec) !important; border-right: 1px solid rgba(255,152,40,0.1) !important; }
            section[data-testid="stSidebar"] h2 { font-family: 'Rajdhani', sans-serif !important; color: #e0780a !important; letter-spacing: 2px !important; }
            section[data-testid="stSidebar"] h5 { font-family: 'Rajdhani', sans-serif !important; color: #c06000 !important; letter-spacing: 2px !important; text-transform: uppercase !important; }
            [data-testid="stMetricValue"] { font-family: 'Rajdhani', sans-serif !important; color: #e0780a !important; }
            [data-testid="stMetricLabel"] { color: #5a6a7a !important; }

            .ow-corner-tl { position: fixed; width: 60px; height: 60px; top: 8px; left: 8px; border-top: 2px solid rgba(255,152,40,0.3); border-left: 2px solid rgba(255,152,40,0.3); pointer-events: none; z-index: 999; }
            .ow-corner-br { position: fixed; width: 60px; height: 60px; bottom: 8px; right: 8px; border-bottom: 2px solid rgba(59,130,246,0.3); border-right: 2px solid rgba(59,130,246,0.3); pointer-events: none; z-index: 999; }

            hr { border-color: rgba(0,0,0,0.08) !important; }

            /* 퀴즈 스타일 - 라이트 */
            .quiz-option-btn { background: rgba(255,255,255,0.9); border: 2px solid rgba(59,130,246,0.25); border-radius: 8px; padding: 0.8rem 1.2rem; margin: 0.4rem 0; color: #1a2a3a; cursor: pointer; transition: all 0.2s; width: 100%; text-align: left; font-size: 0.95rem; }
            .quiz-correct { background: rgba(34,197,94,0.12) !important; border-color: #22c55e !important; color: #15803d !important; }
            .quiz-wrong { background: rgba(239,68,68,0.12) !important; border-color: #ef4444 !important; color: #dc2626 !important; }
            .quiz-card { background: rgba(255,255,255,0.8); border: 1px solid rgba(59,130,246,0.15); border-radius: 12px; padding: 1.5rem; margin: 1rem 0; }
            .quiz-question { color: #1a2a3a; font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; line-height: 1.6; }
            .quiz-explanation { background: rgba(255,152,40,0.06); border-left: 3px solid #ff9828; padding: 1rem; border-radius: 0 8px 8px 0; margin-top: 1rem; color: #3a4a5a; font-size: 0.9rem; line-height: 1.6; }
        </style>
        <div class="ow-corner-tl"></div><div class="ow-corner-br"></div>
        """
    else:
        return """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');

            .stApp {
                background:
                    radial-gradient(ellipse at 10% 20%, rgba(255,152,40,0.12) 0%, transparent 50%),
                    radial-gradient(ellipse at 90% 80%, rgba(59,130,246,0.10) 0%, transparent 50%),
                    linear-gradient(180deg, #0a1628 0%, #0d1f3c 15%, #102a4a 30%, #0f2844 50%, #0d1f3c 70%, #0b1a33 85%, #091425 100%) !important;
                font-family: 'Noto Sans KR', sans-serif;
            }
            .stApp::before {
                content: ''; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background: linear-gradient(90deg, rgba(255,152,40,0.03) 1px, transparent 1px), linear-gradient(0deg, rgba(255,152,40,0.03) 1px, transparent 1px);
                background-size: 60px 60px; pointer-events: none; z-index: 0;
            }
            .stApp::after {
                content: ''; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px);
                pointer-events: none; z-index: 0;
            }

            .main-header h1 {
                font-family: 'Rajdhani', sans-serif; color: #ffffff; font-size: 2.8rem; font-weight: 700; letter-spacing: 3px;
                text-shadow: 0 0 30px rgba(255,152,40,0.3), 0 0 60px rgba(255,152,40,0.1);
            }
            .main-header .ow-subtitle { color: #ff9828; }

            .chat-user {
                background: linear-gradient(135deg, rgba(255,152,40,0.15), rgba(255,120,20,0.08));
                border: 1px solid rgba(255,152,40,0.3); border-left: 3px solid #ff9828;
                border-radius: 4px 12px 12px 4px; padding: 1rem 1.3rem; margin: 0.8rem 0;
                color: #fde8c8; max-width: 88%; margin-left: auto; font-size: 0.95rem; line-height: 1.6;
                box-shadow: 0 2px 15px rgba(255,152,40,0.08); position: relative;
            }
            .chat-user::before { content: ''; position: absolute; top: 0; right: 0; width: 40px; height: 3px; background: linear-gradient(90deg, transparent, #ff9828); }
            .chat-ai {
                background: linear-gradient(135deg, rgba(59,130,246,0.10), rgba(37,99,235,0.05));
                border: 1px solid rgba(59,130,246,0.2); border-left: 3px solid #3b82f6;
                border-radius: 12px 4px 4px 12px; padding: 1rem 1.3rem; margin: 0.8rem 0;
                color: #c8dff5; max-width: 88%; font-size: 0.95rem; line-height: 1.7;
                box-shadow: 0 2px 15px rgba(59,130,246,0.06); position: relative;
            }
            .chat-ai::before { content: ''; position: absolute; top: 0; left: 0; width: 40px; height: 3px; background: linear-gradient(90deg, #3b82f6, transparent); }
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

            section[data-testid="stSidebar"] { background: linear-gradient(180deg, #060e1a, #091624, #0b1a2e, #081420) !important; border-right: 1px solid rgba(255,152,40,0.1) !important; }
            section[data-testid="stSidebar"] h2 { font-family: 'Rajdhani', sans-serif !important; color: #ff9828 !important; letter-spacing: 2px !important; }
            section[data-testid="stSidebar"] h5 { font-family: 'Rajdhani', sans-serif !important; color: #ffb347 !important; letter-spacing: 2px !important; text-transform: uppercase !important; }
            [data-testid="stMetricValue"] { font-family: 'Rajdhani', sans-serif !important; color: #ffb347 !important; }
            [data-testid="stMetricLabel"] { color: #5a7ca3 !important; }

            .ow-corner-tl { position: fixed; width: 60px; height: 60px; top: 8px; left: 8px; border-top: 2px solid rgba(255,152,40,0.15); border-left: 2px solid rgba(255,152,40,0.15); pointer-events: none; z-index: 999; }
            .ow-corner-br { position: fixed; width: 60px; height: 60px; bottom: 8px; right: 8px; border-bottom: 2px solid rgba(59,130,246,0.15); border-right: 2px solid rgba(59,130,246,0.15); pointer-events: none; z-index: 999; }

            hr { border-color: rgba(255,152,40,0.1) !important; }
            ::-webkit-scrollbar { width: 6px; }
            ::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); }
            ::-webkit-scrollbar-thumb { background: rgba(255,152,40,0.3); border-radius: 3px; }

            /* 퀴즈 스타일 - 다크 */
            .quiz-option-btn { background: rgba(255,255,255,0.05); border: 2px solid rgba(59,130,246,0.2); border-radius: 8px; padding: 0.8rem 1.2rem; margin: 0.4rem 0; color: #c8dff5; cursor: pointer; transition: all 0.2s; width: 100%; text-align: left; font-size: 0.95rem; }
            .quiz-correct { background: rgba(34,197,94,0.15) !important; border-color: #22c55e !important; color: #86efac !important; }
            .quiz-wrong { background: rgba(239,68,68,0.15) !important; border-color: #ef4444 !important; color: #fca5a5 !important; }
            .quiz-card { background: rgba(255,255,255,0.04); border: 1px solid rgba(59,130,246,0.15); border-radius: 12px; padding: 1.5rem; margin: 1rem 0; }
            .quiz-question { color: #e2e8f0; font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; line-height: 1.6; }
            .quiz-explanation { background: rgba(255,152,40,0.08); border-left: 3px solid #ff9828; padding: 1rem; border-radius: 0 8px 8px 0; margin-top: 1rem; color: #c8dff5; font-size: 0.9rem; line-height: 1.6; }
        </style>
        <div class="ow-corner-tl"></div><div class="ow-corner-br"></div>
        """

# ============================================================
# 공통 버튼 CSS (테마 무관)
# ============================================================
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
        box-shadow: 0 4px 20px rgba(255,152,40,0.3), inset 0 1px 0 rgba(255,255,255,0.2) !important;
    }
    .stFormSubmitButton:nth-of-type(1) > button:hover {
        background: linear-gradient(135deg, #ffb347, #ff9828) !important;
        box-shadow: 0 6px 30px rgba(255,152,40,0.5) !important; transform: translateY(-1px) !important;
    }
    .stFormSubmitButton:nth-of-type(2) > button {
        background: linear-gradient(135deg, rgba(59,130,246,0.25), rgba(37,99,235,0.15)) !important;
        border: 1px solid rgba(59,130,246,0.4) !important; color: #60a5fa !important;
    }
    .stFormSubmitButton:nth-of-type(2) > button:hover {
        background: linear-gradient(135deg, rgba(59,130,246,0.4), rgba(37,99,235,0.25)) !important;
        box-shadow: 0 4px 20px rgba(59,130,246,0.3) !important; color: #ffffff !important;
    }
    .stFormSubmitButton:nth-of-type(3) > button {
        background: linear-gradient(135deg, rgba(239,68,68,0.2), rgba(220,38,38,0.1)) !important;
        border: 1px solid rgba(239,68,68,0.3) !important; color: #f87171 !important;
    }
    .stFormSubmitButton:nth-of-type(3) > button:hover {
        background: linear-gradient(135deg, rgba(239,68,68,0.35), rgba(220,38,38,0.2)) !important;
        color: #ffffff !important;
    }
    section[data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(135deg, rgba(255,152,40,0.08), rgba(255,120,20,0.04)) !important;
        border: 1px solid rgba(255,152,40,0.2) !important; color: #c0a070 !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: linear-gradient(135deg, rgba(255,152,40,0.2), rgba(255,120,20,0.12)) !important;
        border-color: #ff9828 !important; color: #ffb347 !important;
        box-shadow: 0 0 15px rgba(255,152,40,0.15) !important;
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
    "🎓 기본 도우미": {"system": "당신은 당곡고등학교 학생들의 학습을 돕는 친절한 AI 도우미입니다. 한국어로 답변합니다.", "greeting": "안녕하세요! 무엇이든 물어보세요 🙂"},
    "🔬 과학 선생님": {"system": "당신은 열정적인 과학 선생님입니다. 실생활 예시와 함께 설명합니다. 한국어로 답변합니다.", "greeting": "과학의 세계에 오신 걸 환영합니다! 🔬"},
    "📐 수학 튜터": {"system": "당신은 수학 튜터입니다. 단계별로 풀이하고 원리를 설명합니다. 한국어로 답변합니다.", "greeting": "수학 문제 함께 풀어봐요! 📐"},
    "📚 역사 해설가": {"system": "당신은 역사 해설가입니다. 이야기처럼 생동감 있게 전달합니다. 한국어로 답변합니다.", "greeting": "역사 속 이야기를 들려드릴게요! 📚"},
    "🇬🇧 영어 코치": {"system": "당신은 영어 코치입니다. 한국어로 설명하되 영어 예문을 풍부하게 사용합니다.", "greeting": "Let's learn English together! 🇬🇧"},
    "🏛️ 소크라테스": {"system": "당신은 소크라테스입니다. 답을 직접 알려주지 않고 질문으로 사고를 유도합니다. 한국어로 대화합니다.", "greeting": "나는 소크라테스라네. 🏛️"},
    "💻 코딩 멘토": {"system": "당신은 프로그래밍 멘토입니다. 전체 코드와 주석을 제공합니다. 한국어로 설명합니다.", "greeting": "코딩 세계에 오신 걸 환영합니다! 💻"},
    "✍️ 논술 코치": {"system": "당신은 논술 코치입니다. 논리 구조와 표현력을 개선하도록 도와줍니다. 한국어로 답변합니다.", "greeting": "글쓰기 실력을 함께 키워봐요! ✍️"},
    "🧩 퀴즈 출제자": {"system": "당신은 퀴즈 출제자입니다. 주어진 주제에 대해 4지선다 퀴즈를 JSON 형식으로 출제합니다. 반드시 아래 형식의 JSON만 출력하세요. 다른 텍스트 없이 JSON만 출력합니다:\n[{\"question\": \"문제\", \"options\": [\"A\", \"B\", \"C\", \"D\"], \"answer\": 0, \"explanation\": \"해설\"}]\nanswer는 0-3 정수(정답 인덱스)입니다. 한국어로 출제합니다. 최소 3문제 이상 출제하세요.", "greeting": "퀴즈 주제를 알려주세요! 🧩"},
}

# ============================================================
# 세션 초기화
# ============================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "display_name" not in st.session_state:
    st.session_state.display_name = ""
if "rooms" not in st.session_state:
    st.session_state.rooms = {}
if "current_room" not in st.session_state:
    st.session_state.current_room = ""
if "total_input_tokens" not in st.session_state:
    st.session_state.total_input_tokens = 0
if "total_output_tokens" not in st.session_state:
    st.session_state.total_output_tokens = 0
if "total_cost" not in st.session_state:
    st.session_state.total_cost = 0.0
if "theme" not in st.session_state:
    st.session_state.theme = "dark"
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "quiz_answers" not in st.session_state:
    st.session_state.quiz_answers = {}
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False

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

# ============================================================
# 사이드바
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
                    st.session_state.quiz_data = None
                    st.session_state.quiz_answers = {}
                    st.session_state.quiz_submitted = False
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
# 메인 헤더
# ============================================================
st.markdown("""
<div class="main-header">
    <h1>🤖 CLAUDE AI</h1>
    <div class="ow-subtitle">LEARNING ASSISTANT</div>
</div>
""", unsafe_allow_html=True)

room = get_current_room()
if room is None:
    st.markdown("<div style='text-align:center; padding:4rem 0;'>"
                "<p style='font-size:3.5rem;'>💬</p>"
                "<p style='font-family:Rajdhani,sans-serif; font-size:1.3rem; color:#ff9828; letter-spacing:3px;'>START NEW CONVERSATION</p>"
                "</div>", unsafe_allow_html=True)
    st.stop()

# 정보 표시
ci1, ci2, ci3 = st.columns([3, 2, 2])
with ci1:
    st.markdown(f"**💬 {room['title']}**")
with ci2:
    st.markdown(f"<span class='model-badge'>{MODELS[model_name]['short']}</span>", unsafe_allow_html=True)
with ci3:
    st.markdown(f"<span class='persona-badge'>{persona_key}</span>", unsafe_allow_html=True)

st.markdown("---")

# ============================================================
# 퀴즈 모드 (🧩 퀴즈 출제자 페르소나일 때)
# ============================================================
is_quiz_mode = (persona_key == "🧩 퀴즈 출제자") or (room.get("persona") == "🧩 퀴즈 출제자")

# ============================================================
# 대화 내용 표시
# ============================================================
if not room["messages"]:
    greeting = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🎓 기본 도우미"])["greeting"]
    st.markdown(f'<div class="chat-ai"><div class="chat-role chat-role-ai">AI ASSISTANT</div>{greeting}</div>', unsafe_allow_html=True)
else:
    for i, msg in enumerate(room["messages"]):
        if msg["role"] == "user":
            # 파일 첨부 표시
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
            st.markdown(f'<div class="chat-ai"><div class="chat-role chat-role-ai">AI ASSISTANT</div></div>', unsafe_allow_html=True)

            # 퀴즈 모드: JSON 파싱 시도
            is_quiz_response = False
            if is_quiz_mode and i == len(room["messages"]) - 1:
                try:
                    raw = msg["content"].strip()
                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    quiz_list = json.loads(raw)
                    if isinstance(quiz_list, list) and len(quiz_list) > 0 and "question" in quiz_list[0]:
                        is_quiz_response = True
                        if st.session_state.quiz_data != quiz_list:
                            st.session_state.quiz_data = quiz_list
                            st.session_state.quiz_answers = {}
                            st.session_state.quiz_submitted = False
                except:
                    pass

            if is_quiz_response and st.session_state.quiz_data:
                # 인터랙티브 퀴즈 렌더링
                quiz_list = st.session_state.quiz_data
                total_q = len(quiz_list)
                st.markdown(f"### 🧩 퀴즈 ({total_q}문제)")

                for qi, q in enumerate(quiz_list):
                    st.markdown(f'<div class="quiz-card"><div class="quiz-question">Q{qi+1}. {q["question"]}</div></div>', unsafe_allow_html=True)

                    options = q["options"]
                    correct_idx = int(q["answer"])
                    submitted = st.session_state.quiz_submitted
                    user_ans = st.session_state.quiz_answers.get(qi)

                    option_labels = ["A", "B", "C", "D"]
                    for oi, opt in enumerate(options):
                        label = f"{option_labels[oi]}. {opt}"
                        btn_key = f"quiz_{qi}_{oi}"

                        if submitted:
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

                    if submitted:
                        st.markdown(f'<div class="quiz-explanation">💡 <strong>해설:</strong> {q["explanation"]}</div>', unsafe_allow_html=True)

                    st.markdown("---")

                # 제출 / 결과
                all_answered = len(st.session_state.quiz_answers) == total_q

                if not st.session_state.quiz_submitted:
                    if all_answered:
                        if st.button("📝 정답 확인하기!", use_container_width=True, key="submit_quiz"):
                            st.session_state.quiz_submitted = True
                            st.rerun()
                    else:
                        st.info(f"🖊️ {len(st.session_state.quiz_answers)}/{total_q} 문제 선택 완료. 모든 문제를 선택해주세요!")
                else:
                    correct_count = sum(
                        1 for qi, q in enumerate(quiz_list)
                        if st.session_state.quiz_answers.get(qi) == int(q["answer"])
                    )
                    score = int(correct_count / total_q * 100)
                    if score == 100:
                        emoji = "🏆"
                    elif score >= 70:
                        emoji = "👏"
                    elif score >= 40:
                        emoji = "💪"
                    else:
                        emoji = "📖"
                    st.markdown(f"### {emoji} 결과: {correct_count}/{total_q} ({score}점)")

                    if st.button("🔄 다시 풀기", key="retry_quiz", use_container_width=True):
                        st.session_state.quiz_answers = {}
                        st.session_state.quiz_submitted = False
                        st.rerun()
            else:
                st.markdown(msg["content"])

            # 토큰 사용량
            token_idx = len([m for m in room["messages"][:i+1] if m["role"] == "assistant"]) - 1
            if token_idx < len(room["token_log"]):
                tlog = room["token_log"][token_idx]
                st.markdown(f"""
                <div class="usage-bar">
                    <div class="usage-chip">📥 INPUT <strong>{tlog['input']:,}</strong></div>
                    <div class="usage-chip">📤 OUTPUT <strong>{tlog['output']:,}</strong></div>
                    <div class="usage-chip">💰 <strong>${tlog['cost']:.4f}</strong></div>
                    <div class="usage-chip">⏱ <strong>{tlog.get('elapsed',0):.1f}s</strong></div>
                </div>""", unsafe_allow_html=True)

# ============================================================
# 파일 업로드
# ============================================================
st.markdown("")
uploaded_file = st.file_uploader(
    "📎 파일 첨부 (이미지/텍스트, 최대 10MB)",
    type=["png", "jpg", "jpeg", "gif", "webp", "txt", "py", "js", "csv", "md"],
    label_visibility="collapsed",
    key="file_upload",
)

# ============================================================
# 입력 영역
# ============================================================
with st.form("chat_form", clear_on_submit=True):
    if is_quiz_mode and not room["messages"]:
        placeholder_text = "퀴즈 주제를 입력하세요! 예: '한국사 조선시대', '고1 화학 원소 주기율표'"
    elif is_quiz_mode:
        placeholder_text = "다른 주제로 퀴즈를 원하면 입력하세요!"
    else:
        placeholder_text = "질문을 입력하세요... (Ctrl+Enter로 전송)"

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

# ============================================================
# 내보내기
# ============================================================
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

# ============================================================
# 대화 초기화
# ============================================================
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
    st.session_state.quiz_data = None
    st.session_state.quiz_answers = {}
    st.session_state.quiz_submitted = False
    save_room_to_sheet(st.session_state.username, room)
    save_user_stats(st.session_state.username)
    st.rerun()

# ============================================================
# 메시지 전송
# ============================================================
if submitted and user_input.strip():
    # 첫 메시지면 제목 자동 생성 & 페르소나 저장
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
            media_type_map = {
                "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp",
            }
            file_content_for_api = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type_map.get(file_ext, "image/png"),
                    "data": file_b64,
                },
            }
        else:
            # 텍스트 파일
            try:
                text_content = uploaded_file.read().decode("utf-8")
            except:
                text_content = uploaded_file.read().decode("latin-1")
            file_content_for_api = {
                "type": "text",
                "text": f"[첨부 파일: {file_name}]\n```\n{text_content[:10000]}\n```",
            }

    # 유저 메시지 저장 (표시용)
    user_msg = {
        "role": "user",
        "content": user_input.strip(),
        "has_file": file_name is not None,
        "file_name": file_name or "",
    }
    room["messages"].append(user_msg)

    # API 메시지 구성
    model_info = MODELS[model_name]
    active_persona = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🎓 기본 도우미"])

    # 대화 맥락 (최근 20개)
    context_messages = room["messages"][-20:]
    api_messages = []

    for m in context_messages:
        if m["role"] == "user":
            # 마지막 메시지이고 파일이 있으면 멀티파트
            if m is context_messages[-1] and file_content_for_api:
                content_parts = []
                if file_is_image:
                    content_parts.append(file_content_for_api)
                    content_parts.append({"type": "text", "text": m["content"]})
                else:
                    content_parts.append(file_content_for_api)
                    content_parts.append({"type": "text", "text": m["content"]})
                api_messages.append({"role": "user", "content": content_parts})
            else:
                api_messages.append({"role": "user", "content": m["content"]})
        else:
            api_messages.append({"role": "assistant", "content": m["content"]})

    # API 호출
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

            # AI 메시지 추가
            room["messages"].append({"role": "assistant", "content": answer})
            room["token_log"].append({
                "input": input_tokens,
                "output": output_tokens,
                "cost": turn_cost,
                "elapsed": elapsed,
            })

            # 통계 업데이트
            room["total_input"] += input_tokens
            room["total_output"] += output_tokens
            room["total_cost"] += turn_cost

            st.session_state.total_input_tokens += input_tokens
            st.session_state.total_output_tokens += output_tokens
            st.session_state.total_cost += turn_cost

            # 퀴즈 상태 리셋 (새 퀴즈 응답 대비)
            if is_quiz_mode:
                st.session_state.quiz_data = None
                st.session_state.quiz_answers = {}
                st.session_state.quiz_submitted = False

            # Google Sheets 저장
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

# ============================================================
# Plotly 토큰 사용량 그래프
# ============================================================
if room["token_log"]:
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

        # 토큰 바 차트
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="📥 Input", x=turns, y=inputs,
            marker=dict(color="rgba(255,152,40,0.8)", line=dict(color="#ff9828", width=1)),
            hovertemplate="Input: %{y:,} tokens<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            name="📤 Output", x=turns, y=outputs,
            marker=dict(color="rgba(59,130,246,0.8)", line=dict(color="#3b82f6", width=1)),
            hovertemplate="Output: %{y:,} tokens<extra></extra>",
        ))
        fig.update_layout(
            barmode="group",
            plot_bgcolor=bg_color, paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Rajdhani, sans-serif", color=font_color),
            title=dict(text="TOKEN USAGE PER TURN", font=dict(size=16, color="#ff9828"), x=0.5),
            xaxis=dict(gridcolor=grid_color),
            yaxis=dict(gridcolor=grid_color, title="Tokens"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            margin=dict(l=40, r=20, t=60, b=40), height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

        # 비용 라인 차트
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=turns, y=costs, mode="lines+markers", name="💰 Cost",
            line=dict(color="#ff9828", width=2, shape="spline"),
            marker=dict(size=8, color="#ff9828", line=dict(color="#ffffff", width=1)),
            fill="tozeroy", fillcolor="rgba(255,152,40,0.1)",
            hovertemplate="Cost: $%{y:.4f}<extra></extra>",
        ))
        fig2.update_layout(
            plot_bgcolor=bg_color, paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Rajdhani, sans-serif", color=font_color),
            title=dict(text="COST PER TURN ($)", font=dict(size=16, color="#3b82f6"), x=0.5),
            xaxis=dict(gridcolor=grid_color),
            yaxis=dict(gridcolor=grid_color, title="USD"),
            margin=dict(l=40, r=20, t=60, b=40), height=300,
        )
        st.plotly_chart(fig2, use_container_width=True)

        # 숫자 요약
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("총 입력", f"{room['total_input']:,}")
        sc2.metric("총 출력", f"{room['total_output']:,}")
        sc3.metric("비용", f"${room['total_cost']:.4f}")
        sc4.metric("원화", f"₩{room['total_cost'] * 1400:.0f}")
