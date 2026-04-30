# Las "skills" (funciones SQL)

import sqlite3
from typing import Dict, List, Union

import pandas as pd


def get_schema(db_path: str) -> Union[Dict[str, List[str]], str]:
	"""Return table names and their columns from a SQLite database."""
	try:
		with sqlite3.connect(db_path) as conn:
			cursor = conn.cursor()
			cursor.execute(
				"SELECT name FROM sqlite_master "
				"WHERE type='table' AND name NOT LIKE 'sqlite_%'"
			)
			tables = [row[0] for row in cursor.fetchall()]

			schema: Dict[str, List[str]] = {}
			for table in tables:
				cursor.execute(f"PRAGMA table_info({table})")
				schema[table] = [row[1] for row in cursor.fetchall()]

			return schema
	except sqlite3.Error as exc:
		return f"SQL error: {exc}"


def execute_query(db_path: str, query: str) -> Union[pd.DataFrame, str]:
	"""Execute a SQL query and return a pandas DataFrame or an error message."""
	try:
		with sqlite3.connect(db_path) as conn:
			return pd.read_sql_query(query, conn)
	except sqlite3.Error as exc:
		return f"SQL error: {exc}"