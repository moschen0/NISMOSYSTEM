"""Remove registros duplicados em `etiq_clients`.

Lógica: faz backup dos arquivos MDB, identifica duplicados por chave
(lower(nome_cliente), lower(endereco), lower(codigo_cliente)) e remove todos
exceto o registro com menor `id` em cada grupo.
"""
from pathlib import Path
import shutil
import pyodbc
import datetime

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]


def backup_file(p: Path) -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = p.with_suffix(p.suffix + f".bak_{ts}")
    shutil.copy2(p, dest)
    return dest


def normalize(val):
    if val is None:
        return ""
    return str(val).strip().lower()


def connect(db_path: Path):
    return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()), autocommit=False)


def process(db_path: Path):
    print(f"\nProcessing {db_path}")
    if not db_path.exists():
        print("  file not found")
        return
    bak = backup_file(db_path)
    print(f"  backup created: {bak.name}")
    conn = connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, nome_cliente, endereco, codigo_cliente FROM etiq_clients")
    except Exception as e:
        print("  error reading table:", e)
        conn.close()
        return
    rows = cur.fetchall()
    groups = {}
    for r in rows:
        rid = int(r[0])
        nome = normalize(r[1])
        endereco = normalize(r[2])
        codigo = normalize(r[3])
        key = (nome, endereco, codigo)
        groups.setdefault(key, []).append(rid)

    to_delete = []
    for key, ids in groups.items():
        if len(ids) > 1:
            ids_sorted = sorted(ids)
            # keep smallest id, delete the rest
            keep = ids_sorted[0]
            dels = ids_sorted[1:]
            to_delete.extend(dels)

    if not to_delete:
        print("  no duplicates found")
        conn.close()
        return

    print(f"  duplicates to delete: {len(to_delete)}")
    deleted = 0
    for rid in to_delete:
        try:
            cur.execute("DELETE FROM etiq_clients WHERE id = ?", (rid,))
            deleted += 1
        except Exception as e:
            print(f"   error deleting id {rid}: {e}")
    conn.commit()
    conn.close()
    print(f"  deleted: {deleted}")


def main():
    for db in DB_CANDIDATES:
        process(db)


if __name__ == '__main__':
    main()
