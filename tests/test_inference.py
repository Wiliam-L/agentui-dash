"""Fixtures hostiles → JSON esperado.

Red de seguridad de ``inference.py``: por muy sucio que venga el CSV, el
``ui_config.json`` generado debe seguir siendo un dashboard válido y su SQL
debe pasar el allow-list (solo lectura, sin acceso a archivos ni red).

Cada fixture cubre una rama distinta del generador:

* ``ventas_hostil.csv``      → roles de ventas (sucursal/fecha/categoría/monto)
* ``inventario_hostil.csv``  → roles de inventario + columna con comillas dobles
* ``sensores_hostil.csv``    → sin roles conocidos → generador genérico
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app_base.core.data import safe_sql
from app_base.core.inference import _detectar_tipo, _q, generar_ui_config

FIXTURES = Path(__file__).parent / "fixtures"
TABLA = "hostil"

# Valores de las fixtures que jamás deben acabar dentro de una consulta SQL.
VALORES_PELIGROSOS = ("evil.test", "alert(1)", "rm -rf", "OR 1=1", "/C calc")


def _cargar(nombre: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / nombre, encoding="utf-8-sig")


def _sqls(config: dict) -> list[str]:
    """Every SQL string in the config, wherever it lives."""
    consultas: list[str] = []
    for modulo in config["modulos"]:
        for seccion in ("kpis", "graficos", "tablas"):
            for item in modulo.get(seccion) or []:
                if item.get("sql"):
                    consultas.append(item["sql"])
        for filtro in modulo.get("filtros") or []:
            if filtro.get("sql"):
                consultas.append(filtro["sql"])
    for filtro in config.get("filtros_globales") or []:
        if filtro.get("sql"):
            consultas.append(filtro["sql"])
    return consultas


def _validar(config: dict, df: pd.DataFrame) -> list[str]:
    """Assertions shared by every fixture. Returns the generated SQL list."""
    assert config["modulos"], "el dashboard no puede quedar vacío"

    for modulo in config["modulos"]:
        assert modulo.get("id"), f"módulo sin id: {modulo.get('nombre')}"
        assert modulo.get("nombre"), "módulo sin nombre"
        assert modulo.get("kpis") or modulo.get("graficos"), (
            f"el módulo {modulo.get('nombre')!r} no tiene KPIs ni gráficos"
        )

    # Toda columna mapeada debe existir de verdad en el CSV.
    for rol, columna in config.get("column_mapping", {}).items():
        assert columna in df.columns, f"{rol} apunta a una columna inexistente: {columna!r}"

    # Todo SQL generado debe ser de solo lectura y apuntar a la tabla correcta.
    consultas = _sqls(config)
    assert consultas, "el dashboard no generó ninguna consulta"
    for sql in consultas:
        motivo = safe_sql(sql, tablas={TABLA})
        assert motivo is None, f"{motivo}\nSQL: {sql}"
        assert TABLA in sql, f"SQL sin tabla {TABLA!r}: {sql}"

    # Los datos del CSV nunca se interpolan en el SQL.
    texto = " ".join(consultas)
    for valor in VALORES_PELIGROSOS:
        assert valor not in texto, f"valor del CSV interpolado en SQL: {valor!r}"

    return consultas


# --------------------------------------------------------------------------- #
# Fixture 1 — ventas (rama especializada)
# --------------------------------------------------------------------------- #
def test_ventas_hostil_genera_dashboard_valido():
    df = _cargar("ventas_hostil.csv")
    assert _detectar_tipo(df) == "sales"

    config = generar_ui_config(df, table_name=TABLA)
    consultas = _validar(config, df)

    assert config["column_mapping"]["sales_sucursal"] == "Sucursal"
    assert any("SUM(" in sql for sql in consultas)
    # Los filtros globales deben apuntar a columnas reales del CSV.
    for filtro in config["filtros_globales"]:
        assert filtro["columna"] in df.columns
        assert filtro["tabla"] == TABLA


# --------------------------------------------------------------------------- #
# Fixture 2 — inventario (rama especializada + identificadores con comillas)
# --------------------------------------------------------------------------- #
def test_inventario_hostil_escapa_comillas_en_identificadores():
    df = _cargar("inventario_hostil.csv")
    assert _detectar_tipo(df) == "inventory"
    assert 'Categoría "Interna"' in df.columns

    config = generar_ui_config(df, table_name=TABLA)
    _validar(config, df)

    # _q debe duplicar las comillas dobles para producir un identificador válido.
    assert _q('Categoría "Interna"') == '"Categoría ""Interna"""'
    assert '""' in _q('a"b')


