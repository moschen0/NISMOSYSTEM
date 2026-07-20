"""
Blueprint: Expedição
Fluxo: Checkin de Entrada -> Geração de Onda de Picking -> Picking com
Doublecheck -> Embala e Fatura.

Segue o mesmo padrão de blueprint isolado usado por etiquetas_bp.py e
confirmations_bp.py: cada blueprint gerencia suas próprias tabelas/migrações
via db_mdb.get_connection(), evitando alterar db_mdb.py e import circular
com web_app.py.
"""

from __future__ import annotations

import os
import sys
import re
from datetime import datetime
from functools import wraps
from threading import Lock
from typing import Any

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import db_mdb
import json

expedicao_bp = Blueprint("expedicao", __name__, url_prefix="/expedicao")

LOTES_TABLE = "expedicao_lotes"
LOTE_ITEMS_TABLE = "expedicao_lote_items"
ONDAS_TABLE = "expedicao_ondas"
ONDA_LOTES_TABLE = "expedicao_onda_lotes"
PICKING_SCANS_TABLE = "expedicao_picking_scans"

_SCHEMA_LOCK = Lock()
_schema_ready = False


def _get_runtime_data_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


SECTORS_PATH = os.path.join(_get_runtime_data_dir(), "sectors.json")


def _import_integrador_opto():
    """Importa integrador_opto adicionando OPTO_INTEGRATIONS ao sys.path.

    Cópia do helper equivalente em web_app.py (_import_integrador_opto) —
    duplicado aqui para manter o blueprint isolado (sem import circular).
    """
    if getattr(sys, "frozen", False):
        opto_dir = os.path.join(os.path.dirname(sys.executable), "OPTO_INTEGRATIONS")
    else:
        opto_dir = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "OPTO_INTEGRATIONS")
        )
    if opto_dir not in sys.path:
        sys.path.insert(0, opto_dir)
    import importlib
    import integrador_opto as _m  # type: ignore
    return importlib.reload(_m) if _m.__spec__ else _m


def _resolve_client_number_from_txt(order_id: str) -> str | None:
    """Lê o arquivo {order_id}.txt do SIOU e retorna o campo 2 (codigo_cliente).

    O "ID Master" bipado no Checkin é o próprio nome do arquivo .txt (mesmo
    padrão usado em web_app.py::_build_envio_label_data). Retorna None se o
    arquivo não existir ou não puder ser lido — nesse caso o operador deve
    informar o número do cliente manualmente.
    """
    try:
        opto = _import_integrador_opto()
        opto.init_database()
        _txt_path, fields = opto.resolve_txt_fields(order_id)
    except Exception:
        return None
    codigo_cliente = str(fields.get(2, "") or "").strip()
    return codigo_cliente or None


# ---------------------------------------------------------------------------
# Auth & permission helpers (padrão copiado de confirmations_bp.py / etiquetas_bp.py)
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    return session.get("user")


def get_current_unit():
    return session.get("unit", db_mdb.DEFAULT_UNIT)


def get_current_sector():
    return session.get("sector", db_mdb.DEFAULT_SECTOR)


def is_admin():
    return (get_current_user() or "").lower() == "admin"


def can_access_feature(feature: str) -> bool:
    if is_admin():
        return True
    permissions = session.get("permissions", [])
    return feature in permissions if isinstance(permissions, list) else False


@expedicao_bp.before_request
def _check_expedicao_access():
    if request.endpoint and "static" in request.endpoint:
        return
    if "user" not in session:
        flash("Faça login para continuar.", "warning")
        return redirect(url_for("login"))
    if is_admin():
        return
    if can_access_feature("expedicao"):
        return
    flash("Acesso restrito ao setor autorizado para expedição ou admin.", "danger")
    return redirect(url_for("dashboard"))


@expedicao_bp.app_template_global("expedicao_can_access")
def expedicao_can_access(feature: str) -> bool:
    return can_access_feature(feature)


def _first_accessible_expedicao_redirect():
    if can_access_feature("expedicao_checkin"):
        return redirect(url_for("expedicao.checkin_page"))
    if can_access_feature("expedicao_picking"):
        return redirect(url_for("expedicao.picking_page"))
    if can_access_feature("expedicao_doublecheck"):
        return redirect(url_for("expedicao.doublecheck_page"))
    if can_access_feature("expedicao_embalagem"):
        return redirect(url_for("expedicao.embalagem_page"))
    flash("Acesso restrito para os recursos de expedição.", "danger")
    return redirect(url_for("dashboard"))


