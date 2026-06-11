# Etiqueta de Envio 150×100 mm (Paisagem)

## Visão Geral

Módulo de geração e impressão de etiqueta de envio no formato **150 × 100 mm** em orientação **paisagem**, replicando o layout do modelo de referência.

---

## Layout da Etiqueta

```
┌──────────────────────────────────────────────────────────────────┐
│ [QR]  OS OPTO: 2BA-123456                  Enviado por: admin    │ ← topo
├──┬──────────────────────────┬──────────────────────────────────  ┤
│  │                          │  OD  Esf.  Cil.  Eixo.  Ad.       │
│E │   TRATAMENTO OPTO        │      [+2.00][-0.50][ 90 ][+1.50]  │
│N │   <descrição>            │  OE  Esf.  Cil.  Eixo.  Ad.       │
│D │                          │      [+1.75][-0.25][ 85 ][+1.50]  │
│E │                          │                                    │
│R │                          │  CAIXA: CX-005                    │
│Ç │                          │                                    │
├──┴──────────────────────────┴────────────────────────────────────┤
│ [======Code128 ID MASTER=======]  ID MASTER: 10102736            │ ← base
└──────────────────────────────────────────────────────────────────┘
```

---

## Arquivos

| Arquivo | Descrição |
|---|---|
| `WMS_SISTEMA/etiquetas_100x150.py` | Gerador ReportLab (função `draw_label_100x150_pdf`) |
| `WMS_SISTEMA/templates/etiq/label_print_100x150.html` | Template de preview + formulário |
| `WMS_SISTEMA/static/etiq/styles.css` | Regras `@page` 150×100 mm |

---

## Rotas Flask

| Rota | Método | Descrição |
|---|---|---|
| `/etiq/etiquetas/print_100x150/<id>` | GET | Preview com formulário de campos |
| `/etiq/etiquetas/print_100x150/<id>/pdf` | GET | Download / embed do PDF gerado |

### Parâmetros de Query

Todos os campos do formulário são passados via query string:

| Parâmetro | Exemplo |
|---|---|
| `os_id` | `2BA-123456` |
| `id_master` | `10102736` |
| `endereco` | `P-01-01` |
| `tratamento` | `Grau alto / bifocal` |
| `caixa` | `CX-005` |
| `enviado_por` | `admin` |
| `od_esf`, `od_cil`, `od_eixo`, `od_ad` | `+2.00`, `-0.50`, `90`, `+1.50` |
| `oe_esf`, `oe_cil`, `oe_eixo`, `oe_ad` | `+1.75`, `-0.25`, `85`, `+1.50` |

---

## Botões na Interface

### Imprimir Etiqueta
- Abre o diálogo de impressão do navegador (Chrome / Edge) com o PDF embutido.
- Selecione a impressora de etiquetas e configure:
  - Papel: **100 × 150 mm** (ou 4 × 6 polegadas)
  - Orientação: **Paisagem**
  - Escala: **100%** (não ajustar ao papel)

### Configurar Impressora
- Exibe um modal com instruções passo a passo para selecionar a impressora e configurar o tamanho de papel no diálogo do Windows.
- Não altera a impressora padrão do sistema permanentemente.

---

## Teste Local

```powershell
python "WMS_SISTEMA/scripts/generate_sample_label.py"
# Saída: WMS_SISTEMA/scripts/sample_etiqueta_paisagem.pdf
```

---

## Dependências

Já inclusas no `requirements.txt`:
- `reportlab>=4.0`
