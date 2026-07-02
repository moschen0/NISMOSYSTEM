"""Preenche `numero_cliente` usando correspondência fuzzy em `nome_cliente`.

Uso: python fill_numero_by_fuzzy.py --threshold 80
"""
from pathlib import Path
import pyodbc
import argparse
from difflib import SequenceMatcher, get_close_matches

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]


def normalize(s):
    if s is None:
        return ""
    return " ".join(str(s).strip().lower().split())


def connect(db_path: Path):
    return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()), autocommit=False)


def best_match(name, candidates, cutoff):
    name_norm = normalize(name)
    if not name_norm:
        return None, 0.0
    # try get_close_matches first
    keys = list(candidates.keys())
    close = get_close_matches(name_norm, keys, n=5, cutoff=cutoff)
    best = None
    best_score = 0.0
    for k in close:
        score = SequenceMatcher(None, name_norm, k).ratio()
        if score > best_score:
            best_score = score
            best = k
    # if none found by get_close_matches, try scanning for a best score (slower)
    if best is None:
        for k in keys:
            score = SequenceMatcher(None, name_norm, k).ratio()
            if score > best_score:
                best_score = score
                best = k
    return best, best_score


def process(db_path: Path, threshold: float):
    print(f"Processing {db_path}")
    if not db_path.exists():
        print("  file not found")
        return
    conn = connect(db_path)
    cur = conn.cursor()
    # build candidate map: normalized nome -> numero_cliente (choose first non-null)
    candidates = {}
    try:
        cur.execute("SELECT numero_cliente, nome_cliente FROM etiq_clients WHERE nome_cliente IS NOT NULL")
        for row in cur.fetchall():
            numero = row[0]
            nome = row[1]
            if nome is None:
                continue
            key = normalize(nome)
            if key and numero is not None and key not in candidates:
                candidates[key] = numero
    except Exception as e:
        print("  error reading candidates:", e)
        conn.close()
        return

    # find rows missing numero_cliente
    try:
        cur.execute("SELECT id, nome_cliente FROM etiq_clients WHERE numero_cliente IS NULL AND nome_cliente IS NOT NULL")
    except Exception as e:
        print("  error selecting missing rows:", e)
        conn.close()
        return

    rows = cur.fetchall()
    updated = 0
    for r in rows:
        rid = int(r[0])
        nome = r[1]
        if not nome:
            continue
        match_key, score = best_match(nome, candidates, cutoff=threshold/100.0)
        if match_key and score >= (threshold / 100.0):
            numero_val = candidates.get(match_key)
            try:
                cur.execute("UPDATE etiq_clients SET numero_cliente = ? WHERE id = ?", (int(numero_val), rid))
                updated += 1
            except Exception as e:
                print(f"  error updating id {rid}: {e}")
    conn.commit()
    conn.close()
    print(f"  updated rows: {updated}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--threshold', type=int, default=80, help='Matching threshold percentage (0-100)')
    args = parser.parse_args()
    thr = max(0, min(100, args.threshold))
    for db in DB_CANDIDATES:
        process(db, thr)


if __name__ == '__main__':
    main()
