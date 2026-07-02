"""Importa `clientes 0207.csv` para `etiq_clients`.

Operacao:
- cria backup dos MDBs antes de alterar;
- garante colunas de endereco/CNPJ/telefone;
- limpa os dados antigos dessas colunas;
- atualiza/insere usando CLICODIGO como codigo do cliente.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import pyodbc


DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]

TEXT_COLUMNS = [
    "codigo_cliente",
    "cnpj_cpf",
    "tipo_rua",
    "rua",
    "endereco",
    "numero",
    "complemento",
    "bairro",
    "cep",
    "cidade",
    "estado",
    "telefone",
    "telefone2",
    "telefone_fax",
    "celular",
    "inscricao_estadual",
    "data_cadastro",
]

RESET_COLUMNS = [
    "cnpj_cpf",
    "tipo_rua",
    "rua",
    "endereco",
    "numero",
    "complemento",
    "bairro",
    "cep",
    "cidade",
    "estado",
    "telefone",
    "telefone2",
    "telefone_fax",
    "celular",
    "inscricao_estadual",
    "data_cadastro",
]


def connect(db_path: Path):
    conn_str = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve())
    return pyodbc.connect(conn_str, autocommit=False)


def column_exists(cursor, table: str, column: str) -> bool:
    try:
        cursor.columns(table=table, column=column)
        return cursor.fetchone() is not None
    except Exception:
        return False


def table_columns(cursor, table: str) -> set[str]:
    return {str(row.column_name).lower() for row in cursor.columns(table=table)}


def add_missing_columns(cursor):
    existing = table_columns(cursor, "etiq_clients")
    for column in TEXT_COLUMNS:
        if column.lower() not in existing:
            cursor.execute(f"ALTER TABLE etiq_clients ADD COLUMN {column} TEXT(255)")
            existing.add(column.lower())


def read_csv_rows(csv_path: Path):
    last_error = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            with csv_path.open("r", newline="", encoding=encoding) as file:
                reader = csv.DictReader(file, delimiter=";")
                rows = list(reader)
                if rows and "CLICODIGO" in rows[0]:
                    return rows, encoding
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Nao foi possivel ler CSV: {last_error}")


def clean(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\ufeff", "").strip().split())


def build_record(row: dict) -> dict:
    codigo = clean(row.get("CLICODIGO"))
    tipo_rua = clean(row.get("ENDTPRUA"))
    rua = clean(row.get("ENDENDERECO"))
    numero = clean(row.get("ENDNR"))
    complemento = clean(row.get("ENDCOMPLE"))
    bairro = clean(row.get("ENDBAIRRO"))
    endereco_parts = [tipo_rua, rua]
    endereco = " ".join(part for part in endereco_parts if part)
    return {
        "codigo_cliente": codigo,
        "numero_cliente": int(codigo) if codigo.isdigit() else None,
        "nome_cliente": clean(row.get("CLINOMEFANT")),
        "cnpj_cpf": clean(row.get("CLICNPJCPF")),
        "tipo_rua": tipo_rua,
        "rua": rua,
        "endereco": endereco,
        "numero": numero,
        "complemento": complemento,
        "bairro": bairro,
        "cep": clean(row.get("ENDCEP")),
        "cidade": clean(row.get("CIDNOME")),
        "estado": clean(row.get("CIDUF")),
        "telefone": clean(row.get("FONE")),
        "telefone2": clean(row.get("FONE2")),
        "telefone_fax": clean(row.get("FONEFAX")),
        "celular": clean(row.get("CELULAR")),
        "data_cadastro": clean(row.get("CLIDTCAD")),
        "inscricao_estadual": clean(row.get("CLIINSCEST")),
    }


def dedupe_records(rows: list[dict]):
    records = OrderedDict()
    duplicates = []
    for row in rows:
        record = build_record(row)
        codigo = record["codigo_cliente"]
        if not codigo:
            continue
        if codigo in records:
            duplicates.append(codigo)
            continue
        records[codigo] = record
    return list(records.values()), duplicates


def backup_db(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(db_path.suffix + f".bak_clientes0207_{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def find_client_id(cursor, codigo: str):
    cursor.execute("SELECT TOP 1 id FROM etiq_clients WHERE codigo_cliente = ? ORDER BY id ASC", (codigo,))
    row = cursor.fetchone()
    if row:
        return row[0]
    if codigo.isdigit():
        cursor.execute("SELECT TOP 1 id FROM etiq_clients WHERE numero_cliente = ? ORDER BY id ASC", (int(codigo),))
        row = cursor.fetchone()
        if row:
            return row[0]
    return None


def reset_old_client_info(cursor):
    assignments = ", ".join(f"{column} = NULL" for column in RESET_COLUMNS)
    cursor.execute(f"UPDATE etiq_clients SET {assignments}")


def update_client(cursor, record: dict, client_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    columns = [
        "numero_cliente",
        "codigo_cliente",
        "nome_cliente",
        "cnpj_cpf",
        "tipo_rua",
        "rua",
        "endereco",
        "numero",
        "complemento",
        "bairro",
        "cep",
        "cidade",
        "estado",
        "telefone",
        "telefone2",
        "telefone_fax",
        "celular",
        "data_cadastro",
        "inscricao_estadual",
    ]
    assignments = ", ".join(f"{column} = ?" for column in columns)
    values = [record.get(column) for column in columns]
    cursor.execute(
        f"UPDATE etiq_clients SET {assignments}, updated_at = ? WHERE id = ?",
        (*values, now, client_id),
    )


def insert_client(cursor, record: dict):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    columns = [
        "numero_cliente",
        "codigo_cliente",
        "nome_cliente",
        "cnpj_cpf",
        "tipo_rua",
        "rua",
        "endereco",
        "numero",
        "complemento",
        "bairro",
        "cep",
        "cidade",
        "estado",
        "telefone",
        "telefone2",
        "telefone_fax",
        "celular",
        "data_cadastro",
        "inscricao_estadual",
        "created_at",
        "updated_at",
    ]
    values = [record.get(column) for column in columns[:-2]] + [now, now]
    placeholders = ", ".join("?" for _ in columns)
    cursor.execute(
        f"INSERT INTO etiq_clients ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )


def cleanup_duplicate_codigo_cliente(cursor):
    cursor.execute(
        "SELECT codigo_cliente FROM etiq_clients "
        "WHERE codigo_cliente IS NOT NULL AND codigo_cliente <> '' "
        "GROUP BY codigo_cliente HAVING COUNT(*) > 1"
    )
    duplicate_codes = [str(row[0]) for row in cursor.fetchall()]
    deleted = 0
    for codigo in duplicate_codes:
        cursor.execute(
            "SELECT id, numero_cliente, cnpj_cpf, endereco, nome_cliente FROM etiq_clients "
            "WHERE codigo_cliente = ? ORDER BY id ASC",
            (codigo,),
        )
        rows = cursor.fetchall()
        if len(rows) <= 1:
            continue

        def score(row):
            row_id, numero_cliente, cnpj_cpf, endereco, nome_cliente = row
            value = 0
            if str(numero_cliente or "").strip() == codigo:
                value += 4
            if str(cnpj_cpf or "").strip():
                value += 3
            if str(endereco or "").strip():
                value += 2
            if str(nome_cliente or "").strip():
                value += 1
            # Prefer older id only as tie-breaker.
            return (value, -int(row_id))

        keep = max(rows, key=score)
        keep_id = keep[0]
        for row in rows:
            row_id = row[0]
            if row_id == keep_id:
                continue
            cursor.execute("DELETE FROM etiq_clients WHERE id = ?", (row_id,))
            deleted += 1
    return deleted, duplicate_codes


def process_db(db_path: Path, records: list[dict]):
    print(f"\n== {db_path} ==")
    if not db_path.exists():
        print("arquivo nao encontrado")
        return
    backup_path = backup_db(db_path)
    print(f"backup: {backup_path}")
    conn = connect(db_path)
    cursor = conn.cursor()
    try:
        add_missing_columns(cursor)
        reset_old_client_info(cursor)
        updated = 0
        inserted = 0
        for record in records:
            client_id = find_client_id(cursor, record["codigo_cliente"])
            if client_id:
                update_client(cursor, record, client_id)
                updated += 1
            else:
                insert_client(cursor, record)
                inserted += 1
        deleted_duplicates, duplicate_codes = cleanup_duplicate_codigo_cliente(cursor)
        conn.commit()
        print(f"updated={updated} inserted={inserted} duplicate_rows_deleted={deleted_duplicates}")
        if duplicate_codes:
            print("duplicate_codes_cleaned=" + ", ".join(duplicate_codes[:20]))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="clientes 0207.csv")
    args = parser.parse_args()
    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV nao encontrado: {csv_path}")
    rows, encoding = read_csv_rows(csv_path)
    records, duplicates = dedupe_records(rows)
    print(f"CSV: {csv_path} encoding={encoding} rows={len(rows)} unique_clients={len(records)} duplicates_skipped={len(duplicates)}")
    if duplicates:
        sample = ", ".join(duplicates[:20])
        print(f"codigos duplicados ignorados (amostra): {sample}")
    for db_path in DB_CANDIDATES:
        process_db(db_path, records)


if __name__ == "__main__":
    main()