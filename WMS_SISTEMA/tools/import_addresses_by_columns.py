"""Importa colunas A-D do Excel (A=CODIGO, B=NOME, C=ENDERECO, D=CIDADE)
e atualiza `etiq_clients` nos MDBs do projeto.

Uso: python import_addresses_by_columns.py --excel clientes.xlsx
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import pandas as pd
import pyodbc

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]


def connect(db_path: Path):
    return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()), autocommit=False)


def find_record(cursor, codigo, nome):
    # Try match by codigo (numero_cliente or codigo_cliente), then by nome
    try:
        cursor.execute("SELECT TOP 1 id FROM etiq_clients WHERE CStr(codigo_cliente)=? OR CStr(numero_cliente)=?", (str(codigo), str(codigo)))
        r = cursor.fetchone()
        if r:
            return int(r[0])
    except Exception:
        pass
    try:
        cursor.execute("SELECT TOP 1 id FROM etiq_clients WHERE nome_cliente = ?", (nome,))
        r = cursor.fetchone()
        if r:
            return int(r[0])
    except Exception:
        pass
    return None


def process_db(db_path: Path, rows):
    print(f"Processing DB: {db_path}")
    if not db_path.exists():
        print("  not found")
        return
    conn = connect(db_path)
    cur = conn.cursor()
    updated = 0
    inserted = 0
    for codigo, nome, endereco, cidade in rows:
        if pd.isna(codigo) and pd.isna(nome):
            continue
        codigo_val = None
        if not pd.isna(codigo):
            codigo_val = str(codigo).strip()
        nome_val = None
        if not pd.isna(nome):
            nome_val = str(nome).strip()
        endereco_val = None
        if not pd.isna(endereco):
            endereco_val = str(endereco).strip()
        cidade_val = None
        if not pd.isna(cidade):
            cidade_val = str(cidade).strip()

        rec_id = find_record(cur, codigo_val, nome_val)
        try:
            if rec_id:
                # update
                updates = []
                params = []
                if endereco_val is not None:
                    updates.append("endereco = ?")
                    params.append(endereco_val)
                if cidade_val is not None:
                    updates.append("cidade = ?")
                    params.append(cidade_val)
                if nome_val is not None:
                    updates.append("nome_cliente = ?")
                    params.append(nome_val)
                if updates:
                    params.append(rec_id)
                    sql = f"UPDATE etiq_clients SET {', '.join(updates)}, updated_at = ? WHERE id = ?"
                    from datetime import datetime
                    params.insert(len(params)-1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    cur.execute(sql, params)
                    updated += 1
            else:
                # insert
                cols = []
                vals = []
                if codigo_val is not None:
                    cols.append('codigo_cliente')
                    vals.append(codigo_val)
                if nome_val is not None:
                    cols.append('nome_cliente')
                    vals.append(nome_val)
                if endereco_val is not None:
                    cols.append('endereco')
                    vals.append(endereco_val)
                if cidade_val is not None:
                    cols.append('cidade')
                    vals.append(cidade_val)
                from datetime import datetime
                cols += ['created_at', 'updated_at']
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                vals += [now, now]
                placeholders = ', '.join(['?' for _ in cols])
                sql = f"INSERT INTO etiq_clients ({', '.join(cols)}) VALUES ({placeholders})"
                cur.execute(sql, vals)
                inserted += 1
        except Exception as e:
            print(f"  error processing codigo={codigo_val} nome={nome_val}: {e}")
    conn.commit()
    conn.close()
    print(f"  updated={updated} inserted={inserted}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--excel', required=True)
    parser.add_argument('--sheet', default=0)
    args = parser.parse_args()
    excel = Path(args.excel)
    if not excel.exists():
        print('excel not found:', excel)
        sys.exit(1)
    df = pd.read_excel(excel, sheet_name=args.sheet, engine='openpyxl', header=0)
    # read columns by position: A=0, B=1, C=2, D=3
    rows = []
    for idx in range(len(df)):
        row = df.iloc[idx]
        def get_col(i):
            try:
                return row.iat[i]
            except Exception:
                return None
        codigo = get_col(0)
        nome = get_col(1)
        endereco = get_col(2)
        cidade = get_col(3)
        rows.append((codigo, nome, endereco, cidade))

    for db in DB_CANDIDATES:
        process_db(db, rows)


if __name__ == '__main__':
    main()
