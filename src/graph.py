"""LangGraph state machine for SQL generation, execution, and analysis."""

from __future__ import annotations

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
			"Answer the user based on the data provided.",
			"Focus on accuracy and clarity.",
			"",
			f"Question: {question}",
			"",
			"Data:",
			data_preview,
		]
	)


def _build_suggestions_prompt(question: str, db_result: Union[pd.DataFrame, str]) -> str:
	if isinstance(db_result, pd.DataFrame):
		data_preview = db_result.head(50).to_markdown(index=False)
	else:
		data_preview = str(db_result)

	return "\n".join(
		[
			"You are a proactive data analyst.",
			"Based on the question and data, propose exactly 2 follow-up questions.",
			"Return them as a simple list, one per line.",
			"",
			f"Question: {question}",
			"",
			"Data:",
			data_preview,
		]
	)


def _parse_suggestions(raw_text: str) -> List[str]:
	lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
	suggestions: List[str] = []
	for line in lines:
		cleaned = line.lstrip("- ").strip()
		if cleaned[:2].isdigit() and cleaned[2:3] in {".", ")"}:
			cleaned = cleaned[3:].strip()
		if cleaned:
			suggestions.append(cleaned)
	if len(suggestions) >= 2:
		return suggestions[:2]
	if raw_text.strip():
		return [raw_text.strip()][:2]
	return []


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
		if state.get("error"):
			answer = (
				"I could not execute a valid SQL query after multiple attempts. "
				f"Error: {state['error']}"
			)
		else:
			prompt = _build_analyst_prompt(question, state.get("db_result", ""))
			answer = _call_agent(analyst_agent, prompt)

			suggestions_prompt = _build_suggestions_prompt(
				question, state.get("db_result", "")
			)
			suggestions_raw = _call_agent(analyst_agent, suggestions_prompt)
			suggestions = _parse_suggestions(suggestions_raw)

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