def _expedicao_feature_required(feature: str):
    """Protege uma rota exigindo uma permissão granular da Expedição."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if can_access_feature(feature):
                return view_func(*args, **kwargs)
            if request.method == "GET":
                flash("Acesso restrito para este recurso de expedição.", "danger")
                return _first_accessible_expedicao_redirect()
            return jsonify({"error": "Acesso restrito para este recurso."}), 403
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# DDL helpers (cópia local do padrão usado em etiquetas_bp.py)
# ---------------------------------------------------------------------------

def _table_exists(cursor: Any, table_name: str) -> bool:
    try:
        cursor.tables(table=table_name, tableType="TABLE")
        return cursor.fetchone() is not None
    except Exception:
        return False


def _run_ddl_on_conn(conn: Any, sql: str) -> None:
    old_autocommit = getattr(conn, "autocommit", False)
    try:
        conn.autocommit = True
        conn.execute(sql)
    finally:
        conn.autocommit = old_autocommit


def _ensure_expedicao_schema(conn: Any) -> None:
    cursor = conn.cursor()

    if not _table_exists(cursor, LOTES_TABLE):
        _run_ddl_on_conn(conn, f"""
            CREATE TABLE {LOTES_TABLE} (
                id COUNTER PRIMARY KEY,
                lote_code TEXT(50),
                seq_number LONG,
                client_number TEXT(50),
                endereco TEXT(100),
                [status] TEXT(30),
                created_by TEXT(100),
                created_at TEXT(50),
                closed_by TEXT(100),
                closed_at TEXT(50),
                confirmed_by TEXT(100),
                confirmed_at TEXT(50),
                embalado_by TEXT(100),
                embalado_at TEXT(50),
                faturado_by TEXT(100),
                faturado_at TEXT(50),
                [unit] TEXT(100),
                [sector] TEXT(50)
            )
        """)

    if not _table_exists(cursor, LOTE_ITEMS_TABLE):
        _run_ddl_on_conn(conn, f"""
            CREATE TABLE {LOTE_ITEMS_TABLE} (
                id COUNTER PRIMARY KEY,
                lote_id LONG,
                order_id TEXT(100),
                scanned_by TEXT(100),
                scanned_at TEXT(50),
                [unit] TEXT(100),
                [sector] TEXT(50)
            )
        """)

    if not _table_exists(cursor, ONDAS_TABLE):
        _run_ddl_on_conn(conn, f"""
            CREATE TABLE {ONDAS_TABLE} (
                id COUNTER PRIMARY KEY,
                horario TEXT(20),
                created_by TEXT(100),
                created_at TEXT(50),
                [status] TEXT(30),
                [unit] TEXT(100),
                [sector] TEXT(50)
            )
        """)

    if not _table_exists(cursor, ONDA_LOTES_TABLE):
        _run_ddl_on_conn(conn, f"""
            CREATE TABLE {ONDA_LOTES_TABLE} (
                id COUNTER PRIMARY KEY,
                onda_id LONG,
                lote_id LONG
            )
        """)

    if not _table_exists(cursor, PICKING_SCANS_TABLE):
        _run_ddl_on_conn(conn, f"""
            CREATE TABLE {PICKING_SCANS_TABLE} (
                id COUNTER PRIMARY KEY,
                lote_id LONG,
                onda_id LONG,
                order_id TEXT(100),
                username TEXT(100),
                result TEXT(20),
                created_at TEXT(50),
                [data] TEXT(20),
                hora TEXT(20),
                [unit] TEXT(100),
                [sector] TEXT(50)
            )
        """)

    conn.commit()


def ensure_database_ready() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _SCHEMA_LOCK:
        if _schema_ready:
            return
        conn = db_mdb.get_connection()
        _ensure_expedicao_schema(conn)
        _schema_ready = True


@expedicao_bp.before_request
def _prepare_database():
    try:
        ensure_database_ready()
    except Exception:
        pass

    # After faturamento, if this lote is part of one or more ondas, check
    # whether all lotes de cada onda já estão faturados. If so, mark a onda
    # como fechada and include closed onda ids in the response.
    closed_ondas = []
    try:
        conn = db_mdb.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT DISTINCT onda_id FROM {ONDA_LOTES_TABLE} WHERE lote_id = ?", (lote_id,))
        rows = cursor.fetchall()
        for row in rows:
            try:
                onda_id = row[0]
                if not onda_id:
                    continue
                lotes = get_onda_lotes(onda_id)
                if not lotes:
                    continue
                all_faturado = all((l.get("status") == "faturado") for l in lotes)
                if all_faturado:
                    update_onda_status(onda_id, "fechada")
                    closed_ondas.append(onda_id)
            except Exception:
                pass
    except Exception:
        pass

    # After faturamento, if this lote is part of one or more ondas, check
    # whether all lotes de cada onda já estão faturados. If so, mark a onda
    # como fechada and include closed onda ids in the response.
    closed_ondas = []
    try:
        conn = db_mdb.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT DISTINCT onda_id FROM {ONDA_LOTES_TABLE} WHERE lote_id = ?", (lote_id,))
        rows = cursor.fetchall()
        for row in rows:
            try:
                onda_id = row[0]
                if not onda_id:
                    continue
                lotes = get_onda_lotes(onda_id)
                if not lotes:
                    continue
                all_faturado = all((l.get("status") == "faturado") for l in lotes)
                if all_faturado:
                    update_onda_status(onda_id, "fechada")
                    closed_ondas.append(onda_id)
            except Exception:
                pass
    except Exception:
        pass

    # After faturamento, if this lote is part of one or more ondas, check
    # whether all lotes de cada onda já estão faturados. If so, mark a onda
    # como fechada and include closed onda ids in the response.
    closed_ondas = []
    try:
        conn = db_mdb.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT DISTINCT onda_id FROM {ONDA_LOTES_TABLE} WHERE lote_id = ?", (lote_id,))
        rows = cursor.fetchall()
        for row in rows:
            try:
                onda_id = row[0]
                if not onda_id:
                    continue
                lotes = get_onda_lotes(onda_id)
                if not lotes:
                    continue
                all_faturado = all((l.get("status") == "faturado") for l in lotes)
                if all_faturado:
                    update_onda_status(onda_id, "fechada")
                    closed_ondas.append(onda_id)
            except Exception:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers de data/hora
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _today_str() -> str:
    return datetime.now().strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# CRUD — Lotes (Checkin de Entrada)
# ---------------------------------------------------------------------------

def get_lote(lote_id):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {LOTES_TABLE} WHERE id = ?", (lote_id,))
    row = cursor.fetchone()
    return db_mdb.dict_from_row(cursor, row)


def get_open_lote_for_client(client_number, unit, sector):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""SELECT TOP 1 * FROM {LOTES_TABLE}
            WHERE client_number = ? AND [status] = 'aberto' AND [unit] = ? AND [sector] = ?
            ORDER BY id DESC""",
        (client_number, unit, sector),
    )
    row = cursor.fetchone()
    return db_mdb.dict_from_row(cursor, row)


def _next_seq_number(unit, sector):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    today = _today_str()
    cursor.execute(
        f"SELECT MAX(seq_number) FROM {LOTES_TABLE} WHERE [unit] = ? AND [sector] = ? AND created_at LIKE ?",
        (unit, sector, f"{today}%"),
    )
    row = cursor.fetchone()
    current_max = row[0] if row and row[0] else 0
    return int(current_max) + 1


