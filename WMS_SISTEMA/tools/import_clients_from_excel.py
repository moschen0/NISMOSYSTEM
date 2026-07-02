"""Importa informações de endereço de um arquivo Excel para a tabela `etiq_clients`.

Uso:
  python import_clients_from_excel.py --excel Clientes.xlsx

O script tenta localizar uma coluna de chave do cliente (ex: numero_cliente, cliente_codigo, id)
e atualiza os registros existentes na tabela `etiq_clients`. Colunas que não existirem
serão adicionadas como `TEXT(255)`.

Configuração:
  - Requer `pandas`, `openpyxl` e `pyodbc` instalados no mesmo ambiente Python.
  - Detecta automaticamente bancos em `WMS_BD/wms_database_test.mdb` e
    `WMS_BD/wms_database.mdb` (se existirem). Você pode passar caminhos customizados.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import pandas as pd

try:
    import pyodbc
except Exception as e:
    print("Erro: pyodbc não está instalado. Instale com: pip install pyodbc")
    raise


DEFAULT_DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]


def find_dbs(explicit: list[str]) -> list[Path]:
    if explicit:
        return [Path(p) for p in explicit]
    existing = [p for p in DEFAULT_DB_CANDIDATES if p.exists()]
    return existing


def connect_access(db_path: Path):
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve())
    )
    return pyodbc.connect(conn_str, autocommit=False)


def table_has_column(cursor, table_name: str, column_name: str) -> bool:
    try:
        cursor.columns(table=table_name, column=column_name)
        return cursor.fetchone() is not None
    except Exception:
        return False


def add_column(cursor, table_name: str, column_name: str):
    ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT(255)"
    try:
        cursor.execute(ddl)
    except Exception as e:
        # tentar ignorar se a coluna já existir por concorrência
        print(f"Aviso adicionando coluna {column_name}: {e}")


def get_existing_columns(cursor, table_name: str) -> set[str]:
    cols = set()
    try:
        for row in cursor.columns(table=table_name):
            cols.add(row.column_name)
    except Exception:
        pass
    return cols


POSSIBLE_KEY_NAMES = [
    "numero_cliente",
    "codigo_cliente",
    "cliente_codigo",
    "cliente_id",
    "id",
    "codigo",
    "numero",
]


def detect_key_column(df: pd.DataFrame) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for key in POSSIBLE_KEY_NAMES:
        if key in lower:
            return lower[key]
    return None


def upsert_row(cursor, table: str, key_col: str, key_val, data: dict):
    # busca registro existente
    cursor.execute(f"SELECT TOP 1 id FROM {table} WHERE {key_col} = ?", (key_val,))
    row = cursor.fetchone()
    now = None
    if row:
        # UPDATE
        set_parts = ", ".join([f"{k} = ?" for k in data.keys()])
        params = list(data.values()) + [int(row[0])]
        sql = f"UPDATE {table} SET {set_parts}, updated_at = ? WHERE id = ?"
        # updated_at
        from datetime import datetime

        params.insert(len(data), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cursor.execute(sql, params)
    else:
        # INSERT: incluir campo chave e created_at/updated_at
        cols = [key_col] + list(data.keys()) + ["created_at", "updated_at"]
        placeholders = ", ".join(["?" for _ in cols])
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        from datetime import datetime

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        params = [key_val] + list(data.values()) + [now, now]
        cursor.execute(sql, params)


def process_db(db_path: Path, df: pd.DataFrame, table_name: str = "etiq_clients"):
    print(f"Conectando: {db_path}")
    conn = connect_access(db_path)
    cursor = conn.cursor()

    existing_cols = get_existing_columns(cursor, table_name)
    to_add = [c for c in df.columns if c not in existing_cols]
    if to_add:
        print(f"Adicionando colunas em {db_path}: {to_add}")
        for col in to_add:
            add_column(cursor, table_name, col)
        conn.commit()

    key_col = detect_key_column(df)
    if key_col is None:
        raise RuntimeError(
            "Não foi possível detectar uma coluna de chave do cliente no Excel."
            " Renomeie a coluna para 'numero_cliente' ou passe um arquivo com essa coluna."
        )

    # normalizar key values
    for idx, row in df.iterrows():
        raw_key = row.get(key_col)
        if pd.isna(raw_key):
            continue
        try:
            key_val = int(str(raw_key).strip())
        except Exception:
            key_val = str(raw_key).strip()
        data = {}
        for col in df.columns:
            if col == key_col:
                continue
            val = row.get(col)
            if pd.isna(val):
                val = None
            else:
                val = str(val).strip()
            data[col] = val

        try:
            upsert_row(cursor, table_name, key_col, key_val, data)
        except Exception as e:
            print(f"Erro ao persistir {key_val} em {db_path}: {e}")

    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", required=True, help="Caminho para o arquivo Excel (.xlsx)")
    parser.add_argument("--db", action="append", help="Caminho para um arquivo .mdb/.accdb. Pode ser usado múltiplas vezes.")
    parser.add_argument("--sheet", default=None, help="Nome da planilha (opcional)")
    args = parser.parse_args()

    excel_path = Path(args.excel)
    if not excel_path.exists():
        print("Arquivo Excel não encontrado:", excel_path)
        sys.exit(1)

    try:
        if args.sheet:
            df = pd.read_excel(excel_path, sheet_name=args.sheet, engine="openpyxl")
        else:
            # ler a primeira planilha por padrão
            df = pd.read_excel(excel_path, sheet_name=0, engine="openpyxl")
    except Exception as e:
        print("Erro ao ler Excel:", e)
        sys.exit(1)

    # normalizar nomes de colunas: remover espaços e padronizar minusculas mas preservar original
    cleaned_cols = [str(c).strip() for c in df.columns]
    df.columns = cleaned_cols

    dbs = find_dbs(args.db or [])
    if not dbs:
        print("Nenhum arquivo de banco encontrado automaticamente. Passe --db caminhos para os .mdb/.accdb")
        sys.exit(1)

    for db in dbs:
        try:
            process_db(db, df)
        except Exception as e:
            print(f"Erro processando {db}: {e}")


if __name__ == "__main__":
    main()
