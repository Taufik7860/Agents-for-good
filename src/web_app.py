import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agents import Runner, SQLiteSession

from .agents_setup import host_agent


app = FastAPI(
    title="StudyPath – Agents for Good (Web)",
    description="Simple web chat UI for the multi-agent StudyPath tutor.",
)

# Allow local browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for local dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.get("/", response_class=HTMLResponse)
async def index():
    """Return a very simple HTML chat UI."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <title>StudyPath – Agents for Good</title>
        <style>
            body {
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                background: #0f172a;
                color: #e5e7eb;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .chat-container {
                background: #020617;
                border-radius: 16px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.5);
                width: 100%;
                max-width: 800px;
                height: 80vh;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .header {
                padding: 16px 20px;
                border-bottom: 1px solid #1f2937;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .header-title {
                font-size: 18px;
                font-weight: 600;
            }
            .header-badge {
                font-size: 12px;
                padding: 4px 8px;
                border-radius: 999px;
                background: #111827;
                border: 1px solid #374151;
            }
            .messages {
                flex: 1;
                padding: 16px;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }
            .msg {
                max-width: 80%;
                padding: 10px 12px;
                border-radius: 12px;
                line-height: 1.4;
                font-size: 14px;
                white-space: pre-wrap;
            }
            .msg-user {
                align-self: flex-end;
                background: #1d4ed8;
            }
            .msg-bot {
                align-self: flex-start;
                background: #111827;
                border: 1px solid #1f2937;
            }
            .footer {
                padding: 12px;
                border-top: 1px solid #1f2937;
                display: flex;
                gap: 8px;
            }
            .input-box {
                flex: 1;
                padding: 10px;
                border-radius: 999px;
                border: 1px solid #374151;
                background: #020617;
                color: #e5e7eb;
                outline: none;
                font-size: 14px;
            }
            .send-btn {
                padding: 0 18px;
                border-radius: 999px;
                border: none;
                background: #22c55e;
                color: #022c22;
                font-weight: 600;
                cursor: pointer;
            }
            .send-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }
            .hint {
                font-size: 11px;
                color: #9ca3af;
                padding: 0 16px 8px;
            }
        </style>
    </head>
    <body>
    <div class="chat-container">
        <div class="header">
            <div class="header-title">StudyPath – Agents for Good</div>
            <div class="header-badge">Multi-agent tutor (web UI)</div>
        </div>
        <div id="messages" class="messages">
            <div class="msg msg-bot">
                👋 Namaste! I’m StudyPath, your AI tutor for under-resourced learners.
                You can ask me for a study plan or a quiz. For example:
                – "Make a 5 day plan to study algebra"
                – "Quiz me on fractions"
            </div>
        </div>
        <div class="hint">Tip: Your chat is remembered while this page is open.</div>
        <div class="footer">
            <input id="input" class="input-box" placeholder="Type your question..." />
            <button id="send" class="send-btn">Send</button>
        </div>
    </div>

    <script>
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('send');
        const messagesDiv = document.getElementById('messages');

        let sessionId = null;
        let isSending = false;

        function appendMessage(text, isUser) {
            const div = document.createElement('div');
            div.className = 'msg ' + (isUser ? 'msg-user' : 'msg-bot');
            div.textContent = text;
            messagesDiv.appendChild(div);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        async function sendMessage() {
            if (isSending) return;
            const text = input.value.trim();
            if (!text) return;

            appendMessage(text, true);
            input.value = '';
            input.focus();
            isSending = true;
            sendBtn.disabled = true;

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: text,
                        session_id: sessionId
                    })
                });

                if (!res.ok) {
                    appendMessage('Error: ' + res.status + ' ' + res.statusText, false);
                } else {
                    const data = await res.json();
                    sessionId = data.session_id;
                    appendMessage(data.reply, false);
                }
            } catch (err) {
                appendMessage('Network error: ' + err, false);
            } finally {
                isSending = false;
                sendBtn.disabled = false;
            }
        }

        sendBtn.addEventListener('click', sendMessage);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    </script>
    </body>
    </html>
    """


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Handle chat messages from the web UI."""
    # Create or reuse a session ID so conversation has memory
    session_id = req.session_id or str(uuid.uuid4())
    session = SQLiteSession(session_id=session_id, db_path="study_sessions_web.db")

    result = await Runner.run(
        host_agent,
        input=req.message,
        session=session,
    )

    return ChatResponse(
        reply=str(result.final_output),
        session_id=session_id,
    )

