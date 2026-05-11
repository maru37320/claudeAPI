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
# 셀 값 최대 길이
# ============================================================
CELL_LIMIT = 45000

def split_long_text(text, limit=CELL_LIMIT):
    if len(text) <= limit:
        return [text]
    chunks = []
    for i in range(0, len(text), limit):
        chunks.append(text[i:i+limit])
    return chunks

def join_chunked_text(chunks):
    return "".join(str(c) for c in chunks if c)

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
    all_data = sheet.get_all_values()
    
    messages_json = json.dumps(room["messages"], ensure_ascii=False)
    token_log_json = json.dumps(room["token_log"], ensure_ascii=False)
    
    msg_chunks = split_long_text(messages_json)
    tlog_chunks = split_long_text(token_log_json)
    
    row_data = (
        [username, room["id"], room["title"],
         room.get("persona", "🔬 학습 도우미"), room["created_at"]]
        + [len(msg_chunks)] + msg_chunks
        + [len(tlog_chunks)] + tlog_chunks
        + [room["total_input"], room["total_output"], room["total_cost"]]
    )
    
    row_idx = None
    for i, row in enumerate(all_data):
        if len(row) >= 2 and row[0] == username and row[1] == room["id"]:
            row_idx = i + 1
            break
    
    if row_idx:
        sheet.delete_rows(row_idx)
        sheet.append_row(row_data)
    else:
        sheet.append_row(row_data)

def delete_room_from_sheet(username, room_id):
    sheet = get_sheet("conversations")
    all_data = sheet.get_all_values()
    for i, row in enumerate(all_data):
        if len(row) >= 2 and row[0] == username and row[1] == room_id:
            sheet.delete_rows(i + 1)
            break

def load_rooms_from_sheet(username):
    sheet = get_sheet("conversations")
    all_data = sheet.get_all_values()
    rooms = {}
    
    for row in all_data:
        if not row or row[0] != username:
            continue
        if len(row) < 6:
            continue
        
        try:
            room_id = row[1]
            title = row[2]
            persona = row[3] if len(row) > 3 else "🔬 학습 도우미"
            created_at = row[4] if len(row) > 4 else ""
            
            idx = 5
            
            try:
                msg_chunk_count = int(row[idx]) if idx < len(row) else 0
            except:
                msg_chunk_count = 0
            idx += 1
            
            msg_chunks = []
            for _ in range(msg_chunk_count):
                if idx < len(row):
                    msg_chunks.append(row[idx])
                    idx += 1
            
            messages_json = join_chunked_text(msg_chunks)
            try:
                messages = json.loads(messages_json) if messages_json else []
            except:
                messages = []
            
            try:
                tlog_chunk_count = int(row[idx]) if idx < len(row) else 0
            except:
                tlog_chunk_count = 0
            idx += 1
            
            tlog_chunks = []
            for _ in range(tlog_chunk_count):
                if idx < len(row):
                    tlog_chunks.append(row[idx])
                    idx += 1
            
            tlog_json = join_chunked_text(tlog_chunks)
            try:
                token_log = json.loads(tlog_json) if tlog_json else []
            except:
                token_log = []
            
            total_input = int(row[idx]) if idx < len(row) and row[idx] else 0
            idx += 1
            total_output = int(row[idx]) if idx < len(row) and row[idx] else 0
            idx += 1
            total_cost = float(row[idx]) if idx < len(row) and row[idx] else 0.0
            
            rooms[room_id] = {
                "id": room_id, "title": title, "persona": persona,
                "messages": messages, "token_log": token_log,
                "created_at": created_at,
                "total_input": total_input,
                "total_output": total_output,
                "total_cost": total_cost,
            }
        except Exception as e:
            continue
    
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
# 테마 CSS — Canvas/채팅 스크롤 분리 포함
# ============================================================
def get_theme_css(theme):
    # 공통: Canvas와 채팅창 독립 스크롤
    scroll_css = """
/* ── 독립 스크롤: 채팅 영역 ── */
.chat-scroll-area {
    height: calc(100vh - 260px);
    overflow-y: auto;
    padding-right: 8px;
}
/* ── 독립 스크롤: Canvas 영역 ── */
.canvas-scroll-area {
    height: calc(100vh - 120px);
    overflow-y: auto;
    padding-right: 4px;
    position: sticky;
    top: 0;
}
/* Canvas 패널 고정 */
.canvas-panel {
    position: sticky;
    top: 0;
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}
"""
    if theme == "light":
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

