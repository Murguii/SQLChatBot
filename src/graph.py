"""LangGraph state machine for SQL generation, execution, and analysis."""

from __future__ import annotations

import ast
import re
from typing import Any, Callable, Dict, List, Optional, TypedDict, Union

import pandas as pd
from langgraph.graph import END, StateGraph

from .tools import execute_query, get_schema


class AgentState(TypedDict):
	messages: List[Dict[str, str]]
	sql_query: str
	db_result: Optional[Union[pd.DataFrame, str]]
	error: Optional[str]
	retries: int
	suggestions: List[str]


def _extract_latest_question(messages: List[Dict[str, str]]) -> str:
	for message in reversed(messages):
		if message.get("role") == "user":
			return message.get("content", "")
	return messages[-1]["content"] if messages else ""


def _call_agent(agent: Callable[..., Any], prompt: str) -> str:
	result = agent(prompt)
	if hasattr(result, "content"):
		return str(result.content).strip()
	return str(result).strip()


def _clean_sql(text: str) -> str:
	cleaned = text.strip()
	if cleaned.startswith("```"):
		lines = cleaned.splitlines()
		if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
			cleaned = "\n".join(lines[1:-1]).strip()
	if cleaned.lower().startswith("sql\n"):
		cleaned = cleaned[4:].strip()
	return cleaned


def _build_sql_prompt(question: str, schema: Dict[str, List[str]], error: Optional[str]) -> str:
	lines = [
		"Generate a SQL query for the following question.",
		"Return only the SQL query.",
		"",
		f"Question: {question}",
		"",
		"Database schema:",
	]
	for table, columns in schema.items():
		lines.append(f"- {table}({', '.join(columns)})")
	if error:
		lines.extend(["", "Previous error to fix:", error])
	return "\n".join(lines)


def _build_analyst_prompt(question: str, db_result: Union[pd.DataFrame, str]) -> str:
	if isinstance(db_result, pd.DataFrame):
		data_preview = db_result.head(50).to_markdown(index=False)
	else:
		data_preview = str(db_result)

	return "\n".join(
		[
			"You are a data analyst.",
			"Golden rule: If a fact or value is not in db_result, it does not exist.",
			"Do not use external knowledge or invented examples.",
			"Do not mention bands, dates, or statistics that are not present in db_result.",
			"If the data is missing, say it is not available in the data.",
			"Answer briefly and naturally in the user's language.",
			"Priority rules:",
			"1) If the database result is 0 or empty, FIRST check for a misspelled search term.",
			"2) If there is a misspelling, do NOT mention the 0. Respond only: "
			"'No encontre resultados para [error]. Es posible que te refieras a [correcto]. "
			"Tienes opciones debajo para consultar su informacion.'",
			"3) If the term is correct and the result is 0, then say it is 0.",
			"If a sales query includes a name column in the result and that name is NULL, "
			"you must say there are no records for that name. Do not say it sold 0.",
			"Use the result columns to infer missing joins or missing names.",
			"Do not ask open questions or request confirmation.",
			"Do not assume results apply to the corrected term.",
			"Your response must contain ONLY the answer to the user's question.",
			"Do not append follow-up questions or extra sections at the end.",
			"Format: one short sentence, no bullet points.",
			"Example: 'El genero mas vendido es el Rock con un total de 12.9 EUR'.",
			"",
			f"Question: {question}",
			"",
			"Data:",
			data_preview,
		]
	)


def _build_suggestions_prompt(
	question: str,
	db_result: Union[pd.DataFrame, str],
	schema: Optional[Dict[str, List[str]]],
) -> str:
	if isinstance(db_result, pd.DataFrame):
		data_preview = db_result.head(50).to_markdown(index=False)
	else:
		data_preview = str(db_result)

	if schema:
		schema_lines = [f"- {table}({', '.join(columns)})" for table, columns in schema.items()]
	else:
		schema_lines = ["(schema unavailable)"]

	return "\n".join(
		[
			"You are a proactive data analyst.",
			"Propose exactly 2 follow-up questions.",
			"Each suggestion must be 3 to 4 words (no truncation).",
			"Do not include answers, numbers, or data from the results.",
			"Use only the available tables in the schema and the data shown.",
			"Do not invent facts or mention tables that are not listed.",
			"Avoid regional analysis unless there is a region-related table.",
			"Return them as a Python list literal of two strings (e.g., ['Ventas por artista', 'Lista de generos']).",
			"",
			f"Question: {question}",
			"",
			"Database schema:",
			*schema_lines,
			"",
			"Data:",
			data_preview,
		]
	)


