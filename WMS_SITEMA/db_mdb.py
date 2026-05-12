"""
Módulo de acesso ao banco de dados Access MDB para o WMS
Substitui o sistema JSON por banco de dados relacional
"""
try:
    import pyodbc
    _PYODBC_IMPORT_ERROR = None
except Exception as exc:
    pyodbc = None
    _PYODBC_IMPORT_ERROR = exc
import os
import sys
import threading
import re
from functools import lru_cache

# Caminho do banco de dados (prioriza WMS_BD do projeto)
DB_TEST_NETWORK_PATH = r'\\192.168.1.210\WMS Master\WMS CORRETO\DATABASE TESTE\wms_database.mdb'
DB_NETWORK_PATH = r'\\192.168.1.210\WMS Master\WMS CORRETO\DATABASE\wms_database.mdb'


def get_runtime_base_dir():
    """Retorna a pasta base de execucao (script no dev, .exe em producao)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resolve_db_path():
    """Resolve caminho do MDB priorizando a pasta WMS_BD do projeto.

    No modo EXE (PyInstaller 6.x), os dados bundlados ficam em _MEIPASS
    (subpasta _internal/ dentro da pasta do exe).  O banco de rede em
    WMS_BD e o override por variavel de ambiente sempre tem prioridade.
    """
    # Override por variavel de ambiente tem prioridade absoluta.
    env_override = os.environ.get('WMS_MDB_PATH', '').strip()
    if env_override and os.path.exists(env_override):
        return env_override

    runtime_dir = get_runtime_base_dir()

    # Procura WMS_BD subindo niveis a partir da pasta de execucao.
    wms_bd_candidates = []
    current_dir = runtime_dir
    for _ in range(5):
        wms_bd_candidates.append(os.path.join(current_dir, 'WMS_BD', 'wms_database.mdb'))
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir

    runtime_local_db = os.path.join(runtime_dir, 'wms_database.mdb')

    # Quando congelado, PyInstaller 6.x extrai datas em sys._MEIPASS
    # (tipicamente <exe_dir>/_internal/).
    meipass_dir = getattr(sys, '_MEIPASS', None)
    meipass_bd  = os.path.join(meipass_dir, 'WMS_BD', 'wms_database.mdb') if meipass_dir else None

    candidates = [
        *wms_bd_candidates,   # WMS_BD em diferentes niveis da execucao
        meipass_bd,           # arquivo bundlado dentro do _internal do EXE
        runtime_local_db,     # .mdb ao lado do executavel
        DB_TEST_NETWORK_PATH,
        DB_NETWORK_PATH,
    ]

    for path in candidates:
        if path and os.path.exists(path):
            return path

    # Fallback: retorna caminho local ao lado do executavel/script.
    return runtime_local_db


DB_PATH = resolve_db_path()
DEFAULT_UNIT = 'MASTER'
DEFAULT_SECTOR = 'AR'
AVAILABLE_UNITS = ('MASTER', 'WR', 'AMX')
UNIT_ALIASES = {
    'MATRIZ SAO LOURENCO': 'MASTER',
    'SAO LOURENCO': 'MASTER',
    'MATRIZ': 'MASTER',
    'FILIAL WR': 'WR',
}

# Connection pooling por thread para otimizar
_thread_local = threading.local()
_schema_lock = threading.Lock()
_schema_checked = False


def normalize_unit(unit):
    """Padroniza nome da unidade (matriz/filial)."""
    text = str(unit or '').strip().upper()
    text = re.sub(r'\s+', ' ', text)
    if not text:
        return DEFAULT_UNIT
    return UNIT_ALIASES.get(text, text)


def _column_exists(cursor, table_name, column_name):
    """Verifica se uma coluna existe em uma tabela."""
    try:
        cursor.columns(table=table_name, column=column_name)
        row = cursor.fetchone()
        # Esgota o result set para liberar o cursor para próximas operações
        cursor.fetchall()
        return row is not None
    except Exception:
        return False


def _run_ddl_on_conn(conn, sql):
    """Executa DDL no Access via autocommit na conexão existente."""
    old_autocommit = conn.autocommit
    conn.autocommit = True
    try:
        conn.execute(sql)
    finally:
        conn.autocommit = old_autocommit


def _ensure_unit_schema(conn):
    """Garante a coluna [unit] nas tabelas principais e preenche legado."""
    global _schema_checked
    if _schema_checked:
        return

    with _schema_lock:
        if _schema_checked:
            return

        cursor = conn.cursor()
        target_tables = ['users', 'shelves', 'orders', 'movements']

        for table_name in target_tables:
            if not _column_exists(cursor, table_name, 'unit'):
                try:
                    _run_ddl_on_conn(conn, f"ALTER TABLE {table_name} ADD COLUMN [unit] TEXT(100)")
                except Exception as _e:
                    if not _column_exists(cursor, table_name, 'unit'):
                        import logging
                        logging.warning(f"Nao foi possivel adicionar [unit] em {table_name}: {_e}")
                        continue

            try:
                cursor.execute(
                    f"UPDATE {table_name} SET [unit] = ? WHERE [unit] IS NULL OR [unit] = ''",
                    (DEFAULT_UNIT,)
                )
            except Exception:
                pass

            # Migra nomes legados para o nome canonico atual da unidade.
            for alias, canonical in UNIT_ALIASES.items():
                if alias != canonical:
                    try:
                        cursor.execute(
                            f"UPDATE {table_name} SET [unit] = ? WHERE UCASE([unit]) = ?",
                            (canonical, alias)
                        )
                    except Exception:
                        pass

        # Adiciona coluna sector em shelves/orders/movements e migra dados legados para AR
        for table_name in ['shelves', 'orders', 'movements']:
            if not _column_exists(cursor, table_name, 'sector'):
                try:
                    _run_ddl_on_conn(conn, f"ALTER TABLE {table_name} ADD COLUMN [sector] TEXT(50)")
                except Exception as _e:
                    if not _column_exists(cursor, table_name, 'sector'):
                        import logging
                        logging.warning(f"Nao foi possivel adicionar [sector] em {table_name}: {_e}")
                        continue
            try:
                cursor.execute(
                    f"UPDATE {table_name} SET [sector] = ? WHERE [sector] IS NULL OR [sector] = ''",
                    (DEFAULT_SECTOR,)
                )
            except Exception:
                pass

        conn.commit()
        _schema_checked = True


@lru_cache(maxsize=1)
def get_access_driver_name():
    """Resolve o melhor driver ODBC do Access disponível no Windows."""
    installed = [driver.strip() for driver in pyodbc.drivers()]
    if not installed:
        return None

    preferred = [
        'Microsoft Access Driver (*.mdb, *.accdb)',
        'Microsoft Access Driver (*.mdb)',
    ]

    for name in preferred:
        if name in installed:
            return name

    # Fallback: qualquer driver que pareca ser do Access
    for name in installed:
        lowered = name.lower()
        if 'access' in lowered and '.mdb' in lowered:
            return name

    return None

def get_connection():
    """Retorna uma conexão com o banco de dados MDB (reutiliza por thread)"""
    if pyodbc is None:
        raise RuntimeError(
            'O pacote pyodbc nao esta instalado neste ambiente Python. '
            'Instale com "pip install pyodbc" e garanta o driver ODBC do Access. '
            f'Detalhe: {_PYODBC_IMPORT_ERROR}'
        )

    conn = getattr(_thread_local, 'connection', None)

    # Se a conexao foi fechada manualmente em outro ponto do codigo,
    # este ping forca a reconexao e evita erro "connection is closed".
    if conn is not None:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            cursor.fetchone()
            cursor.close()
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _thread_local.connection = None

    driver_name = get_access_driver_name()
    if not driver_name:
        raise RuntimeError(
            'Nenhum driver ODBC do Microsoft Access foi encontrado. '
            'Instale o "Microsoft Access Database Engine" (x64) para usar arquivos .mdb/.accdb.'
        )

    conn_str = f'Driver={{{driver_name}}};DBQ={DB_PATH};'
    try:
        _thread_local.connection = pyodbc.connect(conn_str)
    except pyodbc.Error as exc:
        raise RuntimeError(
            f'Falha ao conectar no banco MDB usando driver "{driver_name}" em "{DB_PATH}". '
            f'Detalhe: {exc}'
        ) from exc
    _ensure_unit_schema(_thread_local.connection)
    return _thread_local.connection

def close_connection():
    """Fecha a conexão da thread atual"""
    if hasattr(_thread_local, 'connection') and _thread_local.connection:
        _thread_local.connection.close()
        _thread_local.connection = None

def dict_from_row(cursor, row):
    """Converte uma linha do banco em dicionário"""
    if row is None:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))

def dicts_from_rows(cursor, rows):
    """Converte múltiplas linhas em lista de dicionários"""
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]

# ============================================================================
# USERS
# ============================================================================

def get_all_users(unit=None):
    """Retorna todos os usuários"""
    conn = get_connection()
    cursor = conn.cursor()
    if unit is not None:
        unit = normalize_unit(unit)
        cursor.execute("SELECT * FROM users WHERE [unit] = ?", (unit,))
    else:
        cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    users = dicts_from_rows(cursor, rows)
    return users

def get_user_by_username(username, unit=None):
    """Retorna um usuário específico"""
    conn = get_connection()
    cursor = conn.cursor()
    if unit is not None:
        unit = normalize_unit(unit)
        cursor.execute("SELECT * FROM users WHERE username = ? AND [unit] = ?", (username, unit))
    else:
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    user = dict_from_row(cursor, row)
    return user

def add_user(username, password, sector="", created_at="", active=True, unit=DEFAULT_UNIT):
    """Adiciona um novo usuário"""
    unit = normalize_unit(unit)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password, sector, created_at, active, [unit]) VALUES (?, ?, ?, ?, ?, ?)",
        (username, password, sector, created_at, 1 if active else 0, unit)
    )
    conn.commit()

def update_user(username, unit=None, **kwargs):
    """Atualiza dados de um usuário"""
    fields = []
    values = []
    for key, value in kwargs.items():
        if key in ['password', 'sector', 'active', 'unit']:
            if key == 'unit':
                value = normalize_unit(value)
            fields.append(f"{key} = ?")
            values.append(value)
    
    if not fields:
        return
    
    values.append(username)
    sql = f"UPDATE users SET {', '.join(fields)} WHERE username = ?"
    if unit is not None:
        unit = normalize_unit(unit)
        sql += " AND [unit] = ?"
        values.append(unit)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, values)
    conn.commit()

def delete_user(username, unit=None):
    """Remove um usuario pelo username."""
    conn = get_connection()
    cursor = conn.cursor()
    if unit is not None:
        unit = normalize_unit(unit)
        cursor.execute("DELETE FROM users WHERE username = ? AND [unit] = ?", (username, unit))
    else:
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()

# ============================================================================
# SHELVES
# ============================================================================

def get_all_shelves(unit=None, sector=None):
    """Retorna todas as prateleiras"""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = []
    params = []
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor.execute(f"SELECT * FROM shelves {where} ORDER BY zone, module", params)
    rows = cursor.fetchall()
    shelves = dicts_from_rows(cursor, rows)
    return shelves

def add_shelf(zone, module, levels, columns, slots, unit=DEFAULT_UNIT, sector=DEFAULT_SECTOR):
    """Adiciona uma nova prateleira"""
    unit = normalize_unit(unit)
    sector = sector or DEFAULT_SECTOR
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO shelves (zone, module, levels, columns, slots, [unit], [sector]) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (zone, module, levels, columns, slots, unit, sector)
    )
    conn.commit()

def delete_shelf(zone, module, unit=None):
    """Remove uma prateleira"""
    conn = get_connection()
    cursor = conn.cursor()
    if unit is not None:
        unit = normalize_unit(unit)
        cursor.execute("DELETE FROM shelves WHERE zone = ? AND module = ? AND [unit] = ?", (zone, module, unit))
    else:
        cursor.execute("DELETE FROM shelves WHERE zone = ? AND module = ?", (zone, module))
    conn.commit()

# ============================================================================
# ORDERS
# ============================================================================

def get_all_orders(status_filter=None, unit=None, sector=None):
    """Retorna todos os pedidos, opcionalmente filtrados por status"""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = []
    params = []
    if status_filter:
        conditions.append("[status] = ?")
        params.append(status_filter)
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor.execute(f"SELECT * FROM orders {where} ORDER BY [timestamp] DESC", params)
    rows = cursor.fetchall()
    orders = dicts_from_rows(cursor, rows)
    return orders

def get_order_by_id(order_id, unit=None):
    """Retorna um pedido específico pelo ID"""
    conn = get_connection()
    cursor = conn.cursor()
    if unit is not None:
        unit = normalize_unit(unit)
        cursor.execute("SELECT * FROM orders WHERE order_id = ? AND [unit] = ?", (order_id, unit))
    else:
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    order = dict_from_row(cursor, row)
    return order

def add_order(position, order_id, box, date, timestamp, created_by, status='add', unit=DEFAULT_UNIT, sector=DEFAULT_SECTOR):
    """Adiciona um novo pedido"""
    unit = normalize_unit(unit)
    sector = sector or DEFAULT_SECTOR
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (position, order_id, box, [date], [timestamp], created_by, [status], [unit], [sector]) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (position, order_id, box, date, timestamp, created_by, status, unit, sector)
    )
    conn.commit()

def update_order_status(order_id, status, removed_at=None, removed_by=None, unit=None):
    """Atualiza o status de um pedido"""
    conn = get_connection()
    cursor = conn.cursor()

    if removed_at and removed_by:
        if unit is not None:
            unit = normalize_unit(unit)
            cursor.execute(
                "UPDATE orders SET [status] = ?, removed_at = ?, removed_by = ? WHERE order_id = ? AND [unit] = ?",
                (status, removed_at, removed_by, order_id, unit)
            )
        else:
            cursor.execute(
                "UPDATE orders SET [status] = ?, removed_at = ?, removed_by = ? WHERE order_id = ?",
                (status, removed_at, removed_by, order_id)
            )
    else:
        if unit is not None:
            unit = normalize_unit(unit)
            cursor.execute("UPDATE orders SET [status] = ? WHERE order_id = ? AND [unit] = ?", (status, order_id, unit))
        else:
            cursor.execute("UPDATE orders SET [status] = ? WHERE order_id = ?", (status, order_id))
    
    conn.commit()

def reactivate_order(order_id, position, box, timestamp, unit=None):
    """Reativa pedido removido sem criar novo registro (evita conflito UNIQUE)."""
    conn = get_connection()
    cursor = conn.cursor()
    if unit is not None:
        unit = normalize_unit(unit)
        cursor.execute(
            "UPDATE orders SET position = ?, box = ?, [status] = 'add', [timestamp] = ?, removed_at = NULL, removed_by = NULL WHERE order_id = ? AND [unit] = ?",
            (position, box, timestamp, order_id, unit)
        )
    else:
        cursor.execute(
            "UPDATE orders SET position = ?, box = ?, [status] = 'add', [timestamp] = ?, removed_at = NULL, removed_by = NULL WHERE order_id = ?",
            (position, box, timestamp, order_id)
        )
    conn.commit()

def clear_order_position(order_id, unit=None):
    """Limpa a posição de um pedido (evita reaparecer em visões por posição/andar)"""
    conn = get_connection()
    cursor = conn.cursor()
    if unit is not None:
        unit = normalize_unit(unit)
        cursor.execute("UPDATE orders SET position = '' WHERE order_id = ? AND [unit] = ?", (order_id, unit))
    else:
        cursor.execute("UPDATE orders SET position = '' WHERE order_id = ?", (order_id,))
    conn.commit()

def update_order_position(order_id, destination, unit=None):
    """Atualiza apenas a posicao de um pedido ativo."""
    conn = get_connection()
    cursor = conn.cursor()
    if unit is not None:
        unit = normalize_unit(unit)
        cursor.execute(
            "UPDATE orders SET position = ? WHERE order_id = ? AND [status] = 'add' AND [unit] = ?",
            (destination, order_id, unit)
        )
    else:
        cursor.execute(
            "UPDATE orders SET position = ? WHERE order_id = ? AND [status] = 'add'",
            (destination, order_id)
        )
    conn.commit()

def delete_order_by_position(position):
    """Remove pedido de uma posição"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders WHERE position = ? AND [status] = 'add'", (position,))
    conn.commit()

