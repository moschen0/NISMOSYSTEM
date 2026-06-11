"""Gerador de etiqueta de envio 150×100 mm (PAISAGEM).

Layout:
  ┌────────────────────────────────────────────────────────────────┐
  │ [QR]  OS OPTO: <os_id>                     Enviado por: <env> │  ← topo
  ├──┬───────────────────────────┬──────────────────────────────── ┤
  │  │                           │  OD  Esf.  Cil.  Eixo.  Ad.   │
  │E │   TRATAMENTO OPTO         │      [  ]  [  ]  [   ]  [  ]  │
  │N │   <tratamento>            │  OE  Esf.  Cil.  Eixo.  Ad.   │
  │D │                           │      [  ]  [  ]  [   ]  [  ]  │
  │E │                           │                                │
  │R │                           │  CAIXA: <caixa>               │
  │Ç │                           │                                │
  ├──┴───────────────────────────┴────────────────────────────────┤
  │ [======Code128 Barcode=======]  ID MASTER: <id_master>        │  ← base
  └────────────────────────────────────────────────────────────────┘
"""
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from io import BytesIO


def _draw_qr(c, x, y, size, value: str):
    """Render a QR code at (x, y) with the given pt size."""
    try:
        qr = QrCodeWidget(value or "WMS")
        bounds = qr.getBounds()
        bw = bounds[2] - bounds[0]
        bh = bounds[3] - bounds[1]
        d = Drawing(size, size, transform=[size / bw, 0, 0, size / bh, 0, 0])
        d.add(qr)
        renderPDF.draw(d, c, x, y)
    except Exception:
        c.rect(x, y, size, size, stroke=1, fill=0)
        c.setFont("Helvetica", 6)
        c.drawCentredString(x + size / 2, y + size / 2 - 2, "QR")


