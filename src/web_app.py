# src/web_app.py
# STUDYPATH – Agents For You
# Dark web UI + logo + voice input + per-answer voice output button
# + difficulty meter feedback + quiz mode
# + right saved chats (rename/delete) + collapsible sidebar + file upload on "+"
# + image/PDF Q&A + PDF export + login + profile display bottom-left
# + live voice transcription into input box
# + quiz result saved into main chat & saved chats + Clear Quiz button

import os
import io
import json
import uuid
import hashlib
import base64
import mimetypes
import time
from typing import Optional, List, Dict

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Response,
    Cookie,
    Query,
    Form,
)
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agents import Runner, SQLiteSession
from .agents_setup import host_agent

from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

openai_client = OpenAI()  # needs OPENAI_API_KEY in .env

# ---------- paths ----------
ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
CHATS_INDEX = os.path.join(DATA_DIR, "chats_index.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

for p in [USERS_FILE, SESSIONS_FILE, CHATS_INDEX]:
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            json.dump({}, f)

# ---------- helper functions ----------
def load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def hash_password(password: str, salt: Optional[str] = None):
    if salt is None:
        salt = uuid.uuid4().hex
    return salt, hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def create_user(name: str, email: str, password: str):
    users = load_json(USERS_FILE)
    if email in users:
        return False, "User already exists"
    salt, h = hash_password(password)
    users[email] = {"name": name, "salt": salt, "hash": h}
    save_json(USERS_FILE, users)
    return True, "Account created"


def verify_user(email: str, password: str):
    users = load_json(USERS_FILE)
    user = users.get(email)
    if not user:
        return False, "User not found"
    salt = user["salt"]
    _, h = hash_password(password, salt)
    if h == user["hash"]:
        return True, user["name"]
    return False, "Incorrect password"


def create_session(email: str) -> str:
    sessions = load_json(SESSIONS_FILE)
    token = uuid.uuid4().hex
    sessions[token] = {"email": email}
    save_json(SESSIONS_FILE, sessions)
    return token


def delete_session(token: Optional[str]):
    if not token:
        return
    sessions = load_json(SESSIONS_FILE)
    if token in sessions:
        sessions.pop(token)
        save_json(SESSIONS_FILE, sessions)


def meta_file(session_id: str) -> str:
    safe = session_id.replace("/", "_")
    return os.path.join(DATA_DIR, f"session_{safe}.json")


def append_history(session_id: str, role: str, content: str):
    path = meta_file(session_id)
    data = load_json(path)
    hist: List[Dict] = data.get("history", [])
    hist.append({"role": role, "content": content})
    data["history"] = hist
    save_json(path, data)


def get_history(session_id: str) -> List[Dict]:
    data = load_json(meta_file(session_id))
    return data.get("history", [])


def ensure_chat_index(session_id: str, first_message: str):
    idx = load_json(CHATS_INDEX)
    if session_id in idx:
        return
    idx[session_id] = {
        "title": first_message.strip()[:60] or "New chat",
        "created_at": time.time(),
    }
    save_json(CHATS_INDEX, idx)


# ---------- FastAPI app ----------
app = FastAPI(title="STUDYPATH – Agents For You")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(ROOT, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ---------- HTML (frontend) ----------
MAIN_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>STUDYPATH – Agents For You</title>
  <style>
    * { box-sizing:border-box; }
    body {
      margin:0;
      font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      background:#020617;
      color:#e5e7eb;
    }
    .layout {
      display:flex;
      min-height:100vh;
    }
    /* Left sidebar */
    .sidebar {
      width:220px;
      background:#020617;
      border-right:1px solid #111827;
      padding:16px;
      display:flex;
      flex-direction:column;
      gap:16px;
      transition:width 0.2s ease, opacity 0.2s ease;
    }
    .sidebar.collapsed {
      width:0;
      padding:16px 0;
      overflow:hidden;
      opacity:0;
    }
    .logo-box {
      display:flex;
      align-items:center;
      gap:10px;
      margin-bottom:10px;
    }
    .logo-img {
      height:44px;
      width:44px;
      border-radius:999px;
      border:2px solid #22c55e;
      box-shadow:0 0 12px rgba(34,197,94,0.6);
      object-fit:cover;
      background:#020617;
    }
    .logo-text-title { font-weight:600; font-size:14px; }
    .logo-text-sub { font-size:11px; color:#9ca3af; }
    .nav-section-title {
      font-size:11px;
      text-transform:uppercase;
      letter-spacing:0.08em;
      color:#6b7280;
      margin-bottom:4px;
    }
    .nav-buttons {
      display:flex;
      flex-direction:column;
      gap:6px;
    }
    .nav-btn {
      width:100%;
      text-align:left;
      padding:7px 10px;
      border-radius:999px;
      border:1px solid #111827;
      background:#020617;
      color:#e5e7eb;
      font-size:13px;
      cursor:pointer;
    }
    .nav-btn:hover { background:#111827; }
    .search-input {
      width:100%;
      padding:6px 10px;
      border-radius:999px;
      border:1px solid #1f2937;
      background:#020617;
      color:#e5e7eb;
      font-size:12px;
      outline:none;
      margin-bottom:6px;
    }
    .agents-panel {
      border-radius:12px;
      border:1px solid #111827;
      background:#020617;
      padding:10px;
      font-size:12px;
    }
    .agents-panel ul { margin:4px 0 0; padding-left:18px; }

    /* Main center */
    .main {
      flex:1;
      display:flex;
      flex-direction:column;
      padding:16px 20px;
    }
    header {
      display:flex;
      justify-content:space-between;
      align-items:center;
      margin-bottom:10px;
    }
    .header-left {
      display:flex;
      align-items:center;
      gap:8px;
    }
    #toggleSidebarBtn {
      border-radius:999px;
      border:1px solid #1f2937;
      background:#020617;
      color:#e5e7eb;
      width:32px;
      height:32px;
      cursor:pointer;
      font-size:18px;
    }
    header h1 { margin:0; font-size:20px; font-weight:600; }
    header small { display:block; color:#9ca3af; font-size:12px; }

    .card {
      background:#020617;
      border-radius:18px;
      border:1px solid #1f2937;
      padding:16px;
      box-shadow:0 18px 40px rgba(0,0,0,0.6);
      margin-bottom:12px;
    }
    .heading { font-size:22px; margin:0 0 4px; }
    .sub { margin:0 0 8px; color:#9ca3af; font-size:13px; }
    .examples-box {
      margin-top:8px;
      border-radius:12px;
      border:1px solid #1f2937;
      background:#030712;
      padding:8px 10px;
      font-size:12px;
    }
    .examples-title {
      font-size:11px;
      text-transform:uppercase;
      letter-spacing:0.08em;
      color:#9ca3af;
      margin-bottom:2px;
    }
    .examples-list div::before { content:"• "; color:#22c55e; }

    /* Quiz card */
    .quiz-controls {
      display:flex;
      flex-wrap:wrap;
      gap:8px;
      align-items:center;
      margin-top:6px;
    }
    .quiz-input {
      padding:6px 8px;
      border-radius:8px;
      border:1px solid #1f2937;
      background:#020617;
      color:#e5e7eb;
      font-size:13px;
      min-width:160px;
    }
    .quiz-select {
      padding:6px 8px;
      border-radius:8px;
      border:1px solid #1f2937;
      background:#020617;
      color:#e5e7eb;
      font-size:13px;
    }
    .quiz-btn {
      padding:7px 10px;
      border-radius:999px;
      border:none;
      background:#22c55e;
      color:#022c22;
      font-weight:600;
      cursor:pointer;
      font-size:13px;
    }
    .quiz-panel {
      margin-top:10px;
      border-radius:12px;
      border:1px solid #1f2937;
      background:#020617;
      padding:10px;
      max-height:260px;
      overflow-y:auto;
      font-size:13px;
    }
    .quiz-question {
      margin-bottom:10px;
      padding-bottom:6px;
      border-bottom:1px solid #111827;
    }
    .quiz-options label {
      display:block;
      margin:2px 0;
      cursor:pointer;
    }
    .quiz-actions {
      margin-top:6px;
      display:flex;
      gap:8px;
      flex-wrap:wrap;
    }
    .quiz-result {
      margin-top:8px;
      font-size:13px;
      color:#e5e7eb;
    }

    /* Chat area */
    #messages {
      height:360px;
      border-radius:14px;
      border:1px solid #111827;
      background:#020617;
      padding:10px;
      overflow-y:auto;
      font-size:14px;
      display:flex;
      flex-direction:column;
    }
    .msg {
      margin:6px 0;
      max-width:100%;
      display:flex;
    }
    /* REVERSED: user left, tutor right */
    .msg-user { justify-content:flex-start; }
    .msg-bot { justify-content:flex-end; }

    .msg-inner { max-width:90%; }
    .msg-header {
      font-size:11px;
      color:#9ca3af;
      margin-bottom:2px;
      display:flex;
      justify-content:space-between;
    }
    .msg-role { font-weight:600; }
    .msg-time { font-size:10px; margin-left:8px; }
    .msg-bubble {
      padding:8px;
      border-radius:10px;
    }
    .msg-user .msg-bubble {
      background:#111827;
      border:1px solid #1f2937;
    }
    .msg-bot .msg-bubble {
      background:#030712;
      border:1px solid #111827;
    }
    .msg-tools {
      margin-top:4px;
      display:flex;
      gap:10px;
      font-size:11px;
      color:#9ca3af;
      flex-wrap:wrap;
    }
    .tool-btn {
      border:none;
      background:transparent;
      color:#9ca3af;
      cursor:pointer;
      font-size:12px;
      padding:0;
    }
    .tool-btn:hover { color:#e5e7eb; }

    mark.search-hit {
      background:#facc15;
      color:#111827;
      padding:0 2px;
      border-radius:2px;
    }

    .bottom { margin-top:10px; display:flex; flex-direction:column; gap:8px; }
    .input-shell {
      display:flex;
      align-items:center;
      gap:8px;
      background:#020617;
      border-radius:999px;
      border:1px solid #1f2937;
      padding:8px 12px;
    }
    .input-plus {
      width:30px;
      height:30px;
      border-radius:999px;
      border:1px solid #374151;
      display:flex;
      align-items:center;
      justify-content:center;
      font-size:20px;
      color:#e5e7eb;
      cursor:pointer;
    }
    .chat-input {
      flex:1;
      border:none;
      outline:none;
      background:transparent;
      color:#e5e7eb;
      font-size:14px;
    }
    .chat-input::placeholder { color:#6b7280; }
    .icon-btn {
      width:34px;
      height:34px;
      border-radius:999px;
      border:none;
      background:#111827;
      color:#e5e7eb;
      font-size:18px;
      display:flex;
      align-items:center;
      justify-content:center;
      cursor:pointer;
    }
    .icon-btn:hover { background:#1f2937; }

    #typingIndicator {
      font-size:12px;
      color:#9ca3af;
      margin-top:4px;
      display:none;
    }

    /* Right Saved Chats */
    .right-panel {
      width:260px;
      border-left:1px solid #111827;
      background:#020617;
      padding:16px 12px;
      display:flex;
      flex-direction:column;
      gap:10px;
    }
    .right-title {
      font-size:12px;
      text-transform:uppercase;
      letter-spacing:0.08em;
      color:#6b7280;
    }
    #chatList {
      flex:1;
      overflow-y:auto;
      font-size:13px;
    }
    .chat-item {
      padding:6px 8px;
      border-radius:10px;
      border:1px solid #1f2937;
      background:#020617;
      cursor:pointer;
      margin-bottom:6px;
      display:flex;
      justify-content:space-between;
      align-items:center;
      gap:6px;
    }
    .chat-item:hover { background:#111827; }
    .chat-item.active {
      border-color:#22c55e;
      background:#022c22;
    }
    .chat-title {
      flex:1;
      white-space:nowrap;
      overflow:hidden;
      text-overflow:ellipsis;
    }
    .chat-actions {
      display:flex;
      gap:6px;
    }
    .chat-action-btn {
      border:none;
      background:transparent;
      color:#9ca3af;
      cursor:pointer;
      font-size:16px;
      padding:0;
    }
    .chat-action-btn:hover { color:#e5e7eb; }
    .file-hint {
      font-size:10px;
      color:#6b7280;
      margin-top:4px;
    }

    /* Profile */
    .profile-box {
      border-radius:12px;
      border:1px solid #111827;
      background:#020617;
      padding:10px;
      font-size:12px;
      display:flex;
      align-items:center;
      gap:8px;
    }
    .profile-avatar {
      width:28px;
      height:28px;
      border-radius:999px;
      background:#111827;
      display:flex;
      align-items:center;
      justify-content:center;
      font-size:16px;
    }
    .profile-text-main { font-weight:500; }
    .profile-text-sub { font-size:11px; color:#9ca3af; }
    .profile-footer {
      margin-top:auto;
    }
    .profile-link-btn {
      border:none;
      background:transparent;
      color:#a5b4fc;
      font-size:11px;
      cursor:pointer;
      padding:0;
      margin-top:4px;
      text-decoration:underline;
    }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>
<div class="layout">
  <!-- Left sidebar -->
  <aside id="sidebar" class="sidebar">
    <div class="logo-box">
      <img src="https://i.pinimg.com/736x/49/9f/3b/499f3b838ccb4e655ffa68eb05e22d1d.jpg" class="logo-img" alt="Logo">
      <div>
        <div class="logo-text-title">STUDYPATH</div>
        <div class="logo-text-sub">Agents For You</div>
      </div>
    </div>

    <div>
      <div class="nav-section-title">Session</div>
      <div class="nav-buttons">
        <button class="nav-btn" id="newChatBtn">🆕 New Chat</button>
        <button class="nav-btn" id="downloadChatBtn">⬇ Download Chat (PDF)</button>
      </div>
    </div>

    <div>
      <div class="nav-section-title">Search Chat</div>
      <input id="searchInput" class="search-input" placeholder="Search in this chat..." />
      <button id="searchBtn" class="nav-btn">🔍 Search</button>
    </div>

    <div>
      <div class="nav-section-title">Agents</div>
      <div class="agents-panel">
        <b>Multi-Agent Team</b>
        <ul>
          <li>📚 Study Planner Agent</li>
          <li>🧠 Quiz & Practice Agent</li>
          <li>👨‍🏫 Concept Explainer Agent</li>
          <li>🔍 Resource & Topic Agent</li>
        </ul>
      </div>
    </div>

    <div class="profile-footer">
      <div class="nav-section-title">Profile</div>
      <div id="profileBox" class="profile-box">
        <div class="profile-avatar" id="profileAvatar">🙂</div>
        <div>
          <div id="profileMain" class="profile-text-main">Not logged in</div>
          <div id="profileSub" class="profile-text-sub">Login to sync chats</div>
          <button id="loginProfileBtn" class="profile-link-btn">Login / Register</button>
          <button id="logoutBtn" class="profile-link-btn" style="display:none;">Logout</button>
        </div>
      </div>
    </div>
  </aside>

  <!-- Main center -->
  <main class="main">
    <header>
      <div class="header-left">
        <button id="toggleSidebarBtn">☰</button>
        <div>
          <h1>STUDYPATH – Agents For You</h1>
          <small>Ask anything you want to learn. Voice + text + multi-agent tutoring.</small>
        </div>
      </div>
    </header>

    <div class="card">
      <h2 class="heading">What can I help you with today?</h2>
      <p class="sub">
        Use voice or text. I’ll format answers with bullets, steps, and tables for comparison questions.
      </p>
      <div class="examples-box">
        <div class="examples-title">Example prompts</div>
        <div class="examples-list">
          <div>Make a 5-day study plan for Operating Systems exam.</div>
          <div>Quiz me on Python OOP with 10 MCQs.</div>
          <div>Explain deadlock in OS in very simple words.</div>
          <div>Comparison table between OOP and Python as a language.</div>
          <div>Help me revise DBMS in 3 days with topics per day.</div>
        </div>
      </div>
    </div>

    <!-- Quiz card -->
    <div class="card">
      <h3 class="heading">🧠 Quiz Mode</h3>
      <p class="sub">Generate MCQ quizzes for any topic and check your score.</p>
      <div class="quiz-controls">
        <input id="quizTopic" class="quiz-input" placeholder="e.g. OS deadlock, Python loops" />
        <select id="quizCount" class="quiz-select">
          <option value="5">5 questions</option>
          <option value="10">10 questions</option>
        </select>
        <button id="startQuizBtn" class="quiz-btn">Start Quiz</button>
      </div>
      <div id="quizPanel" class="quiz-panel" style="display:none;"></div>
    </div>

    <div class="card">
      <div id="messages"></div>
      <div id="typingIndicator">StudyPath is thinking…</div>

      <div class="bottom">
        <div class="input-shell">
          <div id="plusBtn" class="input-plus">+</div>
          <input id="chatInput" class="chat-input" placeholder="Ask anything..." />
          <button id="voiceInputBtn" class="icon-btn" title="Voice input">🎙</button>
          <button id="sendBtn" class="icon-btn" title="Send">↑</button>
        </div>
        <input id="fileInput" type="file" style="display:none" accept=".pdf,.jpg,.jpeg,.png" />
        <div class="file-hint">Tip: click + to upload PDF/image, or paste an image (Ctrl+V).</div>
      </div>
    </div>
  </main>

  <!-- Right saved chats -->
  <aside class="right-panel">
    <div class="right-title">Saved Chats</div>
    <div id="chatList"></div>
  </aside>
</div>

<script>
let sessionId = null;
let recognition = null;
let currentUtterance = null;
let quizData = null;

// ----- helpers -----
function copyText(text) {
  if (!navigator.clipboard) {
    alert("Clipboard not supported in this browser.");
    return;
  }
  navigator.clipboard.writeText(text).then(() => {}, () => {
    alert("Could not copy text.");
  });
}

function stopSpeaking() {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    currentUtterance = null;
  }
}

function speakBubble(bubble, button) {
  if (!('speechSynthesis' in window)) {
    alert("Voice output not supported in this browser.");
    return;
  }
  if (currentUtterance) {
    stopSpeaking();
    if (button) button.textContent = "🔊 Read";
    return;
  }
  const text = bubble.textContent;
  const ut = new SpeechSynthesisUtterance(text);
  currentUtterance = ut;
  if (button) button.textContent = "⏹ Stop";
  ut.onend = () => {
    currentUtterance = null;
    if (button) button.textContent = "🔊 Read";
  };
  window.speechSynthesis.speak(ut);
}

// Difficulty feedback
async function sendFeedback(rating, answerText) {
  if (!sessionId) {
    alert("No session yet.");
    return;
  }
  try {
    const res = await fetch('/api/feedback', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        session_id: sessionId,
        rating: rating,
        answer: answerText
      })
    });
    const j = await res.json();
    if (j.followup) {
      addMessage(j.followup, false);
    }
  } catch (e) {
    console.error(e);
    addMessage("⚠️ Could not process feedback. Please try again.", false);
  }
}

// add message bubble
function addMessage(markdown, isUser, originalText=null){
  const box = document.getElementById('messages');
  const row = document.createElement('div');
  row.className = 'msg ' + (isUser ? 'msg-user' : 'msg-bot');

  const inner = document.createElement('div');
  inner.className = 'msg-inner';

  const header = document.createElement('div');
  header.className = 'msg-header';
  const roleSpan = document.createElement('span');
  roleSpan.className = 'msg-role';
  roleSpan.textContent = isUser ? 'You' : 'StudyPath Tutor';
  const timeSpan = document.createElement('span');
  timeSpan.className = 'msg-time';
  const now = new Date();
  timeSpan.textContent = now.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  header.appendChild(roleSpan);
  header.appendChild(timeSpan);

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = marked.parse(markdown);

  const tools = document.createElement('div');
  tools.className = 'msg-tools';

  // copy button
  const copyBtn = document.createElement('button');
  copyBtn.className = 'tool-btn';
  copyBtn.textContent = "📋 Copy";
  copyBtn.onclick = () => copyText(bubble.textContent.trim());
  tools.appendChild(copyBtn);

  if (isUser) {
    // edit: put back into input
    const editBtn = document.createElement('button');
    editBtn.className = 'tool-btn';
    editBtn.textContent = "✏️ Edit";
    editBtn.onclick = () => {
      document.getElementById('chatInput').value = originalText || bubble.textContent.trim();
      document.getElementById('chatInput').focus();
    };
    tools.appendChild(editBtn);
  } else {
    // voice read button
    const speakBtn = document.createElement('button');
    speakBtn.className = 'tool-btn';
    speakBtn.textContent = "🔊 Read";
    speakBtn.onclick = () => speakBubble(bubble, speakBtn);
    tools.appendChild(speakBtn);

    // difficulty meter
    const easyBtn = document.createElement('button');
    easyBtn.className = 'tool-btn';
    easyBtn.textContent = "👍 Easy";
    easyBtn.onclick = () => sendFeedback("easy", bubble.textContent.trim());
    tools.appendChild(easyBtn);

    const okBtn = document.createElement('button');
    okBtn.className = 'tool-btn';
    okBtn.textContent = "😐 OK";
    okBtn.onclick = () => sendFeedback("ok", bubble.textContent.trim());
    tools.appendChild(okBtn);

    const hardBtn = document.createElement('button');
    hardBtn.className = 'tool-btn';
    hardBtn.textContent = "😵 Too hard";
    hardBtn.onclick = () => sendFeedback("hard", bubble.textContent.trim());
    tools.appendChild(hardBtn);
  }

  inner.appendChild(header);
  inner.appendChild(bubble);
  inner.appendChild(tools);

  row.appendChild(inner);
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

// safe regex escape
function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
}
function clearHighlights() {
  const bubbles = document.querySelectorAll(".msg-bubble");
  bubbles.forEach(b => {
    b.innerHTML = b.innerHTML.replace(/<mark class="search-hit">(.*?)<\\/mark>/gi, "$1");
  });
}
function highlightMessages(query) {
  clearHighlights();
  if (!query) return;
  const pattern = new RegExp(escapeRegExp(query), "gi");
  const bubbles = document.querySelectorAll(".msg-bubble");
  bubbles.forEach(b => {
    if (!b.innerHTML) return;
    b.innerHTML = b.innerHTML.replace(pattern, (match) => {
      return '<mark class="search-hit">' + match + "</mark>";
    });
  });
}

// ----- send text -----
async function send(){
  const chatText = document.getElementById('chatInput').value.trim();
  if (!chatText) {
    alert("Please type or speak something to ask.");
    return;
  }
  addMessage(chatText, true, chatText);
  document.getElementById('chatInput').value = "";

  const typing = document.getElementById('typingIndicator');
  typing.style.display = 'block';

  try {
    const res = await fetch('/api/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message: chatText, session_id: sessionId})
    });
    const j = await res.json();
    sessionId = j.session_id;
    addMessage(j.reply, false);
    loadChats();
  } catch (err) {
    addMessage("⚠️ I couldn't reach the server. Please try again.", false);
  } finally {
    typing.style.display = 'none';
  }
}

document.getElementById('sendBtn').onclick = send;
document.getElementById('chatInput').addEventListener('keyup', e => {
  if (e.key === 'Enter') send();
});

// ----- new chat -----
document.getElementById('newChatBtn').onclick = () => {
  sessionId = null;
  document.getElementById('messages').innerHTML = "";
  document.getElementById('typingIndicator').style.display = 'none';
  addMessage("🆕 Started a new chat session.", false);
  loadChats();
};

// ----- search in current chat -----
document.getElementById('searchBtn').onclick = async () => {
  const q = document.getElementById('searchInput').value.trim();
  highlightMessages(q);
  if (!q) return;
  if (!sessionId) {
    alert("No chat yet to search.");
    return;
  }
  const res = await fetch('/api/search_chat?session_id=' + encodeURIComponent(sessionId) + '&q=' + encodeURIComponent(q));
  const j = await res.json();
  if (!j.results || j.results.length === 0) {
    addMessage("🔍 No results found for **" + q + "** in this chat.", false);
  } else {
    const joined = j.results.map(r => `- **${r.role}**: ${r.content}`).join("\\n");
    addMessage("🔍 Search results for **" + q + "**:\\n\\n" + joined, false);
  }
};

// ----- file upload via "+" -----
async function handleFileUpload(file) {
  if (!file) return;
  const question =
    document.getElementById('chatInput').value.trim() ||
    "Explain this file/image for my exam preparation.";
  addMessage("📎 (File) " + question, true, question);
  document.getElementById('chatInput').value = "";

  const typing = document.getElementById('typingIndicator');
  typing.style.display = 'block';

  try {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('question', question);
    fd.append('session_id', sessionId || "");

    const res = await fetch('/api/chat_with_file', { method:'POST', body: fd });
    const j = await res.json();
    if (j.session_id) sessionId = j.session_id;
    addMessage(j.reply || "Done.", false);
    loadChats();
  } catch (err) {
    addMessage("⚠️ I couldn't process that file. Please try again.", false);
  } finally {
    typing.style.display = 'none';
  }
}

document.getElementById('plusBtn').onclick = () => {
  document.getElementById('fileInput').click();
};

document.getElementById('fileInput').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) handleFileUpload(file);
});

// paste image
document.addEventListener('paste', (event) => {
  const items = event.clipboardData && event.clipboardData.items;
  if (!items) return;
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile();
      if (!file) continue;
      const allowed = ['image/png', 'image/jpeg', 'image/jpg'];
      if (!allowed.includes(file.type)) {
        alert("Only image paste supported (PNG / JPG).");
        return;
      }
      handleFileUpload(file);
      break;
    }
  }
});

