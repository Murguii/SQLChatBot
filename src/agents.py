"""Agent factory functions for the SQL Music Chatbot."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional


_SQL_SYSTEM_PROMPT = (
	"You are a SQL generator. Return only the SQL query for the user question. "
	"Before generating SQL, decide whether the provided name looks like a customer_name in sales "
	"or a name in artists. If the user asks for 'ventas de [Nombre]', check customers first. "
	"For name searches, always use LOWER(column) LIKE LOWER('%value%') instead of '='. "
	"Example: WHERE LOWER(a.name) LIKE LOWER('%Fleetwood Mac%'). "
	"Use COALESCE(SUM(...), 0) for sums that could be NULL. "
	"If the question is about sales for an artist or customer, return two columns: "
	"the requested numeric value and the real matched name from artists or sales. "
	"If the name is not found, return NULL in the name column."
)

_ANALYST_SYSTEM_PROMPT = "You are a data analyst. Answer the user concisely."


def _build_openrouter_agent(
	*,
	system_prompt: str,
	model: str,
	langfuse: Optional[Any],
) -> Callable[[str], str]:
	"""Create an OpenRouter-backed LLM agent with optional Langfuse tracing."""
	try:
		from openai import OpenAI
	except ImportError:

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
	model_name = model or os.getenv("OPENROUTER_MODEL", "openrouter/auto")

	def _agent(prompt: str) -> str:
		if langfuse is None:
			response = client.responses.create(
				model=model_name,
				input=[
					{"role": "system", "content": system_prompt},
					{"role": "user", "content": prompt},
				],
			)
			return response.output_text.strip()

		with langfuse.start_as_current_observation(
			as_type="generation",
			name=model_name,
			model=model_name,
			input=prompt,
		) as generation:
			response = client.responses.create(
				model=model_name,
				input=[
					{"role": "system", "content": system_prompt},
					{"role": "user", "content": prompt},
				],
			)
			output_text = response.output_text.strip()
			generation.update(output=output_text)
			return output_text

	return _agent


def create_sql_agent(model: str, langfuse: Optional[Any]) -> Callable[[str], str]:
	"""Return a callable SQL-generation agent backed by OpenRouter."""
	return _build_openrouter_agent(
		system_prompt=_SQL_SYSTEM_PROMPT,
		model=model,
		langfuse=langfuse,
	)


def create_analyst_agent(model: str, langfuse: Optional[Any]) -> Callable[[str], str]:
	"""Return a callable data-analyst agent backed by OpenRouter."""
	return _build_openrouter_agent(
		system_prompt=_ANALYST_SYSTEM_PROMPT,
		model=model,
		langfuse=langfuse,
	)