def create_lote(client_number, unit, sector, created_by):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    seq = _next_seq_number(unit, sector)
    lote_code = f"{seq:03d}-{client_number}-PENDENTE"
    cursor.execute(
        f"""INSERT INTO {LOTES_TABLE}
            (lote_code, seq_number, client_number, endereco, [status], created_by, created_at, [unit], [sector])
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (lote_code, seq, client_number, "", "aberto", created_by, _now_str(), unit, sector),
    )
    conn.commit()
    cursor.execute(f"SELECT MAX(id) FROM {LOTES_TABLE}")
    lote_id = cursor.fetchone()[0]
    return get_lote(lote_id)


def get_or_create_open_lote(client_number, unit, sector, created_by):
    lote = get_open_lote_for_client(client_number, unit, sector)
    if lote:
        return lote
    return create_lote(client_number, unit, sector, created_by)


def get_open_lotes(unit, sector):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT * FROM {LOTES_TABLE} WHERE [status] = 'aberto' AND [unit] = ? AND [sector] = ? ORDER BY id DESC",
        (unit, sector),
    )
    rows = cursor.fetchall()
    return db_mdb.dicts_from_rows(cursor, rows)


def add_lote_item(lote_id, order_id, scanned_by, unit, sector):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""INSERT INTO {LOTE_ITEMS_TABLE} (lote_id, order_id, scanned_by, scanned_at, [unit], [sector])
            VALUES (?, ?, ?, ?, ?, ?)""",
        (lote_id, order_id, scanned_by, _now_str(), unit, sector),
    )
    conn.commit()


def lote_item_exists(lote_id, order_id) -> bool:
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT COUNT(*) FROM {LOTE_ITEMS_TABLE} WHERE lote_id = ? AND order_id = ?",
        (lote_id, order_id),
    )
    row = cursor.fetchone()
    return bool(row and row[0])


def get_lote_items(lote_id):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {LOTE_ITEMS_TABLE} WHERE lote_id = ? ORDER BY id ASC", (lote_id,))
    rows = cursor.fetchall()
    return db_mdb.dicts_from_rows(cursor, rows)


def close_lote(lote_id, endereco, closed_by):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT lote_code FROM {LOTES_TABLE} WHERE id = ?", (lote_id,))
    row = cursor.fetchone()
    lote_code = row[0] if row else ""
    if lote_code and lote_code.endswith("-PENDENTE"):
        lote_code = lote_code.rsplit("-PENDENTE", 1)[0] + f"-{endereco}"
    cursor.execute(
        f"""UPDATE {LOTES_TABLE}
            SET [status] = 'fechado_aguardando_confirmacao', endereco = ?, lote_code = ?,
                closed_by = ?, closed_at = ?
            WHERE id = ?""",
        (endereco, lote_code, closed_by, _now_str(), lote_id),
    )
    conn.commit()


def set_lote_endereco(lote_id, endereco):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT lote_code FROM {LOTES_TABLE} WHERE id = ?", (lote_id,))
    row = cursor.fetchone()
    lote_code = row[0] if row else ""
    if lote_code and lote_code.endswith("-PENDENTE"):
        lote_code = lote_code.rsplit("-PENDENTE", 1)[0] + f"-{endereco}"
    cursor.execute(
        f"UPDATE {LOTES_TABLE} SET endereco = ?, lote_code = ? WHERE id = ?",
        (endereco, lote_code, lote_id),
    )
    conn.commit()


def confirm_lote(lote_id, confirmed_by):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE {LOTES_TABLE} SET [status] = 'armazenado', confirmed_by = ?, confirmed_at = ? WHERE id = ?",
        (confirmed_by, _now_str(), lote_id),
    )
    conn.commit()


def update_lote_status(lote_id, status):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE {LOTES_TABLE} SET [status] = ? WHERE id = ?", (status, lote_id))
    conn.commit()


def update_onda_status(onda_id, status):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE {ONDAS_TABLE} SET [status] = ? WHERE id = ?", (status, onda_id))
    conn.commit()

def mark_embalado(lote_id, username):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE {LOTES_TABLE} SET [status] = 'embalado', embalado_by = ?, embalado_at = ? WHERE id = ?",
        (username, _now_str(), lote_id),
    )
    conn.commit()


def mark_faturado(lote_id, username):
    """Registra o handoff manual para faturamento.

    NOTA: integração real com SISTEMA ACERT / faturamento fica fora de escopo
    (decisão do plano) — apenas timestamp/usuário são gravados aqui.
    """
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE {LOTES_TABLE} SET [status] = 'faturado', faturado_by = ?, faturado_at = ? WHERE id = ?",
        (username, _now_str(), lote_id),
    )
    conn.commit()


def get_lotes_by_statuses(statuses, unit, sector):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    placeholders = ", ".join(["?"] * len(statuses))
    cursor.execute(
        f"""SELECT * FROM {LOTES_TABLE}
            WHERE [status] IN ({placeholders}) AND [unit] = ? AND [sector] = ?
            ORDER BY id DESC""",
        (*statuses, unit, sector),
    )
    rows = cursor.fetchall()
    return db_mdb.dicts_from_rows(cursor, rows)


def _finalize_order_position(order_id, position, unit, sector):
    """Atualiza a posição final do pedido após confirmação do endereçamento do lote."""
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE orders SET position = ? WHERE order_id = ? AND [unit] = ? AND [sector] = ?",
        (position, order_id, unit, sector),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# etiq_clients lookup (identifica clientes vinculados a um horário de onda)
# ---------------------------------------------------------------------------

def get_distinct_horarios():
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    # Use the labels clients table (`etiq_clients`) and the `horario_roteiro` column
    # (this is the same source used by the etiquetas system when generating labels).
    cursor.execute(
        "SELECT DISTINCT horario_roteiro FROM etiq_clients "
        "WHERE horario_roteiro IS NOT NULL AND horario_roteiro <> ''"
    )
    # Return a curated default list of horarios used by the UI for generating
    # picking waves. This list is intentionally fixed (only these slots
    # should appear in the UI regardless of the DB contents).
    default_slots = [
        "08:30",
        "10:00",
        "14:00",
        "14:30",
        "16:00",
        "17:00",
        "18:00",
    ]
    return default_slots


def get_clients_by_horario(horario):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    # Return client numbers from the labels table matching the given horario_roteiro
    cursor.execute(
        "SELECT DISTINCT numero_cliente FROM etiq_clients WHERE horario_roteiro = ?",
        (horario,),
    )
    return [str(row[0]) for row in cursor.fetchall() if row[0] is not None]


# ---------------------------------------------------------------------------
# CRUD — Ondas de Picking
# ---------------------------------------------------------------------------

