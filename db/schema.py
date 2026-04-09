from typing import Optional
from db.connection import OracleConnection


class SchemaDiscovery:
    """Auto-discovers Oracle table schemas, columns, constraints, and relationships."""

    def __init__(self, conn: OracleConnection):
        self.conn = conn
        self._cache: dict = {}

    def discover_tables(self, schema: Optional[str] = None) -> list[dict]:
        owner_clause = f"WHERE OWNER = :schema" if schema else "WHERE OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
        params = {"schema": schema.upper()} if schema else {}
        sql = f"""
            SELECT OWNER, TABLE_NAME, NUM_ROWS, LAST_ANALYZED
            FROM ALL_TABLES
            {owner_clause}
            ORDER BY TABLE_NAME
        """
        result = self.conn.execute(sql, params)
        tables = []
        for row in result["rows"]:
            tables.append({
                "owner": row[0],
                "table_name": row[1],
                "num_rows": row[2],
                "last_analyzed": str(row[3]) if row[3] else None,
            })
        return tables

    def describe_table(self, table_name: str, schema: Optional[str] = None) -> dict:
        cache_key = f"{schema or ''}.{table_name}".upper()
        if cache_key in self._cache:
            return self._cache[cache_key]

        owner_clause = "AND OWNER = :schema" if schema else "AND OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
        params = {"table_name": table_name.upper()}
        if schema:
            params["schema"] = schema.upper()

        # Get columns
        col_sql = f"""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE,
                   NULLABLE, DATA_DEFAULT, COLUMN_ID
            FROM ALL_TAB_COLUMNS
            WHERE TABLE_NAME = :table_name {owner_clause}
            ORDER BY COLUMN_ID
        """
        col_result = self.conn.execute(col_sql, params)
        columns = []
        for row in col_result["rows"]:
            columns.append({
                "name": row[0],
                "type": row[1],
                "length": row[2],
                "precision": row[3],
                "scale": row[4],
                "nullable": row[5] == "Y",
                "default": str(row[6]).strip() if row[6] else None,
            })

        # Get primary key
        pk_sql = f"""
            SELECT cols.COLUMN_NAME
            FROM ALL_CONSTRAINTS cons
            JOIN ALL_CONS_COLUMNS cols ON cons.CONSTRAINT_NAME = cols.CONSTRAINT_NAME
                AND cons.OWNER = cols.OWNER
            WHERE cons.TABLE_NAME = :table_name
              AND cons.CONSTRAINT_TYPE = 'P'
              {owner_clause}
            ORDER BY cols.POSITION
        """
        pk_result = self.conn.execute(pk_sql, params)
        primary_keys = [row[0] for row in pk_result["rows"]]

        # Get foreign keys
        fk_sql = f"""
            SELECT a.COLUMN_NAME, c_pk.TABLE_NAME AS REF_TABLE, b.COLUMN_NAME AS REF_COLUMN
            FROM ALL_CONS_COLUMNS a
            JOIN ALL_CONSTRAINTS c ON a.CONSTRAINT_NAME = c.CONSTRAINT_NAME AND a.OWNER = c.OWNER
            JOIN ALL_CONSTRAINTS c_pk ON c.R_CONSTRAINT_NAME = c_pk.CONSTRAINT_NAME AND c.R_OWNER = c_pk.OWNER
            JOIN ALL_CONS_COLUMNS b ON c_pk.CONSTRAINT_NAME = b.CONSTRAINT_NAME
                AND c_pk.OWNER = b.OWNER AND a.POSITION = b.POSITION
            WHERE c.TABLE_NAME = :table_name
              AND c.CONSTRAINT_TYPE = 'R'
              {owner_clause}
            ORDER BY a.COLUMN_NAME
        """
        fk_result = self.conn.execute(fk_sql, params)
        foreign_keys = []
        for row in fk_result["rows"]:
            foreign_keys.append({
                "column": row[0],
                "ref_table": row[1],
                "ref_column": row[2],
            })

        # Get indexes
        idx_sql = f"""
            SELECT i.INDEX_NAME, ic.COLUMN_NAME, i.UNIQUENESS
            FROM ALL_INDEXES i
            JOIN ALL_IND_COLUMNS ic ON i.INDEX_NAME = ic.INDEX_NAME AND i.OWNER = ic.INDEX_OWNER
            WHERE i.TABLE_NAME = :table_name
              {owner_clause.replace('OWNER', 'i.OWNER')}
            ORDER BY i.INDEX_NAME, ic.COLUMN_POSITION
        """
        idx_result = self.conn.execute(idx_sql, params)
        indexes = {}
        for row in idx_result["rows"]:
            idx_name = row[0]
            if idx_name not in indexes:
                indexes[idx_name] = {"columns": [], "unique": row[2] == "UNIQUE"}
            indexes[idx_name]["columns"].append(row[1])

        info = {
            "table_name": table_name.upper(),
            "schema": schema.upper() if schema else None,
            "columns": columns,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
            "indexes": list(indexes.values()),
        }
        self._cache[cache_key] = info
        return info

    def find_tables(self, keyword: str, schema: Optional[str] = None) -> list[dict]:
        owner_clause = "AND OWNER = :schema" if schema else "AND OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
        params = {"keyword": f"%{keyword.upper()}%"}
        if schema:
            params["schema"] = schema.upper()

        sql = f"""
            SELECT OWNER, TABLE_NAME, NUM_ROWS
            FROM ALL_TABLES
            WHERE UPPER(TABLE_NAME) LIKE :keyword {owner_clause}
            ORDER BY TABLE_NAME
        """
        result = self.conn.execute(sql, params)
        return [{"owner": r[0], "table_name": r[1], "num_rows": r[2]} for r in result["rows"]]

    def find_columns(self, keyword: str, schema: Optional[str] = None) -> list[dict]:
        owner_clause = "AND OWNER = :schema" if schema else "AND OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
        params = {"keyword": f"%{keyword.upper()}%"}
        if schema:
            params["schema"] = schema.upper()

        sql = f"""
            SELECT OWNER, TABLE_NAME, COLUMN_NAME, DATA_TYPE
            FROM ALL_TAB_COLUMNS
            WHERE UPPER(COLUMN_NAME) LIKE :keyword {owner_clause}
            ORDER BY TABLE_NAME, COLUMN_NAME
        """
        result = self.conn.execute(sql, params)
        return [{"owner": r[0], "table_name": r[1], "column": r[2], "type": r[3]} for r in result["rows"]]

    def get_table_comments(self, table_name: str, schema: Optional[str] = None) -> dict:
        owner_clause = "AND OWNER = :schema" if schema else "AND OWNER = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')"
        params = {"table_name": table_name.upper()}
        if schema:
            params["schema"] = schema.upper()

        tab_sql = f"""
            SELECT COMMENTS FROM ALL_TAB_COMMENTS
            WHERE TABLE_NAME = :table_name {owner_clause}
        """
        tab_result = self.conn.execute(tab_sql, params)
        table_comment = tab_result["rows"][0][0] if tab_result["rows"] else None

        col_sql = f"""
            SELECT COLUMN_NAME, COMMENTS FROM ALL_COL_COMMENTS
            WHERE TABLE_NAME = :table_name {owner_clause} AND COMMENTS IS NOT NULL
        """
        col_result = self.conn.execute(col_sql, params)
        col_comments = {r[0]: r[1] for r in col_result["rows"]}

        return {"table_comment": table_comment, "column_comments": col_comments}
