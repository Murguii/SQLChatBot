# SQL Music Chatbot 🎵🤖

**SQL Music Chatbot** is a conversational assistant for SQLite databases focused on music queries. It is designed to convert natural language into robust SQL, execute queries safely, and return clear explanations in a **multi-agent LangGraph** flow. The primary goal is **to solve real AI engineering problems**: typos, ambiguities, complex queries, and end-to-end traceability.

---

## ✨ Highlights
- **Agent architecture** with three key nodes and a self-correcting state graph.
- **Smart data handling**: fuzzy matching and existence validation with SQL logic.
- **Telegram as frontend** with **Inline Keyboards** for contextual suggestions.
- **Observability** with Langfuse for SQL auditing, traces, and latency.

---

## 🧠 Agent Architecture (LangGraph)
The bot uses LangGraph to orchestrate a state graph with three main nodes:

| Node | Responsibility | Inputs | Outputs |
| --- | --- | --- | --- |
| `sql_generator` | Translates natural language into robust SQL using `LOWER` and `LIKE` | User question + schema | Safe, explainable SQL |
| `execute_sql` | Executes SQL against SQLite and captures errors | SQL | Result or error |
| `analyst` | Interprets results, explains, and handles errors or suggestions | Result + errors | Final response + suggestions |

**Summary flow:**
1. User asks in Telegram.
2. `sql_generator` creates the SQL query.
3. `execute_sql` validates and runs it.
4. `analyst` interprets, explains, and suggests.

---

## 🧪 Smart Data Handling (key to the project)

### ✅ Fuzzy Matching (typo tolerance)
The bot understands typos by applying SQL logic with `LOWER` and `LIKE`, plus a reasoning layer in `analyst` for suggestions. Real example:

**Input:**
```text
Ventas de Nirvna
```

**Approx SQL (simplified):**
```sql
SELECT artist_name
FROM artists
WHERE LOWER(artist_name) LIKE '%nirvna%'
```

**Expected output:**
```text
No encontré "Nirvna". ¿Quizás quisiste decir "Nirvana"?
```

> 💡 The analyst combines partial matches with question context to propose useful corrections.

### ✅ Existence Validation (0 vs No records)
It is not the same for an artist to exist with **0 sales** versus **not existing in the DB**. We implement a double-checking logic by crossing SQL results with table metadata to avoid false negatives (for example, "Bad Bunny"):

| Case | Result | Interpretation |
| --- | --- | --- |
| Artist exists + sales = 0 | `0` | The artist exists but has no recorded sales |
| Artist does not exist | `No hay registros` | No matches in the database |

**Strategy:**
1. Artist existence check (by normalized name).
2. Validation using relevant table metadata to confirm presence.
3. Sales query if the artist exists.
4. `analyst` decides the final message and avoids false negatives.

---

## 💬 Interface and UX

- **Telegram** as the conversational frontend.
- **Inline Keyboards** for dynamic suggestions and disambiguation.
- Responses designed to be **interpretable** and **decision-oriented**.

Keyboard example:
```text
¿Te refieres a?
[ Nirvana ]  [ Nirvana (Unplugged) ]  [ Nirvana (Remastered) ]
```

---

## 🧩 Portability (Schema-Agnostic)
The design is **schema-agnostic**. The bot extracts DDL dynamically from SQLite, so `sql_generator` adapts to any schema with minimal changes to the system prompt. This allows migration across SQLite databases without rewriting graph logic.

## 🔭 Observability
The **Langfuse** integration provides:

- 📌 Full tracing of the agent flow.
- 🧾 Auditing of generated SQL.
- ⏱️ Latency and cost monitoring per query.
- 🧪 Post-mortem debugging with per-user traces.

---

## 🖼️ Visual Assets
<p align="center"><img src="./assets/telegram_demo1.jpeg" width="400" alt="Interaccion en Telegram (Demo) - 1"></p>
<p align="center"><em>Telegram Interaction (Demo) - 1</em></p>

<p align="center"><img src="./assets/telegram_demo2.jpeg" width="400" alt="Interaccion en Telegram (Demo) - 2"></p>
<p align="center"><em>Telegram Interaction (Demo) - 2</em></p>

<p align="center"><img src="./assets/graph_structure.png" width="400" alt="Visualizacion del Grafo de Estados (LangGraph)"></p>
<p align="center"><em>State Graph Visualization (LangGraph)</em></p>

<p align="center"><img src="./assets/langfuse_trace.png" width="700" alt="Traza de observabilidad (Langfuse)"></p>
<p align="center"><em>Observability Trace (Langfuse)</em></p>

## 🧾 Query Examples

### Simple level
```text
¿Qué álbumes tiene Radiohead?
```

### Complex level (JOINs)
```text
¿Qué canciones de Rock ha comprado Jordan Lee?
```

### Error handling (fuzzy matching)
```text
Ventas de Flitwood Mac
```

---

## ⚙️ Installation Guide

### 1) Create a virtual environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies
```powershell
pip install -r requirements.txt
```

### 3) Configure environment variables
Create a `.env` file with the following variables:

```env
TELEGRAM_BOT_TOKEN=your_telegram_token
OPENROUTER_API_KEY=your_openrouter_key
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 4) Run the bot
```powershell
python -m src.bot
```

---

## 📁 Project Structure
```text
main.py
src/
	agents.py
	bot.py
	graph.py
	init_db.py
	tools.py
data/
	music.db
requirements.txt
```

---

## ✅ Project Status
Fully functional project focused on **robustness**, **observability**, and **conversational UX**. The main challenges solved include:

- Typo handling without degrading precision.
- Correct detection of non-existence vs lack of sales.
- Full SQL and latency auditing with Langfuse.
- Immediate execution thanks to `data/music.db` included in the repo after API keys are configured.

---

## 👤 Author
- **Name:** David Murguialday Oses
- **Course:** Generative AI for Software Engineering
- **Professor:** @juananpe

---

*Developed with GitHub Copilot as the primary assistant.*