def create_onda(horario, unit, sector, created_by):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""INSERT INTO {ONDAS_TABLE} (horario, created_by, created_at, [status], [unit], [sector])
            VALUES (?, ?, ?, ?, ?, ?)""",
        (horario, created_by, _now_str(), "aberta", unit, sector),
    )
    conn.commit()
    cursor.execute(f"SELECT MAX(id) FROM {ONDAS_TABLE}")
    onda_id = cursor.fetchone()[0]
    return get_onda(onda_id)


def get_onda(onda_id):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {ONDAS_TABLE} WHERE id = ?", (onda_id,))
    row = cursor.fetchone()
    return db_mdb.dict_from_row(cursor, row)


def get_ondas(unit, sector):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT * FROM {ONDAS_TABLE} WHERE [unit] = ? AND [sector] = ? ORDER BY id DESC",
        (unit, sector),
    )
    rows = cursor.fetchall()
    return db_mdb.dicts_from_rows(cursor, rows)


def link_lote_to_onda(onda_id, lote_id):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"INSERT INTO {ONDA_LOTES_TABLE} (onda_id, lote_id) VALUES (?, ?)",
        (onda_id, lote_id),
    )
    conn.commit()


def get_onda_lotes(onda_id):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""SELECT l.* FROM {LOTES_TABLE} l
            INNER JOIN {ONDA_LOTES_TABLE} ol ON ol.lote_id = l.id
            WHERE ol.onda_id = ? ORDER BY l.id ASC""",
        (onda_id,),
    )
    rows = cursor.fetchall()
    return db_mdb.dicts_from_rows(cursor, rows)


def get_lotes_armazenados_by_clients(client_numbers, unit, sector):
    if not client_numbers:
        return []
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    placeholders = ", ".join(["?"] * len(client_numbers))
    cursor.execute(
        f"""SELECT * FROM {LOTES_TABLE}
            WHERE [status] = 'armazenado' AND client_number IN ({placeholders})
            AND [unit] = ? AND [sector] = ? ORDER BY id ASC""",
        (*client_numbers, unit, sector),
    )
    rows = cursor.fetchall()
    return db_mdb.dicts_from_rows(cursor, rows)


# ---------------------------------------------------------------------------
# Histórico de Ondas (UI)
# ---------------------------------------------------------------------------


@expedicao_bp.route("/ondas/historico", methods=["GET"])
@login_required
@_expedicao_feature_required("expedicao_ondas_historico")
def ondas_historico_page():
    unit = get_current_unit()
    sector = get_current_sector()
    ondas = get_ondas(unit, sector)
    # enrich ondas with lotes, items and summary
    for onda in ondas:
        lotes = get_onda_lotes(onda.get("id")) or []
        for lote in lotes:
            lote_items = get_lote_items(lote.get("id")) or []
            lote["items"] = lote_items
            lote["progress"] = get_lote_picking_progress(lote.get("id"))
            lote["missing_items"] = []
            lote["invalid_scans"] = []
        onda["lotes"] = lotes
        total_lotes = len(lotes)
        total_items = sum(len(l.get("items") or []) for l in lotes)
        confirmed = sum(int(l.get("progress", {}).get("confirmed") or 0) for l in lotes)
        missing = sum(int(l.get("progress", {}).get("missing") or 0) for l in lotes)
        onda["summary"] = {
            "total_lotes": total_lotes,
            "total_items": total_items,
            "confirmed": confirmed,
            "missing": missing,
            "sent_with_missing_count": 0,
        }

    return render_template("expedicao_ondas_historico.html", ondas=ondas, onda_id=None)


# ---------------------------------------------------------------------------
# CRUD — Picking com Doublecheck
# ---------------------------------------------------------------------------