.stSelectbox > div > div {{
    background: #ffffff !important; border: 1px solid rgba(0,0,0,0.15) !important;
    color: #1a1a1a !important; border-radius: 8px !important;
}}
.stSelectbox > div > div > div {{ color: #1a1a1a !important; }}
[data-baseweb="popover"] {{ background: #ffffff !important; }}
[data-baseweb="menu"] {{ background: #ffffff !important; }}
[data-baseweb="option"] {{ background: #ffffff !important; color: #1a1a1a !important; }}
[data-baseweb="option"]:hover {{ background: #f0efea !important; }}

section[data-testid="stSidebar"] .stSelectbox > div > div {{
    background: #ffffff !important; color: #1a1a1a !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] {{
    background: #ffffff !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] * {{
    color: #1a1a1a !important; background: #ffffff !important;
}}

/* 페르소나 selectbox 텍스트 입력 차단 */
section[data-testid="stSidebar"] [data-baseweb="select"] input {{
    pointer-events: none !important;
    user-select: none !important;
    caret-color: transparent !important;
}}

.stMarkdown, .stMarkdown p, .stMarkdown li,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {{ color: #1a1a1a !important; }}
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

.stButton > button, .stFormSubmitButton > button {{
    font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
    font-size: 0.82rem !important; border-radius: 8px !important;
    transition: all 0.18s ease !important;
}}
.stButton > button {{
    background: #ffffff !important; border: 1px solid rgba(0,0,0,0.18) !important; color: #1a1a1a !important;
}}
.stButton > button:hover {{ background: #f0efea !important; color: #000 !important; }}
.stFormSubmitButton > button {{
    background: #ffffff !important; border: 1px solid rgba(0,0,0,0.18) !important; color: #1a1a1a !important;
}}
.stFormSubmitButton > button:hover {{ background: #e8e7e2 !important; color: #000 !important; }}
.stDownloadButton > button {{
    background: #ffffff !important; border: 1px solid rgba(0,0,0,0.18) !important;
    color: #1a1a1a !important; border-radius: 8px !important;
}}

/* Canvas 열림 표시 버튼 */
.canvas-btn-active > button {{
    background: #1a1a1a !important; color: #ffffff !important; border-color: #1a1a1a !important;
}}

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
    background: rgba(0,0,0,0.06); border: 1px solid rgba(0,0,0,0.12);
    border-radius: 8px; padding: 5px 10px;
    font-size: 0.8rem; font-weight: 500; color: #333; margin: 2px 4px 2px 0;
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

{scroll_css}
/* 라이트모드 스크롤바 */
.chat-scroll-area::-webkit-scrollbar,
.canvas-scroll-area::-webkit-scrollbar {{ width: 5px; }}
.chat-scroll-area::-webkit-scrollbar-track,
.canvas-scroll-area::-webkit-scrollbar-track {{ background: transparent; }}
.chat-scroll-area::-webkit-scrollbar-thumb,
.canvas-scroll-area::-webkit-scrollbar-thumb {{ background: rgba(0,0,0,0.15); border-radius: 3px; }}
</style>
"""
    else:  # dark
        return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
* {{ box-sizing: border-box; }}
.stApp {{ background: #1c1c1e !important; font-family: 'Inter', -apple-system, sans-serif; color: #e8e6e1 !important; }}

section[data-testid="stSidebar"] {{ background: #161618 !important; border-right: 1px solid rgba(255,255,255,0.06) !important; }}
section[data-testid="stSidebar"] * {{ color: #e8e6e1 !important; }}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaption {{ color: #888 !important; }}

.stSelectbox > div > div {{
    background: #2a2a2d !important; border: 1px solid rgba(255,255,255,0.1) !important;
    color: #e8e6e1 !important; border-radius: 8px !important;
}}
.stSelectbox > div > div > div {{ color: #e8e6e1 !important; }}
[data-baseweb="popover"] {{ background: #2a2a2d !important; }}
[data-baseweb="menu"] {{ background: #2a2a2d !important; }}
[data-baseweb="option"] {{ background: #2a2a2d !important; color: #e8e6e1 !important; }}
[data-baseweb="option"]:hover {{ background: #3a3a3d !important; }}
.stSelectbox svg {{ fill: #888 !important; }}

/* 페르소나 selectbox 텍스트 입력 차단 */
section[data-testid="stSidebar"] [data-baseweb="select"] input {{
    pointer-events: none !important;
    user-select: none !important;
    caret-color: transparent !important;
}}

.stMarkdown, .stMarkdown p, .stMarkdown li,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {{ color: #e8e6e1 !important; }}
[data-testid="stMetricValue"] {{ color: #e8e6e1 !important; font-weight: 600 !important; }}
[data-testid="stMetricLabel"] {{ color: #777 !important; }}
.stCaption, small {{ color: #666 !important; }}
.stInfo {{ color: #e8e6e1 !important; background: rgba(255,255,255,0.06) !important; }}

.stTextArea textarea {{
    background: #2a2a2d !important; border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 14px !important; color: #e8e6e1 !important;
    font-size: 0.95rem !important; line-height: 1.6 !important;
    padding: 14px 16px !important; resize: none !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.2) !important; caret-color: #e8e6e1 !important;
}}
.stTextArea textarea:focus {{
    border-color: rgba(255,255,255,0.25) !important;
    box-shadow: 0 0 0 3px rgba(255,255,255,0.05) !important; outline: none !important;
}}
.stTextArea textarea::placeholder {{ color: #555 !important; }}
.stTextInput input {{
    background: #2a2a2d !important; border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important; color: #e8e6e1 !important; caret-color: #e8e6e1 !important;
}}
.stTextInput input:focus {{ border-color: rgba(255,255,255,0.25) !important; }}

.stButton > button, .stFormSubmitButton > button {{
    font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
    font-size: 0.82rem !important; border-radius: 8px !important;
    transition: all 0.18s ease !important;
}}
.stButton > button {{
    background: #3a3a3d !important;
    border: 1px solid rgba(255,255,255,0.2) !important; color: #e8e6e1 !important;
}}
.stButton > button:hover {{
    background: #4a4a4e !important;
    border-color: rgba(255,255,255,0.35) !important; color: #fff !important;
}}
.stFormSubmitButton > button {{
    background: #3a3a3d !important;
    border: 1px solid rgba(255,255,255,0.2) !important; color: #e8e6e1 !important;
}}
.stFormSubmitButton > button:hover {{
    background: #4a4a4e !important; color: #fff !important;
}}
.stDownloadButton > button {{
    background: #3a3a3d !important;
    border: 1px solid rgba(255,255,255,0.2) !important; color: #e8e6e1 !important; border-radius: 8px !important;
}}

/* Canvas 열림 표시 버튼 (다크) */
.canvas-btn-active > button {{
    background: #e8e6e1 !important; color: #1c1c1e !important; border-color: #e8e6e1 !important;
}}

.msg-user {{
    background: #2a2a2d; border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px 18px 4px 18px; padding: 12px 16px;
    margin: 6px 0 6px auto; max-width: 88%; color: #e8e6e1;
    font-size: 0.93rem; line-height: 1.65; box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}}
.msg-ai {{ background: transparent; padding: 4px 0; margin: 6px 0; max-width: 92%; color: #e8e6e1; font-size: 0.93rem; line-height: 1.7; }}
.msg-role {{ font-size: 0.7rem; font-weight: 600; letter-spacing: 0.04em; margin-bottom: 4px; text-transform: uppercase; }}
.msg-role-user {{ text-align: right; color: #555; }}
.msg-role-ai {{ color: #555; }}
.token-bar {{ display: flex; gap: 12px; flex-wrap: wrap; padding: 6px 0; font-size: 0.72rem; color: #555; }}
.token-bar strong {{ color: #888; }}

.quiz-q {{ font-weight: 600; color: #e8e6e1; margin-bottom: 10px; line-height: 1.6; }}
.quiz-exp {{ background: rgba(255,255,255,0.04); border-left: 3px solid #555; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-top: 10px; font-size: 0.86rem; color: #aaa; line-height: 1.6; }}
.score-box {{ background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 16px; }}
.score-num {{ font-size: 2.4rem; font-weight: 700; color: #e8e6e1; }}

.pasted-chip {{
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.14);
    border-radius: 8px; padding: 5px 10px;
    font-size: 0.8rem; font-weight: 500; color: #bbb; margin: 2px 4px 2px 0;
    cursor: pointer;
}}

.img-thumb {{
    width: 72px; height: 54px; object-fit: cover;
    border-radius: 8px; border: 1px solid rgba(255,255,255,0.12);
    cursor: pointer; margin: 2px 4px 2px 0; display: inline-block;
    transition: opacity 0.15s; vertical-align: middle;
}}
.img-thumb:hover {{ opacity: 0.75; }}

hr {{ border-color: rgba(255,255,255,0.06) !important; }}
.streamlit-expanderHeader {{ color: #e8e6e1 !important; }}
.streamlit-expanderContent {{ color: #e8e6e1 !important; }}
.stCodeBlock {{ border-radius: 10px !important; }}
::-webkit-scrollbar {{ width: 5px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.12); border-radius: 3px; }}

{scroll_css}
.chat-scroll-area::-webkit-scrollbar {{ width: 5px; }}
.chat-scroll-area::-webkit-scrollbar-track {{ background: transparent; }}
.chat-scroll-area::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 3px; }}
.canvas-scroll-area::-webkit-scrollbar {{ width: 5px; }}
.canvas-scroll-area::-webkit-scrollbar-track {{ background: transparent; }}
.canvas-scroll-area::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 3px; }}
</style>
"""

ICON_BTN_CSS = """
<style>
div[data-testid="stFormSubmitButton"]:nth-of-type(1) > button {
    background: #e8e6e1 !important;
    color: #1c1c1e !important;
    border: none !important;
    border-radius: 50% !important;
    width: 40px !important; height: 40px !important;
    padding: 0 !important; font-size: 1.1rem !important;
    display: flex !important; align-items: center !important; justify-content: center !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.2) !important;
}
div[data-testid="stFormSubmitButton"]:nth-of-type(1) > button:hover {
    background: #d0cec8 !important; transform: scale(1.05) !important;
}
div[data-testid="stFormSubmitButton"]:nth-of-type(n+2) > button {
    border-radius: 8px !important; width: 40px !important; height: 40px !important;
    padding: 0 !important; font-size: 0.95rem !important;
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
# 페르소나
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
반드시 아래 형식의 JSON만 출력하세요 (다른 설명 없이):
[{"question": "문제", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "해설"}]
answer는 0-3 정수. 한국어로 최소 4문제 이상 출제합니다.""",
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
을 체계적으로 수행합니다. 한국어로 답변합니다.""",
        "greeting": "분석할 주제나 주장을 입력하세요.",
        "canvas_type": "doc",
    },
    "🍳 요리 · 레시피 도우미": {
        "system": """당신은 요리 전문가입니다. 레시피를 요청받으면 다음 형식의 JSON으로만 응답하세요:
{"title": "요리명", "servings": 2, "time": "30분", "ingredients": [{"name": "재료", "amount": "분량"}], "steps": ["단계1", "단계2"], "tips": "팁"}
일반 질문은 한국어로 친절하게 답변합니다.""",
        "greeting": "어떤 요리나 레시피가 궁금하신가요?",
        "canvas_type": "doc",
    },
    "🎯 목표 · 계획 코치": {
        "system": """당신은 목표 설정 및 계획 수립 전문가입니다. 사용자의 목표를 SMART 기준으로 분석하고,
구체적인 실행 계획을 수립합니다. 결과는 아래 구조로 정리해주세요:
1. 목표 명확화
2. 현황 분석
3. 단계별 실행 계획 (주차별/월별)
4. 예상 장애물과 대응 전략
5. 진척도 체크포인트
한국어로 답변합니다.""",
        "greeting": "달성하고 싶은 목표를 알려주세요.",
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
    "code_content": "", "code_language": "python",
    # 팝업 — st.session_state 기반으로만 관리 (st.stop() 사용 안 함)
    "popup_type": None,
    "popup_content": None,
    "popup_label": "",
    # 파일 첨부 (다중 이미지 지원)
    "pending_files": [],   # list of {b64, type, name, is_image, api_content}
    # 이전 업로드 파일명 추적 (중복 방지)
    "uploaded_file_names": [],
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
def has_empty_room():
    """메시지가 없는 빈 대화방이 존재하는지 확인"""
    for r in st.session_state.rooms.values():
        if not r["messages"]:
            return True
    return False

def create_room(persona_key="🔬 학습 도우미"):
    # 이미 빈 대화방이 있으면 그 방으로 이동
    for rid, r in st.session_state.rooms.items():
        if not r["messages"]:
            st.session_state.current_room = rid
            return rid
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
        if isinstance(content, dict):
            st.session_state.code_content = content.get("code", "")
            st.session_state.code_language = content.get("language", "python")

def close_canvas():
    st.session_state.canvas_open = False
    st.session_state.canvas_type = None
    st.session_state.canvas_content = None

def try_parse_ai_response(text, persona_key):
    persona_info = PERSONAS.get(persona_key, {})
    canvas_type = persona_info.get("canvas_type")

    if canvas_type == "quiz":
        try:
            raw = text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 0 and "question" in data[0]:
                return "quiz", data
        except:
            pass

    elif canvas_type == "code":
        try:
            raw = text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
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
            raw = text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
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
    if len(text) < 150:
        return False
    code_signals = [
        "def ", "class ", "import ", "function ", "const ", "var ", "let ",
        "#include", "public class", "SELECT ", "CREATE TABLE", "<?php",
        "async def", "export default", "return (", "@app.route",
        "from ", "require(", "module.exports",
    ]
    signal_count = sum(1 for s in code_signals if s in text)
    return signal_count >= 2

def render_ai_message_content(text, msg_index, persona_key, room):
    parts = []
    remaining = text
    while "```" in remaining:
        pre = remaining[:remaining.index("```")]
        rest = remaining[remaining.index("```")+3:]
        lang = "text"
        if "\n" in rest:
            first_line = rest[:rest.index("\n")]
            if first_line.strip() and " " not in first_line.strip():
                lang = first_line.strip()
                rest = rest[rest.index("\n")+1:]
        if "```" in rest:
            code_block = rest[:rest.index("```")]
            remaining = rest[rest.index("```")+3:]
        else:
            code_block = rest
            remaining = ""
        if pre.strip():
            parts.append(("text", pre))
        parts.append(("code", code_block, lang))
    if remaining.strip():
        parts.append(("text", remaining))

    code_idx = 0
    for part in parts:
        if part[0] == "text":
            st.markdown(part[1])
        elif part[0] == "code":
            code_content = part[1]
            lang = part[2] if len(part) > 2 else "text"
            lines = code_content.strip().split("\n")
            preview_lines = lines[:6]
            preview = "\n".join(preview_lines)
            if len(lines) > 6:
                preview += f"\n... ({len(lines)}줄 전체)"

            btn_key = f"open_code_inline_{msg_index}_{code_idx}"
            col_code, col_btn = st.columns([5, 1])
            with col_code:
                st.code(preview, language=lang)
            with col_btn:
                if st.button("⊞", key=btn_key, help="Canvas에서 전체 보기"):
                    open_canvas("code", {
                        "code": code_content,
                        "language": lang,
                        "explanation": "",
                        "title": f"코드 #{code_idx+1}",
                    }, "코드")
                    st.rerun()
            code_idx += 1

# ============================================================
# 팝업 모달 — st.stop() 없이 overlay + 닫기 버튼 방식
# ============================================================
def render_popup():
    if st.session_state.popup_type is None:
        return
    
    th = st.session_state.theme
    bg_popup = "#1c1c1e" if th == "dark" else "#ffffff"
    overlay_content = st.session_state.popup_content
    fname = st.session_state.popup_label

    if st.session_state.popup_type == "image" and overlay_content:
        st.markdown(f"""
        <div style="position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:9999;
                    display:flex;align-items:center;justify-content:center;">
            <div style="background:{bg_popup};border-radius:16px;padding:20px;
                        max-width:82vw;max-height:88vh;overflow:auto;
                        box-shadow:0 24px 64px rgba(0,0,0,0.6);">
                <div style="font-size:0.75rem;color:#888;margin-bottom:10px;">{fname}</div>
                <img src="data:image/png;base64,{overlay_content}"
                     style="max-width:100%;max-height:70vh;border-radius:8px;display:block;" />
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("✕ 닫기", key="close_popup_btn"):
            st.session_state.popup_type = None
            st.session_state.popup_content = None
            st.rerun()

    elif st.session_state.popup_type == "pasted" and overlay_content:
        st.markdown(f"""
        <div style="position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:9998;
                    display:flex;align-items:center;justify-content:center;">
            <div style="background:{bg_popup};border-radius:16px;padding:20px;
                        max-width:85vw;max-height:88vh;overflow:auto;
                        box-shadow:0 24px 64px rgba(0,0,0,0.6);">
                <div style="font-size:0.75rem;color:#888;margin-bottom:10px;">📋 {fname}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        # 코드는 팝업 밖에 렌더링되지만, 닫기 버튼을 먼저 보여줌
        col_close, _ = st.columns([1, 4])
        with col_close:
            if st.button("✕ 닫기", key="close_popup_pasted_btn"):
                st.session_state.popup_type = None
                st.session_state.popup_content = None
                st.rerun()
        st.code(overlay_content)

# 팝업 렌더링 (최상단에)
render_popup()

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
    # selectbox — Streamlit 기본 selectbox는 드롭다운 선택만 가능 (직접 입력 없음)
    persona_key = st.selectbox(
        "페르소나", list(PERSONAS.keys()),
        label_visibility="collapsed", key="persona_select"
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
# 메인 레이아웃
# ============================================================
room = get_current_room()

# Canvas는 항상 열릴 수 있음 (빈 방 포함)
if st.session_state.canvas_open:
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
            st.caption(f"**{MODELS[model_name]['id'].split('-')[1].upper()}** · {room.get('persona','')}")

    if room is None:
        st.markdown("<div style='text-align:center; padding:6rem 0; color:#555;'>새 대화를 시작하세요</div>", unsafe_allow_html=True)
    else:
        st.markdown("---")

        # ── 대화 내용 (독립 스크롤 컨테이너) ──
        # Streamlit에서는 CSS height + overflow 컨테이너를 직접 지원하지 않아
        # JS 자동 스크롤을 inject하는 방식으로 처리
        chat_container = st.container()

        with chat_container:
            if not room["messages"]:
                greeting = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🔬 학습 도우미"])["greeting"]
                st.markdown(f'<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div>{greeting}</div>', unsafe_allow_html=True)
            else:
                ai_turn_idx = 0
                for i, msg in enumerate(room["messages"]):
                    if msg["role"] == "user":
                        # 첨부 파일 표시
                        if msg.get("has_file"):
                            fname = msg.get("file_name", "파일")
                            is_img = msg.get("file_is_image", False)
                            fkey = msg.get("file_key", "")

                            if is_img and fkey:
                                # 이미지: 썸네일 자체를 클릭하면 팝업
                                # Streamlit에서는 버튼으로 대체 (이미지 클릭 직접 처리 불가)
                                col_thumb, _ = st.columns([1, 6])
                                with col_thumb:
                                    # 이미지 + 클릭 버튼 (버튼에 이미지 올리기)
                                    if st.button(
                                        f"🖼 {fname[:12]}",
                                        key=f"img_btn_{i}",
                                        help="클릭하여 이미지 미리보기"
                                    ):
                                        st.session_state.popup_type = "image"
                                        st.session_state.popup_content = fkey
                                        st.session_state.popup_label = fname
                                        st.rerun()
                                    # 썸네일 표시
                                    st.markdown(
                                        f'<img src="data:image/png;base64,{fkey}" '
                                        f'class="img-thumb" title="{fname} — 클릭하여 보기" />',
                                        unsafe_allow_html=True
                                    )

                            elif not is_img and fkey:
                                char_count = len(fkey)
                                col_chip, _ = st.columns([3, 4])
                                with col_chip:
                                    if st.button(
                                        f"📋 PASTED · {fname} · {char_count:,}자",
                                        key=f"pasted_btn_{i}",
                                        help="클릭하여 내용 보기"
                                    ):
                                        st.session_state.popup_type = "pasted"
                                        st.session_state.popup_content = fkey
                                        st.session_state.popup_label = fname
                                        st.rerun()

                        # 다중 파일 표시 (file_list)
                        if msg.get("file_list"):
                            for fi, f_item in enumerate(msg["file_list"]):
                                if f_item.get("is_image") and f_item.get("b64"):
                                    col_t2, _ = st.columns([1, 6])
                                    with col_t2:
                                        if st.button(
                                            f"🖼 {f_item['name'][:12]}",
                                            key=f"img_btn_{i}_{fi}",
                                            help="클릭하여 이미지 미리보기"
                                        ):
                                            st.session_state.popup_type = "image"
                                            st.session_state.popup_content = f_item["b64"]
                                            st.session_state.popup_label = f_item["name"]
                                            st.rerun()
                                        st.markdown(
                                            f'<img src="data:image/png;base64,{f_item["b64"]}" '
                                            f'class="img-thumb" title="{f_item["name"]}" />',
                                            unsafe_allow_html=True
                                        )
                                elif not f_item.get("is_image") and f_item.get("b64"):
                                    if st.button(
                                        f"📋 PASTED · {f_item['name']} · {len(f_item['b64']):,}자",
                                        key=f"pasted_btn_{i}_{fi}",
                                        help="클릭하여 내용 보기"
                                    ):
                                        st.session_state.popup_type = "pasted"
                                        st.session_state.popup_content = f_item["b64"]
                                        st.session_state.popup_label = f_item["name"]
                                        st.rerun()

                        display_text = msg.get("display", msg["content"])
                        if display_text and display_text.strip():
                            st.markdown(f"""
                            <div class="msg-user">
                                <div class="msg-role msg-role-user">You</div>
                                {display_text}
                            </div>""", unsafe_allow_html=True)

                    else:
                        active_persona = room.get("persona", persona_key)
                        c_type, c_data = try_parse_ai_response(msg["content"], active_persona)

                        st.markdown('<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div></div>', unsafe_allow_html=True)

                        if c_type in ("quiz", "mindmap"):
                            type_labels = {"quiz": "🧩 퀴즈", "mindmap": "🗺️ 마인드맵"}
                            label = type_labels.get(c_type, "Canvas")
                            preview = f"{len(c_data)}문제 준비 완료" if c_type == "quiz" else c_data.get("title", "")
                            st.markdown(f"**{label}** — {preview}")
                            if st.button(f"Canvas에서 열기 →", key=f"open_canvas_{i}"):
                                open_canvas(c_type, c_data, label.replace("🧩 ", "").replace("🗺️ ", ""))
                                st.rerun()

                        elif c_type == "code":
                            lang = c_data.get("language", "python") if isinstance(c_data, dict) else "python"
                            title = c_data.get("title", "코드") if isinstance(c_data, dict) else "코드"
                            explanation = c_data.get("explanation", "") if isinstance(c_data, dict) else ""
                            code_str = c_data.get("code", "") if isinstance(c_data, dict) else ""
                            st.markdown(f"**💻 코드** — `{lang.upper()}` · {title}")
                            if explanation:
                                st.caption(explanation)
                            preview_lines = code_str.strip().split("\n")[:6]
                            st.code("\n".join(preview_lines) + ("\n..." if len(code_str.split("\n")) > 6 else ""), language=lang)
                            if st.button(f"Canvas에서 전체 보기 →", key=f"open_code_cv_{i}"):
                                open_canvas("code", c_data, "코드")
                                st.rerun()

                        elif c_type == "doc":
                            st.markdown(msg["content"])
                            if st.button("📄 문서로 보기 →", key=f"open_doc_{i}"):
                                open_canvas("doc", c_data, "문서")
                                st.rerun()

                        else:
                            render_ai_message_content(msg["content"], i, active_persona, room)

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

            streaming_placeholder = st.empty()

        # ── 파일 업로더 (다중 파일) ──
        st.markdown("")
        uploaded_files = st.file_uploader(
            "파일 첨부 (여러 파일 선택 가능)",
            type=["png", "jpg", "jpeg", "gif", "webp", "txt", "py", "js", "ts", "csv", "md", "json"],
            label_visibility="collapsed",
            key="file_upload",
            accept_multiple_files=True,
        )

        # 업로드된 파일들 처리 — 새로 추가된 파일만 pending_files에 추가
        if uploaded_files:
            current_names = [f.name for f in uploaded_files]
            # pending_files 동기화: 현재 uploader에 있는 파일만 유지
            existing_names = [pf["name"] for pf in st.session_state.pending_files]
            
            for uf in uploaded_files:
                if uf.name not in existing_names:
                    fext = uf.name.split(".")[-1].lower()
                    if fext in ["png", "jpg", "jpeg", "gif", "webp"]:
                        file_bytes = uf.read()
                        fb64 = base64.b64encode(file_bytes).decode("utf-8")
                        mtype_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                                     "gif": "image/gif", "webp": "image/webp"}
                        mtype = mtype_map.get(fext, "image/png")
                        st.session_state.pending_files.append({
                            "name": uf.name, "b64": fb64, "type": mtype,
                            "is_image": True,
                            "api_content": {"type": "image", "source": {"type": "base64", "media_type": mtype, "data": fb64}}
                        })
                    else:
                        try:
                            text_content = uf.read().decode("utf-8")
                        except:
                            text_content = uf.read().decode("latin-1")
                        text_content = text_content[:10000]
                        st.session_state.pending_files.append({
                            "name": uf.name, "b64": text_content, "type": "text",
                            "is_image": False,
                            "api_content": {"type": "text", "text": f"[첨부 파일: {uf.name}]\n```\n{text_content}\n```"}
                        })

        # 첨부 파일 미리보기 표시
        if st.session_state.pending_files:
            st.caption(f"첨부됨 ({len(st.session_state.pending_files)}개)")
            cols_per_row = 4
            pf_list = st.session_state.pending_files
            rows = (len(pf_list) + cols_per_row - 1) // cols_per_row
            for row_i in range(rows):
                cols = st.columns(cols_per_row)
                for col_i in range(cols_per_row):
                    idx = row_i * cols_per_row + col_i
                    if idx >= len(pf_list):
                        break
                    pf = pf_list[idx]
                    with cols[col_i]:
                        if pf["is_image"]:
                            # 이미지 썸네일 — 클릭하면 팝업
                            st.markdown(
                                f'<img src="data:image/{pf["type"].split("/")[-1]};base64,{pf["b64"]}" '
                                f'class="img-thumb" title="{pf["name"]}" />',
                                unsafe_allow_html=True
                            )
                            if st.button(f"🔍", key=f"preview_img_{idx}", help=pf["name"]):
                                st.session_state.popup_type = "image"
                                st.session_state.popup_content = pf["b64"]
                                st.session_state.popup_label = pf["name"]
                                st.rerun()
                        else:
                            st.markdown(
                                f'<span class="pasted-chip">📋 {pf["name"][:10]}</span>',
                                unsafe_allow_html=True
                            )
                            if st.button(f"👁", key=f"preview_pasted_{idx}", help=pf["name"]):
                                st.session_state.popup_type = "pasted"
                                st.session_state.popup_content = pf["b64"]
                                st.session_state.popup_label = pf["name"]
                                st.rerun()
                        # 개별 파일 제거 버튼
                        if st.button("✕", key=f"remove_file_{idx}", help=f"{pf['name']} 제거"):
                            st.session_state.pending_files.pop(idx)
                            st.rerun()

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
                key="user_input_area",
            )
            col_send, col_canvas, col_export, col_reset, col_spacer = st.columns([1, 1, 1, 1, 6])
            with col_send:
                submitted = st.form_submit_button("↑")
            with col_canvas:
                # Canvas 버튼: 열려있으면 채워진 아이콘, 닫혀있으면 빈 아이콘
                canvas_icon = "⊟ ON" if st.session_state.canvas_open else "⊞ OFF"
                canvas_toggled = st.form_submit_button(canvas_icon)
            with col_export:
                download_btn = st.form_submit_button("↓")
            with col_reset:
                clear_btn = st.form_submit_button("✕")

        # Canvas 토글 — form 밖에서 처리
        if canvas_toggled:
            if st.session_state.canvas_open:
                close_canvas()
            else:
                # Canvas 열기: 빈 대화방이면 빈 Canvas, 내용 있으면 마지막 응답
                if room and room["messages"]:
                    found = False
                    for msg in reversed(room["messages"]):
                        if msg["role"] == "assistant":
                            active_p = room.get("persona", persona_key)
                            c_type, c_data = try_parse_ai_response(msg["content"], active_p)
                            if c_type:
                                labels = {"quiz": "퀴즈", "code": "코드", "mindmap": "마인드맵", "doc": "문서"}
                                open_canvas(c_type, c_data, labels.get(c_type, "Canvas"))
                                found = True
                                break
                    if not found:
                        # 파싱되는 Canvas 없어도 패널만 열기
                        st.session_state.canvas_open = True
                        st.session_state.canvas_content = None
                else:
                    # 빈 대화방 — 빈 Canvas 패널 열기
                    st.session_state.canvas_open = True
                    st.session_state.canvas_content = None
            st.rerun()

        # 내보내기
        if download_btn and room["messages"]:
            lines = [f"=== {room['title']} ===", f"{room['created_at']}", ""]
            for m in room["messages"]:
                role = "나" if m["role"] == "user" else "Claude"
                lines += [f"[{role}]", m.get("display", m["content"]), ""]
            lines.append(f"Input: {room['total_input']:,} · Output: {room['total_output']:,} · ${room['total_cost']:.4f}")
            st.download_button("💾 다운로드", data="\n".join(lines).encode("utf-8"),
                               file_name=f"chat_{room['id']}.txt", mime="text/plain")

        # 초기화
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
            st.session_state.pending_files = []
            save_room_to_sheet(st.session_state.username, room)
            save_user_stats(st.session_state.username)
            st.rerun()

        # ── 메시지 전송 (스트리밍) ──
        if submitted and user_input.strip():
            if not room["messages"]:
                title = user_input.strip()
                room["title"] = title[:28] + "…" if len(title) > 28 else title
                room["persona"] = persona_key

            # 붙여넣기 코드 감지 — 텍스트 내 코드블록만 PASTED 처리
            display_input = user_input.strip()
            pasted_segments = []   # {"text": ..., "is_code": bool}
            raw_input = user_input.strip()
            
            # 코드 블록 ``` ``` 추출
            temp = raw_input
            clean_parts = []
            while "```" in temp:
                before = temp[:temp.index("```")]
                rest = temp[temp.index("```")+3:]
                if "```" in rest:
                    code_block = rest[:rest.index("```")]
                    temp = rest[rest.index("```")+3:]
                    if before.strip():
                        clean_parts.append({"text": before.strip(), "is_code": False})
                    clean_parts.append({"text": code_block.strip(), "is_code": True})
                else:
                    clean_parts.append({"text": before.strip() + "```" + rest, "is_code": False})
                    temp = ""
            if temp.strip():
                clean_parts.append({"text": temp.strip(), "is_code": False})
            
            # 코드 블록 없는 경우 — 긴 코드 붙여넣기 감지
            auto_pasted_name = None
            auto_pasted_content = None
            plain_text_for_api = raw_input
            
            if not any(p["is_code"] for p in clean_parts) and is_likely_code_paste(raw_input):
                # 전체가 코드 붙여넣기인 경우
                auto_pasted_name = "붙여넣은 코드"
                auto_pasted_content = raw_input
                plain_text_for_api = "(코드 첨부됨)"
                display_input = "(코드 첨부됨)"
            
            # API 메시지 구성
            pending = st.session_state.pending_files.copy()
            if auto_pasted_content:
                pending.append({
                    "name": auto_pasted_name,
                    "b64": auto_pasted_content,
                    "is_image": False,
                    "api_content": {"type": "text", "text": f"[붙여넣은 코드]\n```\n{auto_pasted_content}\n```"}
                })
            
            # user 메시지 저장용 파일 리스트
            file_list_for_msg = [
                {"name": pf["name"], "b64": pf["b64"], "is_image": pf["is_image"]}
                for pf in pending
            ] if pending else []
            
            user_msg = {
                "role": "user",
                "content": plain_text_for_api,
                "display": display_input,
                "has_file": len(file_list_for_msg) > 0,
                "file_name": file_list_for_msg[0]["name"] if len(file_list_for_msg) == 1 else "",
                "file_is_image": file_list_for_msg[0]["is_image"] if len(file_list_for_msg) == 1 else False,
                "file_key": file_list_for_msg[0]["b64"] if len(file_list_for_msg) == 1 else "",
                "file_list": file_list_for_msg if len(file_list_for_msg) > 1 else [],
            }

            room["messages"].append(user_msg)

            model_info = MODELS[model_name]
            active_persona = PERSONAS.get(room.get("persona", persona_key), PERSONAS["🔬 학습 도우미"])
            context_messages = room["messages"][-20:]
            api_messages = []

            for m in context_messages:
                if m["role"] == "user":
                    if m is context_messages[-1] and pending:
                        # 다중 파일 지원
                        parts_api = []
                        for pf in pending:
                            parts_api.append(pf["api_content"])
                        parts_api.append({"type": "text", "text": m["content"]})
                        api_messages.append({"role": "user", "content": parts_api})
                    else:
                        api_messages.append({"role": "user", "content": m["content"]})
                else:
                    api_messages.append({"role": "assistant", "content": m["content"]})

            # 스트리밍
            with streaming_placeholder.container():
                st.markdown('<div class="msg-ai"><div class="msg-role msg-role-ai">Claude</div></div>', unsafe_allow_html=True)
                stream_out = st.empty()

            client = anthropic.Anthropic(api_key=API_KEY)
            start_time = time.time()
            full_answer = ""

            # ── 답변 중단 방지: max_tokens를 충분히 크게, 스트리밍 끊김 방지 ──
            # Claude API 최대: 8192 (Sonnet/Opus 모두 동일)
            MAX_TOKENS = 8192

            try:
                with client.messages.stream(
                    model=model_info["id"],
                    max_tokens=MAX_TOKENS,
                    system=active_persona["system"],
                    messages=api_messages,
                ) as stream:
                    for text_chunk in stream.text_stream:
                        full_answer += text_chunk
                        stream_out.markdown(full_answer + " ▌")

                stream_out.empty()
                streaming_placeholder.empty()

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
                st.session_state.pending_files = []

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
# Canvas 패널 (오른쪽 컬럼) — 항상 독립 스크롤
# ============================================================
if canvas_col is not None:
    with canvas_col:
        th = st.session_state.theme
        text_col = "#e8e6e1" if th == "dark" else "#1a1a1a"
        sub_col = "#555" if th == "dark" else "#888"
        bg_panel = "#1c1c1e" if th == "dark" else "#f5f4ef"
        border_col = "rgba(255,255,255,0.08)" if th == "dark" else "rgba(0,0,0,0.08)"

        # Canvas 헤더
        ch1, ch2 = st.columns([4, 1])
        with ch1:
            title_disp = st.session_state.canvas_title if st.session_state.canvas_content is not None else "Canvas"
            st.markdown(f"**{title_disp}**")
        with ch2:
            if st.button("✕", key="close_canvas_btn"):
                close_canvas()
                st.rerun()
        st.markdown("---")

        ct = st.session_state.canvas_type
        cc = st.session_state.canvas_content

        # 빈 Canvas (대화 전 또는 파싱 불가)
        if cc is None:
            persona_info = PERSONAS.get(persona_key, {})
            cv_type_hint = persona_info.get("canvas_type", None)
            hint_map = {
                "quiz": "🧩 퀴즈 출제자 페르소나로 대화하면\n퀴즈가 여기에 표시됩니다.",
                "code": "💻 코딩 멘토 페르소나로 대화하면\n코드가 여기에 표시됩니다.",
                "mindmap": "🗺️ 마인드맵 메이커 페르소나로 대화하면\n마인드맵이 여기에 표시됩니다.",
                "doc": "📄 대화 내용이 문서로\n여기에 표시됩니다.",
                None: "💬 대화를 시작하면\nCanvas 내용이 여기에 표시됩니다.",
            }
            hint = hint_map.get(cv_type_hint, hint_map[None])
            st.markdown(
                f'<div style="text-align:center; padding:4rem 1rem; color:{sub_col}; '
                f'border: 1px dashed {border_col}; border-radius:12px; line-height:1.8; white-space:pre-line;">'
                f'{hint}</div>',
                unsafe_allow_html=True
            )

        # ── 퀴즈 ──
        elif ct == "quiz":
            quiz_list = cc
            if not isinstance(quiz_list, list):
                st.error("퀴즈 데이터가 올바르지 않습니다.")
            else:
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

        # ── 코드 (실행 버튼 제거) ──
        elif ct == "code":
            code_data = cc
            if not isinstance(code_data, dict):
                st.error("코드 데이터가 올바르지 않습니다.")
            else:
                lang = code_data.get("language", "python")
                title = code_data.get("title", "코드")
                explanation = code_data.get("explanation", "")

                st.markdown(f"**{title}** · `{lang.upper()}`")
                if explanation:
                    st.info(explanation)

                edited_code = st.text_area(
                    "코드",
                    value=st.session_state.code_content or code_data.get("code", ""),
                    height=440,
                    key="canvas_code_editor",
                    label_visibility="collapsed",
                )
                st.session_state.code_content = edited_code

                cc1, cc2 = st.columns(2)
                with cc1:
                    st.download_button(
                        "↓ 저장",
                        data=edited_code.encode(),
                        file_name=f"code.{lang}",
                        mime="text/plain",
                        key="dl_code_cv"
                    )
                with cc2:
                    line_count = len(edited_code.split("\n"))
                    st.caption(f"{line_count}줄 · {len(edited_code):,}자")

        # ── 문서 ──
        elif ct == "doc":
            doc_content = cc.get("content", "") if isinstance(cc, dict) else str(cc)
            doc_title = cc.get("title", "문서") if isinstance(cc, dict) else "문서"
            st.markdown(f"### {doc_title}")
            st.markdown("---")

            edit_mode = st.toggle("편집 모드", key="doc_edit_cv")
            if edit_mode:
                edited_doc = st.text_area(
                    "", value=doc_content, height=480,
                    label_visibility="collapsed", key="doc_edit_area"
                )
                if st.button("저장", key="save_doc_cv"):
                    if isinstance(st.session_state.canvas_content, dict):
                        st.session_state.canvas_content["content"] = edited_doc
                    st.rerun()
            else:
                st.markdown(doc_content)

            st.download_button(
                "↓ 문서 저장",
                data=doc_content.encode("utf-8"),
                file_name=f"{doc_title}.txt",
                mime="text/plain",
                key="dl_doc"
            )

        # ── 마인드맵 ──
        elif ct == "mindmap":
            import plotly.graph_objects as go

            mm_data = cc
            if not isinstance(mm_data, dict):
                st.error("마인드맵 데이터가 올바르지 않습니다.")
            else:
                mm_title = mm_data.get("title", "마인드맵")
                mm_nodes = mm_data.get("nodes", [])
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
