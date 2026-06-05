"""
Script para rodar o WMS em modo produção usando Waitress
"""
from waitress import serve
from web_app import app, start_daily_backup_scheduler, start_telegram_schedulers, apply_db_mode, save_db_mode
import db_mdb
import socket
import sys
import traceback

def get_local_ip():
    """Detecta automaticamente o IP local da máquina"""
    try:
        # Cria socket temporário para detectar IP da interface ativa
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "127.0.0.1"

if __name__ == '__main__':
    try:
        print("=" * 60)
        print("WMS Web Application - MODO PRODUÇÃO")
        print("=" * 60)
        print(f"[INFO] Banco MDB em uso: {db_mdb.get_db_path()}")
        stats = db_mdb.get_database_stats()
        print("[OK] Banco de dados MDB conectado com sucesso!")
        print(f"   - Usuarios: {stats['users']}")
        print(f"   - Prateleiras: {stats['shelves']}")
        print(f"   - Pedidos ativos: {stats['active_orders']}")
        print(f"   - Pedidos removidos: {stats['removed_orders']}")

        # Detectar IP local automaticamente
        local_ip = get_local_ip()

        print(f"\nServidor WMS iniciado!")
        print(f"Acesse: http://localhost:5000")
        print(f"Ou via rede: http://{local_ip}:5000")
        print("=" * 60)
        print("\nPressione CTRL+C para parar o servidor\n")

        # Sempre inicia em PRODUÇÃO (ignora db_mode.json salvo pelo admin)
        apply_db_mode('production')
        save_db_mode('production')
        print(f'[DB] Modo forcado: PRODUCTION -> {db_mdb.get_db_path()}')

        # Inicia agendador de backup automático diário (02:00)
        start_daily_backup_scheduler()

        # Inicia schedulers do Telegram (alertas de status e relatório diário)
        start_telegram_schedulers()

        # Rodar com Waitress (servidor WSGI adequado para produção)
        serve(app, host='0.0.0.0', port=5000, threads=4)
    except Exception:
        traceback.print_exc()
        if getattr(sys, 'frozen', False):
            try:
                input("\nPressione Enter para fechar...")
            except Exception:
                pass
        sys.exit(1)
