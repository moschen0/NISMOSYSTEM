from pathlib import Path
import sys
from importlib.machinery import SourceFileLoader

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load module directly by path (no __init__.py needed)
_mod = SourceFileLoader("etiquetas_100x150", str(PROJECT_ROOT / "etiquetas_100x150.py")).load_module()
draw_label_100x150_pdf = _mod.draw_label_100x150_pdf

OUT = Path(__file__).resolve().parent / "sample_etiqueta_paisagem.pdf"

def main():
    data = {
        "os_id":       "2BA-123456",
        "id_master":   "10102736",
        "endereco":    "P-01-01",
        "tratamento":  "Grau alto / bifocal",
        "caixa":       "CX-005",
        "enviado_por": "admin",
        # OD
        "od_esf":  "+2.00",
        "od_cil":  "-0.50",
        "od_eixo": "90",
        "od_ad":   "+1.50",
        # OE
        "oe_esf":  "+1.75",
        "oe_cil":  "-0.25",
        "oe_eixo": "85",
        "oe_ad":   "+1.50",
    }
    buf = draw_label_100x150_pdf(data)
    with open(OUT, "wb") as f:
        f.write(buf.read())
    print(f"PDF gerado: {OUT}")

if __name__ == "__main__":
    main()