def _parse_suggestions(raw_text: str) -> List[str]:
	match = re.search(r"\[[\s\S]*\]", raw_text)
	if match:
		try:
			parsed = ast.literal_eval(match.group(0))
			if isinstance(parsed, list):
				return [str(item).strip() for item in parsed if str(item).strip()]
		except (ValueError, SyntaxError):
			pass

	lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
	suggestions: List[str] = []
	for line in lines:
		cleaned = line.lstrip("- ").strip()
		if cleaned[:2].isdigit() and cleaned[2:3] in {".", ")"}:
			cleaned = cleaned[3:].strip()
		if cleaned:
			suggestions.append(cleaned)
	if raw_text.strip():
		return suggestions[:2] if suggestions else [raw_text.strip()][:2]
	return suggestions


def _clean_suggestions(suggestions: List[str]) -> List[str]:
	cleaned_list: List[str] = []
	for suggestion in suggestions:
		cleaned = suggestion.strip()
		if not cleaned:
			continue
		if cleaned.lower().startswith("sugerencia:"):
			cleaned = cleaned.split(":", 1)[-1].strip()
		if cleaned:
			cleaned_list.append(cleaned)

	filtered: List[str] = []
	for suggestion in cleaned_list:
		word_count = len(suggestion.split())
		if 3 <= word_count <= 4:
			filtered.append(suggestion)
		if len(filtered) >= 2:
			return filtered[:2]

	if len(cleaned_list) >= 2:
		return cleaned_list[:2]
	return cleaned_list


def _is_zero_result(db_result: Union[pd.DataFrame, str]) -> bool:
	if not isinstance(db_result, pd.DataFrame):
		return False
	if db_result.empty:
		return False
	try:
		if db_result.size == 1:
			value = db_result.iloc[0, 0]
			return pd.notna(value) and float(value) == 0.0
	except (ValueError, TypeError):
		return False
	return False


def _extract_name_candidate(question: str) -> Optional[str]:
	quoted = re.search(r"['\"]([^'\"]+)['\"]", question)
	if quoted:
		return quoted.group(1).strip()

	match = re.search(
		r"(?:ventas de|de la|del|de|por)\s+([\w\s\-\.]+)",
		question,
		flags=re.IGNORECASE,
	)
	if match:
		candidate = match.group(1)
		candidate = re.split(r"[\?\!\,\.;:]", candidate)[0].strip()
		return candidate
	return None


def _build_like_pattern(name: str) -> Optional[str]:
	tokens = re.findall(r"[A-Za-z0-9]+", name.lower())
	if not tokens:
		return None
	parts = [token[:3] for token in tokens if len(token) >= 3]
	if not parts:
		parts = [tokens[0]]
	return "%" + "%".join(parts) + "%"


def _extract_genre_candidate(question: str) -> Optional[str]:
	if re.search(r"\brock\b", question, flags=re.IGNORECASE):
		return "Rock"
	return None


def _escape_sql_literal(value: str) -> str:
	return value.replace("'", "''")


def _find_table_with_columns(schema: Dict[str, List[str]], required: List[str]) -> Optional[str]:
	required_lower = {column.lower() for column in required}
	for table, columns in schema.items():
		column_set = {column.lower() for column in columns}
		if required_lower.issubset(column_set):
			return table
	return None


def _find_customer_name_like(
	*,
	db_path: str,
	schema: Dict[str, List[str]],
	name: str,
) -> Optional[str]:
	customer_table = _find_table_with_columns(schema, ["first_name", "last_name"])
	if not customer_table:
		return None
	first_token = name.strip().split()[0] if name.strip() else ""
	if not first_token:
		return None
	pattern_sql = _escape_sql_literal(f"%{first_token}%")
	query = (
		"SELECT DISTINCT first_name || ' ' || last_name AS full_name "
		f"FROM {customer_table} "
		"WHERE LOWER(first_name || ' ' || last_name) "
		f"LIKE LOWER('{pattern_sql}') "
		"LIMIT 5"
	)
	result = execute_query(db_path, query)
	if isinstance(result, pd.DataFrame) and not result.empty:
		return str(result.iloc[0]["full_name"]).strip()
	return None


