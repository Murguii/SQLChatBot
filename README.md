# SQLChatbot: Intelligent SQL Agent via Telegram

## 👤 Author
- **Name:** David Murguialday Osés
- **Course:** Generative AI for Software Engineering
- **Professor:** @juananpe

---

## 🎯 Project Overview
**SQLChatbot** is a multi-agent system designed to bridge the gap between non-technical users and relational databases. Through a simple **Telegram bot interface**, users can query, analyze, and visualize data using natural language.

The project goes beyond simple text-to-SQL conversion by implementing a **self-correcting agentic workflow** using LangGraph, ensuring that even if the AI generates an incorrect SQL query, it can fix itself before responding to the user.

## 🛠️ Tech Stack & Key Concepts
This project implements several advanced patterns discussed during the course:

* **Orchestrator-Worker Pattern:** Based on the OpenAI Agents SDK, utilizing specialized agents for Data Retrieval (SQL), Data Analysis (Insights), and Visualization.
* **LangGraph:** Manages the state and flow of the conversation. It specifically handles a **self-correction loop**: if a SQL execution fails, the error is fed back to the agent for an immediate retry.
* **Telegram Bot API:** Provides a real-world interface for the end-user.
* **Langfuse:** Integrated for full observability, tracking traces, token costs, and agent latency.
* **SQL Skills:** Custom tools developed to allow the agent to inspect schemas and execute safe queries on a SQLite database.

## 🤖 Agent Features
1.  **Natural Language to SQL:** Converts user intent into precise SQL queries.
2.  **Autonomous Self-Correction:** Detects SQL syntax or schema errors and iterates until a valid query is produced.
3.  **Smart Follow-up Suggestions:** After each answer, a dedicated analyst agent suggests 2-3 relevant questions to help the user explore the data further.


## 🏗️ Architecture
The system follows a cyclic graph logic:
1.  **User Input (Telegram)** -> Input Node.
2.  **Schema Inspector** -> Agent learns the DB structure.
3.  **SQL Generator** -> Agent writes the query.
4.  **Validator/Executor** -> If it fails, it loops back to step 3 with the error log.
5.  **Analyst** -> Generates insights and follow-up questions.
6.  **Response** -> Results are sent back to Telegram.

## 🚀 How to Run (Development)
*(This section will be updated as the code is pushed)*
1.  Clone the repository.
2.  Install dependencies: `pip install -r requirements.txt`.
3.  Set up environment variables (`OPENAI_API_KEY`, `TELEGRAM_TOKEN`, `LANGFUSE_KEYS`).
4.  Run the main bot script: `python bot.py`.

---
*Developed using GitHub Copilot as a primary coding assistant.*