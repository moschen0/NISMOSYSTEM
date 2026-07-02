"""Adiciona colunas de endereço em `etiq_clients` para todos MDBs detectados."""
from pathlib import Path
import pyodbc

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]

ADDRESS_COLUMNS = [
    "endereco",
    "numero",
    "complemento",
    "bairro",
    "cidade",
    "estado",
    "cep",
]


def connect(db_path: Path):
    conn_str = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve())
    return pyodbc.connect(conn_str, autocommit=True)


def column_exists(cursor, table, column):
    try:
        cursor.columns(table=table, column=column)
        return cursor.fetchone() is not None
    except Exception:
        return False


def add_columns_to_db(db_path: Path):
    print(f"Processing {db_path}")
    if not db_path.exists():
        print("  file not found")
        return
    conn = connect(db_path)
    cur = conn.cursor()
    for col in ADDRESS_COLUMNS:
        if not column_exists(cur, 'etiq_clients', col):
            try:
                cur.execute(f"ALTER TABLE etiq_clients ADD COLUMN {col} TEXT(255)")
                print(f"  added {col}")
            except Exception as e:
                print(f"  error adding {col}: {e}")
        else:
            print(f"  exists {col}")
    conn.close()


def main():
    for p in DB_CANDIDATES:
        add_columns_to_db(p)


if __name__ == '__main__':
    main()
