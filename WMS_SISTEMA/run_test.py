"""
WMS - Servidor de TESTE local (porta 5001)
NUNCA altere o banco de rede nem o banco de producao.

Este script força o uso do banco LOCAL em:
  <raiz_repo>/WMS_BD/wms_database.mdb
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
# 2. Resolve o caminho do banco LOCAL (WMS_BD na raiz do repositório)
# ---------------------------------------------------------------------------
LOCAL_DB = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'WMS_BD', 'wms_database.mdb'))

if not os.path.exists(LOCAL_DB):
    print(f"[ERRO] Banco de dados local não encontrado em:\n  {LOCAL_DB}")
    print("Execute primeiro: Copy-Item <rede>\\wms_database.mdb WMS_BD\\")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 3. Importa db_mdb e SOBRESCREVE DB_PATH antes de qualquer conexão
#    (impede uso do caminho de rede definido em preferred_paths)
# ---------------------------------------------------------------------------
import db_mdb
db_mdb.DB_PATH = LOCAL_DB          # força banco local
# Fecha qualquer conexão residual que possa ter sido aberta
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
from web_app import app, start_daily_backup_scheduler, start_telegram_schedulers

# ---------------------------------------------------------------------------
# 5. Inicializa e verifica conexão com o banco LOCAL
# ---------------------------------------------------------------------------
print("=" * 60)
print("WMS Web Application - MODO TESTE (banco LOCAL)")
print("=" * 60)
print(f"[INFO] Banco MDB local : {db_mdb.get_db_path()}")

try:
    stats = db_mdb.get_database_stats()
    print("[OK]  Banco de dados LOCAL conectado com sucesso!")
    print(f"   - Usuarios         : {stats['users']}")
    print(f"   - Prateleiras      : {stats['shelves']}")
    print(f"   - Pedidos ativos   : {stats['active_orders']}")
    print(f"   - Pedidos removidos: {stats['removed_orders']}")
except Exception as e:
    print(f"[ERRO] Não foi possível conectar ao banco local: {e}")
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

# ---------------------------------------------------------------------------
# 7. Inicia o servidor Flask em modo debug (apenas local, porta 5001)
# ---------------------------------------------------------------------------
app.run(debug=True, host='127.0.0.1', port=5001, use_reloader=False)