// ----- download chat PDF -----
document.getElementById('downloadChatBtn').onclick = () => {
  if (!sessionId) {
    alert("No chat yet to download.");
    return;
  }
  window.location = '/api/export_chat_pdf?session_id=' + encodeURIComponent(sessionId);
};

// ----- voice input with live transcription -----
document.getElementById('voiceInputBtn').onclick = () => {
  window.SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!window.SpeechRecognition) {
    alert("Voice input not supported in this browser.");
    return;
  }
  const inputEl = document.getElementById('chatInput');
  const btn = document.getElementById('voiceInputBtn');

  if (recognition) {
    recognition.stop();
    recognition = null;
    inputEl.placeholder = "Ask anything...";
    btn.textContent = "🎙";
    return;
  }
  recognition = new window.SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    inputEl.placeholder = "Listening... speak your question";
    btn.textContent = "🛑";
  };

  recognition.onresult = (event) => {
    let transcript = "";
    for (let i = 0; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript + " ";
    }
    inputEl.value = transcript.trim();
  };

  recognition.onerror = () => {
    recognition = null;
    inputEl.placeholder = "Ask anything...";
    btn.textContent = "🎙";
  };
  recognition.onend = () => {
    recognition = null;
    inputEl.placeholder = "Ask anything...";
    btn.textContent = "🎙";
  };

  recognition.start();
};

