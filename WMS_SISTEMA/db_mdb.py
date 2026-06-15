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
try:
    from werkzeug.security import generate_password_hash, check_password_hash as _check_hash
    _HASH_AVAILABLE = True
except ImportError:
    _HASH_AVAILABLE = False

# A coluna users.password no MDB atual e VARCHAR(100). O hash default do
# Werkzeug (scrypt) tem ~162 chars e era truncado, quebrando o login.
_PASSWORD_HASH_METHOD = 'pbkdf2:sha256:260000'
_PASSWORD_HASH_SALT_LENGTH = 8


def hash_password(plain: str) -> str:
    """Retorna hash bcrypt/pbkdf2 da senha. Fallback para texto puro se werkzeug indisponivel."""
    if _HASH_AVAILABLE:
        return generate_password_hash(
            plain,
            method=_PASSWORD_HASH_METHOD,
            salt_length=_PASSWORD_HASH_SALT_LENGTH
        )
    return plain


def verify_password(plain: str, stored: str) -> bool:
    """Verifica senha contra hash armazenado (ou texto puro legado)."""
    if _HASH_AVAILABLE and stored.startswith(('pbkdf2:', 'scrypt:', 'bcrypt:')):
        try:
            return _check_hash(stored, plain)
        except Exception:
            # Hash legado truncado/corrompido: nao deixa a aplicacao quebrar.
            return False
    return plain == stored  # legado: texto puro


