"""Conta registros em que `numero_cliente` está ausente em cada MDB."""
from pathlib import Path
import pyodbc

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]


def connect(db_path: Path):
    return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()))


def process(db_path: Path):
    print(f"\n== {db_path} ==")
    if not db_path.exists():
        print("  not found")
        return
    conn = connect(db_path)
    cur = conn.cursor()
    try:
        # Avoid CStr on NULL values; count rows where numero_cliente IS NULL
        cur.execute("SELECT COUNT(*) FROM etiq_clients WHERE numero_cliente IS NULL")
        cnt = cur.fetchone()[0]
        print(f"  missing numero_cliente (NULL): {cnt}")
        if cnt > 0:
            cur.execute("SELECT TOP 10 id, nome_cliente, codigo_cliente FROM etiq_clients WHERE numero_cliente IS NULL")
            for r in cur.fetchall():
                print("   ", r[0], r[1], r[2])
    except Exception as e:
        print("  error:", e)
    finally:
        conn.close()


def main():
    for db in DB_CANDIDATES:
        process(db)


if __name__ == '__main__':
    main()