def _customer_has_purchases(
	*,
	db_path: str,
	schema: Dict[str, List[str]],
	name: str,
) -> Optional[bool]:
	customer_table = _find_table_with_columns(schema, ["customer_id", "first_name", "last_name"])
	invoice_table = _find_table_with_columns(schema, ["invoice_id", "customer_id"])
	if not customer_table or not invoice_table:
		return None
	pattern_sql = _escape_sql_literal(f"%{name.strip()}%")
	query = (
		"SELECT COUNT(*) AS total "
		f"FROM {customer_table} c "
		f"JOIN {invoice_table} i ON c.customer_id = i.customer_id "
		"WHERE LOWER(c.first_name || ' ' || c.last_name) "
		f"LIKE LOWER('{pattern_sql}')"
	)
	result = execute_query(db_path, query)
	if isinstance(result, pd.DataFrame) and not result.empty:
		try:
			return float(result.iloc[0]["total"]) > 0
		except (ValueError, TypeError, KeyError):
			return None
	return None


def _find_name_suggestion(
	*,
	db_path: str,
	schema: Dict[str, List[str]],
	name: str,
) -> Optional[str]:
	pattern = _build_like_pattern(name)
	if not pattern:
		return None
	pattern_sql = _escape_sql_literal(pattern)

	for table, columns in schema.items():
		lower_cols = [column.lower() for column in columns]
		if "first_name" in lower_cols and "last_name" in lower_cols:
			query = (
				"SELECT DISTINCT first_name || ' ' || last_name AS full_name "
				f"FROM {table} "
				"WHERE LOWER(first_name || ' ' || last_name) "
				f"LIKE LOWER('{pattern_sql}') "
				"LIMIT 5"
			)
			result = execute_query(db_path, query)
			if isinstance(result, pd.DataFrame) and not result.empty:
				return str(result.iloc[0]["full_name"]).strip()

	for table, columns in schema.items():
		for column in columns:
			if "name" not in column.lower():
				continue
			query = (
				f"SELECT DISTINCT {column} AS name FROM {table} "
				f"WHERE LOWER({column}) LIKE LOWER('{pattern_sql}') "
				"LIMIT 5"
			)
			result = execute_query(db_path, query)
			if isinstance(result, pd.DataFrame) and not result.empty:
				return str(result.iloc[0]["name"]).strip()

	return None


def _name_exists(
	*,
	db_path: str,
	schema: Dict[str, List[str]],
	name: str,
) -> bool:
	pattern = f"%{name.strip()}%"
	pattern_sql = _escape_sql_literal(pattern)

	for table, columns in schema.items():
		lower_cols = [column.lower() for column in columns]
		if "first_name" in lower_cols and "last_name" in lower_cols:
			query = (
				"SELECT 1 FROM "
				f"{table} "
				"WHERE LOWER(first_name || ' ' || last_name) "
				f"LIKE LOWER('{pattern_sql}') "
				"LIMIT 1"
			)
			result = execute_query(db_path, query)
			if isinstance(result, pd.DataFrame) and not result.empty:
				return True

	for table, columns in schema.items():
		for column in columns:
			if "name" not in column.lower():
				continue
			query = (
				"SELECT 1 FROM "
				f"{table} "
				f"WHERE LOWER({column}) LIKE LOWER('{pattern_sql}') "
				"LIMIT 1"
			)
			result = execute_query(db_path, query)
			if isinstance(result, pd.DataFrame) and not result.empty:
				return True

	return False


