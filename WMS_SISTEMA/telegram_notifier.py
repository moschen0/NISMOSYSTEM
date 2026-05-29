"""
telegram_notifier.py

Módulo de integração com a Telegram Bot API para o WMS.
Usa apenas a stdlib do Python (urllib) — sem dependências externas.

Todas as funções retornam (ok: bool, mensagem: str) e falham silenciosamente
para não interromper o fluxo principal da aplicação.
"""

import csv
import io
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
import calendar
from datetime import datetime, date as _date, timedelta

logger = logging.getLogger('wms')


# ============================================================================
# CREDENCIAIS
# ============================================================================

def get_credentials():
    """Retorna (token, chat_id) das variáveis de ambiente."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    return token, chat_id


def is_configured():
    """Retorna True se TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID estão definidos."""
    token, chat_id = get_credentials()
    return bool(token and chat_id)


# ============================================================================
# PRIMITIVAS DE ENVIO
# ============================================================================

def send_message(text):
    """Envia mensagem de texto (HTML) para o chat configurado.

    Retorna (ok: bool, mensagem: str).
    """
    if not is_configured():
        return False, 'Telegram não configurado (verifique TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env)'

    token, chat_id = get_credentials()
    try:
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
        }).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        if result.get('ok'):
            return True, 'Mensagem enviada'
        return False, result.get('description', 'Erro desconhecido do Telegram')
    except Exception as exc:
        logger.error(f'TELEGRAM | send_message erro: {exc}')
        return False, str(exc)


def send_document(file_bytes, filename, caption=''):
    """Envia um arquivo binário (ex.: CSV) para o chat configurado.

    Retorna (ok: bool, mensagem: str).
    """
    if not is_configured():
        return False, 'Telegram não configurado'

    token, chat_id = get_credentials()
    try:
        boundary = 'WMSBoundaryTelegram987654321'
        crlf = b'\r\n'

        def _field(name, value):
            header = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            ).encode('utf-8')
            return header + str(value).encode('utf-8') + crlf

        body = b''
        body += _field('chat_id', chat_id)
        if caption:
            body += _field('caption', caption)
        body += (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
            f'Content-Type: text/csv\r\n\r\n'
        ).encode('utf-8') + file_bytes + crlf
        body += f'--{boundary}--\r\n'.encode('utf-8')

        url = f'https://api.telegram.org/bot{token}/sendDocument'
        req = urllib.request.Request(
            url, data=body, method='POST',
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        if result.get('ok'):
            return True, 'Arquivo enviado com sucesso'
        return False, result.get('description', 'Erro desconhecido do Telegram')
    except Exception as exc:
        logger.error(f'TELEGRAM | send_document erro: {exc}')
        return False, str(exc)


# ============================================================================
# BUILDERS
# ============================================================================

def build_conference_csv(address, result, scanned_by=''):
    """Gera bytes UTF-8-BOM de CSV com o resultado da conferência.

    Args:
        address: Endereço auditado (ex.: 'P-01-02').
        result: Dict com chaves ok, missing, wrong_location, not_found.
        scanned_by: Nome do usuário que realizou a conferência.

    Returns:
        bytes do CSV (com BOM para compatibilidade com Excel PT-BR).
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['WMS — Relatório de Conferência'])
    writer.writerow(['Endereço', address])
    writer.writerow(['Gerado em', datetime.now().strftime('%d/%m/%Y %H:%M:%S')])
    if scanned_by:
        writer.writerow(['Usuário', scanned_by])
    writer.writerow([])
    writer.writerow(['STATUS', 'PEDIDO', 'CAIXA', 'POSIÇÃO', 'OBSERVAÇÃO'])

    for oid in result.get('ok', []):
        writer.writerow(['OK', oid, '', '', ''])

    for order in result.get('missing', []):
        writer.writerow([
            'FALTANDO',
            order.get('order_id', ''),
            order.get('box', ''),
            order.get('position', ''),
            'Esperado mas não bipado',
        ])

    for item in result.get('wrong_location', []):
        order = item.get('order', {})
        writer.writerow([
            'ENDEREÇO ERRADO',
            item.get('scanned_id', ''),
            order.get('box', ''),
            order.get('position', ''),
            f'Cadastrado em {order.get("position", "")}',
        ])

    for oid in result.get('not_found', []):
        writer.writerow(['NÃO CADASTRADO', oid, '', '', 'Bipado mas não existe no sistema'])

    return output.getvalue().encode('utf-8-sig')  # BOM para Excel PT-BR