def get_runtime_base_dir():
    """Retorna a pasta base de execucao (script no dev, .exe em producao)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resolve_db_path():
    """Resolve caminho do MDB de producao.

    Prioridade: WMS_MDB_PATH_PROD (env) → copia local do banco no bundle/exe.
    """
    # Variavel de ambiente tem prioridade maxima (permite override em qualquer maquina).
    env_override = os.environ.get('WMS_MDB_PATH_PROD', '').strip()
    if not env_override:
        env_override = os.environ.get('WMS_MDB_PATH', '').strip()

    candidates = []
    if env_override:
        if os.path.isdir(env_override):
            env_override = os.path.join(env_override, 'wms_database.mdb')
        candidates.append(env_override)

    base_dir = get_runtime_base_dir()
    candidates.extend([
        os.path.join(base_dir, 'wms_database.mdb'),
        os.path.join(base_dir, 'WMS_BD', 'wms_database.mdb'),
        os.path.normpath(os.path.join(base_dir, '..', 'WMS_BD', 'wms_database.mdb')),
    ])

    for path in candidates:
        if path and os.path.exists(path):
            return path

    if env_override:
        return env_override

    return candidates[0] if candidates else ''


def resolve_db_path_test():
    """Resolve caminho do MDB de teste.

    Prioridade: WMS_MDB_PATH_TEST (env) → mesmo diretório do prod com sufixo _test.
    """
    env_override = os.environ.get('WMS_MDB_PATH_TEST', '').strip()
    if env_override:
        if os.path.isdir(env_override):
            env_override = os.path.join(env_override, 'wms_database_test.mdb')
        return env_override  # retorna mesmo que nao exista ainda (admin cria/copia)

    # Fallback: mesmo diretório do banco de produção, com sufixo _test
    prod = resolve_db_path()
    base_dir = os.path.dirname(prod)
    return os.path.join(base_dir, 'wms_database_test.mdb')


# ── Caminhos iniciais (podem ser trocados em runtime via switch_database) ──
DB_PATH_PROD = resolve_db_path()
DB_PATH_TEST = resolve_db_path_test()

DB_PATH = DB_PATH_PROD          # banco ativo no momento
_db_generation = 0              # incrementado a cada troca de banco
_db_gen_lock   = threading.Lock()


def switch_database(new_path: str):
    """Troca o banco ativo em runtime e invalida todas as conexoes cacheadas."""
    global DB_PATH, _db_generation
    with _db_gen_lock:
        DB_PATH = new_path
        _db_generation += 1


def get_db_path():
    """Retorna o caminho do banco atualmente ativo."""
    return DB_PATH


def get_db_path_prod():
    return DB_PATH_PROD


def get_db_path_test():
    return DB_PATH_TEST


# ============================================================================
# CONSTANTES E CONFIGURAÇÃO
# ============================================================================

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


def _table_exists(cursor, table_name):
    """Verifica se uma tabela existe no MDB."""
    try:
        cursor.tables(table=table_name, tableType='TABLE')
        row = cursor.fetchone()
        cursor.fetchall()
        return row is not None
    except Exception:
        return False


def _run_ddl_on_conn(conn, sql):
    """Executa DDL no Access via autocommit na conexão existente."""
    try:
        old_autocommit = conn.autocommit
        conn.autocommit = True
        try:
            conn.execute(sql)
        finally:
            conn.autocommit = old_autocommit
        return
    except Exception:
        # Alguns drivers Access podem rejeitar SQLSetConnectAttr(HY011).
        # Fallback seguro: executa DDL e commit explicito na transacao atual.
        pass

    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()


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

        # Adiciona coluna de atividade para relatorios e normaliza legado.
        if not _column_exists(cursor, 'orders', 'ativo_inativo'):
            try:
                _run_ddl_on_conn(conn, "ALTER TABLE orders ADD COLUMN ativo_inativo TEXT(20)")
            except Exception as _e:
                if not _column_exists(cursor, 'orders', 'ativo_inativo'):
                    import logging
                    logging.warning(f"Nao foi possivel adicionar [ativo_inativo] em orders: {_e}")

        if not _column_exists(cursor, 'orders', 'os_opto'):
            try:
                _run_ddl_on_conn(conn, "ALTER TABLE orders ADD COLUMN os_opto TEXT(100)")
            except Exception as _e:
                if not _column_exists(cursor, 'orders', 'os_opto'):
                    import logging
                    logging.warning(f"Nao foi possivel adicionar [os_opto] em orders: {_e}")

        try:
            cursor.execute(
                "UPDATE orders SET ativo_inativo = ? WHERE [status] = 'add' AND (ativo_inativo IS NULL OR ativo_inativo = '')",
                ('ativo',)
            )
            cursor.execute(
                "UPDATE orders SET ativo_inativo = ? WHERE [status] <> 'add' AND (ativo_inativo IS NULL OR ativo_inativo = '')",
                ('inativo',)
            )
        except Exception:
            pass

        conn.commit()

        # So marca schema como validado quando todas as colunas criticas existem.
        required_columns = [
            ('users', 'unit'),
            ('shelves', 'unit'),
            ('orders', 'unit'),
            ('movements', 'unit'),
            ('shelves', 'sector'),
            ('orders', 'sector'),
            ('movements', 'sector'),
            ('orders', 'ativo_inativo'),
            ('orders', 'os_opto'),
        ]
        all_ready = all(_column_exists(cursor, table_name, column_name) for table_name, column_name in required_columns)
        _schema_checked = all_ready
        if not all_ready:
            import logging
            logging.warning('Schema parcial detectado; migracao sera tentada novamente na proxima conexao.')


def _ensure_triage_schema(conn):
    """Garante estrutura de recebimento de triagem no MDB."""
    cursor = conn.cursor()

    if not _table_exists(cursor, 'triage_receipts'):
        # Access SQL: evita IF NOT EXISTS e cria tabela apenas quando ausente.
        _run_ddl_on_conn(
            conn,
            """
            CREATE TABLE triage_receipts (
                id COUNTER PRIMARY KEY,
                order_id TEXT(100),
                customer_code TEXT(100),
                customer_name TEXT(255),
                service_name TEXT(255),
                quantity INTEGER,
                received_at TEXT(50),
                received_by TEXT(100),
                notes LONGTEXT,
                [status] TEXT(30),
                created_at TEXT(50),
                updated_at TEXT(50),
                [unit] TEXT(100),
                [sector] TEXT(50)
            )
            """
        )

    expected_columns = {
        'order_id': "ALTER TABLE triage_receipts ADD COLUMN order_id TEXT(100)",
        'customer_code': "ALTER TABLE triage_receipts ADD COLUMN customer_code TEXT(100)",
        'customer_name': "ALTER TABLE triage_receipts ADD COLUMN customer_name TEXT(255)",
        'service_name': "ALTER TABLE triage_receipts ADD COLUMN service_name TEXT(255)",
        'quantity': "ALTER TABLE triage_receipts ADD COLUMN quantity INTEGER",
        'received_at': "ALTER TABLE triage_receipts ADD COLUMN received_at TEXT(50)",
        'received_by': "ALTER TABLE triage_receipts ADD COLUMN received_by TEXT(100)",
        'notes': "ALTER TABLE triage_receipts ADD COLUMN notes LONGTEXT",
        'status': "ALTER TABLE triage_receipts ADD COLUMN [status] TEXT(30)",
        'created_at': "ALTER TABLE triage_receipts ADD COLUMN created_at TEXT(50)",
        'updated_at': "ALTER TABLE triage_receipts ADD COLUMN updated_at TEXT(50)",
        'unit': "ALTER TABLE triage_receipts ADD COLUMN [unit] TEXT(100)",
        'sector': "ALTER TABLE triage_receipts ADD COLUMN [sector] TEXT(50)",
    }

    for col_name, ddl in expected_columns.items():
        if not _column_exists(cursor, 'triage_receipts', col_name):
            try:
                _run_ddl_on_conn(conn, ddl)
            except Exception:
                pass

    try:
        cursor.execute(
            "UPDATE triage_receipts SET [status] = 'received' WHERE [status] IS NULL OR [status] = ''"
        )
    except Exception:
        pass

    try:
        cursor.execute(
            "UPDATE triage_receipts SET quantity = 1 WHERE quantity IS NULL OR quantity <= 0"
        )
    except Exception:
        pass

    try:
        cursor.execute(
            "UPDATE triage_receipts SET [unit] = ? WHERE [unit] IS NULL OR [unit] = ''",
            (DEFAULT_UNIT,)
        )
    except Exception:
        pass

    try:
        cursor.execute(
            "UPDATE triage_receipts SET [sector] = ? WHERE [sector] IS NULL OR [sector] = ''",
            (DEFAULT_SECTOR,)
        )
    except Exception:
        pass

    conn.commit()


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
    conn_gen = getattr(_thread_local, 'db_generation', -1)

    # Invalida conexao cacheada se o banco foi trocado desde a ultima abertura.
    if conn is not None and conn_gen != _db_generation:
        try:
            conn.close()
        except Exception:
            pass
        conn = None
        _thread_local.connection = None

    if not os.path.exists(DB_PATH):
        raise RuntimeError(
            f'Arquivo MDB nao encontrado no caminho configurado: "{DB_PATH}". '
            'Use o banco oficial em C:\\APPS MASTER\\WMS\\WMS_BD\\wms_database.mdb '
            'ou configure WMS_MDB_PATH para um caminho valido.'
        )

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
    _thread_local.db_generation = _db_generation
    _ensure_unit_schema(_thread_local.connection)
    _ensure_triage_schema(_thread_local.connection)
    return _thread_local.connection

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
        (username, hash_password(password), sector, created_at, 1 if active else 0, unit)
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
            elif key == 'password':
                value = hash_password(value)
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

def get_order_by_id(order_id, unit=None, sector=None):
    """Retorna um pedido específico pelo ID.

    Quando sector é informado a busca é restrita a (unit, sector, order_id),
    permitindo o mesmo order_id em setores distintos da mesma unidade.
    Retorna o registro mais recente quando há múltiplos (ex.: removido + ativo).
    """
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["order_id = ?"]
    params = [order_id]
    if unit is not None:
        unit = normalize_unit(unit)
        conditions.append("[unit] = ?")
        params.append(unit)
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}"
    cursor.execute(f"SELECT * FROM orders {where} ORDER BY [timestamp] DESC", params)
    row = cursor.fetchone()
    order = dict_from_row(cursor, row)
    return order

def add_order(position, order_id, box, date, timestamp, created_by, status='add', unit=DEFAULT_UNIT, sector=DEFAULT_SECTOR, os_opto=''):
    """Adiciona um novo pedido"""
    unit = normalize_unit(unit)
    sector = sector or DEFAULT_SECTOR
    os_opto = str(os_opto or '').strip().upper()
    activity_flag = 'ativo' if str(status).strip().lower() == 'add' else 'inativo'
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (position, order_id, box, [date], [timestamp], created_by, [status], ativo_inativo, [unit], [sector], os_opto) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (position, order_id, box, date, timestamp, created_by, status, activity_flag, unit, sector, os_opto)
    )
    conn.commit()

def update_order_status(order_id, status, removed_at=None, removed_by=None, unit=None, sector=None):
    """Atualiza o status de um pedido.

    Quando sector é informado a atualização é restrita a (unit, sector, order_id)
    para não afetar registros homônimos em outros setores.
    """
    conn = get_connection()
    cursor = conn.cursor()
    activity_flag = 'ativo' if str(status).strip().lower() == 'add' else 'inativo'

    id_conditions = ["order_id = ?"]
    id_params = [order_id]
    if unit is not None:
        unit = normalize_unit(unit)
        id_conditions.append("[unit] = ?")
        id_params.append(unit)
    if sector is not None:
        id_conditions.append("[sector] = ?")
        id_params.append(sector)
    where = f"WHERE {' AND '.join(id_conditions)}"

    if removed_at and removed_by:
        cursor.execute(
            f"UPDATE orders SET [status] = ?, ativo_inativo = ?, removed_at = ?, removed_by = ? {where}",
            (status, activity_flag, removed_at, removed_by, *id_params)
        )
    else:
        cursor.execute(
            f"UPDATE orders SET [status] = ?, ativo_inativo = ? {where}",
            (status, activity_flag, *id_params)
        )

    conn.commit()

def reactivate_order(order_id, position, box, timestamp, unit=None, sector=None, os_opto=''):
    """Reativa pedido removido sem criar novo registro.

    Quando sector é informado a atualização é restrita a (unit, sector, order_id).
    """
    conn = get_connection()
    cursor = conn.cursor()
    os_opto = str(os_opto or '').strip().upper()
    id_conditions = ["order_id = ?"]
    id_params = [order_id]
    if unit is not None:
        unit = normalize_unit(unit)
        id_conditions.append("[unit] = ?")
        id_params.append(unit)
    if sector is not None:
        id_conditions.append("[sector] = ?")
        id_params.append(sector)
    where = f"WHERE {' AND '.join(id_conditions)}"
    cursor.execute(
        f"UPDATE orders SET position = ?, box = ?, [status] = 'add', ativo_inativo = 'ativo', [timestamp] = ?, removed_at = NULL, removed_by = NULL, os_opto = ? {where}",
        (position, box, timestamp, os_opto, *id_params)
    )
    conn.commit()

def clear_order_position(order_id, unit=None, sector=None):
    """Limpa a posição de um pedido (evita reaparecer em visões por posição/andar).

    Quando sector é informado a atualização é restrita a (unit, sector, order_id).
    """
    conn = get_connection()
    cursor = conn.cursor()
    id_conditions = ["order_id = ?"]
    id_params = [order_id]
    if unit is not None:
        unit = normalize_unit(unit)
        id_conditions.append("[unit] = ?")
        id_params.append(unit)
    if sector is not None:
        id_conditions.append("[sector] = ?")
        id_params.append(sector)
    where = f"WHERE {' AND '.join(id_conditions)}"
    cursor.execute(f"UPDATE orders SET position = '' {where}", id_params)
    conn.commit()

def update_order_position(order_id, destination, unit=None, sector=None):
    """Atualiza apenas a posicao de um pedido ativo.

    Quando sector é informado a atualização é restrita a (unit, sector, order_id).
    """
    conn = get_connection()
    cursor = conn.cursor()
    id_conditions = ["order_id = ?", "[status] = 'add'"]
    id_params = [order_id]
    if unit is not None:
        unit = normalize_unit(unit)
        id_conditions.append("[unit] = ?")
        id_params.append(unit)
    if sector is not None:
        id_conditions.append("[sector] = ?")
        id_params.append(sector)
    where = f"WHERE {' AND '.join(id_conditions)}"
    cursor.execute(f"UPDATE orders SET position = ? {where}", (destination, *id_params))
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

def _parse_any_datetime(value):
    """Tenta converter datas armazenadas em formatos mistos do sistema."""
    text = str(value or '').strip()
    if not text:
        return None

    from datetime import datetime

    for fmt in (
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y %H:%M',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None

def get_all_movements(limit=None, unit=None, sector=None, filters=None):
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
    cursor.execute(f"SELECT * FROM movements {where}", params)
    rows = cursor.fetchall()

    movements = dicts_from_rows(cursor, rows)
    filters = filters or {}

    def _matches_contains(value, expected):
        expected_text = str(expected or '').strip().lower()
        if not expected_text:
            return True
        return expected_text in str(value or '').strip().lower()

    def _matches_exact(value, expected):
        expected_text = str(expected or '').strip().lower()
        if not expected_text:
            return True
        return str(value or '').strip().lower() == expected_text

    date_from = _parse_any_datetime(filters.get('date_from'))
    date_to = _parse_any_datetime(filters.get('date_to'))

    filtered_movements = []
    for movement in movements:
        if not _matches_contains(movement.get('username'), filters.get('username')):
            continue
        if not _matches_exact(movement.get('action'), filters.get('action')):
            continue
        if not _matches_contains(movement.get('order_id'), filters.get('order_id')):
            continue
        if not _matches_contains(movement.get('box'), filters.get('box')):
            continue
        if not _matches_contains(movement.get('position'), filters.get('position')):
            continue

        movement_dt = _parse_any_datetime(movement.get('timestamp'))
        if date_from and (movement_dt is None or movement_dt.date() < date_from.date()):
            continue
        if date_to and (movement_dt is None or movement_dt.date() > date_to.date()):
            continue

        filtered_movements.append(movement)

    filtered_movements.sort(
        key=lambda item: (
            _parse_any_datetime(item.get('timestamp')) or _parse_any_datetime('1970-01-01'),
            int(str(item.get('id', 0) or 0)) if str(item.get('id', 0) or '0').isdigit() else 0,
        ),
        reverse=True,
    )

    if limit:
        filtered_movements = filtered_movements[:int(limit)]

    return filtered_movements


def get_top_triage_customer_codes(limit=8, unit=None, sector=None):
    """Retorna os códigos de cliente mais usados na triagem."""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["[status] = 'received'"]
    params = []

    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor.execute(
        f"""
        SELECT TOP {int(limit)} customer_code, COUNT(*) AS total
        FROM triage_receipts {where}
        GROUP BY customer_code
        ORDER BY COUNT(*) DESC, customer_code ASC
        """,
        params,
    )
    rows = cursor.fetchall()
    return [str(row[0]).strip() for row in rows if str(row[0] or '').strip()]


def get_top_movements_suggestions(field, limit=8, unit=None, sector=None):
    """Retorna valores mais comuns de movimentos para campos de filtro rápidos."""
    allowed_fields = {'username', 'action'}
    if field not in allowed_fields:
        return []

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
    cursor.execute(
        f"""
        SELECT TOP {int(limit)} [{field}], COUNT(*) AS total
        FROM movements {where}
        GROUP BY [{field}]
        HAVING [{field}] IS NOT NULL AND [{field}] <> ''
        ORDER BY COUNT(*) DESC, [{field}] ASC
        """,
        params,
    )
    rows = cursor.fetchall()
    return [str(row[0]).strip() for row in rows if str(row[0] or '').strip()]

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


def get_active_orders_by_order_ids(order_ids, unit=None, sector=None):
    """Retorna pedidos ativos/endereço por uma lista de order_id."""
    clean_ids = [str(x or '').strip().upper() for x in (order_ids or []) if str(x or '').strip()]
    if not clean_ids:
        return []

    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ','.join(['?'] * len(clean_ids))
    conditions = [f"order_id IN ({placeholders})", "[status] = 'add'"]
    params = list(clean_ids)

    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)

    where = f"WHERE {' AND '.join(conditions)}"
    cursor.execute(f"SELECT * FROM orders {where} ORDER BY [timestamp] DESC", params)
    rows = cursor.fetchall()
    return dicts_from_rows(cursor, rows)

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


def get_orders_by_date(date_str, unit=None, sector=None):
    """Retorna pedidos ativos adicionados na data fornecida.

    O campo [date] é armazenado como 'dd/mm/yyyy HH:MM:SS', portanto a busca
    usa LIKE 'dd/mm/yyyy%' para encontrar todos os registros do dia.
    `date_str` deve estar no formato 'dd/mm/yyyy' (ex: '09/06/2026').
    Retorna apenas pedidos com [status] = 'add' e ativo_inativo = 'ativo'.
    """
    if not date_str:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    # usa LIKE porque o campo guarda data + hora ('dd/mm/yyyy HH:MM:SS')
    like_prefix = str(date_str).strip().rstrip('%') + '%'
    conditions = ["[date] LIKE ?", "[status] = 'add'", "ativo_inativo = 'ativo'"]
    params = [like_prefix]
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}"
    cursor.execute(f"SELECT * FROM orders {where} ORDER BY [timestamp]", params)
    rows = cursor.fetchall()
    return dicts_from_rows(cursor, rows)


def get_active_orders_by_client_number(client_number, unit=None, sector=None, limit=20):
    """Retorna servicos ativos enderecados para um numero de cliente."""
    raw_value = str(client_number or '').strip().upper()
    if not raw_value:
        return []

    def normalize_client_number(value):
        text = str(value or '').strip().upper()
        text = re.sub(r'[^A-Z0-9]+', '', text)
        if text.isdigit():
            text = text.lstrip('0') or '0'
        return text

    normalized_value = normalize_client_number(raw_value)
    if not normalized_value:
        return []

    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["[status] = 'add'", "box IS NOT NULL", "box <> ''"]
    params = []

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

    matched = []
    for order in orders:
        order_client = normalize_client_number(order.get('box', ''))
        if order_client == normalized_value:
            matched.append(order)
            if len(matched) >= int(limit):
                break

    return matched

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

    try:
        if unit is not None:
            cursor.execute("SELECT COUNT(*) FROM triage_receipts WHERE [unit] = ?", (unit,))
        else:
            cursor.execute("SELECT COUNT(*) FROM triage_receipts")
        stats['triage_receipts'] = cursor.fetchone()[0]
    except Exception:
        stats['triage_receipts'] = 0

    return stats


# ============================================================================
# TRIAGE RECEIPTS
# ============================================================================

def get_triage_receipt_by_order_id(order_id, unit=None, sector=None):
    """Retorna recebimento de triagem por order_id."""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["order_id = ?"]
    params = [order_id]
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}"
    cursor.execute(f"SELECT TOP 1 * FROM triage_receipts {where} ORDER BY id DESC", params)
    row = cursor.fetchone()
    return dict_from_row(cursor, row)


def upsert_triage_receipt(
    order_id,
    customer_code,
    customer_name,
    service_name,
    quantity,
    received_at,
    received_by,
    notes='',
    status='received',
    unit=DEFAULT_UNIT,
    sector='TRIAGEM'
):
    """Cria/atualiza recebimento de triagem.

    Se order_id vier vazio, cria novo registro (sem upsert por pedido).
    """
    unit = normalize_unit(unit)
    sector = sector or 'TRIAGEM'
    order_id = str(order_id or '').strip().upper()
    service_name = str(service_name or '').strip()
    conn = get_connection()
    cursor = conn.cursor()

    row = None
    if order_id:
        cursor.execute(
            "SELECT TOP 1 id FROM triage_receipts WHERE order_id = ? AND [unit] = ? AND [sector] = ? ORDER BY id DESC",
            (order_id, unit, sector)
        )
        row = cursor.fetchone()
    now_str = datetime_now_str()

    if row:
        triage_id = int(row[0])
        cursor.execute(
            """
            UPDATE triage_receipts
            SET customer_code = ?, customer_name = ?, service_name = ?, quantity = ?,
                received_at = ?, received_by = ?, notes = ?, [status] = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                customer_code,
                customer_name,
                service_name,
                int(quantity or 1),
                received_at,
                received_by,
                notes,
                status,
                now_str,
                triage_id,
            )
        )
        conn.commit()
        return {'id': triage_id, 'is_new': False}

    created_at = now_str
    cursor.execute(
        """
        INSERT INTO triage_receipts (
            order_id, customer_code, customer_name, service_name, quantity,
            received_at, received_by, notes, [status], created_at, updated_at, [unit], [sector]
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            customer_code,
            customer_name,
            service_name,
            int(quantity or 1),
            received_at,
            received_by,
            notes,
            status,
            created_at,
            created_at,
            unit,
            sector,
        )
    )
    conn.commit()

    cursor.execute("SELECT @@IDENTITY")
    row = cursor.fetchone()
    triage_id = int(row[0]) if row else None
    return {'id': triage_id, 'is_new': True}


def get_recent_triage_receipts(limit=100, unit=None, sector=None):
    """Retorna recebimentos recentes de triagem."""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["[status] = 'received'"]
    params = []
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor.execute(
        f"SELECT TOP {int(limit)} * FROM triage_receipts {where} ORDER BY id DESC",
        params
    )
    rows = cursor.fetchall()
    return dicts_from_rows(cursor, rows)


def search_triage_receipts(query=None, unit=None, sector=None, order_id=None, customer_code=None, customer_name=None, service_name=None, received_by=None, notes=None, date_from=None, date_to=None):
    """Busca triagem por texto livre e filtros específicos."""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["[status] = 'received'"]
    params = []

    search_text = str(query or '').strip()
    if search_text:
        pattern = f"%{search_text}%"
        conditions.append("(order_id LIKE ? OR customer_code LIKE ? OR customer_name LIKE ? OR service_name LIKE ? OR received_by LIKE ? OR notes LIKE ?)")
        params.extend([pattern, pattern, pattern, pattern, pattern, pattern])

    if order_id:
        conditions.append("order_id LIKE ?")
        params.append(f"%{str(order_id).strip()}%")

    if customer_code:
        conditions.append("customer_code LIKE ?")
        params.append(f"%{str(customer_code).strip()}%")

    if customer_name:
        conditions.append("customer_name LIKE ?")
        params.append(f"%{str(customer_name).strip()}%")

    if service_name:
        conditions.append("service_name LIKE ?")
        params.append(f"%{str(service_name).strip()}%")

    if received_by:
        conditions.append("received_by LIKE ?")
        params.append(f"%{str(received_by).strip()}%")

    if notes:
        conditions.append("notes LIKE ?")
        params.append(f"%{str(notes).strip()}%")

    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(conditions)}"
    cursor.execute(f"SELECT * FROM triage_receipts {where}", params)
    rows = cursor.fetchall()
    receipts = dicts_from_rows(cursor, rows)

    parsed_date_from = _parse_any_datetime(date_from)
    parsed_date_to = _parse_any_datetime(date_to)
    filtered_receipts = []

    for item in receipts:
        received_dt = _parse_any_datetime(item.get('received_at'))
        if parsed_date_from and (received_dt is None or received_dt.date() < parsed_date_from.date()):
            continue
        if parsed_date_to and (received_dt is None or received_dt.date() > parsed_date_to.date()):
            continue
        filtered_receipts.append(item)

    filtered_receipts.sort(
        key=lambda item: (
            _parse_any_datetime(item.get('received_at')) or _parse_any_datetime(item.get('created_at')) or _parse_any_datetime('1970-01-01'),
            int(str(item.get('id', 0) or 0)) if str(item.get('id', 0) or '0').isdigit() else 0,
        ),
        reverse=True,
    )

    return filtered_receipts


def get_triage_receipts_by_order_ids(order_ids, unit=None, sector=None):
    """Retorna recebimentos de triagem para um conjunto de order_ids."""
    if not order_ids:
        return []

    clean_ids = [str(x).strip() for x in order_ids if str(x).strip()]
    if not clean_ids:
        return []

    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ','.join(['?'] * len(clean_ids))
    conditions = [f"order_id IN ({placeholders})", "[status] = 'received'"]
    params = list(clean_ids)

    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)

    where = f"WHERE {' AND '.join(conditions)}"
    cursor.execute(f"SELECT * FROM triage_receipts {where}", params)
    rows = cursor.fetchall()
    return dicts_from_rows(cursor, rows)


def get_next_triage_order_id(unit=None, sector=None, start_at=1):
    """Retorna proximo numero de pedido sequencial da triagem."""
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
    cursor.execute(f"SELECT order_id FROM triage_receipts {where}", params)
    rows = cursor.fetchall()

    max_number = int(start_at or 1) - 1
    for row in rows:
        value = str(row[0] or '').strip()
        if value.isdigit():
            num = int(value)
            if num > max_number:
                max_number = num

    return max_number + 1


def get_triage_customer_name_by_code(customer_code, unit=None, sector=None):
    """Busca o nome do cliente em etiq_clients pelo numero_cliente.

    A fonte de verdade é a tabela etiq_clients (importada do catálogo de
    clientes), não triage_receipts que é apenas um registro de pedidos recebidos.
    Os parâmetros unit/sector são mantidos por compatibilidade de assinatura mas
    não são usados na consulta, pois etiq_clients não é particionada por unidade.
    """
    code = str(customer_code or '').strip()
    if not code:
        return ''

    # numero_cliente é INTEGER na tabela; aceita código numérico com zeros à esquerda
    code_stripped = code.lstrip('0') or '0'
    if not code_stripped.isdigit():
        return ''

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TOP 1 nome_cliente FROM etiq_clients "
            "WHERE numero_cliente = ? AND nome_cliente IS NOT NULL AND nome_cliente <> '' "
            "ORDER BY id DESC",
            (int(code_stripped),),
        )
        row = cursor.fetchone()
        return str(row[0]).strip() if row and row[0] is not None else ''
    except Exception:
        return ''


def datetime_now_str():
    """Timestamp padrao do sistema."""
    from datetime import datetime
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


# ============================================================================
# CONFIRMAÇÕES DE OS (Conferência de Ordens de Serviço)
# ============================================================================

def add_confirmation(username, sector, os_reference, os_confirmation, result, unit=None):
    """Insere novo registro de confirmação de OS
    
    NOTA: Usa SQL direto (not parametrized) por compatibilidade com Access via ODBC.
    Os valores são escapados apropriadamente para evitar SQL injection.
    """
    conn = get_connection()
    cursor = conn.cursor()
    unit = normalize_unit(unit)
    now = datetime_now_str()
    timestamp = int(__import__('time').time())  # Usar segundos, não milissegundos
    
    # Extrai data e hora do timestamp
    from datetime import datetime
    dt = datetime.now()
    data = dt.strftime("%d/%m/%Y")
    hora = dt.strftime("%H:%M:%S")
    
    # Escape de valores de string (simples proteção contra SQL injection)
    def escape_sql(value):
        if isinstance(value, str):
            # Escape single quotes by doubling them
            return f"'{value.replace(chr(39), chr(39) + chr(39))}'"
        elif value is None:
            return 'NULL'
        else:
            return str(value)
    
    # Construir query com SQL direto (compatível com Access)
    sql = f"""
        INSERT INTO order_confirmations (
            username, sector, os_reference, os_confirmation, result, unit,
            created_at, [data], hora, ts_millis
        ) VALUES (
            {escape_sql(username)}, {escape_sql(sector)}, {escape_sql(os_reference)},
            {escape_sql(os_confirmation)}, {escape_sql(result)}, {escape_sql(unit)},
            {escape_sql(now)}, {escape_sql(data)}, {escape_sql(hora)}, {timestamp}
        )
    """
    
    cursor.execute(sql)
    conn.commit()
    
    # Tenta obter ID da última inserção (Access)
    try:
        cursor.execute("SELECT MAX(id) FROM order_confirmations")
        row = cursor.fetchone()
        conf_id = int(row[0]) if row and row[0] else None
    except:
        conf_id = None
    
    return {
        'id': conf_id,
        'username': username,
        'sector': sector,
        'os_reference': os_reference,
        'os_confirmation': os_confirmation,
        'result': result,
        'unit': unit,
        'data': data,
        'hora': hora,
        'timestamp': timestamp,
    }


def get_confirmations(unit=None, sector=None, username=None, result=None, limit=None):
    """Retorna confirmações com filtros opcionais"""
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
    
    if username is not None:
        conditions.append("[username] = ?")
        params.append(username)
    
    if result is not None:
        conditions.append("[result] = ?")
        params.append(result)
    
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit_clause = f" LIMIT {int(limit)}" if limit else ""
    
    cursor.execute(
        f"SELECT * FROM order_confirmations {where} ORDER BY [timestamp] DESC{limit_clause}",
        params
    )
    
    rows = cursor.fetchall()
    confirmations = dicts_from_rows(cursor, rows)
    return confirmations


def get_confirmations_filtered(filters, unit=None):
    """Retorna confirmações filtradas por período e resultado"""
    conn = get_connection()
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    unit = normalize_unit(unit) if unit else None
    if unit:
        conditions.append("[unit] = ?")
        params.append(unit)
    
    # Filtro de resultado (ok, erro, todos)
    if filters.get('result') and filters['result'] != 'all':
        conditions.append("[result] = ?")
        params.append(filters['result'])
    
    # Filtro de usuário
    if filters.get('username'):
        conditions.append("[username] = ?")
        params.append(filters['username'])
    
    # Filtro de data inicial
    if filters.get('date_from'):
        conditions.append("[data] >= ?")
        params.append(filters['date_from'])
    
    # Filtro de data final
    if filters.get('date_to'):
        conditions.append("[data] <= ?")
        params.append(filters['date_to'])
    
    # Filtro de setor
    if filters.get('sector') and filters['sector'] != 'all':
        conditions.append("[sector] = ?")
        params.append(filters['sector'])
    
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    cursor.execute(
        f"SELECT * FROM order_confirmations {where} ORDER BY [timestamp] DESC",
        params
    )
    
    rows = cursor.fetchall()
    confirmations = dicts_from_rows(cursor, rows)
    return confirmations


def get_confirmation_stats(unit=None, filters=None):
    """Retorna estatísticas das confirmações"""
    conn = get_connection()
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    unit = normalize_unit(unit) if unit else None
    if unit:
        conditions.append("[unit] = ?")
        params.append(unit)
    
    if filters:
        if filters.get('result') and filters['result'] != 'all':
            conditions.append("[result] = ?")
            params.append(filters['result'])
        
        if filters.get('username'):
            conditions.append("[username] = ?")
            params.append(filters['username'])
        
        if filters.get('date_from'):
            conditions.append("[data] >= ?")
            params.append(filters['date_from'])
        
        if filters.get('date_to'):
            conditions.append("[data] <= ?")
            params.append(filters['date_to'])
        
        if filters.get('sector') and filters['sector'] != 'all':
            conditions.append("[sector] = ?")
            params.append(filters['sector'])
    
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    # Total
    cursor.execute(f"SELECT COUNT(*) FROM order_confirmations {where}", params)
    total = cursor.fetchone()[0]
    
    # OK
    ok_where = f"{where} AND [result] = 'ok'" if where else "WHERE [result] = 'ok'"
    cursor.execute(f"SELECT COUNT(*) FROM order_confirmations {ok_where}", params if where else [])
    ok_count = cursor.fetchone()[0]
    
    # Erro
    error_where = f"{where} AND [result] <> 'ok'" if where else "WHERE [result] <> 'ok'"
    cursor.execute(f"SELECT COUNT(*) FROM order_confirmations {error_where}", params if where else [])
    error_count = cursor.fetchone()[0]
    
    accuracy = round((ok_count / total * 100), 1) if total > 0 else 0
    
    return {
        'total': total,
        'ok': ok_count,
        'error': error_count,
        'accuracy_percent': accuracy,
    }


def search_confirmations(query, unit=None, sector=None):
    """Busca confirmações por OS ou usuário"""
    conn = get_connection()
    cursor = conn.cursor()
    
    search_pattern = f"%{query}%"
    conditions = ["(os_reference LIKE ? OR os_confirmation LIKE ? OR username LIKE ?)"]
    params = [search_pattern, search_pattern, search_pattern]
    
    if unit is not None:
        conditions.append("[unit] = ?")
        params.append(normalize_unit(unit))
    
    if sector is not None:
        conditions.append("[sector] = ?")
        params.append(sector)
    
    where = f"WHERE {' AND '.join(conditions)}"
    
    cursor.execute(
        f"SELECT * FROM order_confirmations {where} ORDER BY [timestamp] DESC",
        params
    )
    
    rows = cursor.fetchall()
    confirmations = dicts_from_rows(cursor, rows)
    return confirmations
