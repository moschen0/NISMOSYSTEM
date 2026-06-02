"""
Script de inicialização: criar tabela order_confirmations na .mdb
Executar uma vez para preparar o banco de dados
"""

import pyodbc
import os
import sys

# Adicionar parent directory ao path para importar db_mdb
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_db_path():
    """Retorna o caminho do banco de dados"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, '..', 'WMS_BD', 'wms_database.mdb')
    return os.path.abspath(db_path)

def create_connection(db_path):
    """Cria conexão com o banco de dados"""
    try:
        # Tenta driver 32-bit primeiro (mais compatível com .mdb)
        driver = "{Microsoft Access Driver (*.mdb, *.accdb)}"
        conn_str = f'Driver={driver};DBQ={db_path};'
        conn = pyodbc.connect(conn_str)
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        sys.exit(1)

def table_exists(cursor, table_name):
    """Verifica se tabela existe"""
    try:
        cursor.execute(f"SELECT * FROM {table_name} WHERE 1=0")
        return True
    except:
        return False

def create_order_confirmations_table(conn):
    """Cria tabela order_confirmations se não existir"""
    cursor = conn.cursor()
    
    if table_exists(cursor, "order_confirmations"):
        print("✓ Tabela 'order_confirmations' já existe.")
        return True
    
    print("📋 Criando tabela 'order_confirmations'...")
    
    try:
        # SQL para criar tabela (sintaxe Access simplificada)
        # Nota: Access é bem restritivo com CREATE TABLE via ODBC
        sql = """
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
            [timestamp] LONG
        )
        """
        
        cursor.execute(sql)
        conn.commit()
        print("✓ Tabela 'order_confirmations' criada com sucesso!")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao criar tabela: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()

def create_indexes(conn):
    """Cria índices para melhor performance"""
    cursor = conn.cursor()
    
    indexes = [
        ("idx_confirmations_username", "CREATE INDEX idx_confirmations_username ON order_confirmations (username)"),
        ("idx_confirmations_unit", "CREATE INDEX idx_confirmations_unit ON order_confirmations (unit)"),
        ("idx_confirmations_sector", "CREATE INDEX idx_confirmations_sector ON order_confirmations (sector)"),
        ("idx_confirmations_result", "CREATE INDEX idx_confirmations_result ON order_confirmations (result)"),
        ("idx_confirmations_timestamp", "CREATE INDEX idx_confirmations_timestamp ON order_confirmations (timestamp)"),
    ]
    
    for idx_name, sql in indexes:
        try:
            cursor.execute(sql)
            conn.commit()
            print(f"✓ Índice '{idx_name}' criado")
        except Exception as e:
            # Índice pode já existir, não é erro fatal
            pass
    
    cursor.close()

def main():
    """Função principal"""
    print("=" * 60)
    print("  INICIALIZAR BANCO DE DADOS - CONFERÊNCIA DE OS")
    print("=" * 60)
    
    db_path = get_db_path()
    print(f"📁 Banco de dados: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"❌ Arquivo não encontrado: {db_path}")
        sys.exit(1)
    
    # Conectar ao banco
    conn = create_connection(db_path)
    
    # Criar tabela
    if create_order_confirmations_table(conn):
        # Criar índices
        create_indexes(conn)
        print("\n✓ Banco de dados pronto para uso!")
    else:
        print("\n❌ Erro ao preparar banco de dados")
        conn.close()
        sys.exit(1)
    
    conn.close()

if __name__ == '__main__':
    main()
