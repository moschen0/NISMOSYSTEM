"""Verifica contagem e mostra amostra de `etiq_clients` em bancos Access do projeto."""
from pathlib import Path
import pyodbc

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]


def connect(db_path: Path):
    conn_str = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve())
    return pyodbc.connect(conn_str)


def describe_db(db_path: Path):
    print(f"\n== {db_path} ==")
    if not db_path.exists():
        print("  arquivo não encontrado")
        return
    try:
        conn = connect(db_path)
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM etiq_clients")
            cnt = cur.fetchone()[0]
            print(f"  count(etiq_clients) = {cnt}")
        except Exception as e:
            print(f"  erro ao contar tabela: {e}")
            cnt = 0

        try:
            cur.execute("SELECT TOP 5 * FROM etiq_clients")
            rows = cur.fetchall()
            if not rows:
                print("  tabela vazia ou sem resultados")
            else:
                cols = [c[0] for c in cur.description] if cur.description else []
                print("  colunas:", cols)
                for r in rows:
                    print("   ", dict(zip(cols, r)))
        except Exception as e:
            print(f"  erro ao ler amostra: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    for p in DB_CANDIDATES:
        describe_db(p)


if __name__ == '__main__':
    main()