def build_graph(
	*,
	sql_agent: Callable[[str], Any],
	analyst_agent: Callable[[str], Any],
	db_path: str,
) -> StateGraph:
	def sql_generator(state: AgentState) -> Dict[str, Any]:
		schema = get_schema(db_path)
		if isinstance(schema, str):
			return {
				"sql_query": "",
				"error": schema,
				"db_result": None,
				"retries": state.get("retries", 0) + 1,
			}

		question = _extract_latest_question(state.get("messages", []))
		prompt = _build_sql_prompt(question, schema, state.get("error"))
		sql_query = _clean_sql(_call_agent(sql_agent, prompt))
		print(f"--- SQL GENERADO: {sql_query} ---")
		return {"sql_query": sql_query, "error": None}

	def execute_sql(state: AgentState) -> Dict[str, Any]:
		query = state.get("sql_query", "")
		result = execute_query(db_path, query)
		if isinstance(result, str):
			return {
				"db_result": None,
				"error": result,
				"retries": state.get("retries", 0) + 1,
			}
		return {"db_result": result, "error": None}

	def analyst(state: AgentState) -> Dict[str, Any]:
		question = _extract_latest_question(state.get("messages", []))
		suggestions: List[str] = []
		db_result = state.get("db_result")
		if state.get("error"):
			answer = (
				"I could not execute a valid SQL query after multiple attempts. "
				f"Error: {state['error']}"
			)
		elif db_result is None:
			answer = "No encontre datos para esa consulta."
		elif isinstance(db_result, pd.DataFrame) and db_result.empty:
			schema = get_schema(db_path)
			candidate_name = _extract_name_candidate(question)
			suggestion = None
			if isinstance(schema, dict) and candidate_name:
				suggestion = _find_name_suggestion(
					db_path=db_path,
					schema=schema,
					name=candidate_name,
				)
				diagnostic_name = _find_customer_name_like(
					db_path=db_path,
					schema=schema,
					name=candidate_name,
				)
				genre_candidate = _extract_genre_candidate(question) or "ese genero"
				has_purchases = None
				if diagnostic_name:
					has_purchases = _customer_has_purchases(
						db_path=db_path,
						schema=schema,
						name=diagnostic_name,
					)
				if has_purchases:
					answer = (
						f"No encontre compras de {genre_candidate} para {candidate_name}, "
						"pero veo que este cliente ha comprado otros generos. "
						"Deseas ver su historial completo?"
					)
					suggestions = [f"Historial de {diagnostic_name}"]
					messages = list(state.get("messages", []))
					messages.append({"role": "assistant", "content": answer})
					return {"messages": messages, "suggestions": suggestions}
			if candidate_name and suggestion and suggestion.lower() != candidate_name.lower():
				answer = (
					"No encontre resultados para "
					f"{candidate_name}. Es posible que te refieras a {suggestion}. "
					"Tienes opciones debajo para consultar su informacion."
				)
				suggestions = [f"Ver ventas de {suggestion}"]
			elif candidate_name:
				answer = f"No encontre resultados para {candidate_name}."
			else:
				answer = "No encontre resultados para esa consulta."
		elif _is_zero_result(db_result):
			schema = get_schema(db_path)
			candidate_name = _extract_name_candidate(question)
			suggestion = None
			if isinstance(schema, dict) and candidate_name:
				suggestion = _find_name_suggestion(
					db_path=db_path,
					schema=schema,
					name=candidate_name,
				)
			if candidate_name and suggestion and suggestion.lower() != candidate_name.lower():
				answer = (
					"No encontre resultados para "
					f"{candidate_name}. Es posible que te refieras a {suggestion}. "
					"Tienes opciones debajo para consultar su informacion."
				)
				suggestions = [f"Ver ventas de {suggestion}"]
			elif isinstance(schema, dict) and candidate_name:
				if not _name_exists(db_path=db_path, schema=schema, name=candidate_name):
					answer = (
						"No tengo registros de "
						f"{candidate_name} en mi base de datos actual."
					)
				else:
					prompt = _build_analyst_prompt(question, db_result)
					answer = _call_agent(analyst_agent, prompt)
			else:
				prompt = _build_analyst_prompt(question, db_result)
				answer = _call_agent(analyst_agent, prompt)
		else:
			prompt = _build_analyst_prompt(question, db_result)
			answer = _call_agent(analyst_agent, prompt)
			schema = get_schema(db_path)
			if isinstance(schema, str):
				schema = None
			suggestions_prompt = _build_suggestions_prompt(question, db_result, schema)
			suggestions_raw = _call_agent(analyst_agent, suggestions_prompt)
			suggestions = _clean_suggestions(_parse_suggestions(suggestions_raw))
			print(f"Sugerencias generadas: {suggestions}")

		messages = list(state.get("messages", []))
		messages.append({"role": "assistant", "content": answer})
		return {"messages": messages, "suggestions": suggestions}

	def route_after_execute(state: AgentState) -> str:
		if state.get("error") and state.get("retries", 0) < 3:
			return "retry"
		return "analyst"

	graph = StateGraph(AgentState)
	graph.add_node("sql_generator", sql_generator)
	graph.add_node("execute_sql", execute_sql)
	graph.add_node("analyst", analyst)

	graph.set_entry_point("sql_generator")
	graph.add_edge("sql_generator", "execute_sql")
	graph.add_conditional_edges(
		"execute_sql", route_after_execute, {"retry": "sql_generator", "analyst": "analyst"}
	)
	graph.add_edge("analyst", END)

	return graph.compile()