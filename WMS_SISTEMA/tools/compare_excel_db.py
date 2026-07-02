"""Compara `Clientes.xlsx` com `etiq_clients` nos MDBs usando similaridade de nome.

Gera CSV: `WMS_SISTEMA/tools/compare_report.csv` com melhores matches por DB.
"""
from __future__ import annotations

from pathlib import Path
import csv
import sys
from difflib import SequenceMatcher
import pandas as pd
import pyodbc

DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]

REPORT_CSV = Path("WMS_SISTEMA/tools/compare_report.csv")


def normalize(s: str) -> str:
    if s is None:
        return ""
    return " ".join(str(s).strip().lower().split())


def load_db_entries(db_path: Path) -> list[dict]:
    entries = []
    if not db_path.exists():
        return entries
    conn = pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()))
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, numero_cliente, nome_cliente, endereco, cidade FROM etiq_clients WHERE nome_cliente IS NOT NULL")
        for r in cur.fetchall():
            entries.append({
                "id": r[0],
                "numero": r[1],
                "nome": r[2],
                "endereco": r[3],
                "cidade": r[4],
                "norm_nome": normalize(r[2]),
            })
    finally:
        conn.close()
    return entries


def best_match(name: str, entries: list[dict]) -> tuple[dict|None, float]:
    if not name or not entries:
        return None, 0.0
    n = normalize(name)
    best = None
    best_score = 0.0
    for e in entries:
        score = SequenceMatcher(None, n, e["norm_nome"]).ratio()
        if score > best_score:
            best_score = score
            best = e
    return best, best_score


def main(threshold: float = 0.8):
    excel = Path("Clientes.xlsx")
    if not excel.exists():
        print("Clientes.xlsx not found")
        sys.exit(1)
    df = pd.read_excel(excel, sheet_name=0, engine="openpyxl", header=0)
    # read rows
    rows = []
    for i in range(len(df)):
        row = df.iloc[i]
        def get(i):
            try:
                return row.iat[i]
            except Exception:
                return None
        rows.append({
            "codigo": get(0),
            "nome": get(1),
            "endereco": get(2),
            "cidade": get(3),
        })

    # load DB entries per DB
    db_entries = {str(db): load_db_entries(db) for db in DB_CANDIDATES}

    REPORT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_CSV.open("w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "excel_codigo", "excel_nome", "excel_endereco", "excel_cidade",
            "db", "db_id", "db_numero", "db_nome", "db_endereco", "db_cidade",
            "score", "matched"
        ])
        writer.writeheader()
        for r in rows:
            for db, entries in db_entries.items():
                best, score = best_match(r["nome"], entries)
                matched = score >= threshold
                writer.writerow({
                    "excel_codigo": r["codigo"],
                    "excel_nome": r["nome"],
                    "excel_endereco": r["endereco"],
                    "excel_cidade": r["cidade"],
                    "db": db,
                    "db_id": best["id"] if best else None,
                    "db_numero": best["numero"] if best else None,
                    "db_nome": best["nome"] if best else None,
                    "db_endereco": best["endereco"] if best else None,
                    "db_cidade": best["cidade"] if best else None,
                    "score": round(score, 3),
                    "matched": matched,
                })

    print(f"Report written: {REPORT_CSV}")


if __name__ == '__main__':
    main(0.8)
