r"""
WMS - Servidor de TESTE local (porta 5001)
NUNCA altere o banco de produção.

Usa o banco de teste definido em WMS_MDB_PATH_TEST no .env:
  \\192.168.1.210\apps master\DATABASE WMS\BD TEST\wms_database_test.mdb
"""
import os
import sys
# ---------------------------------------------------------------------------
# 1. Garante que o diretório do script está no sys.path
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# ---------------------------------------------------------------------------
# 2. Carrega .env antes de qualquer import (necessário para WMS_MDB_PATH_TEST)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(SCRIPT_DIR, '.env'), override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 3. Importa db_mdb e força banco de TESTE antes de qualquer conexão
# ---------------------------------------------------------------------------
import db_mdb
TEST_DB = db_mdb.DB_PATH_TEST

if not TEST_DB:
    print("[ERRO] WMS_MDB_PATH_TEST não configurado no .env")
    sys.exit(1)

db_mdb.switch_database(TEST_DB)
# Fecha qualquer conexão residual
try:
    conn = getattr(db_mdb._thread_local, 'connection', None)
    if conn:
        conn.close()
        db_mdb._thread_local.connection = None
except Exception:
    pass

# ---------------------------------------------------------------------------
# 4. Importa a aplicação Flask (reutiliza o módulo db_mdb já patchado)
# ---------------------------------------------------------------------------
import web_app

# Mantém o estado de modo do banco isolado do ambiente de produção.
web_app.DB_MODE_FILE = os.path.join(SCRIPT_DIR, 'db_mode_test.json')
web_app.save_db_mode('test')

from web_app import app, start_daily_backup_scheduler, start_telegram_schedulers, start_opto_scheduler

# ---------------------------------------------------------------------------
# 5. Inicializa e verifica conexão com o banco de TESTE
# ---------------------------------------------------------------------------
print("=" * 60)
print("WMS Web Application - MODO TESTE (banco de rede)")
print("=" * 60)
print(f"[INFO] Backend teste   : {db_mdb.get_db_backend()}")
print(f"[INFO] Banco teste     : {db_mdb.get_db_path()}")

try:
    stats = db_mdb.get_database_stats()
    print("[OK]  Banco de dados TESTE conectado com sucesso!")
    print(f"   - Usuarios         : {stats['users']}")
    print(f"   - Prateleiras      : {stats['shelves']}")
    print(f"   - Pedidos ativos   : {stats['active_orders']}")
    print(f"   - Pedidos removidos: {stats['removed_orders']}")
except Exception as e:
    print(f"[ERRO] Não foi possível conectar ao banco de teste: {e}")
    sys.exit(1)

print()
print("Servidor de TESTE iniciado em http://127.0.0.1:5001")
print("(produção roda na porta 5000 — sem conflito)")
print("Pressione CTRL+C para parar\n")
print("=" * 60)

# ---------------------------------------------------------------------------
# 6. Inicia schedulers em background (backup + Telegram)
# ---------------------------------------------------------------------------
start_daily_backup_scheduler()
start_telegram_schedulers()
start_opto_scheduler()

# ---------------------------------------------------------------------------
# 7. Inicia o servidor Flask em modo debug (apenas local, porta 5001)
# ---------------------------------------------------------------------------
app.run(debug=True, host='127.0.0.1', port=5001, use_reloader=False)