def count_orders_in_position(position, unit=None, sector=None):
    """Conta pedidos ativos em uma posição"""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["position = ?", "[status] = 'add'"]
    params = [position]
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    cursor.execute(f"SELECT COUNT(*) FROM orders WHERE {' AND '.join(conditions)}", params)
    count = cursor.fetchone()[0]
    return count

def count_all_orders_in_positions(unit=None, sector=None):
    """Retorna contagem de pedidos para TODAS as posições em uma só query (otimizado)"""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["[status] = 'add'"]
    params = []
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}"
    cursor.execute(f"SELECT position, COUNT(*) as count FROM orders {where} GROUP BY position", params)
    rows = cursor.fetchall()
    # Converter em dicionário para acesso rápido
    result = {}
    for row in rows:
        result[row[0]] = row[1]
    return result

# ============================================================================
# MOVEMENTS
# ============================================================================

def get_all_movements(limit=None, unit=None, sector=None):
    """Retorna movimentações, opcionalmente limitadas"""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = []
    params = []
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    if limit:
        cursor.execute(f"SELECT TOP {int(limit)} * FROM movements {where} ORDER BY [timestamp] DESC", params)
    else:
        cursor.execute(f"SELECT * FROM movements {where} ORDER BY [timestamp] DESC", params)
    rows = cursor.fetchall()
    movements = dicts_from_rows(cursor, rows)
    return movements