def build_daily_report_message(orders, thresholds, unit='', sector=''):
    """Gera mensagem HTML para o relatório diário de pedidos ativos.

    Args:
        orders: Lista de pedidos ativos.
        thresholds: Dict com green_days, yellow_days, red_days.
        unit: Nome da unidade (exibição).
        sector: Nome do setor (exibição).

    Returns:
        Texto HTML formatado para o Telegram.
    """
    today_str = datetime.now().strftime('%d/%m/%Y')
    today_prefix = datetime.now().strftime('%d/%m/%Y')

    today_orders = [
        o for o in orders
        if str(o.get('timestamp', '') or '').startswith(today_prefix)
    ]

    lines = [
        '📦 <b>WMS — Relatório Diário</b>',
        f'📅 Data: {today_str}',
    ]
    if unit:
        lines.append(f'🏢 Unidade: {unit}')
    if sector and sector not in ('ALL', ''):
        lines.append(f'📂 Setor: {sector}')
    lines.append('')
    lines.append(f'<b>Total de pedidos ativos: {len(orders)}</b>')
    lines.append(f'Cadastrados hoje: {len(today_orders)}')

    gd = int(thresholds.get('green_days', 3))
    yd = int(thresholds.get('yellow_days', 4))
    rd = int(thresholds.get('red_days', 6))
    counts = {'normal': 0, 'attention': 0, 'urgent': 0, 'critical': 0}

    for o in orders:
        age = _calc_age_days(o.get('timestamp'))
        if age is None or age < gd:
            counts['normal'] += 1
        elif age < yd:
            counts['attention'] += 1
        elif age < rd:
            counts['urgent'] += 1
        else:
            counts['critical'] += 1

    lines.append('')
    lines.append('🟢 Normal (verde): ' + str(counts['normal']))
    lines.append('🟡 Atenção (amarelo): ' + str(counts['attention']))
    lines.append('🟠 Urgente (laranja): ' + str(counts['urgent']))
    lines.append('🔴 Crítico (vermelho): ' + str(counts['critical']))

    return '\n'.join(lines)


def build_status_alert_message(orders_by_tier, unit=''):
    """Gera mensagem HTML com alertas de pedidos que mudaram de tier.

    Args:
        orders_by_tier: Dict {tier: [order_dict, ...]} onde cada order_dict
                        pode ter '_age_days' já calculado.
        unit: Nome da unidade (exibição).

    Returns:
        Texto HTML formatado para o Telegram.
    """
    lines = ['⚠️ <b>WMS — Alerta de Pedidos</b>']
    if unit:
        lines.append(f'🏢 Unidade: {unit}')
    lines.append(f'📅 {datetime.now().strftime("%d/%m/%Y %H:%M")}')
    lines.append('')

    tier_labels = {
        'attention': '🟡 Atenção',
        'urgent':    '🟠 Urgente',
        'critical':  '🔴 Crítico',
    }

    any_orders = False
    for tier in ('critical', 'urgent', 'attention'):
        orders = orders_by_tier.get(tier, [])
        if not orders:
            continue
        any_orders = True
        label = tier_labels.get(tier, tier)
        lines.append(f'<b>{label} ({len(orders)} pedido(s)):</b>')
        for o in orders[:10]:
            pos = o.get('position', '?')
            oid = o.get('order_id', '?')
            age = o.get('_age_days', '?')
            lines.append(f'  • {oid} em {pos} ({age} dias)')
        if len(orders) > 10:
            lines.append(f'  ... e mais {len(orders) - 10}')
        lines.append('')

    if not any_orders:
        return ''
    return '\n'.join(lines)


