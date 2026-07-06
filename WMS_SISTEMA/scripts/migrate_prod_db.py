"""
Migração segura do esquema do MDB de produção.

O script:
 - Faz backup do arquivo MDB de produção (no mesmo diretório, com timestamp)
 - Define `WMS_MDB_PATH_PROD` para apontar ao MDB de produção
 - Conecta via `db_mdb.get_connection()` para disparar verificações/migrações automáticas
 - Executa criação da tabela `order_confirmations` caso ausente
 - Chama `ensure_database_ready()` em blueprints que possuem migrações (etiquetas/expedicao)

Uso:
 python migrate_prod_db.py --prod "\\\\192.168.1.210\\apps master\\DATABASE WMS\\BD PRODUCAO\\wms_database.mdb"

ATENÇÃO: execute apenas com autorização — o script fará um backup antes de qualquer alteração.
"""

import argparse
import os
import shutil
import sys
import time
import traceback


def human_ts():
    return time.strftime('%Y%m%d_%H%M%S')


def main():
    parser = argparse.ArgumentParser(description='Migra esquema do MDB de produção (backup + apply)')
    parser.add_argument('--prod', help='Caminho completo para o MDB de produção (UNC ou local)', required=True)
    args = parser.parse_args()

    prod_path = os.path.abspath(args.prod)
    if not os.path.exists(prod_path):
        print(f'[ERRO] Arquivo não encontrado: {prod_path}')
        sys.exit(1)

    # Backup: cria cópia com timestamp no mesmo diretório
    prod_dir = os.path.dirname(prod_path)
    base_name = os.path.splitext(os.path.basename(prod_path))[0]
    backup_name = f"{base_name}_backup_{human_ts()}.mdb"
    backup_path = os.path.join(prod_dir, backup_name)
    try:
        print(f'[INFO] Criando backup: {backup_path} ...')
        shutil.copy2(prod_path, backup_path)
        print('[OK] Backup criado.')
    except Exception as e:
        print(f'[ERRO] Falha ao criar backup: {e}')
        traceback.print_exc()
        sys.exit(1)

    # Exporta variável de ambiente para que db_mdb resolva o caminho correto
    os.environ['WMS_MDB_PATH_PROD'] = prod_path
    print(f'[INFO] WMS_MDB_PATH_PROD set to: {prod_path}')

    # Adiciona root do projeto ao sys.path para importar módulos do WMS
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    try:
        import db_mdb
    except Exception as e:
        print(f'[ERRO] Não foi possível importar db_mdb: {e}')
        traceback.print_exc()
        sys.exit(1)

    try:
        print('[INFO] Abrindo conexão com o MDB de produção (disparará migrações automatizadas)...')
        conn = db_mdb.get_connection()
        print('[OK] Conectado ao MDB de produção.')
    except Exception as e:
        print(f'[ERRO] Falha ao abrir conexão com o MDB: {e}')
        traceback.print_exc()
        sys.exit(1)

    # 1) Criar tabela order_confirmations se ausente (mesma lógica do script existente)
    try:
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT COUNT(*) FROM order_confirmations WHERE 1=0')
            print('[OK] Tabela order_confirmations já existe (ou consulta permitida).')
        except Exception:
            print('[INFO] Tabela order_confirmations ausente — criando...')
            create_sql = '''
            CREATE TABLE order_confirmations (
                [id] COUNTER PRIMARY KEY,
                [username] TEXT(255),
                [sector] TEXT(255),
                [os_reference] TEXT(50),
                [os_confirmation] TEXT(50),
                [result] TEXT(20),
                [unit] TEXT(50),
                [created_at] TEXT(50),
                [data] TEXT(50),
                [hora] TEXT(50),
                [ts_millis] LONG
            )
            '''
            try:
                # Usa autocommit via atributo se disponível
                old_autocommit = getattr(conn, 'autocommit', False)
                try:
                    conn.autocommit = True
                    conn.execute(create_sql)
                finally:
                    conn.autocommit = old_autocommit
                print('[OK] Tabela order_confirmations criada com sucesso.')
            except Exception as e:
                print(f'[ERRO] Falha ao criar order_confirmations: {e}')
                traceback.print_exc()
    except Exception:
        traceback.print_exc()

    # 2) Chamar ensure_database_ready() dos blueprints principais
    try:
        print('[INFO] Aplicando migrações de blueprints (etiquetas, expedicao)...')
        # Importa blueprints e chama ensure_database_ready()
        import etiquetas_bp
        import expedicao_bp
        try:
            etiquetas_bp.ensure_database_ready()
            print('[OK] etiquetas_bp.ensure_database_ready() executado.')
        except Exception as _e:
            print(f'[AVISO] etiquetas_bp migração falhou: {_e}')
        try:
            expedicao_bp.ensure_database_ready()
            print('[OK] expedicao_bp.ensure_database_ready() executado.')
        except Exception as _e:
            print(f'[AVISO] expedicao_bp migração falhou: {_e}')
    except Exception as e:
        print(f'[ERRO] Falha ao importar/chamar blueprints: {e}')
        traceback.print_exc()

    print('\n[FINAL] Migração concluída (verifique logs e valide manualmente).')


if __name__ == '__main__':
    main()