# --------------------------------------------------------------------------- #
# Fixture 3 — sin roles conocidos (generador genérico)
# --------------------------------------------------------------------------- #
def test_csv_sin_roles_conocidos_genera_modulo_generico():
    df = _cargar("sensores_hostil.csv")
    assert _detectar_tipo(df) is None

    config = generar_ui_config(df, table_name=TABLA)
    consultas = _validar(config, df)

    # La columna hostil se cita como identificador, no se ejecuta.
    assert any('"temperatura; DROP TABLE x"' in sql for sql in consultas)
    assert any("COUNT(*)" in sql for sql in consultas)


# --------------------------------------------------------------------------- #
# Allow-list
# --------------------------------------------------------------------------- #
def test_query_valido_con_parametros_nombrados():
    sql = 'SELECT "branch" FROM hostil WHERE "branch" = $f_branch'
    assert safe_sql(sql, tablas={TABLA}) is None


def test_cte_valido():
    sql = "WITH t AS (SELECT * FROM hostil) SELECT * FROM t"
    assert safe_sql(sql, tablas={TABLA}) is None


@pytest.mark.parametrize(
    "sql",
    ["DESCRIBE hostil", 'SELECT "Sucursal" FROM main.hostil LIMIT 1'],
)
def test_lecturas_de_metadatos_permitidas(sql: str):
    assert safe_sql(sql, tablas={TABLA}) is None


def test_tabla_inexistente_se_bloquea_aunque_haya_otra_valida():
    sql = "SELECT * FROM hostil JOIN otra_tabla ON 1 = 1"
    assert safe_sql(sql, tablas={TABLA}) is not None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('C:/Users/wlope/.env')",
        "SELECT * FROM read_csv('https://attacker.test/?x=1')",
        "SELECT * FROM read_parquet('C:/secrets.parquet')",
        "SELECT * FROM glob('C:/**/*.env')",
        "SELECT * FROM query('SELECT 1')",
        "ATTACH 'x.db' AS y",
        "COPY hostil TO 'x.csv'",
        "PRAGMA database_list",
        "INSTALL httpfs",
        "INSERT INTO hostil VALUES (1)",
        "DELETE FROM hostil",
        "SELECT 1; DROP TABLE hostil",
        "SELECT * FROM otra_base.tabla",
        "SELECT * FROM tabla_inexistente",
    ],
)
def test_safe_sql_bloquea_ataques(sql: str):
    assert safe_sql(sql, tablas={TABLA}) is not None


def test_el_config_actual_de_la_ui_pasa_el_allow_list():
    """El ui_config.json del repo (escrito por el agente) debe ser ejecutable."""
    ruta = Path(__file__).parent.parent / "app_base" / "ui_config.json"
    if not ruta.exists():
        pytest.skip("no hay ui_config.json en este checkout")

    config = json.loads(ruta.read_text(encoding="utf-8-sig"))
    tablas = {f["tabla"] for f in config.get("filtros_globales", []) if f.get("tabla")}
    assert tablas, "el config no declara ninguna tabla"

    for sql in _sqls(config):
        motivo = safe_sql(sql, tablas=tablas)
        assert motivo is None, f"{motivo}\nSQL: {sql}"
