"""Insere clientes do Excel que não existem em `etiq_clients`.

Colunas do Excel esperadas por posição:
 A = CODIGO, B = NOME DO CLIENTE, C = ENDERECO, D = CIDADE

Executa check por `codigo_cliente`/`numero_cliente` ou `nome_cliente`.
Se não existir, insere com `codigo_cliente`, `nome_cliente`, `endereco`, `cidade`.
Se `codigo` for numérico, também preenche `numero_cliente`.

Gera CSV com os registros inseridos em `WMS_SISTEMA/tools/inserted_clients.csv`.
"""
from __future__ import annotations

from pathlib import Path
import csv
from datetime import datetime
import sys
import pandas as pd
import pyodbc

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]

OUTPUT_CSV = Path("WMS_SISTEMA/tools/inserted_clients.csv")


def connect(db_path: Path):
    return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()), autocommit=False)


def exists_in_db(cursor, codigo, nome):
    # check by codigo in codigo_cliente or numero_cliente
    try:
        if codigo is not None and str(codigo).strip() != "":
            cursor.execute("SELECT TOP 1 id FROM etiq_clients WHERE CStr(codigo_cliente)=? OR CStr(numero_cliente)=?", (str(codigo).strip(), str(codigo).strip()))
            if cursor.fetchone():
                return True
    except Exception:
        pass
    # check by exact name
    try:
        if nome is not None and str(nome).strip() != "":
            cursor.execute("SELECT TOP 1 id FROM etiq_clients WHERE nome_cliente = ?", (str(nome).strip(),))
            if cursor.fetchone():
                return True
    except Exception:
        pass
    return False


def insert_into_db(cursor, codigo, nome, endereco, cidade):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cols = []
    vals = []
    if codigo is not None and str(codigo).strip() != "":
        cols.append("codigo_cliente")
        vals.append(str(codigo).strip())
        # if numeric, set numero_cliente
        try:
            num = int(str(codigo).strip())
            cols.append("numero_cliente")
            vals.append(num)
        except Exception:
            pass
    if nome is not None and str(nome).strip() != "":
        cols.append("nome_cliente")
        vals.append(str(nome).strip())
    if endereco is not None and str(endereco).strip() != "":
        cols.append("endereco")
        vals.append(str(endereco).strip())
    if cidade is not None and str(cidade).strip() != "":
        cols.append("cidade")
        vals.append(str(cidade).strip())
    cols += ["created_at", "updated_at"]
    vals += [now, now]
    placeholders = ", ".join(["?" for _ in cols])
    sql = f"INSERT INTO etiq_clients ({', '.join(cols)}) VALUES ({placeholders})"
    cursor.execute(sql, vals)


def main():
    excel = Path("Clientes.xlsx")
    if not excel.exists():
        print("Arquivo Clientes.xlsx não encontrado no workspace root.")
        sys.exit(1)
    df = pd.read_excel(excel, sheet_name=0, engine="openpyxl", header=0)
    rows = []
    for i in range(len(df)):
        row = df.iloc[i]
        def get(i):
            try:
                return row.iat[i]
            except Exception:
                return None
        codigo = get(0)
        nome = get(1)
        endereco = get(2)
        cidade = get(3)
        rows.append((codigo, nome, endereco, cidade))

    inserted_records = []
    for db in DB_CANDIDATES:
        if not db.exists():
            print(f"DB not found: {db}")
            continue
        conn = connect(db)
        cur = conn.cursor()
        inserted = 0
        for codigo, nome, endereco, cidade in rows:
            try:
                if exists_in_db(cur, codigo, nome):
                    continue
                insert_into_db(cur, codigo, nome, endereco, cidade)
                inserted += 1
                inserted_records.append({
                    "db": str(db),
                    "codigo": codigo,
                    "nome_cliente": nome,
                    "endereco": endereco,
                    "cidade": cidade,
                })
            except Exception as e:
                print(f"Error inserting into {db}: {e}")
        conn.commit()
        conn.close()
        print(f"Inserted into {db}: {inserted}")

    # write CSV report
    if inserted_records:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_CSV.open("w", newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["db", "codigo", "nome_cliente", "endereco", "cidade"])
            writer.writeheader()
            for r in inserted_records:
                writer.writerow(r)
        print(f"Report written: {OUTPUT_CSV}")
    else:
        print("No new records inserted.")


if __name__ == '__main__':
    main()