def add_movement(username, action, position="", order_id="", box="", details="", timestamp="", unit=DEFAULT_UNIT, sector=DEFAULT_SECTOR):
    """Adiciona uma nova movimentação"""
    unit = normalize_unit(unit)
    sector = sector or DEFAULT_SECTOR
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO movements (username, action, position, order_id, box, details, [timestamp], [unit], [sector]) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (username, action, position, order_id, box, details, timestamp, unit, sector)
    )
    conn.commit()

# ============================================================================
# QUERIES ESPECÍFICAS
# ============================================================================

def search_orders(query, unit=None, sector=None):
    """Busca pedidos por ID, posição, caixa ou usuário (apenas ativos)"""
    conn = get_connection()
    cursor = conn.cursor()
    search_pattern = f"%{query}%"
    conditions = [
        "(order_id LIKE ? OR position LIKE ? OR box LIKE ? OR created_by LIKE ?)",
        "[status] = 'add'"
    ]
    params = [search_pattern, search_pattern, search_pattern, search_pattern]
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}"
    cursor.execute(f"SELECT * FROM orders {where} ORDER BY [timestamp] DESC", params)
    rows = cursor.fetchall()
    orders = dicts_from_rows(cursor, rows)
    return orders

def get_orders_by_position(position, unit=None, sector=None):
    """Retorna pedidos de uma posição específica"""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["position = ?", "[status] = 'add'"]
    params = [position]
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    cursor.execute(f"SELECT * FROM orders WHERE {' AND '.join(conditions)} ORDER BY [timestamp]", params)
    rows = cursor.fetchall()
    orders = dicts_from_rows(cursor, rows)
    return orders

