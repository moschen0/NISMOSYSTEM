"""Preenche `numero_cliente` em `etiq_clients` fazendo match exato por `nome_cliente`.

Uso: python fill_numero_by_name.py
"""
from pathlib import Path
import pyodbc

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]


def connect(db_path: Path):
    return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()), autocommit=False)


def process(db_path: Path):
    print(f"Processing {db_path}")
    if not db_path.exists():
        print("  not found")
        return
    conn = connect(db_path)
    cur = conn.cursor()
    # find rows missing numero_cliente but with nome_cliente
    try:
        cur.execute("SELECT id, nome_cliente FROM etiq_clients WHERE (numero_cliente IS NULL OR CStr(numero_cliente)='') AND nome_cliente IS NOT NULL")
    except Exception as e:
        print("  error selecting rows:", e)
        conn.close()
        return
    rows = cur.fetchall()
    updated = 0
    for r in rows:
        rec_id = r[0]
        nome = r[1]
        if not nome:
            continue
        try:
            cur.execute("SELECT TOP 1 numero_cliente FROM etiq_clients WHERE nome_cliente = ? AND numero_cliente IS NOT NULL ORDER BY id DESC", (nome,))
            found = cur.fetchone()
            if found and found[0] is not None:
                num = found[0]
                try:
                    cur.execute("UPDATE etiq_clients SET numero_cliente = ? WHERE id = ?", (int(num), rec_id))
                    updated += 1
                except Exception as e:
                    print(f"  error updating id {rec_id}: {e}")
        except Exception as e:
            print(f"  error querying match for '{nome}': {e}")
    conn.commit()
    conn.close()
    print(f"  updated rows: {updated}")


def main():
    for db in DB_CANDIDATES:
        process(db)


if __name__ == '__main__':
    main()