# ============================================================================
# HELPERS INTERNOS
# ============================================================================

def _calc_age_days(timestamp_str):
    """Calcula a idade em dias a partir de um timestamp string.

    Retorna int ou None se não for possível parsear.
    """
    if not timestamp_str:
        return None
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            parsed = datetime.strptime(str(timestamp_str).strip(), fmt)
            return max(0, (datetime.now() - parsed).days)
        except ValueError:
            continue
    return None


# ============================================================================
# RELATÓRIO DE PERÍODO (FECHA MÊS)
# ============================================================================

def resolve_report_period(cfg):
    """Calcula (datetime_from, datetime_to) com base no modo configurado.

    Modos:
        'month_to_date'  — do dia start_day do mês atual até hoje
        'full_month'     — do dia start_day até o último dia do mês atual
        'custom_days'    — do dia start_day até o dia end_day do mês atual
                           (end_day=0 significa último dia do mês)

    Returns:
        (datetime, datetime) — início e fim do período (inclusivos).
    """
    today = datetime.now().date()
    mode = cfg.get('scheduled_report_mode', 'month_to_date')
    start_day = max(1, int(cfg.get('scheduled_report_start_day', 1) or 1))
    end_day = int(cfg.get('scheduled_report_end_day', 0) or 0)

    _, last = calendar.monthrange(today.year, today.month)
    start_day = min(start_day, last)

    if mode == 'full_month':
        date_from = _date(today.year, today.month, start_day)
        date_to = _date(today.year, today.month, last)
    elif mode == 'custom_days':
        date_from = _date(today.year, today.month, start_day)
        if end_day <= 0 or end_day > last:
            date_to = _date(today.year, today.month, last)
        else:
            date_to = _date(today.year, today.month, min(end_day, last))
    else:  # month_to_date (default)
        date_from = _date(today.year, today.month, start_day)
        date_to = today

    dt_from = datetime(date_from.year, date_from.month, date_from.day, 0, 0, 0)
    dt_to   = datetime(date_to.year,   date_to.month,   date_to.day,   23, 59, 59)
    return dt_from, dt_to


def _parse_dt(s):
    """Faz parse de string de data/hora para datetime. Retorna None se falhar."""
    if not s:
        return None
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(s).strip(), fmt)
        except ValueError:
            continue
    return None


def filter_orders_by_period(all_orders, dt_from, dt_to):
    """Separa todos os pedidos em três listas:

    - added:   cadastrados (timestamp) dentro do período
    - removed: retirados (removed_at) dentro do período
    - active:  com status='add' (independente do período — snapshot atual)
    """
    added, removed, active = [], [], []
    for o in all_orders:
        ts = _parse_dt(o.get('timestamp'))
        if ts and dt_from <= ts <= dt_to:
            added.append(o)

        ra = _parse_dt(o.get('removed_at'))
        if ra and dt_from <= ra <= dt_to:
            removed.append(o)

        if str(o.get('status', '')).strip().lower() == 'add':
            active.append(o)

    added.sort(key=lambda x: _parse_dt(x.get('timestamp')) or datetime.min)
    removed.sort(key=lambda x: _parse_dt(x.get('removed_at')) or datetime.min)
    active.sort(key=lambda x: _parse_dt(x.get('timestamp')) or datetime.min)
    return added, removed, active