def get_database_stats(unit=None):
    """Retorna estatísticas do banco de dados"""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    if unit is not None:
        unit = normalize_unit(unit)
        cursor.execute("SELECT COUNT(*) FROM users WHERE [unit] = ?", (unit,))
    else:
        cursor.execute("SELECT COUNT(*) FROM users")
    stats['users'] = cursor.fetchone()[0]

    if unit is not None:
        cursor.execute("SELECT COUNT(*) FROM shelves WHERE [unit] = ?", (unit,))
    else:
        cursor.execute("SELECT COUNT(*) FROM shelves")
    stats['shelves'] = cursor.fetchone()[0]

    if unit is not None:
        cursor.execute("SELECT COUNT(*) FROM orders WHERE [status] = 'add' AND [unit] = ?", (unit,))
    else:
        cursor.execute("SELECT COUNT(*) FROM orders WHERE [status] = 'add'")
    stats['active_orders'] = cursor.fetchone()[0]

    if unit is not None:
        cursor.execute("SELECT COUNT(*) FROM orders WHERE [status] = 'removed' AND [unit] = ?", (unit,))
    else:
        cursor.execute("SELECT COUNT(*) FROM orders WHERE [status] = 'removed'")
    stats['removed_orders'] = cursor.fetchone()[0]

    if unit is not None:
        cursor.execute("SELECT COUNT(*) FROM movements WHERE [unit] = ?", (unit,))
    else:
        cursor.execute("SELECT COUNT(*) FROM movements")
    stats['movements'] = cursor.fetchone()[0]

    return stats