def add_picking_scan(lote_id, onda_id, order_id, username, result, unit, sector):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute(
        f"""INSERT INTO {PICKING_SCANS_TABLE}
            (lote_id, onda_id, order_id, username, result, created_at, [data], hora, [unit], [sector])
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (lote_id, onda_id, order_id, username, result, _now_str(),
         now.strftime("%d/%m/%Y"), now.strftime("%H:%M:%S"), unit, sector),
    )
    conn.commit()


def picking_scan_exists_ok(lote_id, order_id) -> bool:
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT COUNT(*) FROM {PICKING_SCANS_TABLE} WHERE lote_id = ? AND order_id = ? AND result = 'ok'",
        (lote_id, order_id),
    )
    row = cursor.fetchone()
    return bool(row and row[0])


def get_lote_picking_progress(lote_id):
    conn = db_mdb.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {LOTE_ITEMS_TABLE} WHERE lote_id = ?", (lote_id,))
    total = cursor.fetchone()[0] or 0
    # Jet/ACE SQL (Access) nao suporta COUNT(DISTINCT col); usa subquery.
    cursor.execute(
        f"""SELECT COUNT(*) FROM (
                SELECT DISTINCT order_id FROM {PICKING_SCANS_TABLE}
                WHERE lote_id = ? AND result = 'ok'
            ) AS t""",
        (lote_id,),
    )
    confirmed = cursor.fetchone()[0] or 0
    total = int(total)
    confirmed = int(confirmed)
    return {"total": total, "confirmed": confirmed, "missing": max(total - confirmed, 0)}


# ---------------------------------------------------------------------------
# Rotas — Index
# ---------------------------------------------------------------------------

@expedicao_bp.route("/", methods=["GET"])
@login_required
def index():
    return _first_accessible_expedicao_redirect()


# ---------------------------------------------------------------------------
# Rotas — Checkin de Entrada
# ---------------------------------------------------------------------------

@expedicao_bp.route("/checkin", methods=["GET"])
@login_required
@_expedicao_feature_required("expedicao_checkin")
def checkin_page():
    unit = get_current_unit()
    sector = get_current_sector()
    open_lotes = get_open_lotes(unit, sector)
    pending_lotes = get_lotes_by_statuses(["fechado_aguardando_confirmacao"], unit, sector)
    for lote in open_lotes:
        lote["items"] = get_lote_items(lote["id"])
    for lote in pending_lotes:
        lote["items"] = get_lote_items(lote["id"])
    horarios = get_distinct_horarios()
    return render_template(
        "expedicao_checkin.html",
        username=get_current_user(),
        open_lotes=open_lotes,
        pending_lotes=pending_lotes,
        horarios=horarios,
    )


@expedicao_bp.route("/api/checkin/scan", methods=["POST"])
@login_required
@_expedicao_feature_required("expedicao_checkin")
def api_checkin_scan():
    data = request.get_json(force=True, silent=True) or {}
    order_id = str(data.get("order_id", "")).strip()
    client_number_input = str(data.get("client_number", "")).strip()
    if not order_id:
        return jsonify({"error": "Informe o ID Master."}), 400

    unit = get_current_unit()
    sector = get_current_sector()
    user = get_current_user()

    # Fonte da verdade do client_number: arquivo {order_id}.txt do SIOU
    # (campo 2 = codigo_cliente). Sem cache — relido a cada bipagem.
    client_number = _resolve_client_number_from_txt(order_id)
    if not client_number:
        if not client_number_input:
            return jsonify({
                "error": "Arquivo do SIOU não encontrado para este ID Master. Informe o número do cliente para continuar.",
                "needs_client_number": True,
            }), 404
        client_number = client_number_input

    order = db_mdb.get_order_by_id(order_id, unit=unit, sector=sector)
    if not order:
        db_mdb.add_order(
            position="PENDENTE",
            order_id=order_id,
            box=client_number,
            date=_now_str(),
            timestamp=_now_str(),
            created_by=user,
            status="add",
            unit=unit,
            sector=sector,
        )

    lote = get_or_create_open_lote(client_number, unit, sector, user)
    if lote_item_exists(lote["id"], order_id):
        return jsonify({"error": "Este ID Master já foi lido neste lote."}), 409

    add_lote_item(lote["id"], order_id, user, unit, sector)
    lote = get_lote(lote["id"])
    # Compute the suggested endereco and persist it so the lote is shown with
    # its address immediately after the first scan.
    suggested_endereco = None
    try:
        if not (lote.get('endereco')):
            # Find shelf level linked to this client and choose a free position on it
            position_counts = db_mdb.count_all_orders_in_positions(unit=unit, sector=sector)
            for shelf in db_mdb.get_all_shelves(unit=unit, sector=sector):
                try:
                    level_clients = json.loads(shelf.get('level_clients') or '{}')
                except Exception:
                    level_clients = {}
                if not isinstance(level_clients, dict):
                    continue
                levels = int(shelf.get('levels') or 1)
                columns = int(shelf.get('columns') or 1)
                slots = int(shelf.get('slots') or 7)
                zone = shelf.get('zone')
                module = str(shelf.get('module') or '').zfill(2)
                for level_key, linked_client in level_clients.items():
                    if linked_client != str(client_number):
                        continue
                    # generate positions for this shelf (levels desc, columns asc)
                    try:
                        lvl_num = int(level_key)
                    except Exception:
                        lvl_num = None
                    positions = []
                    if columns == 1:
                        positions.append(f"{zone}-{module}-{int(level_key):02d}")
                    else:
                        for col in range(1, columns + 1):
                            positions.append(f"{zone}-{module}-{int(level_key):02d}-{col:02d}")

                    # pick first position with available slot
                    for pos in positions:
                        count = position_counts.get(pos, 0)
                        if count < slots:
                            suggested_endereco = pos
                            break
                    if suggested_endereco:
                        break
                if suggested_endereco:
                    break
    except Exception:
        suggested_endereco = None
    if suggested_endereco and not (lote.get("endereco")):
        set_lote_endereco(lote["id"], suggested_endereco)
        lote = get_lote(lote["id"])
    items = get_lote_items(lote["id"])
    return jsonify({"success": True, "lote": lote, "items": items, "suggested_endereco": suggested_endereco})


@expedicao_bp.route("/api/checkin/fechar", methods=["POST"])
@login_required
@_expedicao_feature_required("expedicao_checkin")
def api_checkin_fechar():
    data = request.get_json(force=True, silent=True) or {}
    lote_id = data.get("lote_id")
    endereco = str(data.get("endereco", "")).strip()
    if not lote_id or not endereco:
        return jsonify({"error": "Informe o endereçamento para fechar o lote."}), 400

    lote = get_lote(lote_id)
    if not lote or lote.get("status") != "aberto":
        return jsonify({"error": "Lote não encontrado ou já fechado."}), 404

    # Close lote (keep existing status workflow)
    close_lote(lote_id, endereco, get_current_user())

    # After closing, finalize orders' positions so IDs are placed in the WMS
    try:
        unit = get_current_unit()
        sector = get_current_sector()
        for item in get_lote_items(lote_id):
            _finalize_order_position(item["order_id"], endereco, unit, sector)
    except Exception:
        # non-fatal; closing succeeded but finalization failed
        pass

    return jsonify({"success": True, "lote": get_lote(lote_id)})


@expedicao_bp.route("/checkin/guia/<int:lote_id>", methods=["GET"])
@login_required
@_expedicao_feature_required("expedicao_checkin")
def checkin_guia(lote_id):
    lote = get_lote(lote_id)
    if not lote:
        flash("Lote não encontrado.", "danger")
        return redirect(url_for("expedicao.checkin_page"))
    items = get_lote_items(lote_id)
    return render_template("expedicao_guia_print.html", lote=lote, items=items)


@expedicao_bp.route("/api/checkin/confirmar", methods=["POST"])
@login_required
@_expedicao_feature_required("expedicao_checkin")
def api_checkin_confirmar():
    data = request.get_json(force=True, silent=True) or {}
    lote_id = data.get("lote_id")
    lote = get_lote(lote_id)
    if not lote or lote.get("status") != "fechado_aguardando_confirmacao":
        return jsonify({"error": "Lote não encontrado ou não está aguardando confirmação."}), 404

    unit = get_current_unit()
    sector = get_current_sector()
    confirm_lote(lote_id, get_current_user())

    for item in get_lote_items(lote_id):
        _finalize_order_position(item["order_id"], lote.get("endereco") or "", unit, sector)

    return jsonify({"success": True, "lote": get_lote(lote_id)})


# ---------------------------------------------------------------------------
# Rotas — Geração de Onda de Picking
# ---------------------------------------------------------------------------

@expedicao_bp.route("/picking", methods=["GET"])
@login_required
@_expedicao_feature_required("expedicao_picking")
def picking_page():
    unit = get_current_unit()
    sector = get_current_sector()
    horarios = get_distinct_horarios()
    ondas = get_ondas(unit, sector)
    # If a horario query param is provided, generate the onda immediately and redirect
    horario_q = request.args.get('horario', '').strip()
    if horario_q:
        user = get_current_user()
        client_numbers = get_clients_by_horario(horario_q)
        lotes = get_lotes_armazenados_by_clients(client_numbers, unit, sector)
        if lotes:
            onda = create_onda(horario_q, unit, sector, user)
            for lote in lotes:
                link_lote_to_onda(onda["id"], lote["id"])
                update_lote_status(lote["id"], "em_onda")
            return redirect(url_for('expedicao.picking_onda_detail', onda_id=onda["id"]))
        else:
            flash("Nenhum lote armazenado encontrado para os clientes deste horário.", "warning")
            return redirect(url_for('expedicao.picking_page'))

    return render_template("expedicao_picking.html", horarios=horarios, ondas=ondas)


@expedicao_bp.route("/api/picking/horarios", methods=["GET"])
@login_required
def api_picking_horarios():
    """Return distinct horarios from etiq_clients as JSON."""
    horarios = get_distinct_horarios()
    return jsonify({"horarios": horarios})


@expedicao_bp.route("/api/picking/lotes", methods=["GET"])
@login_required
def api_picking_lotes():
    """Return stored lotes for clients in the given horario (query param `horario`)."""
    horario = request.args.get("horario", "").strip()
    if not horario:
        return jsonify({"error": "Informe o horário."}), 400
    unit = get_current_unit()
    sector = get_current_sector()
    client_numbers = get_clients_by_horario(horario)
    lotes = get_lotes_armazenados_by_clients(client_numbers, unit, sector)
    return jsonify({"lotes": lotes})


@expedicao_bp.route("/api/picking/gerar-onda", methods=["POST"])
@login_required
@_expedicao_feature_required("expedicao_picking")
def api_gerar_onda():
    data = request.get_json(force=True, silent=True) or {}
    horario = str(data.get("horario", "")).strip()
    if not horario:
        return jsonify({"error": "Selecione um horário."}), 400

    unit = get_current_unit()
    sector = get_current_sector()
    user = get_current_user()

    client_numbers = get_clients_by_horario(horario)
    lotes = get_lotes_armazenados_by_clients(client_numbers, unit, sector)
    if not lotes:
        return jsonify({"error": "Nenhum lote armazenado encontrado para os clientes deste horário."}), 404

    onda = create_onda(horario, unit, sector, user)
    for lote in lotes:
        link_lote_to_onda(onda["id"], lote["id"])
        update_lote_status(lote["id"], "em_onda")

    return jsonify({"success": True, "onda": onda, "lotes": get_onda_lotes(onda["id"])})


@expedicao_bp.route("/picking/onda/<int:onda_id>", methods=["GET"])
@login_required
@_expedicao_feature_required("expedicao_picking")
def picking_onda_detail(onda_id):
    unit = get_current_unit()
    sector = get_current_sector()
    onda = get_onda(onda_id)
    if not onda:
        flash("Onda não encontrada.", "danger")
        return redirect(url_for("expedicao.picking_page"))
    return render_template(
        "expedicao_picking.html",
        horarios=get_distinct_horarios(),
        ondas=get_ondas(unit, sector),
        onda_atual=onda,
        onda_lotes=get_onda_lotes(onda_id),
    )


@expedicao_bp.route("/picking/onda/<int:onda_id>/lote/<int:lote_id>/selecionar", methods=["POST"])
@login_required
@_expedicao_feature_required("expedicao_picking")
def picking_select_lote(onda_id, lote_id):
    onda = get_onda(onda_id)
    if not onda:
        flash("Onda não encontrada.", "danger")
        return redirect(url_for("expedicao.picking_page"))
    if onda.get("status") == "fechada":
        flash("Esta onda já está fechada e não pode ser utilizada.", "warning")
        return redirect(url_for("expedicao.picking_page"))
    return redirect(url_for("expedicao.doublecheck_page", lote_id=lote_id, onda_id=onda_id))


# ---------------------------------------------------------------------------
# Rotas — Picking com Doublecheck
# ---------------------------------------------------------------------------

@expedicao_bp.route("/label-preview", methods=["GET"])
@login_required
@_expedicao_feature_required("expedicao_doublecheck")
def expedicao_label_preview_page():
    """Página de prévia da etiqueta de expedição (expedicao_label_100x150.html).
    Acessível a quem tem permissão de doublecheck."""
    cliente_codigo = str(request.args.get("cliente_codigo", "")).strip()
    cliente_data = _fetch_expedicao_label_client(cliente_codigo)
    cliente_nome = cliente_data.get("cliente_nome", request.args.get("cliente_nome", ""))
    cliente_endereco = cliente_data.get("cliente_endereco", request.args.get("cliente_endereco", ""))
    embalado_by = request.args.get("embalado_by") or request.args.get("enviado_por") or session.get("user", "")
    embalado_at = request.args.get("embalado_at") or request.args.get("data_envio", "")
    return render_template(
        "etiq/expedicao_label_100x150.html",
        cliente_nome=cliente_nome,
        cliente_codigo=cliente_codigo,
        cliente_endereco=cliente_endereco,
        embalado_by=embalado_by,
        embalado_at=embalado_at,
    )


@expedicao_bp.route("/doublecheck", methods=["GET"])
@login_required
@_expedicao_feature_required("expedicao_doublecheck")
def doublecheck_page():
    lote_id = request.args.get("lote_id", type=int)
    onda_id = request.args.get("onda_id", type=int)
    lote = get_lote(lote_id) if lote_id else None
    progress = get_lote_picking_progress(lote_id) if lote_id else None
    return render_template(
        "expedicao_doublecheck.html",
        lote=lote,
        onda_id=onda_id,
        progress=progress,
    )


@expedicao_bp.route("/api/doublecheck/scan", methods=["POST"])
@login_required
@_expedicao_feature_required("expedicao_doublecheck")
def api_doublecheck_scan():
    data = request.get_json(force=True, silent=True) or {}
    lote_id = data.get("lote_id")
    onda_id = data.get("onda_id")
    order_id = str(data.get("order_id", "")).strip()
    if not lote_id or not order_id:
        return jsonify({"error": "Informe o lote e o ID bipado."}), 400

    unit = get_current_unit()
    sector = get_current_sector()
    user = get_current_user()

    if picking_scan_exists_ok(lote_id, order_id):
        return jsonify({"error": "Este ID já foi bipado e confirmado neste lote."}), 409

    belongs = lote_item_exists(lote_id, order_id)
    result = "ok" if belongs else "nao_pertence"
    add_picking_scan(lote_id, onda_id, order_id, user, result, unit, sector)
    progress = get_lote_picking_progress(lote_id)

    if not belongs:
        return jsonify({
            "success": False,
            "result": result,
            "message": "ID bipado não pertence a este lote.",
            "progress": progress,
        }), 200

    return jsonify({"success": True, "result": result, "progress": progress})


def _user_matches_current_sector(user_sector: str, current_sector: str) -> bool:
    user_sector = str(user_sector or "").strip().upper()
    current_sector = str(current_sector or "").strip().upper()
    if not current_sector:
        return False
    if not user_sector:
        return False
    if user_sector == "ALL":
        return True
    sectors = [part.strip().upper() for part in re.split(r"[;,|/]", user_sector) if part.strip()]
    return current_sector in sectors or user_sector == current_sector


def _parse_user_sectors(user_sector: str) -> list[str]:
    cleaned = str(user_sector or "").strip().upper()
    if not cleaned:
        return []
    if cleaned == "ALL":
        return ["ALL"]
    return [part.strip().upper() for part in re.split(r"[;,|/]", cleaned) if part.strip()]


def _load_sector_permissions() -> dict[str, set[str]]:
    try:
        with open(SECTORS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    parsed: dict[str, set[str]] = {}
    for sector_name, sector in raw.items():
        if not isinstance(sector_name, str) or not isinstance(sector, dict):
            continue
        permissions = sector.get("permissions", [])
        if isinstance(permissions, list):
            parsed[sector_name.strip().upper()] = {
                str(permission).strip()
                for permission in permissions
                if str(permission).strip()
            }
    return parsed


def _user_has_missing_release_permission(user: dict[str, Any]) -> bool:
    if str(user.get("username", "") or "").strip().lower() == "admin":
        return True

    sectors = _parse_user_sectors(user.get("sector", ""))
    if "ALL" in sectors:
        return True
    if not sectors:
        return False

    sector_permissions = _load_sector_permissions()
    if not sector_permissions:
        return False

    required_permission = "expedicao_doublecheck_autorizar_falta"
    for sector_name in sectors:
        if required_permission in sector_permissions.get(sector_name, set()):
            return True
    return False


def _validate_doublecheck_leader(username: str, password: str) -> tuple[bool, str]:
    username = str(username or "").strip()
    password = str(password or "")
    if not username or not password:
        return False, "Informe login e senha do líder."

    unit = get_current_unit()
    search_unit = None if username.lower() == "admin" else unit
    try:
        user = db_mdb.get_user_by_username(username, unit=search_unit)
    except Exception:
        user = None
    if not user:
        return False, "Líder não encontrado ou inválido."

    active_value = user.get("active", 1)
    if str(active_value) in {"0", "False", "false"}:
        return False, "Usuário líder está inativo."

    if not db_mdb.verify_password(password, user.get("password", "")):
        return False, "Senha do líder inválida."

    if username.lower() != "admin":
        if not _user_matches_current_sector(user.get("sector", ""), get_current_sector()):
            return False, "Líder não pertence ao setor atual."
        if not _user_has_missing_release_permission(user):
            return False, "Usuário sem permissão para autorizar finalização com falta."

    return True, "OK"


def _fetch_expedicao_label_client(numero_cliente: str | int) -> dict[str, str]:
    cliente_codigo = str(numero_cliente or "").strip()
    if not cliente_codigo.isdigit():
        return {}

    try:
        conn = db_mdb.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP 1 nome_cliente, endereco, numero, complemento, bairro, cidade, estado, cep, cnpj, cor_roteiro, horario_roteiro, entregador
            FROM etiq_clients
            WHERE numero_cliente = ?
            ORDER BY id DESC
            """,
            (int(cliente_codigo),),
        )
        row = cursor.fetchone()
    except Exception:
        row = None

    if not row:
        return {}

    nome_cliente = str(row[0] or "").strip()
    endereco = str(row[1] or "").strip()
    numero = str(row[2] or "").strip()
    complemento = str(row[3] or "").strip()
    bairro = str(row[4] or "").strip()
    cidade = str(row[5] or "").strip()
    estado = str(row[6] or "").strip()
    cep = str(row[7] or "").strip()
    cnpj = str(row[8] or "").strip()
    cor_roteiro = str(row[9] or "").strip()
    horario_roteiro = str(row[10] or "").strip()
    entregador = str(row[11] or "").strip()

    address_parts = [part for part in [endereco, numero, complemento] if part]
    city_parts = [part for part in [bairro, "/".join([p for p in [cidade, estado] if p]) if (cidade or estado) else ""] if part]
    info_parts = [part for part in [
        cep and f"CEP {cep}",
        cnpj and f"CNPJ {cnpj}",
        cor_roteiro and f"Roteiro {cor_roteiro}",
        horario_roteiro and f"Horário {horario_roteiro}",
        entregador and f"Entregador {entregador}",
    ] if part]

    formatted = " | ".join([part for part in [
        ", ".join(address_parts),
        ", ".join([part for part in city_parts if part]),
        *info_parts,
    ] if part])

    return {
        "cliente_codigo": cliente_codigo,
        "cliente_nome": nome_cliente,
        "cliente_endereco": formatted,
    }


