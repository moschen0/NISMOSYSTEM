"""Popula colunas de endereço em `etiq_clients` a partir de um Excel.

Uso:
  python populate_addresses_from_excel.py --excel clientes.xlsx

Mapeia colunas comuns do Excel para: endereco, numero, complemento, bairro,
cidade, estado, cep e atualiza/insere registros em `etiq_clients` nos MDBs.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
import pandas as pd

import pyodbc

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]

ADDRESS_TARGETS = ["endereco", "numero", "complemento", "bairro", "cidade", "estado", "cep"]

EXCEL_TO_TARGET = {
    # endereco
    "endereco": "endereco",
    "logradouro": "endereco",
    "rua": "endereco",
    "endereco_completo": "endereco",
    # numero
    "numero": "numero",
    "número": "numero",
    "num": "numero",
    # complemento
    "complemento": "complemento",
    # bairro
    "bairro": "bairro",
    # cidade
    "cidade": "cidade",
    "municipio": "cidade",
    # estado
    "estado": "estado",
    "uf": "estado",
    # cep
    "cep": "cep",
    "codigo_postal": "cep",
}

KEY_NAMES = ["numero_cliente", "codigo_cliente", "cliente_codigo", "id", "codigo"]


def connect(db_path: Path):
    return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()), autocommit=False)


def normalize_col_name(name: str) -> str:
    return str(name or "").strip().lower()


def build_mapping(df: pd.DataFrame) -> dict[str, str]:
    mapping = {}
    lower_cols = {normalize_col_name(c): c for c in df.columns}
    for k, target in EXCEL_TO_TARGET.items():
        if k in lower_cols:
            mapping[lower_cols[k]] = target
    # also include exact target names if present
    for col in df.columns:
        if normalize_col_name(col) in ADDRESS_TARGETS:
            mapping[col] = normalize_col_name(col)
    return mapping


def detect_key_in_row(row, df_columns):
    # prefer numero_cliente then codigo_cliente
    for key in KEY_NAMES:
        for col in df_columns:
            if normalize_col_name(col) == key and not pd.isna(row.get(col)):
                return col
    # fallback: if dataframe has a column named 'codigo' or similar
    for col in df_columns:
        if normalize_col_name(col) in ("codigo", "codigo_cliente") and not pd.isna(row.get(col)):
            return col
    return None


def upsert_address_for_row(cursor, table: str, key_col_name: str, key_val, data: dict):
    # Try to find existing record by numero_cliente or codigo_cliente
    cursor.execute(f"SELECT TOP 1 id, numero_cliente, codigo_cliente FROM {table} WHERE numero_cliente = ? OR CStr(codigo_cliente) = ?", (key_val, str(key_val)))
    row = cursor.fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if row:
        rec_id = int(row[0])
        set_parts = ", ".join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_parts}, updated_at = ? WHERE id = ?"
        params = list(data.values()) + [now, rec_id]
        cursor.execute(sql, params)
    else:
        # Insert a new row: include key column (prefer numero_cliente numeric), plus address fields
        cols = []
        vals = []
        if str(key_col_name).strip().lower() == "numero_cliente":
            cols.append("numero_cliente")
            try:
                vals.append(int(key_val))
            except Exception:
                vals.append(None)
        else:
            cols.append("codigo_cliente")
            vals.append(str(key_val))

        for k, v in data.items():
            cols.append(k)
            vals.append(v)
        cols += ["created_at", "updated_at"]
        vals += [now, now]
        placeholders = ", ".join(["?" for _ in cols])
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        cursor.execute(sql, vals)


def process_db(db_path: Path, df: pd.DataFrame, mapping: dict[str, str]):
    print(f"Processing DB: {db_path}")
    if not db_path.exists():
        print("  not found")
        return
    conn = connect(db_path)
    cur = conn.cursor()
    updated = 0
    for idx, row in df.iterrows():
        key_col = detect_key_in_row(row, df.columns)
        if key_col is None:
            continue
        raw_key = row.get(key_col)
        if pd.isna(raw_key):
            continue
        key_val = str(raw_key).strip()
        data = {}
        for excel_col, target in mapping.items():
            val = row.get(excel_col)
            if pd.isna(val):
                continue
            data[target] = str(val).strip()
        if not data:
            continue
        try:
            upsert_address_for_row(cur, 'etiq_clients', key_col, key_val, data)
            updated += 1
        except Exception as e:
            print(f"  error updating key {key_val} in {db_path}: {e}")
    conn.commit()
    conn.close()
    print(f"  updated/inserted rows: {updated}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--excel', required=True)
    parser.add_argument('--sheet', default=None)
    args = parser.parse_args()

    excel = Path(args.excel)
    if not excel.exists():
        print('excel not found:', excel)
        sys.exit(1)
    if args.sheet:
        df = pd.read_excel(excel, sheet_name=args.sheet, engine='openpyxl')
    else:
        df = pd.read_excel(excel, sheet_name=0, engine='openpyxl')

    df.columns = [str(c).strip() for c in df.columns]
    mapping = build_mapping(df)
    if not mapping:
        print('Nenhum mapeamento de colunas detectado entre Excel e campos de endereco.')
        print('Colunas do Excel:', list(df.columns))
        sys.exit(1)

    print('Detected mapping:')
    for k, v in mapping.items():
        print('  ', k, '->', v)

    for db in DB_CANDIDATES:
        process_db(db, df, mapping)


if __name__ == '__main__':
    main()
