import oracledb
from typing import Optional


class OracleConnection:
    """Manages Oracle database connection via TNS names."""

    def __init__(self, dsn: str, user: str, password: str):
        self.dsn = dsn
        self.user = user
        self.password = password
        self._conn: Optional[oracledb.Connection] = None

    def connect(self) -> oracledb.Connection:
        if self._conn is None or not self._is_alive():
            self._conn = oracledb.connect(
                user=self.user,
                password=self.password,
                dsn=self.dsn,
            )
        return self._conn

    def _is_alive(self) -> bool:
        try:
            self._conn.ping()
            return True
        except Exception:
            return False

    def execute(self, sql: str, params: Optional[dict] = None, max_rows: int = 10000):
        conn = self.connect()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or {})
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchmany(max_rows)
                return {"columns": columns, "rows": [list(r) for r in rows], "row_count": len(rows), "truncated": len(rows) == max_rows}
            else:
                conn.commit()
                return {"affected_rows": cursor.rowcount}
        finally:
            cursor.close()

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