@expedicao_bp.route("/api/doublecheck/finalizar", methods=["POST"])
@login_required
@_expedicao_feature_required("expedicao_doublecheck")
def api_doublecheck_finalizar():
    data = request.get_json(force=True, silent=True) or {}
    lote_id = data.get("lote_id")
    lote = get_lote(lote_id)
    if not lote:
        return jsonify({"error": "Lote não encontrado."}), 404

    progress = get_lote_picking_progress(lote_id)
    status = "separado_completo" if progress["missing"] == 0 else "separado_com_falta"
    if progress["missing"] > 0:
        ok, auth_error = _validate_doublecheck_leader(
            data.get("leader_username", ""),
            data.get("leader_password", ""),
        )
        if not ok:
            return jsonify({"error": auth_error, "progress": progress}), 403
    update_lote_status(lote_id, status)
    response = {"success": True, "status": status, "progress": progress}
    # If the lote was completely separated, provide a quick label URL for the cliente
    if status == "separado_completo":
        try:
            cliente = lote.get("client_number")
            if cliente:
                cliente_codigo = str(cliente).strip()
                cliente_data = _fetch_expedicao_label_client(cliente_codigo)
                response["label_url"] = url_for(
                    "expedicao.expedicao_label_preview_page",
                    cliente_codigo=cliente_codigo,
                    cliente_nome=cliente_data.get("cliente_nome") or db_mdb.get_triage_customer_name_by_code(cliente) or "",
                    cliente_endereco=cliente_data.get("cliente_endereco") or (lote.get("endereco") or ""),
                )
        except Exception:
            pass
        # Also, free the shelf positions for the orders in this lote so they don't keep occupying space
        not_cleared = []
        try:
            unit = get_current_unit()
            sector = get_current_sector()
            for item in get_lote_items(lote_id):
                order_id = item.get("order_id")
                if not order_id:
                    continue
                try:
                    # try clearing position scoped to unit/sector first
                    db_mdb.clear_order_position(order_id, unit=unit, sector=sector)
                except Exception:
                    pass
                # verify; if still present, try clearing without unit/sector (fallback)
                try:
                    order = db_mdb.get_order_by_id(order_id, unit=unit, sector=sector)
                    if order and order.get("position"):
                        try:
                            db_mdb.clear_order_position(order_id)
                        except Exception:
                            pass
                        # re-check
                        order2 = db_mdb.get_order_by_id(order_id)
                        if order2 and order2.get("position"):
                            not_cleared.append(order_id)
                except Exception:
                    not_cleared.append(order_id)
        except Exception:
            # non-fatal overall
            pass
        if not_cleared:
            response["not_cleared_positions"] = not_cleared
    return jsonify(response)


