"""Telegram bot interface for the LangGraph SQL workflow."""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from src.graph import build_graph


def _load_dotenv(dotenv_path: Path) -> None:
	if not dotenv_path.exists():
		return

	for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#"):
			continue
		if "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip()
		value = value.strip().strip("\"").strip("'")
		os.environ.setdefault(key, value)


def _init_langfuse() -> Optional[Any]:
	try:
		from langfuse import get_client
	except Exception:
		return None

	if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
		return None

	return get_client()


def _build_openrouter_agent(
	system_prompt: str,
	*,
	name: str,
	langfuse: Optional[Any],
) -> Any:
	try:
		from openai import OpenAI
	except Exception:
		def _fallback(_: str) -> str:
			return "SELECT 1;"

		return _fallback

	api_key = os.getenv("OPENROUTER_API_KEY")
	if not api_key:
		raise RuntimeError("Missing OPENROUTER_API_KEY. Set it in your environment or .env file.")

	client = OpenAI(
		api_key=api_key,
		base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
	)
	model = os.getenv("OPENROUTER_MODEL", "openrouter/auto")

	def _agent(prompt: str) -> str:
		if langfuse is None:
			response = client.responses.create(
				model=model,
				input=[
					{"role": "system", "content": system_prompt},
					{"role": "user", "content": prompt},
				],
			)
			return response.output_text.strip()

		with langfuse.start_as_current_observation(
			as_type="generation",
			name=name,
			model=model,
			input=prompt,
		) as generation:
			response = client.responses.create(
				model=model,
				input=[
					{"role": "system", "content": system_prompt},
					{"role": "user", "content": prompt},
				],
			)
			output_text = response.output_text.strip()
			generation.update(output=output_text)
			return output_text

	return _agent


def _run_turn(
	*,
	graph: Any,
	messages: List[Dict[str, str]],
	user_input: str,
	langfuse: Optional[Any],
	session_id: str,
) -> tuple[List[Dict[str, str]], List[str]]:
	def _execute_turn() -> Dict[str, Any]:
		state = {
			"messages": messages + [{"role": "user", "content": user_input}],
			"sql_query": "",
			"db_result": None,
			"error": None,
			"retries": 0,
			"suggestions": [],
		}

		last_sql = None
		last_error = None
		last_retries = 0

		try:
			for step_state in graph.stream(state, stream_mode="values"):
				sql_query = step_state.get("sql_query")
				error = step_state.get("error")
				retries = step_state.get("retries", 0)

				if sql_query and sql_query != last_sql:
					last_sql = sql_query

				if error and (error != last_error or retries != last_retries):
					last_error = error
					last_retries = retries

			final_state = step_state
		except Exception:
			final_state = graph.invoke(state)

		return final_state

	if langfuse is None:
		final_state = _execute_turn()
		return final_state.get("messages", messages), final_state.get("suggestions", [])

	try:
		from langfuse import propagate_attributes
	except Exception:
		propagate_attributes = None

	def _run_with_trace() -> Dict[str, Any]:
		with langfuse.start_as_current_observation(
			as_type="span",
			name="sql_chat_turn",
			input={"question": user_input},
		) as span:
			final_state = _execute_turn()
			span.update(
				output={
					"answer": final_state.get("messages", [])[-1]["content"],
					"suggestions": final_state.get("suggestions", []),
				}
			)
			return final_state

	if propagate_attributes is not None and session_id:
		with propagate_attributes(session_id=session_id):
			final_state = _run_with_trace()
	else:
		final_state = _run_with_trace()

	return final_state.get("messages", messages), final_state.get("suggestions", [])


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	context.user_data["messages"] = []
	await update.message.reply_text(
		"Hola. Soy un bot para consultar una base de datos de musica. "
		"Pregunta por artistas, albumes, generos o ventas."
	)


def _build_reply_keyboard(suggestions: List[str]) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
	if not suggestions:
		return ReplyKeyboardRemove()
	keyboard = [[suggestion] for suggestion in suggestions]
	return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.message is None or update.message.text is None:
		return

	text = update.message.text.strip()
	user_name = update.effective_user.first_name if update.effective_user else "Desconocido"
	print(f"Mensaje de {user_name}: {text}")

	user_id = update.effective_user.id if update.effective_user else "unknown"
	user_messages = context.user_data.get("messages", [])
	graph = context.application.bot_data["graph"]
	langfuse = context.application.bot_data.get("langfuse")

	messages, suggestions = await asyncio.to_thread(
		_run_turn,
		graph=graph,
		messages=user_messages,
		user_input=text,
		langfuse=langfuse,
		session_id=str(user_id),
	)

	context.user_data["messages"] = messages
	answer = messages[-1]["content"] if messages else "No hay respuesta disponible."
	keyboard = _build_reply_keyboard(suggestions)
	await update.message.reply_text(answer, reply_markup=keyboard)


def main() -> None:
	_load_dotenv(Path(".env"))

	token = os.getenv("TELEGRAM_TOKEN")
	if not token:
		raise RuntimeError("Missing TELEGRAM_TOKEN. Set it in your environment or .env file.")

	db_path = Path(os.getenv("SQLITE_DB_PATH", "data/database.sqlite"))
	if not db_path.exists():
		raise RuntimeError("DB not found. Set SQLITE_DB_PATH in .env or update bot.py.")

	langfuse = _init_langfuse()
	session_id = os.getenv("LANGFUSE_SESSION_ID") or f"telegram-{uuid.uuid4().hex[:8]}"

	sql_agent = _build_openrouter_agent(
		"You are a SQL generator. Return only the SQL query for the user question.",
		name="sql_generator",
		langfuse=langfuse,
	)
	analyst_agent = _build_openrouter_agent(
		"You are a data analyst. Answer the user concisely.",
		name="analyst",
		langfuse=langfuse,
	)

	graph = build_graph(
		sql_agent=sql_agent,
		analyst_agent=analyst_agent,
		db_path=str(db_path),
	)

	application = ApplicationBuilder().token(token).build()
	application.bot_data["graph"] = graph
	application.bot_data["langfuse"] = langfuse
	application.bot_data["session_id"] = session_id

	application.add_handler(CommandHandler("start", _start))
	application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))

	application.run_polling()


if __name__ == "__main__":
	main()