def draw_label_100x150_pdf(data: dict) -> BytesIO:
    """Generate a 150×100 mm landscape shipping-label PDF.

    data keys
    ---------
    os_id        — OS OPTO identifier (e.g. '2BA-123456')
    id_master    — ID Master / barcode (fallback: barcode_value, numero_cliente)
    endereco     — endereçamento (e.g. 'P-01-01')
    tratamento   — description line after TRATAMENTO OPTO heading
    od_esf / od_cil / od_eixo / od_ad — OD dioptria values
    oe_esf / oe_cil / oe_eixo / oe_ad — OE dioptria values
    caixa        — caixa identifier
    enviado_por  — sending user (fallback: entregador)
    """
    # ── page size: LANDSCAPE 150 × 100 mm ────────────────────────────────────
    W = 150 * mm
    H = 100 * mm

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))

    # ── resolve fields ────────────────────────────────────────────────────────
    def _s(key, *fallbacks):
        for k in (key, *fallbacks):
            v = data.get(k, "")
            if v:
                return str(v)
        return ""

    os_id       = _s("os_id")
    id_master   = _s("id_master", "barcode_value", "numero_cliente")
    endereco    = _s("endereco")
    tratamento  = _s("tratamento")
    od_esf      = _s("od_esf")
    od_cil      = _s("od_cil")
    od_eixo     = _s("od_eixo")
    od_ad       = _s("od_ad")
    oe_esf      = _s("oe_esf")
    oe_cil      = _s("oe_cil")
    oe_eixo     = _s("oe_eixo")
    oe_ad       = _s("oe_ad")
    caixa       = _s("caixa")
    enviado_por = _s("enviado_por", "entregador")

    # ── outer border ──────────────────────────────────────────────────────────
    c.setLineWidth(1.2)
    c.rect(1.5 * mm, 1.5 * mm, W - 3 * mm, H - 3 * mm, stroke=1, fill=0)

    # ════════════════════════════════════════════════════════════════════════
    # TOP BAND  y: 74 – 97 mm
    # ════════════════════════════════════════════════════════════════════════
    TOP_Y = 74 * mm
    c.setLineWidth(0.5)
    c.line(1.5 * mm, TOP_Y, W - 1.5 * mm, TOP_Y)

    QR_SIZE = 18 * mm
    QR_X = 3.5 * mm
    QR_Y = TOP_Y + 2.5 * mm
    _draw_qr(c, QR_X, QR_Y, QR_SIZE, os_id or id_master)

    
    c.setFont("Helvetica-Bold", 9)
    c.drawString(26 * mm, TOP_Y + 16 * mm, "OS OPTO:")
    c.setFont("Helvetica", 10)
    c.drawString(26 * mm, TOP_Y + 9 * mm, os_id)

    c.setFont("Helvetica", 7.5)
    c.drawRightString(W - 3 * mm, TOP_Y + 16 * mm, f"Enviado por: {enviado_por}")

    # ════════════════════════════════════════════════════════════════════════
    # BOTTOM BAND  y: 2 – 22 mm
    # ════════════════════════════════════════════════════════════════════════
    BOT_Y = 22 * mm
    c.setLineWidth(0.5)
    c.line(1.5 * mm, BOT_Y, W - 1.5 * mm, BOT_Y)

    # Barcode box — wider to fit 8-digit codes
    BC_X, BC_Y, BC_W, BC_H = 3.5 * mm, 3.5 * mm, 72 * mm, 17 * mm
    c.setLineWidth(0.7)
    c.rect(BC_X, BC_Y, BC_W, BC_H, stroke=1, fill=0)
    c.setFont("Helvetica", 8)
    c.drawString(BC_X + 5 * mm, BC_Y + BC_H - 8 * mm, "ID MASTER:")

    if id_master:
        try:
            bc = code128.Code128(
                id_master,
                barHeight=9 * mm,
                barWidth=1.7,
                humanReadable=True,
                fontSize=10,
            )
            bc.drawOn(c, BC_X + 17 * mm, BC_Y + 5 * mm)
        except Exception:
            c.setFont("Helvetica-Bold", 20)
            c.drawCentredString(BC_X + BC_W / 2, BC_Y + BC_H / 50, id_master)

    # "ID MASTER" text to the right of the barcode box
    id_text_x = BC_X + BC_W + 2 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(id_text_x, BOT_Y - 6 * mm, "ID MASTER")
    c.setFont("Helvetica", 9)
    c.drawString(id_text_x, BOT_Y - 12 * mm, id_master)

    # ════════════════════════════════════════════════════════════════════════
    # LEFT STRIP  x: 1.5 – 16 mm  (ENDEREÇAMENTO)
    # ════════════════════════════════════════════════════════════════════════
    LEFT_X = 16 * mm
    c.setLineWidth(0.5)
    c.line(LEFT_X, BOT_Y, LEFT_X, TOP_Y)

    mid_strip = (BOT_Y + TOP_Y) / 2

    c.saveState()
    c.translate(12 * mm, mid_strip + 10 * mm)
    c.rotate(90)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(0, 0, "")
    c.restoreState()

    c.saveState()
    c.translate(12 * mm, mid_strip)
    c.rotate(90)
    c.setFont("Helvetica", 30)
    c.drawCentredString(0, 0, endereco)
    c.restoreState()

    # ════════════════════════════════════════════════════════════════════════
    # CENTER  x: 17 – 87 mm   (TRATAMENTO OPTO)
    # ════════════════════════════════════════════════════════════════════════
    CTR_RIGHT = 87 * mm
    c.setLineWidth(0.5)
    c.line(CTR_RIGHT, BOT_Y, CTR_RIGHT, TOP_Y)

    c.setFont("Helvetica", 7)
    c.drawString(19 * mm, 60 * mm, "Tratamento Opto:")
    if tratamento:
        c.setFont("Helvetica", 14)
        # Word-wrap: max ~35 chars per line
        _words = tratamento.split()
        _lines, _cur = [], ""
        for _w in _words:
            if len(_cur) + len(_w) + 1 <= 35:
                _cur = (_cur + " " + _w).strip()
            else:
                if _cur:
                    _lines.append(_cur)
                _cur = _w
        if _cur:
            _lines.append(_cur)
        for _li, _line in enumerate(_lines[:3]):
            c.drawString(19 * mm, 53 * mm - _li * 5 * mm, _line)

    # ════════════════════════════════════════════════════════════════════════
    # RIGHT GRID  x: 88 – 148 mm  (dioptria OD / OE  +  CAIXA)
    # ════════════════════════════════════════════════════════════════════════
    G_X        = 89 * mm
    G_W        = W - G_X - 2 * mm          # ≈ 59 mm
    LBL_W      = 9 * mm
    N_COLS     = 4
    COL_W      = (G_W - LBL_W) / N_COLS    # ≈ 12.5 mm
    BOX_H      = 9.5 * mm
    COL_HDR    = ["Esf.", "Cil.", "Eixo.", "Ad."]

    HDR_Y = TOP_Y - 7 * mm
    c.setFont("Helvetica-Bold", 11)
    for i, hdr in enumerate(COL_HDR):
        cx = G_X + LBL_W + i * COL_W + COL_W / 2
        c.drawCentredString(cx, HDR_Y, hdr)

    rows = [
        ("OD", od_esf, od_cil, od_eixo, od_ad),
        ("OE", oe_esf, oe_cil, oe_eixo, oe_ad),
    ]
    for ri, (lbl, v1, v2, v3, v4) in enumerate(rows):
        ry = HDR_Y - (ri + 1) * (BOX_H + 2.5 * mm) - 2 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(G_X + 1 * mm, ry + 1.5 * mm, lbl)
        for ci, val in enumerate([v1, v2, v3, v4]):
            bx = G_X + LBL_W + ci * COL_W
            c.setLineWidth(0.6)
            c.rect(bx, ry, COL_W - 1 * mm, BOX_H, stroke=1, fill=0)
            if val:
                c.setFont("Helvetica", 11)
                c.drawCentredString(bx + (COL_W - 1 * mm) / 2, ry + 2 * mm, val)

    # CAIXA
    c.setFont("Helvetica-Bold", 14)
    c.drawString(G_X + 1 * mm, BOT_Y + 3 * mm, f"CAIXA: {caixa}" if caixa else "CAIXA")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf
