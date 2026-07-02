"""Script de teste: gera uma etiqueta PDF para um cliente do etiq_clients.

Gera WMS_SISTEMA/tools/test_label.pdf com os dados do primeiro cliente encontrado.
"""
from pathlib import Path
import pyodbc
import argparse

from etiquetas_100x150 import draw_label_100x150_pdf


DB_CANDIDATES = [
    Path("WMS_BD/wms_database_test.mdb"),
    Path("WMS_BD/wms_database.mdb"),
    Path("WMS_Server/wms_database.mdb"),
]


def find_first_client(db_path: Path):
    if not db_path.exists():
        return None
    conn = pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()))
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, numero_cliente, nome_cliente, endereco, cidade FROM etiq_clients WHERE endereco IS NOT NULL"
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "numero_cliente": row[1],
            "nome_cliente": row[2],
            "endereco": row[3],
            "cidade": row[4],
        }
    finally:
        conn.close()


def find_client_by_identifier(db_path: Path, id_value: str | int = None, numero: str | int = None):
    if not db_path.exists():
        return None
    conn = pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=%s;" % str(db_path.resolve()))
    cur = conn.cursor()
    try:
        if id_value is not None:
            cur.execute("SELECT id, numero_cliente, nome_cliente, endereco, cidade FROM etiq_clients WHERE id = ?", (int(id_value),))
            row = cur.fetchone()
            if row:
                return {"id": row[0], "numero_cliente": row[1], "nome_cliente": row[2], "endereco": row[3], "cidade": row[4]}
        if numero is not None:
            cur.execute("SELECT id, numero_cliente, nome_cliente, endereco, cidade FROM etiq_clients WHERE numero_cliente = ?", (str(numero),))
            row = cur.fetchone()
            if row:
                return {"id": row[0], "numero_cliente": row[1], "nome_cliente": row[2], "endereco": row[3], "cidade": row[4]}
    finally:
        conn.close()
    return None


def main():
    parser = argparse.ArgumentParser(description='Gerar etiqueta de teste para um cliente')
    parser.add_argument('--id', help='ID do cliente (id)', type=int)
    parser.add_argument('--numero', help='numero_cliente', type=str)
    args = parser.parse_args()

    client = None
    used_db = None
    # If identifier provided, search by that first
    if args.id or args.numero:
        for db in DB_CANDIDATES:
            c = find_client_by_identifier(db, id_value=args.id, numero=args.numero)
            if c:
                client = c
                used_db = db
                break
    else:
        for db in DB_CANDIDATES:
            c = find_first_client(db)
            if c:
                client = c
                used_db = db
                break

    out_pdf = Path("WMS_SISTEMA/tools/test_label.pdf")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    if not client:
        print("Nenhum cliente com endereco encontrado nos DBs.")
        return

    data = {
        "id_master": client.get("numero_cliente") or str(client.get("id")),
        "endereco": client.get("endereco") or "",
        "tratamento": client.get("nome_cliente") or "",
        "caixa": "",
        "enviado_por": "Teste",
    }

    print(
        f"Gerando etiqueta para cliente id={client.get('id')} nome={client.get('nome_cliente')} (DB: {used_db}) -> {out_pdf}"
    )
    buf = draw_label_100x150_pdf(data)
    with open(out_pdf, "wb") as f:
        f.write(buf.read())

    print("Arquivo escrito.")


if __name__ == '__main__':
    main()
