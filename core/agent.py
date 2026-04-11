"""OpenAI tool-use agent — the brain of the actuarial bot."""

import json
import logging
from typing import Generator, Optional
from openai import OpenAI

from core.tools import TOOLS, SYSTEM_PROMPT
from core.reasonability import check_query_result, format_warnings
from db.connection import OracleConnection
from db.schema import SchemaDiscovery
from db.query import format_result_as_text, result_to_records, result_to_json
from executor.python_runner import PythonRunner

log = logging.getLogger("actuarial_bot.agent")


class ActuarialAgent:
    def __init__(self, client: OpenAI, model: str, oracle_conn: Optional[OracleConnection],
                 python_runner: PythonRunner, temperature: float = 0.1, max_tokens: int = 4096):
        self.client = client
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
        self.last_result: Optional[dict] = None
        self.last_query: Optional[str] = None
        log.info("Agent initialized (model=%s, demo_mode=%s)", model, self.demo_mode)

    def reset_conversation(self):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.last_result = None
        self.last_query = None
        log.info("Conversation reset")

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        """Process a user message and yield response chunks."""
        log.info("User message: %s", user_message[:200])
        self.messages.append({"role": "user", "content": user_message})

        turn = 0
        while True:
            turn += 1
            log.debug("API call (turn %d, %d messages in context)", turn, len(self.messages))
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOLS,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                log.debug("API response: usage=%s, finish_reason=%s",
                          response.usage, response.choices[0].finish_reason)
            except Exception as e:
                log.error("LLM API error: %s", e, exc_info=True)
                yield {"type": "error", "content": f"AI API error: {e}"}
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

            if message.content:
                log.info("Assistant response: %s", message.content[:200])
                yield {"type": "text", "content": message.content}

            if not message.tool_calls:
                log.debug("Turn complete (no tool calls)")
                yield {"type": "done"}
                return

            # Process each tool call
            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                log.info("Tool call: %s(%s)", fn_name, json.dumps(args)[:300])
                yield {"type": "tool_call", "name": fn_name, "args": args}

                result_content = self._execute_tool(fn_name, args)

                # Log tool result summary
                if isinstance(result_content, dict):
                    if "error" in result_content:
                        log.warning("Tool %s error: %s", fn_name, result_content["error"])
                    elif "columns" in result_content:
                        log.info("Tool %s returned %d rows, %d columns",
                                 fn_name, result_content.get("row_count", 0), len(result_content["columns"]))
                    else:
                        log.debug("Tool %s result: %s", fn_name, json.dumps(result_content)[:200])
                elif isinstance(result_content, list):
                    log.info("Tool %s returned %d items", fn_name, len(result_content))

                # Yield specialized results based on tool type
                if fn_name == "preview_query":
                    yield {"type": "sql_preview", "sql": args.get("sql", ""), "explanation": args.get("explanation", "")}
                elif fn_name == "run_query":
                    if isinstance(result_content, dict) and "columns" in result_content:
                        text = format_result_as_text(result_content)
                        yield {"type": "query_result", "result": result_content, "text": text}
                        warnings = check_query_result(
                            result_content["columns"], result_content["rows"],
                            context=args.get("sql", ""))
                        warning_text = format_warnings(warnings)
                        if warning_text:
                            log.warning("Reasonability warnings: %s", warning_text)
                            yield {"type": "warning", "content": warning_text}
                        self.last_result = result_content
                        self.last_query = args.get("sql", "")
                        result_str = result_to_json(result_content)
                    else:
                        result_str = json.dumps(result_content) if isinstance(result_content, dict) else str(result_content)
                elif fn_name == "read_file":
                    if isinstance(result_content, dict) and "columns" in result_content:
                        text = format_result_as_text(result_content)
                        yield {"type": "query_result", "result": result_content, "text": text}
                        self.last_result = result_content
                        result_str = result_to_json(result_content)
                    elif isinstance(result_content, dict) and "content" in result_content:
                        # Text file — show as chat bubble
                        yield {"type": "text", "content": f"**File: {result_content['file_path']}**\n```\n{result_content['content'][:3000]}\n```"}
                        result_str = json.dumps(result_content)
                    else:
                        result_str = json.dumps(result_content) if isinstance(result_content, dict) else str(result_content)
                elif fn_name == "run_python":
                    log.info("Python execution: success=%s", result_content.get("success"))
                    if result_content.get("stderr"):
                        log.warning("Python stderr: %s", result_content["stderr"][:500])
                    yield {"type": "python_result", "result": result_content}
                    result_str = json.dumps(result_content)
                else:
                    result_str = json.dumps(result_content) if isinstance(result_content, dict) else str(result_content)
                    yield {"type": "tool_result", "name": fn_name, "content": result_str[:2000]}

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_str if isinstance(result_str, str) else json.dumps(result_str),
                })

    def _execute_tool(self, name: str, args: dict):
        try:
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
                first_word = sql.split()[0].upper() if sql.split() else ""
                if first_word not in ("SELECT", "WITH"):
                    return {"error": "Only SELECT queries are allowed. Use SELECT or WITH...SELECT."}
                log.info("Executing SQL: %s", sql[:300])
                return self.oracle.execute(sql, max_rows=self.max_rows)

            elif name == "run_python":
                log.info("Executing Python script (%d chars)", len(args.get("code", "")))
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
                log.info("Sampling: %s", sql)
                return self.oracle.execute(sql)

            elif name == "list_directory":
                return self._list_directory(args["dir_path"], args.get("pattern"))

            elif name == "read_file":
                return self._read_file(args["file_path"], args.get("max_rows", 100), args.get("sheet_name"))

            else:
                return {"error": f"Unknown tool: {name}"}

        except Exception as e:
            log.error("Tool %s failed: %s", name, e, exc_info=True)
            return {"error": str(e)}

    def _read_file(self, file_path: str, max_rows: int = 100, sheet_name: str = None):
        """Read a local file and return its contents as a structured result."""
        import os
        import pandas as pd

        file_path = file_path.strip().strip('"').strip("'")
        # Handle file:/// URLs
        if file_path.startswith("file:///"):
            file_path = file_path[8:]

        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}

        ext = os.path.splitext(file_path)[1].lower()
        file_size = os.path.getsize(file_path)
        log.info("Reading file: %s (%s, %.1f KB)", file_path, ext, file_size / 1024)

        try:
            if ext == ".csv":
                df = pd.read_csv(file_path, nrows=max_rows)
                total_rows = sum(1 for _ in open(file_path, encoding="utf-8", errors="ignore")) - 1
            elif ext in (".xlsx", ".xls"):
                kwargs = {"sheet_name": sheet_name or 0, "nrows": max_rows}
                df = pd.read_excel(file_path, **kwargs)
                df_full = pd.read_excel(file_path, sheet_name=sheet_name or 0, usecols=[0])
                total_rows = len(df_full)
            elif ext in (".txt", ".log", ".sql", ".json", ".xml"):
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(50000)  # 50KB limit for text files
                return {
                    "file_path": file_path,
                    "file_type": ext,
                    "size_kb": round(file_size / 1024, 1),
                    "content": content,
                    "truncated": file_size > 50000,
                }
            else:
                return {"error": f"Unsupported file type: {ext}. Supported: .csv, .xlsx, .xls, .txt, .log, .sql, .json, .xml"}

            columns = list(df.columns)
            rows = df.where(df.notna(), None).values.tolist()

            return {
                "file_path": file_path,
                "file_type": ext,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "total_rows": total_rows,
                "truncated": total_rows > max_rows,
                "dtypes": {col: str(df[col].dtype) for col in columns},
            }

        except Exception as e:
            log.error("Failed to read file %s: %s", file_path, e)
            return {"error": f"Failed to read file: {e}"}

    def _list_directory(self, dir_path: str, pattern: str = None):
        """List files in a directory with size and type info."""
        import os
        import glob as glob_mod

        dir_path = dir_path.strip().strip('"').strip("'")
        if not os.path.exists(dir_path):
            return {"error": f"Directory not found: {dir_path}"}
        if not os.path.isdir(dir_path):
            return {"error": f"Not a directory: {dir_path}. Use read_file instead."}

        log.info("Listing directory: %s (pattern: %s)", dir_path, pattern)

        if pattern:
            paths = glob_mod.glob(os.path.join(dir_path, pattern))
        else:
            paths = [os.path.join(dir_path, f) for f in os.listdir(dir_path)]

        entries = []
        for p in sorted(paths):
            name = os.path.basename(p)
            is_dir = os.path.isdir(p)
            size = os.path.getsize(p) if not is_dir else None
            entries.append({
                "name": name,
                "type": "directory" if is_dir else os.path.splitext(name)[1].lower(),
                "size_kb": round(size / 1024, 1) if size else None,
                "path": p,
            })

        return {"dir_path": dir_path, "count": len(entries), "entries": entries}
