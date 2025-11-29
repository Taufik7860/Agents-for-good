# StudyPath – Agents for Good (Education)

A simple **multi-agent AI tutor** built with the **OpenAI Agents SDK**, designed for students in **under-resourced communities**.

It is my capstone project for the **Agents Intensive – Capstone (Agents for Good)**.

---

## 1. Problem & Idea (Agents for Good)

In many schools and colleges, especially in low-resource settings, students:

- don't have access to personal tutors,
- have limited internet / mobile data,
- and struggle to get personalized study plans or practice questions.

**StudyPath** tries to help by providing:

- short, realistic **study plans**, and
- friendly **practice quizzes**

for topics like algebra, fractions, English vocabulary and basic environmental science.

---

## 2. Key Agent Concepts Demonstrated

This project implements **at least three** of the required concepts:

1. **Multi-Agent System (with handoffs)**  
   - `host_agent` (StudyPath Orchestrator)  
   - `planner_agent` (Curriculum Planner)  
   - `quiz_agent` (Quiz Coach)  
   The orchestrator uses **handoffs** to delegate to the correct specialist agent based on the user’s request.

2. **Tools**
   - **Hosted tool**: `WebSearchTool` for web search (OpenAI hosted tool).
   - **Custom function tool**: `get_local_tip(topic)` reads a local `data/topics.json` file with offline education tips.

3. **Sessions & Memory**
   - Uses `SQLiteSession` to store conversation history in a local SQLite DB.
   - This allows the tutor to remember previous questions and context within a session.

4. **Observability / Tracing**
   - The OpenAI Agents SDK automatically records traces for:
     - LLM generations,
     - tool calls,
     - handoffs.
   - These can be inspected in the **OpenAI Traces dashboard** without extra code.

5. **Agent Evaluation (bonus)**
   - `src/evaluate.py` runs a few fixed prompts and prints a simple heuristic report.
   - This demonstrates basic, manual agent evaluation.

You can highlight any **3 or more** of these in your written report.

---

## 3. Project Structure

```text
agents-for-good-studypath/
│
├── .env                     ← Your real API key (never upload)
├── .env.example             ← Template for GitHub
├── .gitignore
├── requirements.txt
├── README.md
│
├── data/
│   └── topics.json          ← (Optional) internal data file
│
├── database/
│   ├── users.db             ← Login/Register database
│   ├── sessions.db          ← Save chat & conversation tracking
│   ├── quiz.db              ← Quiz progress save
│   └── files/               ← Uploaded PDF/JPG/PNG storage
│
├── src/
│   ├── __init__.py
│   ├── agents_setup.py      ← OpenAI Agents SDK, models
│   ├── tools.py             ← File-reading, formatting tools
│   ├── auth.py              ← Login, Register backend logic
│   ├── chat_history.py      ← Save/Rename/Delete chat history
│   ├── quiz_engine.py       ← Quiz mode backend logic
│   ├── voice_engine.py      ← Voice-to-text + text-to-voice
│   ├── web_app.py           ← MAIN FastAPI app (UI backend)
│   └── utils.py             ← Helper functions
│
├── templates/
│   ├── index.html           ← Main web chat UI
│   ├── login.html           ← Login page
│   ├── register.html        ← Registration page
│   ├── quiz.html            ← Quiz mode UI
│   ├── history.html         ← Saved conversations list
│   └── layout.html          ← Base template (header/sidebar/footer)
│
├── static/
│   ├── css/
│   │   ├── style.css        ← Dark UI, chat bubbles, animations
│   │   ├── login.css
│   │   └── quiz.css
│   │
│   ├── js/
│   │   ├── main.js          ← Chat + feedback + voice input logic
│   │   ├── quiz.js          ← Quiz mode UI logic
│   │   ├── auth.js          ← Login/Register frontend logic
│   │   └── history.js       ← Rename/Delete saved chats
│   │
│   ├── icons/
│   │   ├── mic.svg
│   │   ├── send.svg
│   │   ├── delete.svg
│   │   ├── rename.svg
│   │   ├── folder.svg
│   │   └── avatar.png
│   │
│   └── images/
│       └── logo.png         ← Your project logo (top-left)
│
└── web_sessions.db          ← Agents SDK session memory

