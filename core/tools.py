"""Tool definitions for the OpenAI function-calling agent."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "List all tables in a schema. Use this first to understand what data is available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schema": {
                        "type": "string",
                        "description": "Schema/owner name. Leave empty for current user schema.",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Optional keyword to filter table names (e.g., 'PREMIUM', 'LOSS', 'CLAIM').",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "Get detailed column definitions, primary keys, foreign keys, and indexes for a table. Use this to understand table structure before writing queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Name of the table to describe."},
                    "schema": {"type": "string", "description": "Schema/owner name. Leave empty for current user schema."},
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_columns",
            "description": "Search for columns across all tables by keyword. Useful for finding join keys or specific data fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Column name keyword to search for (e.g., 'POLICY', 'PREMIUM')."},
                    "schema": {"type": "string", "description": "Schema/owner name. Leave empty for current user schema."},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_comments",
            "description": "Get table and column comments/descriptions. Helpful for understanding business meaning of fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Table name."},
                    "schema": {"type": "string", "description": "Schema/owner name."},
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_query",
            "description": "Show the user a SQL query for review WITHOUT executing it. Use this when you have constructed a query and want the user to approve before running.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "The SQL query to show."},
                    "explanation": {"type": "string", "description": "Brief explanation of what this query does and why."},
                },
                "required": ["sql", "explanation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_query",
            "description": "Execute a SQL query against the Oracle database. Always preview_query first for complex queries. Only use SELECT statements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "The SQL SELECT query to execute."},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute a Python script for data analysis, visualization, or transformation. The script runs in a subprocess with pandas, numpy, openpyxl, matplotlib available. Use 'input_data' to pass CSV data, or write results to files in the current directory. For charts, save with plt.savefig('chart.png', dpi=150, bbox_inches='tight') — images are displayed inline in the chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute."},
                    "input_data": {"type": "string", "description": "Optional CSV data to make available as 'input_data.csv' in the script's working directory."},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sample_data",
            "description": "Get a small sample of data from a table (first 10 rows). Useful for understanding data format and content before writing complex queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Table name to sample."},
                    "schema": {"type": "string", "description": "Schema/owner name."},
                    "where_clause": {"type": "string", "description": "Optional WHERE clause to filter the sample."},
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and folders in a local directory. Use this when the user asks you to look at a folder, see what files are available, or explore a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "Absolute path to the directory."},
                    "pattern": {"type": "string", "description": "Optional glob pattern to filter files (e.g., '*.csv', '*.xlsx'). Default: all files."},
                },
                "required": ["dir_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the user's local filesystem. Supports CSV, Excel (.xlsx/.xls), Parquet, and text files. For large files, returns the first 100 rows as a preview. Use this when the user provides a file path or asks you to look at a local file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to the file (e.g., C:/Users/tuan/data/file.csv)."},
                    "max_rows": {"type": "integer", "description": "Maximum rows to return for preview (default 100)."},
                    "sheet_name": {"type": "string", "description": "Sheet name for Excel files (default: first sheet)."},
                },
                "required": ["file_path"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are an actuarial data analyst assistant with access to an Oracle database containing insurance data. You help users query, analyze, and understand actuarial data.

## Your Capabilities
- Read local files (CSV, Excel, text) from the user's filesystem
- Discover and explore database schemas, tables, and relationships
- Write and execute SQL queries against Oracle
- Run Python scripts for data analysis and visualization
- Export results to Excel

## Workflow for Answering Questions
1. **Understand the request**: Parse what metrics/data the user needs
2. **Discover relevant tables**: Use list_tables and find_columns to locate the right data
3. **Understand table structure**: Use describe_table to understand columns, types, and relationships
4. **Sample data if needed**: Use sample_data to see actual values and understand data format
5. **Build the query**: Construct the SQL step by step
6. **Preview the query**: Show the SQL to the user with explanation using preview_query
7. **Execute when approved**: Run the query with run_query
8. **Validate results**: Check for reasonability — row counts, NULL values, unusual aggregations
9. **Present results**: Format and explain the results clearly

## Actuarial Domain Knowledge
- **Loss Ratio** = Incurred Losses / Earned Premium
- **Combined Ratio** = Loss Ratio + Expense Ratio
- **Earned Premium (EP)**: Premium earned over the policy period
- **Written Premium (WP)**: Total premium at policy inception
- **Incurred Losses**: Paid losses + reserves (case + IBNR)
- **Lines of Business**: BOP (Business Owners Policy), GL (General Liability), WC (Workers Comp), Auto, Property, etc.
- Common join keys: Policy number, policy ID, accounting date/period, line of business code

## Reasonability Checks (Apply Contextually)
- After joins: compare row counts before/after to detect fan-out
- Premium should generally be positive (negatives = endorsements/cancellations)
- Loss ratios > 200% are unusual — flag but don't dismiss (cat losses exist)
- Check for NULL key columns after joins — indicates unmatched records
- Verify date ranges and filters make sense
- When summing: check if granularity is correct (don't double-count)

## Important Rules
- ONLY execute SELECT queries. Never INSERT, UPDATE, DELETE, or DDL.
- Always preview complex queries before executing.
- When unsure about table relationships, explore the schema first.
- Explain your reasoning and the SQL logic to the user.
- If results look suspicious, say so and suggest verification steps.
- For large results, suggest Python analysis or Excel export.
- When generating charts, always use matplotlib and save with plt.savefig('chart.png', dpi=150, bbox_inches='tight'). The image will be displayed inline in the chat. Use plt.style.use('dark_background') for consistency with the dark UI.
"""