# ---------------------------------------------------------------------------
# Rotas — Embala e Fatura
# ---------------------------------------------------------------------------

@expedicao_bp.route("/embalagem", methods=["GET"])
@login_required
@_expedicao_feature_required("expedicao_embalagem")
def embalagem_page():
    unit = get_current_unit()
    sector = get_current_sector()
    lotes = get_lotes_by_statuses(
        ["separado_completo", "separado_com_falta", "embalado"], unit, sector
    )
    return render_template("expedicao_embalagem.html", lotes=lotes)


@expedicao_bp.route("/api/embalagem/embalar", methods=["POST"])
@login_required
@_expedicao_feature_required("expedicao_embalagem")
def api_embalar():
    data = request.get_json(force=True, silent=True) or {}
    lote_id = data.get("lote_id")
    lote = get_lote(lote_id)
    if not lote or lote.get("status") not in ("separado_completo", "separado_com_falta"):
        return jsonify({"error": "Lote não encontrado ou não está pronto para embalar."}), 404
    mark_embalado(lote_id, get_current_user())
    # After embalagem, free shelf positions for orders in this lote
    not_cleared = []
    try:
        unit = get_current_unit()
        sector = get_current_sector()
        for item in get_lote_items(lote_id):
            order_id = item.get("order_id")
            if not order_id:
                continue
            try:
                db_mdb.clear_order_position(order_id, unit=unit, sector=sector)
            except Exception:
                pass
            try:
                order = db_mdb.get_order_by_id(order_id, unit=unit, sector=sector)
                if order and order.get("position"):
                    try:
                        db_mdb.clear_order_position(order_id)
                    except Exception:
                        pass
                    order2 = db_mdb.get_order_by_id(order_id)
                    if order2 and order2.get("position"):
                        not_cleared.append(order_id)
            except Exception:
                not_cleared.append(order_id)
    except Exception:
        pass

    resp = {"success": True, "lote": get_lote(lote_id)}
    if not_cleared:
        resp["not_cleared_positions"] = not_cleared
    return jsonify(resp)