// ----- collapsible sidebar -----
document.getElementById('toggleSidebarBtn').onclick = () => {
  const sb = document.getElementById('sidebar');
  sb.classList.toggle('collapsed');
};

// ----- QUIZ MODE -----
function renderQuiz(quiz) {
  const panel = document.getElementById('quizPanel');
  if (!quiz || quiz.length === 0) {
    panel.style.display = 'none';
    panel.innerHTML = "";
    return;
  }
  panel.style.display = 'block';
  panel.innerHTML = "";

  quiz.forEach((q, idx) => {
    const div = document.createElement('div');
    div.className = "quiz-question";
    const qTitle = document.createElement('div');
    qTitle.textContent = (idx+1) + ". " + q.question;
    div.appendChild(qTitle);

    const optsDiv = document.createElement('div');
    optsDiv.className = "quiz-options";
    q.options.forEach((opt, oidx) => {
      const label = document.createElement('label');
      const radio = document.createElement('input');
      radio.type = "radio";
      radio.name = "quiz_q" + idx;
      radio.value = oidx;
      label.appendChild(radio);
      label.appendChild(document.createTextNode(" " + opt));
      optsDiv.appendChild(label);
    });
    div.appendChild(optsDiv);
    panel.appendChild(div);
  });

  const actions = document.createElement('div');
  actions.className = 'quiz-actions';

  const submitBtn = document.createElement('button');
  submitBtn.className = 'quiz-btn';
  submitBtn.textContent = "Submit Quiz";
  submitBtn.onclick = gradeQuiz;
  actions.appendChild(submitBtn);

  const clearBtn = document.createElement('button');
  clearBtn.className = 'quiz-btn';
  clearBtn.style.background = "#111827";
  clearBtn.style.color = "#e5e7eb";
  clearBtn.textContent = "Clear Quiz";
  clearBtn.onclick = clearQuizPanel;
  actions.appendChild(clearBtn);

  const closeBtn = document.createElement('button');
  closeBtn.className = 'quiz-btn';
  closeBtn.style.background = "#111827";
  closeBtn.style.color = "#e5e7eb";
  closeBtn.textContent = "Close Panel";
  closeBtn.onclick = () => {
    quizData = null;
    panel.style.display = 'none';
    panel.innerHTML = "";
  };
  actions.appendChild(closeBtn);

  panel.appendChild(actions);

  const resultDiv = document.createElement('div');
  resultDiv.id = "quizResult";
  resultDiv.className = "quiz-result";
  panel.appendChild(resultDiv);
}

