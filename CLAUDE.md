# Actuarial Bot

## Overview
PyQt5 chat application for actuarial data analysis. Uses OpenAI GPT-4o with function-calling to query Oracle databases, run Python analysis, and export results to Excel.

## Quick Start
```bash
pip install -r requirements.txt
cp config.yaml config.local.yaml  # Fill in credentials
python main.py
```

## Architecture
- **core/agent.py** — OpenAI tool-use agent (brain), manages conversation and tool dispatch
- **core/tools.py** — Tool definitions (list_tables, describe_table, run_query, run_python, etc.) and system prompt
- **core/reasonability.py** — Contextual validation checks on query results (NULL detection, fan-out, ratio bounds)
- **db/connection.py** — Oracle connection via TNS names using oracledb
- **db/schema.py** — Auto-discovery of tables, columns, PKs, FKs, indexes, comments
- **db/query.py** — Query result formatting and serialization
- **executor/python_runner.py** — Subprocess Python execution with file I/O
- **ui/chat_window.py** — Main PyQt5 chat window with threaded agent execution
- **ui/message_widgets.py** — Chat bubbles, SQL blocks with syntax highlighting, data tables, warnings
- **ui/export.py** — Excel export, clipboard copy, open-in-Excel

## Configuration
- `config.yaml` — defaults and template (committed)
- `config.local.yaml` — user credentials (gitignored)

## Key Patterns
- Agent runs in background thread; communicates to UI via Qt signals
- Tool results flow: Agent → tool execution → yield typed chunks → UI renders appropriate widget
- Schema discovery caches results to avoid repeated Oracle metadata queries
- Only SELECT/WITH queries are allowed (safety check in agent)
- Reasonability checks run automatically after every query execution

## Future Additions
- Outlook email integration (COM or Graph API)
- Saved query library
- Conversation history persistence
