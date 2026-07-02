"""Copia `codigo_cliente` para `numero_cliente` quando este estiver vazio.

Uso: python copy_codigo_to_numero.py
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
    # select rows where numero_cliente is null or empty and codigo_cliente is not null
    try:
        cur.execute("SELECT id, codigo_cliente FROM etiq_clients WHERE (numero_cliente IS NULL OR CStr(numero_cliente) = '') AND codigo_cliente IS NOT NULL")
    except Exception as e:
        print(f"  error selecting rows: {e}")
        conn.close()
        return
    rows = cur.fetchall()
    updated = 0
    for r in rows:
        rec_id = r[0]
        codigo = r[1]
        if codigo is None:
            continue
        codigo_str = str(codigo).strip()
        if not codigo_str:
            continue
        # try to parse integer
        try:
            num = int(codigo_str)
        except Exception:
            # skip non-numeric codes
            continue
        try:
            cur.execute("UPDATE etiq_clients SET numero_cliente = ? WHERE id = ?", (num, rec_id))
            updated += 1
        except Exception as e:
            print(f"  error updating id {rec_id}: {e}")
    conn.commit()
    conn.close()
    print(f"  updated rows: {updated}")


def main():
    for db in DB_CANDIDATES:
        process(db)


if __name__ == '__main__':
    main()