function clearQuizPanel(){
  quizData = null;
  const panel = document.getElementById('quizPanel');
  panel.style.display = 'none';
  panel.innerHTML = "";
}

async function gradeQuiz() {
  if (!quizData) return;
  let score = 0;
  let total = quizData.length;

  quizData.forEach((q, idx) => {
    const sel = document.querySelector('input[name="quiz_q' + idx + '"]:checked');
    const chosen = sel ? parseInt(sel.value) : null;
    const correct = q.answer_index;
    if (chosen === correct) score++;
  });

  // Pretty HTML inside quiz panel
  let html = "<strong>Score:</strong> " + score + " / " + total + "<br><br>";
  html += "<ol>";
  quizData.forEach((q, idx) => {
    const sel = document.querySelector('input[name="quiz_q' + idx + '"]:checked');
    const chosen = sel ? parseInt(sel.value) : null;
    const correct = q.answer_index;
    const yourAns = (chosen != null) ? q.options[chosen] : "Not answered";
    const correctAns = q.options[correct];

    html += "<li>";
    html += "<strong>Q" + (idx+1) + ":</strong> " + q.question + "<br>";
    html += "<strong>Your answer:</strong> " + yourAns + "<br>";
    html += "<strong>Correct answer:</strong> " + correctAns + "<br>";
    html += "<strong>Explanation:</strong> " + q.explanation + "<br>";
    html += "</li>";
  });
  html += "</ol>";

  const resultDiv = document.getElementById('quizResult');
  resultDiv.innerHTML = html;

  // Markdown version for main chat + backend
  let md = `**Quiz Score:** ${score} / ${total}\\n\\n`;
  quizData.forEach((q, idx) => {
    const sel = document.querySelector('input[name="quiz_q' + idx + '"]:checked');
    const chosen = sel ? parseInt(sel.value) : null;
    const correct = q.answer_index;
    const yourAns = (chosen != null) ? q.options[chosen] : "Not answered";
    const correctAns = q.options[correct];

    md += `### Q${idx+1}: ${q.question}\\n`;
    md += `- **Your answer:** ${yourAns}\\n`;
    md += `- **Correct answer:** ${correctAns}\\n`;
    md += `- **Explanation:** ${q.explanation}\\n\\n`;
  });

  // Show as tutor message in main chat
  addMessage(md, false);

  // Save quiz result in backend => saved chats
  if (sessionId) {
    try {
      await fetch('/api/log_quiz_result', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          session_id: sessionId,
          result_markdown: md
        })
      });
      loadChats();
    } catch (e) {
      console.error(e);
    }
  }
}

