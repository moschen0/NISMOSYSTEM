#!/usr/bin/env python
"""
Script para testar e criar manualmente a tabela order_confirmations no banco de dados
"""

import os
import sys
import pyodbc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from dotenv import load_dotenv
load_dotenv('.env')

# Carrega o DB path
db_path = os.environ.get('WMS_MDB_PATH_TEST') or os.environ.get('WMS_MDB_PATH')
print(f"DB Path: {db_path}")

if not db_path:
    print("ERRO: WMS_MDB_PATH não configurado")
    sys.exit(1)

if os.path.isdir(db_path):
    db_path = os.path.join(db_path, 'wms_database_test.mdb')

print(f"Using DB: {db_path}")

if not os.path.exists(db_path):
    print(f"ERRO: Arquivo não existe: {db_path}")
    sys.exit(1)

# Tenta conectar
try:
    # Constrói connection string
    conn_str = f"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={db_path};Uid=;Pwd=;"
    print(f"Connection string: {conn_str}")
    
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    # Lista tabelas
    print("\nTabelas existentes:")
    for table in cursor.tables(tableType='TABLE'):
        print(f"  - {table[2]}")
    
    # Verifica se order_confirmations existe
    print("\nProcurando por 'order_confirmations'...")
    tables = [t[2] for t in cursor.tables(tableType='TABLE')]
    if 'order_confirmations' in tables:
        print("✓ Tabela 'order_confirmations' encontrada!")
        
        # Lista colunas
        print("\nColunas:")
        for col in cursor.columns(table='order_confirmations'):
            print(f"  - {col[3]}: {col[5]}")
    else:
        print("✗ Tabela 'order_confirmations' NÃO encontrada!")
        print("\nCriando tabela...")
        
        # Cria a tabela manualmente com todas as colunas necessárias
        # Usar escape com colchetes para palavras reservadas
        create_sql = "CREATE TABLE order_confirmations (id INT, username TEXT, sector TEXT, os_reference TEXT, os_confirmation TEXT, result TEXT, unit TEXT, created_at TEXT, [data] TEXT, hora TEXT, ts_millis LONG)"
        print(f"Executando SQL: {create_sql}")
        cursor.execute(create_sql)
        conn.commit()
        print("✓ Tabela criada com sucesso!")
    
    # Tenta inserir um registro de teste
    print("\nTestando INSERT com sintaxe NAMED...")
    try:
        sql = """
            INSERT INTO order_confirmations (
                username, sector, os_reference, os_confirmation, result, unit,
                created_at, [data], hora, ts_millis
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        # Tenta usar string formatting em vez de placeholders
        values = (
            'test_user', 'TEST', '123456', '123456', 'ok', 'MASTER',
            '2026-06-02', '02/06/2026', '18:00:00', 1717348800  # Usar INT em vez de LONG
        )
        
        # Tenta escapar as aspas para SQL
        escaped_values = []
        for v in values:
            if isinstance(v, str):
                escaped_values.append(f"'{v.replace(chr(39), chr(39) + chr(39))}'")  # Escape single quotes
            else:
                escaped_values.append(str(v))
        
        sql_formatted = sql
        for i, val in enumerate(escaped_values):
            sql_formatted = sql_formatted.replace('?', val, 1)
        
        print(f"Formatted SQL: {sql_formatted}")
        cursor.execute(sql_formatted)
        conn.commit()
        print("✓ INSERT bem-sucedido com SQL formatado!")
    except Exception as e:
        print(f"✗ Erro no INSERT: {e}")
    
    conn.close()
    
except Exception as e:
    print(f"ERRO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
