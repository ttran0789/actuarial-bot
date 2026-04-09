"""OpenAI tool-use agent — the brain of the actuarial bot."""

import json
from typing import Generator, Optional
from openai import OpenAI

from core.tools import TOOLS, SYSTEM_PROMPT
from core.reasonability import check_query_result, format_warnings
from db.connection import OracleConnection
from db.schema import SchemaDiscovery
from db.query import format_result_as_text, result_to_records, result_to_json
from executor.python_runner import PythonRunner


class ActuarialAgent:
    def __init__(self, api_key: str, model: str, oracle_conn: Optional[OracleConnection],
                 python_runner: PythonRunner, temperature: float = 0.1, max_tokens: int = 4096):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.oracle = oracle_conn
        self.schema = SchemaDiscovery(oracle_conn) if oracle_conn else None
        self.python = python_runner
        self.demo_mode = oracle_conn is None
        prompt = SYSTEM_PROMPT
        if self.demo_mode:
            prompt += "\n\nNOTE: Oracle database is not connected. You can still help with general actuarial questions, write SQL queries (without executing), and run Python scripts. If the user asks to run a query, explain that the database is not connected."
        self.messages: list[dict] = [{"role": "system", "content": prompt}]
        self.max_rows = 10000
        # Stores the last query result for export
        self.last_result: Optional[dict] = None
        self.last_query: Optional[str] = None

    def reset_conversation(self):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.last_result = None
        self.last_query = None

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        """Process a user message and yield response chunks.

        Yields dicts with keys:
          - {"type": "text", "content": "..."} — text content from the assistant
          - {"type": "tool_call", "name": "...", "args": {...}} — tool being called
          - {"type": "tool_result", "name": "...", "content": "..."} — tool result
          - {"type": "sql_preview", "sql": "...", "explanation": "..."} — SQL preview
          - {"type": "query_result", "result": {...}, "text": "..."} — query result data
          - {"type": "warning", "content": "..."} — reasonability warning
          - {"type": "python_result", "result": {...}} — python execution result
          - {"type": "error", "content": "..."} — error message
          - {"type": "done"} — conversation turn complete
        """
        self.messages.append({"role": "user", "content": user_message})

        while True:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOLS,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            except Exception as e:
                yield {"type": "error", "content": f"OpenAI API error: {e}"}
                yield {"type": "done"}
                return

            choice = response.choices[0]
            message = choice.message

            # Collect assistant message for history
            assistant_msg = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in message.tool_calls
                ]
            self.messages.append(assistant_msg)

            # Yield any text content
            if message.content:
                yield {"type": "text", "content": message.content}

            # If no tool calls, we're done
            if not message.tool_calls:
                yield {"type": "done"}
                return

            # Process each tool call
            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                yield {"type": "tool_call", "name": fn_name, "args": args}

                result_content = self._execute_tool(fn_name, args)

                # Yield specialized results based on tool type
                if fn_name == "preview_query":
                    yield {"type": "sql_preview", "sql": args.get("sql", ""), "explanation": args.get("explanation", "")}
                elif fn_name == "run_query":
                    if isinstance(result_content, dict) and "columns" in result_content:
                        text = format_result_as_text(result_content)
                        yield {"type": "query_result", "result": result_content, "text": text}
                        # Run reasonability checks
                        warnings = check_query_result(
                            result_content["columns"], result_content["rows"],
                            context=args.get("sql", ""))
                        warning_text = format_warnings(warnings)
                        if warning_text:
                            yield {"type": "warning", "content": warning_text}
                        # Store for export
                        self.last_result = result_content
                        self.last_query = args.get("sql", "")
                        result_str = result_to_json(result_content)
                    else:
                        result_str = json.dumps(result_content) if isinstance(result_content, dict) else str(result_content)
                elif fn_name == "run_python":
                    yield {"type": "python_result", "result": result_content}
                    result_str = json.dumps(result_content)
                else:
                    result_str = json.dumps(result_content) if isinstance(result_content, dict) else str(result_content)
                    yield {"type": "tool_result", "name": fn_name, "content": result_str[:2000]}

                # Add tool result to message history
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_str if isinstance(result_str, str) else json.dumps(result_str),
                })

            # Loop back to get the next response (agent may call more tools)

    def _execute_tool(self, name: str, args: dict):
        try:
            # Database tools require Oracle connection
            db_tools = {"list_tables", "describe_table", "find_columns", "get_table_comments", "run_query", "sample_data"}
            if name in db_tools and self.demo_mode:
                return {"error": "Oracle database is not connected. Running in demo mode."}

            if name == "list_tables":
                keyword = args.get("keyword")
                schema = args.get("schema")
                if keyword:
                    return self.schema.find_tables(keyword, schema)
                else:
                    return self.schema.discover_tables(schema)

            elif name == "describe_table":
                return self.schema.describe_table(args["table_name"], args.get("schema"))

            elif name == "find_columns":
                return self.schema.find_columns(args["keyword"], args.get("schema"))

            elif name == "get_table_comments":
                return self.schema.get_table_comments(args["table_name"], args.get("schema"))

            elif name == "preview_query":
                return {"status": "previewed", "sql": args["sql"], "explanation": args.get("explanation", "")}

            elif name == "run_query":
                sql = args["sql"].strip()
                # Safety: only allow SELECT
                first_word = sql.split()[0].upper() if sql.split() else ""
                if first_word not in ("SELECT", "WITH"):
                    return {"error": "Only SELECT queries are allowed. Use SELECT or WITH...SELECT."}
                return self.oracle.execute(sql, max_rows=self.max_rows)

            elif name == "run_python":
                return self.python.run(args["code"], args.get("input_data"))

            elif name == "sample_data":
                table = args["table_name"]
                schema = args.get("schema")
                where = args.get("where_clause", "")
                prefix = f"{schema}.{table}" if schema else table
                sql = f"SELECT * FROM {prefix}"
                if where:
                    sql += f" WHERE {where}"
                sql += " FETCH FIRST 10 ROWS ONLY"
                return self.oracle.execute(sql)

            else:
                return {"error": f"Unknown tool: {name}"}

        except Exception as e:
            return {"error": str(e)}