document.getElementById('startQuizBtn').onclick = async () => {
  const topic = document.getElementById('quizTopic').value.trim();
  const count = parseInt(document.getElementById('quizCount').value || "5", 10);
  if (!topic) {
    alert("Enter a topic for quiz.");
    return;
  }
  document.getElementById('quizPanel').style.display = 'block';
  document.getElementById('quizPanel').innerHTML = "Generating quiz…";

  try {
    const res = await fetch('/api/start_quiz', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        topic: topic,
        count: count,
        session_id: sessionId
      })
    });
    const j = await res.json();
    if (j.session_id) sessionId = j.session_id;
    if (j.quiz && j.quiz.length) {
      quizData = j.quiz;
      renderQuiz(quizData);
    } else if (j.raw) {
      quizData = null;
      document.getElementById('quizPanel').innerHTML = "";
      addMessage("Quiz (text only):\\n\\n" + j.raw, false);
    } else {
      document.getElementById('quizPanel').innerHTML = "Could not generate quiz. Try again.";
    }
    loadChats();
  } catch (e) {
    console.error(e);
    document.getElementById('quizPanel').innerHTML = "Error while generating quiz.";
  }
};

// ----- right-side saved chats -----
async function loadChats(){
  const res = await fetch('/api/list_chats');
  const j = await res.json();
  const listDiv = document.getElementById('chatList');
  listDiv.innerHTML = "";
  (j.chats || []).forEach(chat => {
    const div = document.createElement('div');
    div.className = 'chat-item' + (chat.session_id === sessionId ? ' active' : '');
    const titleSpan = document.createElement('div');
    titleSpan.className = 'chat-title';
    titleSpan.textContent = chat.title;
    titleSpan.onclick = () => openChat(chat.session_id);

    const actions = document.createElement('div');
    actions.className = 'chat-actions';

    const renameBtn = document.createElement('button');
    renameBtn.className = 'chat-action-btn';
    renameBtn.textContent = "✏️";
    renameBtn.onclick = (e) => {
      e.stopPropagation();
      renameChat(chat.session_id, chat.title);
    };

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'chat-action-btn';
    deleteBtn.textContent = "🗑";
    deleteBtn.onclick = (e) => {
      e.stopPropagation();
      deleteChat(chat.session_id);
    };

    actions.appendChild(renameBtn);
    actions.appendChild(deleteBtn);

    div.appendChild(titleSpan);
    div.appendChild(actions);
    listDiv.appendChild(div);
  });
}

