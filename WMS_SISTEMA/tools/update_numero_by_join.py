"""Atualiza `numero_cliente` usando JOIN por `nome_cliente` dentro de `etiq_clients`."""
from pathlib import Path
import pyodbc

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]


def connect(db_path: Path):
    return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()), autocommit=True)


def process(db_path: Path):
    print(f"Processing {db_path}")
    if not db_path.exists():
        print("  not found")
        return
    conn = connect(db_path)
    cur = conn.cursor()
    try:
        sql = (
            "UPDATE etiq_clients AS target "
            "INNER JOIN etiq_clients AS src "
            "ON target.nome_cliente = src.nome_cliente "
            "SET target.numero_cliente = src.numero_cliente "
            "WHERE target.numero_cliente IS NULL AND src.numero_cliente IS NOT NULL"
        )
        cur.execute(sql)
        print("  update executed")
    except Exception as e:
        print("  error executing update:", e)
    finally:
        conn.close()


def main():
    for db in DB_CANDIDATES:
        process(db)


if __name__ == '__main__':
    main()
