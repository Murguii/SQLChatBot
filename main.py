"""Terminal chat loop for the LangGraph SQL workflow."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

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
) -> Callable[[str], str]:
	try:
		from openai import OpenAI
	except Exception:
		def _fallback(_: str) -> str:
			return "SELECT 1;"

		return _fallback

	api_key = os.getenv("OPENROUTER_API_KEY")
	if not api_key:
		raise RuntimeError(
			"Missing OPENROUTER_API_KEY. Set it in your environment or .env file."
		)

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
	messages: list[Dict[str, str]],
	user_input: str,
	langfuse: Optional[Any],
	session_id: Optional[str],
) -> tuple[list[Dict[str, str]], list[str]]:
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
					print(f"[sql_generator] SQL generado: {sql_query}")
					last_sql = sql_query

				if error and (error != last_error or retries != last_retries):
					print(
						f"[execute_sql] Error SQL, reintentando ({retries}/3): {error}"
					)
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


def main() -> None:
	_load_dotenv(Path(".env"))

	db_path = Path(os.getenv("SQLITE_DB_PATH", "data/database.sqlite"))
	if not db_path.exists():
		print("DB not found. Set SQLITE_DB_PATH in .env or update main.py.")
		return

	langfuse = _init_langfuse()
	session_id = os.getenv("LANGFUSE_SESSION_ID") or f"terminal-{uuid.uuid4().hex[:8]}"

	sql_agent = _build_openrouter_agent(
		"You are a SQL generator. Return only the SQL query for the user question. "
		"Before generating SQL, decide whether the provided name looks like a customer_name in sales "
		"or a name in artists. If the user asks for 'ventas de [Nombre]', check customers first. "
		"Always use LIKE with % wildcards for artist/customer names (e.g., WHERE a.name LIKE '%Fleetwood Mac%'). "
		"Use COALESCE(SUM(...), 0) for sums that could be NULL.",
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

	print("SQL chatbot ready. Type 'exit' to quit.")
	messages: list[Dict[str, str]] = []
	try:
		while True:
			user_input = input("Tu pregunta: ").strip()
			if not user_input:
				continue
			if user_input.lower() in {"exit", "quit"}:
				break

			messages, suggestions = _run_turn(
				graph=graph,
				messages=messages,
				user_input=user_input,
				langfuse=langfuse,
				session_id=session_id,
			)
			print(messages[-1]["content"])
			if suggestions:
				print("Sugerencias: " + " | ".join(suggestions))
	finally:
		if langfuse is not None:
			try:
				langfuse.flush()
			except Exception:
				pass


if __name__ == "__main__":
	main()