async function openChat(id){
  sessionId = id;
  const res = await fetch('/api/get_chat?session_id=' + encodeURIComponent(id));
  const j = await res.json();
  document.getElementById('messages').innerHTML = "";
  document.getElementById('typingIndicator').style.display = 'none';
  (j.history || []).forEach(m => {
    addMessage(m.content, m.role === 'user', m.role === 'user' ? m.content : null);
  });
  loadChats();
}

async function renameChat(id, currentTitle){
  const newTitle = prompt("Rename chat:", currentTitle || "");
  if (!newTitle) return;
  await fetch('/api/rename_chat', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id:id, title:newTitle})
  });
  loadChats();
}

async function deleteChat(id){
  if (!confirm("Delete this chat?")) return;
  await fetch('/api/delete_chat', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id:id})
  });
  if (sessionId === id) {
    sessionId = null;
    document.getElementById('messages').innerHTML = "";
    document.getElementById('typingIndicator').style.display = 'none';
  }
  loadChats();
}

// ----- profile -----
async function loadProfile(){
  try {
    const res = await fetch('/api/whoami');
    const j = await res.json();
    const main = document.getElementById('profileMain');
    const sub = document.getElementById('profileSub');
    const avatar = document.getElementById('profileAvatar');
    const logoutBtn = document.getElementById('logoutBtn');
    const loginBtn = document.getElementById('loginProfileBtn');

    if (j.logged_in) {
      const name = j.name || "Student";
      const email = j.email || "";
      main.textContent = "Logged in as " + name;
      sub.textContent = email || "Account linked";
      avatar.textContent = (name[0] || "S").toUpperCase();
      logoutBtn.style.display = "inline";
      loginBtn.style.display = "none";
    } else {
      main.textContent = "Not logged in";
      sub.textContent = "Login to sync chats";
      avatar.textContent = "🙂";
      logoutBtn.style.display = "none";
      loginBtn.style.display = "inline";
    }
  } catch (e) {
    console.error(e);
  }
}

document.getElementById('logoutBtn').onclick = async () => {
  await fetch('/api/logout', {method:'POST'});
  window.location.reload();
};

document.getElementById('loginProfileBtn').onclick = () => {
  window.location = "/login";
};

// load chats + profile on first open
loadChats();
loadProfile();
</script>
</body>
</html>
"""

# ---------- login page ----------
LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Login / Register – STUDYPATH</title>
  <style>
    body {
      margin:0;
      font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      background:#020617;
      color:#e5e7eb;
    }
    .wrap {
      max-width:420px;
      margin:40px auto;
      padding:16px;
    }
    .card {
      background:#020617;
      border-radius:18px;
      border:1px solid #1f2937;
      padding:20px;
      box-shadow:0 18px 40px rgba(0,0,0,0.6);
    }
    h2 { margin-top:0; }
    input {
      width:100%;
      padding:8px;
      border-radius:10px;
      border:1px solid #1f2937;
      background:#020617;
      color:#e5e7eb;
      margin:4px 0;
      font-size:14px;
    }
    .btn {
      padding:8px 12px;
      border-radius:999px;
      border:none;
      cursor:pointer;
      font-size:14px;
      margin-top:6px;
    }
    .btn-primary { background:#22c55e; color:#022c22; font-weight:600; }
    .btn-outline { background:transparent; color:#e5e7eb; border:1px solid #4b5563; }
    small { font-size:11px; color:#9ca3af; }
    a { color:#a5b4fc; text-decoration:none; }
  </style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h2>Login / Register</h2>
    <small>Login to keep your sessions and exported plans.</small>

    <h3>Login</h3>
    <input id="login_email" placeholder="Email">
    <input id="login_password" type="password" placeholder="Password">
    <button class="btn btn-primary" onclick="login()">Login</button>

    <h3 style="margin-top:18px;">Register</h3>
    <input id="reg_name" placeholder="Full Name">
    <input id="reg_email" placeholder="Email">
    <input id="reg_password" type="password" placeholder="Password">
    <button class="btn btn-outline" onclick="registerUser()">Create Account</button>

    <p style="margin-top:12px;"><a href="/">← Back to StudyPath</a></p>
  </div>
</div>

<script>
async function login(){
  const email = document.getElementById('login_email').value;
  const password = document.getElementById('login_password').value;
  const res = await fetch('/api/login', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({email,password})
  });
  const j = await res.json();
  if(res.ok){
    alert("Login success");
    window.location = "/";
  } else {
    alert(j.detail || "Login failed");
  }
}

async function registerUser(){
  const name = document.getElementById('reg_name').value;
  const email = document.getElementById('reg_email').value;
  const password = document.getElementById('reg_password').value;
  const res = await fetch('/api/register', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name,email,password})
  });
  const j = await res.json();
  if(res.ok){
    alert("Account created successfully! Please login now.");
    window.location = "/login";
  } else {
    alert(j.detail || "Registration failed");
  }
}
</script>
</body>
</html>
"""