@expedicao_bp.route("/api/embalagem/faturar", methods=["POST"])
@login_required
@_expedicao_feature_required("expedicao_embalagem")
def api_faturar():
    data = request.get_json(force=True, silent=True) or {}
    lote_id = data.get("lote_id")
    lote = get_lote(lote_id)
    if not lote or lote.get("status") != "embalado":
        return jsonify({"error": "Lote não encontrado ou não está embalado."}), 404
    mark_faturado(lote_id, get_current_user())
    # After faturamento, ensure orders positions cleared (defensive)
    not_cleared = []
    try:
        unit = get_current_unit()
        sector = get_current_sector()
        for item in get_lote_items(lote_id):
            order_id = item.get("order_id")
            if not order_id:
                continue
            try:
                db_mdb.clear_order_position(order_id, unit=unit, sector=sector)
            except Exception:
                pass
            try:
                order = db_mdb.get_order_by_id(order_id, unit=unit, sector=sector)
                if order and order.get("position"):
                    try:
                        db_mdb.clear_order_position(order_id)
                    except Exception:
                        pass
                    order2 = db_mdb.get_order_by_id(order_id)
                    if order2 and order2.get("position"):
                        not_cleared.append(order_id)
            except Exception:
                not_cleared.append(order_id)
    except Exception:
        pass

    # After faturamento, if this lote is part of one or more ondas, check
    # whether all lotes de cada onda já estão faturados. If so, mark a onda
    # como fechada and include closed onda ids in the response.
    closed_ondas = []
    try:
        conn = db_mdb.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT DISTINCT onda_id FROM {ONDA_LOTES_TABLE} WHERE lote_id = ?", (lote_id,))
        rows = cursor.fetchall()
        for row in rows:
            try:
                onda_id = row[0]
                if not onda_id:
                    continue
                lotes = get_onda_lotes(onda_id)
                if not lotes:
                    continue
                all_faturado = all((l.get("status") == "faturado") for l in lotes)
                if all_faturado:
                    update_onda_status(onda_id, "fechada")
                    closed_ondas.append(onda_id)
            except Exception:
                pass
    except Exception:
        pass

    resp = {"success": True, "lote": get_lote(lote_id)}
    if not_cleared:
        resp["not_cleared_positions"] = not_cleared
    if closed_ondas:
        resp["ondas_fechadas"] = closed_ondas
    return jsonify(resp)