def build_period_report_csv(added, removed, active, dt_from, dt_to, unit=''):
    """Gera bytes UTF-8-BOM de CSV para o relatório de período (fecha mês).

    Args:
        added:    pedidos cadastrados no período.
        removed:  pedidos retirados no período.
        active:   pedidos ativos no momento do fechamento.
        dt_from:  datetime de início do período.
        dt_to:    datetime de fim do período.
        unit:     unidade (exibição).

    Returns:
        bytes do CSV com BOM para compatibilidade com Excel PT-BR.
    """
    output = io.StringIO()
    w = csv.writer(output)
    fmt = '%d/%m/%Y'

    # ── Cabeçalho ──────────────────────────────────────────────────────────
    w.writerow(['WMS — Relatório de Período'])
    w.writerow(['Período', f'{dt_from.strftime(fmt)} até {dt_to.strftime(fmt)}'])
    w.writerow(['Gerado em', datetime.now().strftime('%d/%m/%Y %H:%M:%S')])
    if unit:
        w.writerow(['Unidade', unit])
    w.writerow([])

    # ── Resumo ──────────────────────────────────────────────────────────────
    w.writerow(['RESUMO'])
    w.writerow(['Pedidos cadastrados no período', len(added)])
    w.writerow(['Pedidos retirados no período',   len(removed)])
    w.writerow(['Pedidos ativos no fechamento',   len(active)])
    w.writerow([])

    # ── Seção A: Cadastrados ─────────────────────────────────────────────
    w.writerow(['=== A. CADASTRADOS NO PERÍODO ==='])
    w.writerow(['PEDIDO', 'CAIXA', 'POSIÇÃO', 'DATA PEDIDO', 'CADASTRADO EM', 'CADASTRADO POR', 'SETOR'])
    for o in added:
        w.writerow([
            o.get('order_id', ''),
            o.get('box', ''),
            o.get('position', ''),
            o.get('date', ''),
            o.get('timestamp', ''),
            o.get('created_by', ''),
            o.get('sector', ''),
        ])
    w.writerow([])

    # ── Seção B: Retirados ───────────────────────────────────────────────
    w.writerow(['=== B. RETIRADOS NO PERÍODO ==='])
    w.writerow(['PEDIDO', 'CAIXA', 'POSIÇÃO', 'RETIRADO EM', 'RETIRADO POR', 'SETOR'])
    for o in removed:
        w.writerow([
            o.get('order_id', ''),
            o.get('box', ''),
            o.get('position', ''),
            o.get('removed_at', ''),
            o.get('removed_by', ''),
            o.get('sector', ''),
        ])
    w.writerow([])

    # ── Seção C: Ativos no fechamento ─────────────────────────────────────
    w.writerow(['=== C. ATIVOS NO FECHAMENTO ==='])
    w.writerow(['PEDIDO', 'CAIXA', 'POSIÇÃO', 'CADASTRADO EM', 'DIAS NO ESTOQUE', 'SETOR'])
    for o in active:
        age = _calc_age_days(o.get('timestamp'))
        w.writerow([
            o.get('order_id', ''),
            o.get('box', ''),
            o.get('position', ''),
            o.get('timestamp', ''),
            age if age is not None else '',
            o.get('sector', ''),
        ])

    return output.getvalue().encode('utf-8-sig')


def build_period_report_message(added, removed, active, dt_from, dt_to, unit=''):
    """Gera mensagem HTML resumida do relatório de período para o Telegram."""
    fmt = '%d/%m/%Y'
    lines = [
        '📊 <b>WMS — Relatório de Período</b>',
        f'📅 {dt_from.strftime(fmt)} → {dt_to.strftime(fmt)}',
    ]
    if unit:
        lines.append(f'🏢 Unidade: {unit}')
    lines.append('')
    lines.append(f'➕ Cadastrados no período: <b>{len(added)}</b>')
    lines.append(f'➖ Retirados no período: <b>{len(removed)}</b>')
    lines.append(f'📦 Ativos no fechamento: <b>{len(active)}</b>')
    lines.append('')
    lines.append('📎 <i>CSV com detalhes em anexo.</i>')
    return '\n'.join(lines)