# ---------- routes ----------
@app.get("/", response_class=HTMLResponse)
async def home():
    return MAIN_PAGE_HTML


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return LOGIN_PAGE_HTML


@app.get("/api/whoami")
async def api_whoami(session_token: Optional[str] = Cookie(None)):
    if not session_token:
        return {"logged_in": False}
    sessions = load_json(SESSIONS_FILE)
    info = sessions.get(session_token)
    if not info:
        return {"logged_in": False}
    email = info.get("email")
    users = load_json(USERS_FILE)
    user = users.get(email, {})
    return {
        "logged_in": True,
        "email": email,
        "name": user.get("name", ""),
    }


@app.post("/api/register")
async def api_register(payload: dict):
    name = payload.get("name")
    email = payload.get("email")
    password = payload.get("password")
    if not (name and email and password):
        return JSONResponse({"detail": "Missing fields"}, status_code=400)
    ok, msg = create_user(name, email, password)
    return JSONResponse({"detail": msg}, status_code=200 if ok else 400)


@app.post("/api/login")
async def api_login(payload: dict, response: Response):
    email = payload.get("email")
    password = payload.get("password")
    ok, info = verify_user(email, password)
    if not ok:
        return JSONResponse({"detail": info}, status_code=400)
    token = create_session(email)
    response.set_cookie("session_token", token, httponly=True)
    return JSONResponse({"detail": "ok"})


@app.post("/api/logout")
async def api_logout(response: Response, session_token: Optional[str] = Cookie(None)):
    delete_session(session_token)
    response.delete_cookie("session_token")
    return JSONResponse({"detail": "logged out"})


# --------- /api/chat with friendly rate-limit ---------
@app.post("/api/chat")
async def api_chat(payload: dict):
    message = payload.get("message", "")
    session_id = payload.get("session_id") or uuid.uuid4().hex

    text = message.lower()
    comparison_keywords = [
        "compare", "comparison", "difference between", "differences between",
        " vs ", "versus", "advantages and disadvantages",
    ]
    is_comparison = any(k in text for k in comparison_keywords)

    if is_comparison:
        instructions = """
You are STUDYPATH – Agents For You, an AI tutor.

The student is asking a COMPARISON question.

Respond ONLY as a **markdown table**, no extra paragraphs before or after the table.
"""
    else:
        instructions = """
You are STUDYPATH – Agents For You, an AI tutor.

Always answer in friendly **markdown** format:

- Start with a short summary line with an emoji.
- Use bullet points for lists.
- Use numbered steps for procedures.
- Use **bold** for key terms.
- Use headings (##, ###) when helpful.
"""

    full_prompt = f"{instructions}\n\nStudent question:\n{message}"

    try:
        session = SQLiteSession(session_id=session_id, db_path="web_sessions.db")
        result = await Runner.run(host_agent, input=full_prompt, session=session)
        reply = str(result.final_output)
    except Exception as e:
        err = str(e).lower()
        if "rate_limit" in err or "rate limit" in err:
            reply = (
                "⚠️ I’ve hit the current API rate limit for this OpenAI account.\n\n"
                "Please wait a little and try again, or use an API key / account with higher limits. "
                "For demos, avoid sending too many questions very quickly."
            )
        else:
            reply = (
                "⚠️ I had a problem generating the answer on the server side.\n\n"
                "Please check that the Agents SDK and your OpenAI API key are configured correctly."
            )

    existing = get_history(session_id)
    if not existing:
        ensure_chat_index(session_id, message or "New chat")

    append_history(session_id, "user", message)
    append_history(session_id, "tutor", reply)

    return {"reply": reply, "session_id": session_id}


# ---------- FEEDBACK ----------
@app.post("/api/feedback")
async def api_feedback(payload: dict):
    session_id = payload.get("session_id") or uuid.uuid4().hex
    rating = payload.get("rating")
    answer = payload.get("answer", "").strip()

    if rating not in ("easy", "ok", "hard"):
        return JSONResponse({"detail": "Bad payload"}, status_code=400)

    hist = get_history(session_id)
    last_user = None
    for m in reversed(hist):
        if m.get("role") == "user":
            last_user = m.get("content")
            break

    if not hist:
        ensure_chat_index(session_id, "Feedback only")

    if rating == "ok":
        append_history(session_id, "feedback", "Student marked answer as OK.")
        return {"followup": ""}

    if rating == "hard":
        instr = """
The student said your last explanation was TOO HARD.

Rewrite the explanation in MUCH simpler words, using:
- very basic, real-world analogies
- short sentences
- bullet points
- step-by-step explanation

Output a friendly markdown explanation only.
"""
    else:  # easy
        instr = """
The student said your last explanation was TOO EASY.

Provide a deeper explanation with:
- more advanced details
- at least 1–2 tricky conceptual questions
- answers and short explanations

Output a friendly markdown explanation only.
"""

    question_part = f"Original question:\n{last_user}\n\n" if last_user else ""
    full_prompt = f"""{instr}

{question_part}
Original answer:
{answer}
"""

    try:
        session = SQLiteSession(session_id=session_id, db_path="web_sessions.db")
        result = await Runner.run(host_agent, input=full_prompt, session=session)
        followup = str(result.final_output)
    except Exception:
        if rating == "hard":
            followup = (
                "🙂 Thanks for your feedback! Here's a shorter and simpler version:\n\n"
                + answer
            )
        else:
            followup = (
                "💡 Thanks for your feedback! Here are a few extra details:\n\n"
                + answer
            )

    append_history(session_id, "feedback", f"rating:{rating}")
    append_history(session_id, "tutor", followup)
    return {"followup": followup}


@app.get("/api/search_chat")
async def api_search_chat(session_id: str, q: str = Query(...)):
    hist = get_history(session_id)
    q_low = q.lower()
    matches = [
        {"role": h.get("role", "?"), "content": h.get("content", "")}
        for h in hist
        if q_low in h.get("content", "").lower()
    ]
    return {"results": matches}


