"""Gera um preview com até N registros por banco mostrando campos principais."""
from pathlib import Path
import pyodbc
from datetime import datetime

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]

FIELDS = ["id", "numero_cliente", "codigo_cliente", "nome_cliente", "endereco", "numero", "complemento", "bairro", "cidade", "estado", "cep"]


def connect(db_path: Path):
    return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()))


def preview_db(db_path: Path, limit=20):
    print(f"\n== Preview {db_path} ==")
    if not db_path.exists():
        print("  arquivo não encontrado")
        return
    conn = connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT {', '.join(FIELDS)} FROM etiq_clients WHERE endereco IS NOT NULL ORDER BY id ASC")
    except Exception:
        try:
            cur.execute(f"SELECT {', '.join(FIELDS)} FROM etiq_clients ORDER BY id ASC")
        except Exception as e:
            print("  erro lendo tabela:", e)
            conn.close()
            return
    rows = cur.fetchmany(limit)
    if not rows:
        print("  sem registros para mostrar")
        conn.close()
        return
    # print header
    print("  | " + " | ".join(FIELDS))
    for r in rows:
        vals = [str(v) if v is not None else "" for v in r]
        print("  | " + " | ".join(vals))
    conn.close()


def main():
    for db in DB_CANDIDATES:
        preview_db(db, limit=20)


if __name__ == '__main__':
    main()