def _wrap_text(text: str, width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for w in words:
        if len(current) + len(w) + 1 <= width:
            current = (current + " " + w).strip()
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


@app.get("/api/export_chat_pdf")
async def api_export_chat_pdf(session_id: str):
    hist = get_history(session_id)
    if not hist:
        return JSONResponse({"detail": "No chat history"}, status_code=404)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    x = 40
    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "STUDYPATH – Chat Transcript")
    y -= 30
    c.setFont("Helvetica", 11)

    for m in hist:
        line = f"{m.get('role','?').capitalize()}: {m.get('content','')}"
        for chunk in _wrap_text(line, 90):
            if y < 40:
                c.showPage()
                c.setFont("Helvetica", 11)
                y = height - 40
            c.drawString(x, y, chunk)
            y -= 14
        y -= 6

    c.showPage()
    c.save()
    buf.seek(0)
    headers = {"Content-Disposition": "attachment; filename=studypath_chat.pdf"}
    return StreamingResponse(buf, media_type="application/pdf", headers=headers)


@app.post("/api/chat_with_file")
async def api_chat_with_file(
    file: UploadFile = File(...),
    question: str = Form("Explain this file/image for my study preparation."),
    session_id: str = Form(""),
):
    sid = session_id or uuid.uuid4().hex
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    contents = await file.read()

    file_id = uuid.uuid4().hex + ext
    dest_path = os.path.join(UPLOADS_DIR, file_id)
    with open(dest_path, "wb") as f:
        f.write(contents)

    mime, _ = mimetypes.guess_type(filename)
    if not mime:
        mime = "application/octet-stream"

    if mime.startswith("image/"):
        b64 = base64.b64encode(contents).decode("utf-8")
        data_url = f"data:{mime};base64,{b64}"
        try:
            completion = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
            reply_text = completion.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            if "rate_limit" in err or "rate limit" in err:
                reply_text = (
                    "⚠️ I saved your image, but the OpenAI API rate limit was reached.\n\n"
                    "Please wait a bit and try again."
                )
            else:
                reply_text = (
                    f"⚠️ I saved your image as **{file_id}**, "
                    f"but I couldn't analyze it: `{e}`"
                )
    else:
        reply_text = (
            f"📎 I saved your file as **{file_id}**.\n\n"
            "Right now I can directly analyze images; "
            "you can still ask me text questions about this file."
        )

    existing = get_history(sid)
    if not existing:
        ensure_chat_index(sid, f"[file] {question}")

    append_history(sid, "user", f"[file:{filename}] {question}")
    append_history(sid, "tutor", reply_text)

    return {"reply": reply_text, "session_id": sid}


@app.post("/api/start_quiz")
async def api_start_quiz(payload: dict):
    topic = payload.get("topic", "").strip()
    count = int(payload.get("count", 5) or 5)
    session_id = payload.get("session_id") or uuid.uuid4().hex

    if not topic:
        return JSONResponse({"detail": "Missing topic"}, status_code=400)

    if count not in (5, 10):
        count = 5

    system_msg = {
        "role": "system",
        "content": (
            "You are a strict quiz generator for exam prep.\n"
            "You MUST output ONLY valid JSON, no backticks, no extra text."
        ),
    }
    user_msg = {
        "role": "user",
        "content": (
            f'Generate {count} multiple-choice questions about "{topic}". '
            "Return JSON only in this exact format:\n"
            '[{"question": "...", "options": ["A","B","C","D"], '
            '"answer_index": 0, "explanation": "..."}]'
        ),
    }

    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[system_msg, user_msg],
        )
        text = completion.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        quiz = json.loads(text)
        if not isinstance(quiz, list):
            raise ValueError("Quiz is not a list")
    except Exception as e:
        append_history(session_id, "user", f"[quiz request] {topic} ({count} Qs)")
        err = str(e).lower()
        if "rate_limit" in err or "rate limit" in err:
            append_history(
                session_id,
                "tutor",
                "⚠️ Quiz generation hit the API rate limit. Please wait and try again.",
            )
            return {
                "quiz": [],
                "raw": "Quiz generation hit the OpenAI API rate limit.",
                "session_id": session_id,
            }

        append_history(session_id, "tutor", "Generated a quiz (raw text).")
        return {
            "quiz": [],
            "raw": "Quiz generation failed or invalid JSON.",
            "session_id": session_id,
        }

    append_history(session_id, "user", f"[quiz request] {topic} ({count} Qs)")
    append_history(
        session_id, "tutor", f"Generated a quiz with {len(quiz)} questions on {topic}."
    )

    return {"quiz": quiz, "session_id": session_id}


@app.post("/api/log_quiz_result")
async def api_log_quiz_result(payload: dict):
    session_id = payload.get("session_id") or uuid.uuid4().hex
    result_markdown = payload.get("result_markdown", "").strip()
    if not result_markdown:
        return JSONResponse({"detail": "Missing result_markdown"}, status_code=400)

    existing = get_history(session_id)
    if not existing:
        ensure_chat_index(session_id, "[Quiz result]")

    append_history(session_id, "tutor", result_markdown)
    return {"session_id": session_id}


@app.get("/api/list_chats")
async def api_list_chats():
    idx = load_json(CHATS_INDEX)
    chats = [
        {
            "session_id": sid,
            "title": info.get("title", "Chat"),
            "created_at": info.get("created_at", 0),
        }
        for sid, info in idx.items()
    ]
    chats.sort(key=lambda c: c["created_at"], reverse=True)
    return {"chats": chats}


@app.get("/api/get_chat")
async def api_get_chat(session_id: str):
    hist = get_history(session_id)
    return {"history": hist}


@app.post("/api/rename_chat")
async def api_rename_chat(payload: dict):
    sid = payload.get("session_id")
    title = payload.get("title")
    if not sid or not title:
        return JSONResponse({"detail": "Missing session_id or title"}, status_code=400)
    idx = load_json(CHATS_INDEX)
    if sid not in idx:
        return JSONResponse({"detail": "Chat not found"}, status_code=404)
    idx[sid]["title"] = title.strip() or "Chat"
    save_json(CHATS_INDEX, idx)
    return {"detail": "renamed"}


@app.post("/api/delete_chat")
async def api_delete_chat(payload: dict):
    sid = payload.get("session_id")
    if not sid:
        return JSONResponse({"detail": "Missing session_id"}, status_code=400)
    idx = load_json(CHATS_INDEX)
    if sid in idx:
        idx.pop(sid)
        save_json(CHATS_INDEX, idx)
    path = meta_file(sid)
    if os.path.exists(path):
        os.remove(path)
    return {"detail": "deleted"}
