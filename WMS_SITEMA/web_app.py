"""
WMS (Warehouse Management System) - Web Application (versão MDB)
Sistema de Gerenciamento de Armazém com Flask + Access Database
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, Response
from functools import wraps
from datetime import datetime
import json
import os
import re
import sys
import db_mdb

# Carrega variáveis do arquivo .env (se existir) sem sobrescrever vars de ambiente já definidas
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=False)
except ImportError:
    pass  # python-dotenv opcional; use variáveis de ambiente do sistema

# ============================================================================
# CONFIGURAÇÃO INICIAL
# ============================================================================

def get_resource_base_dir():
    """Retorna a pasta de recursos (templates/static) para dev e executavel."""
    if not getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(__file__))

    exe_dir = os.path.dirname(sys.executable)
    meipass_dir = getattr(sys, '_MEIPASS', None)
    candidates = [
        meipass_dir,
        os.path.join(exe_dir, '_internal'),
        exe_dir,
    ]

    for base_dir in candidates:
        if not base_dir:
            continue
        templates_dir = os.path.join(base_dir, 'templates')
        static_dir = os.path.join(base_dir, 'static')
        if os.path.isdir(templates_dir) and os.path.isdir(static_dir):
            return base_dir

    return exe_dir


def get_runtime_data_dir():
    """Retorna pasta para dados mutaveis em execucao."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


RESOURCE_BASE_DIR = get_resource_base_dir()
DATA_BASE_DIR = get_runtime_data_dir()
TEMPLATES_DIR = os.path.join(RESOURCE_BASE_DIR, 'templates')
ZONE_METADATA_PATH = os.path.join(DATA_BASE_DIR, 'zone_metadata.json')
TAG_CATALOG_PATH = os.path.join(DATA_BASE_DIR, 'zone_tag_catalog.json')
ZONE_TAGS_PATH = os.path.join(DATA_BASE_DIR, 'zone_tags_map.json')
SECTORS_PATH = os.path.join(DATA_BASE_DIR, 'sectors.json')

TAG_RULES = {
    'maintenance': 'Em manutencao (ignora na alocacao)',
    'priority': 'Prioridade (primeira da fila)',
    'none': 'Sem regra automatica'
}
# 𓃶𓃶
# ============================================================================
# GERENCIAMENTO DE CÉLULAS/SETORES
# ============================================================================

def load_sectors():
    """Carrega definições de células/setores do arquivo JSON."""
    if not os.path.exists(SECTORS_PATH):
        default = {
            'AR': {
                'name': 'AR',
                'description': 'Setor AR',
                'status': 'active',
                'created_at': datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            },
            'VTA': {
                'name': 'VTA',
                'description': 'Setor VTA',
                'status': 'active',
                'created_at': datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            }
        }
        save_sectors(default)
        return default
    try:
        with open(SECTORS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao ler sectors.json: {e}")
        return {}

def save_sectors(sectors):
    """Salva setores de forma atômica."""
    tmp_path = f"{SECTORS_PATH}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(sectors, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, SECTORS_PATH)

def get_active_sector_keys():
    """Retorna lista de chaves de setores ativos."""
    sectors = load_sectors()
    return [k for k, v in sectors.items() if v.get('status') == 'active']

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=os.path.join(RESOURCE_BASE_DIR, 'static'),
    static_url_path='/static'
)
app.secret_key = os.environ.get('WMS_SECRET_KEY', 'wms-dev-key-insecure')
MASTER_PASSWORD = os.environ.get('WMS_MASTER_PASSWORD', 'masterkey')
DEFAULT_UNIT = db_mdb.DEFAULT_UNIT
DEFAULT_SECTOR = db_mdb.DEFAULT_SECTOR
AVAILABLE_UNITS = list(db_mdb.AVAILABLE_UNITS)


@app.context_processor
def inject_admin_context():
    """Injeta variáveis globais úteis em todos os templates."""
    sectors = load_sectors()
    current_sec = session.get('sector', DEFAULT_SECTOR)
    return {
        'is_admin': session.get('user', '').lower() == 'admin',
        'all_units': AVAILABLE_UNITS,
        'current_unit': session.get('unit', DEFAULT_UNIT),
        'all_sectors': sectors,
        'current_sector': current_sec,
        'sector_is_all': current_sec == 'ALL',
    }


# ============================================================================
# AUTENTICAÇÃO
# ============================================================================

def login_required(f):
    """Decorator para proteger rotas que precisam de autenticação"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Faça login para continuar', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def is_master(password):
    """Valida se a senha mestre está correta"""
    return password == MASTER_PASSWORD


def get_current_unit():
    """Retorna a unidade associada ao usuário autenticado."""
    return db_mdb.normalize_unit(session.get('unit', DEFAULT_UNIT))


def get_current_sector():
    """Retorna o setor ativo na sessão. None = sem filtro (admin ALL)."""
    sec = session.get('sector', DEFAULT_SECTOR)
    if sec == 'ALL':
        return None
    return sec or DEFAULT_SECTOR


def is_admin_user():
    """Retorna True se o usuário logado é admin."""
    return session.get('user', '').lower() == 'admin'


def is_valid_unit(unit):
    """Valida se a unidade selecionada existe na lista permitida."""
    return db_mdb.normalize_unit(unit) in AVAILABLE_UNITS

# ============================================================================
# FUNÇÕES UTILITÁRIAS
# ============================================================================

def validate_username(username):
    """Valida formato do nome de usuário"""
    if not username or len(username) < 3:
        return False, "Usuário deve ter pelo menos 3 caracteres"
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "Usuário pode conter apenas letras, números, hífen e underscore"
    return True, ""

def validate_password(password):
    """Valida força da senha"""
    if not password or len(password) < 4:
        return False, "Senha deve ter pelo menos 4 caracteres"
    return True, ""

def find_user(username, unit=None):
    """Encontra usuário no banco de dados"""
    return db_mdb.get_user_by_username(username, unit=unit)

def find_shelf(zone, module, unit=None, sector=None):
    """Encontra prateleira específica"""
    shelves = db_mdb.get_all_shelves(unit=unit, sector=sector)
    return next((s for s in shelves 
                if s.get('zone') == zone and s.get('module') == module), None)

def get_shelf_positions(zone, module, levels, columns):
    """Gera lista de posições disponíveis em uma prateleira"""
    positions = []
    for level in range(levels, 0, -1):
        if columns == 1:
            positions.append(f"{zone}-{module}-{level:02d}")
        else:
            for col in range(1, columns + 1):
                positions.append(f"{zone}-{module}-{level:02d}-{col:02d}")
    return positions


def shelf_sort_key(shelf):
    """Ordena prateleiras numericamente quando possível e alfabeticamente no restante."""
    module = str(shelf.get('module', '')).strip()
    if module.isdigit():
        return (0, int(module))
    return (1, module.upper())

def count_orders_at_position(position, unit=None, sector=None):
    """Conta quantos pedidos ativos (status add) estão em uma posição"""
    return db_mdb.count_orders_in_position(position, unit=unit, sector=sector)

def load_zone_metadata():
    """Carrega descrições de zona salvas localmente."""
    if not os.path.exists(ZONE_METADATA_PATH):
        return {}

    try:
        with open(ZONE_METADATA_PATH, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except Exception as e:
        print(f"Erro ao ler metadados de zona: {e}")
        return {}

    if not isinstance(raw_data, dict):
        return {}

    cleaned = {}
    for zone, name in raw_data.items():
        zone_key = str(zone).strip().upper()
        zone_name = str(name).strip()
        if zone_key and zone_name:
            cleaned[zone_key] = zone_name
    return cleaned

def save_zone_metadata(zone_map):
    """Salva descrições de zona de forma atômica para evitar arquivo corrompido."""
    safe_map = {}
    for zone, name in (zone_map or {}).items():
        zone_key = str(zone).strip().upper()
        zone_name = str(name).strip()
        if zone_key and zone_name:
            safe_map[zone_key] = zone_name

    tmp_path = f"{ZONE_METADATA_PATH}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(safe_map, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, ZONE_METADATA_PATH)

def upsert_zone_name(zone, zone_name):
    """Cria/atualiza a descrição de uma zona."""
    zone_key = (zone or '').strip().upper()
    name = (zone_name or '').strip()
    if not zone_key or not name:
        return

    zone_map = load_zone_metadata()
    zone_map[zone_key] = name
    save_zone_metadata(zone_map)

def delete_zone_name(zone):
    """Remove a descrição de uma zona quando ela for excluída."""
    zone_key = (zone or '').strip().upper()
    if not zone_key:
        return

    zone_map = load_zone_metadata()
    if zone_key in zone_map:
        del zone_map[zone_key]
        save_zone_metadata(zone_map)

def normalize_tag_key(tag_name):
    """Padroniza chave interna de tag."""
    name = (tag_name or '').strip()
    if not name:
        return ''
    return re.sub(r'\s+', ' ', name).upper()

def load_tag_catalog():
    """Carrega catalogo de tags com regras."""
    if not os.path.exists(TAG_CATALOG_PATH):
        return {}

    try:
        with open(TAG_CATALOG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Erro ao ler catalogo de tags: {e}")
        return {}

    if not isinstance(data, dict):
        return {}

    cleaned = {}
    for key, info in data.items():
        tag_key = normalize_tag_key(key)
        if not tag_key or not isinstance(info, dict):
            continue

        display_name = str(info.get('name', '')).strip() or key.title()
        rule = str(info.get('rule', 'none')).strip().lower()
        if rule not in TAG_RULES:
            rule = 'none'
        extra_rules = str(info.get('extra_rules', '')).strip()

        cleaned[tag_key] = {
            'name': display_name,
            'rule': rule,
            'extra_rules': extra_rules
        }
    return cleaned

def save_tag_catalog(tag_catalog):
    """Salva catalogo de tags."""
    safe_data = {}
    for key, info in (tag_catalog or {}).items():
        tag_key = normalize_tag_key(key)
        if not tag_key or not isinstance(info, dict):
            continue

        display_name = str(info.get('name', '')).strip()
        if not display_name:
            continue

        rule = str(info.get('rule', 'none')).strip().lower()
        if rule not in TAG_RULES:
            rule = 'none'

        safe_data[tag_key] = {
            'name': display_name,
            'rule': rule,
            'extra_rules': str(info.get('extra_rules', '')).strip()
        }

    tmp_path = f"{TAG_CATALOG_PATH}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(safe_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, TAG_CATALOG_PATH)

def load_zone_tags_map():
    """Carrega relacao zona -> tags."""
    if not os.path.exists(ZONE_TAGS_PATH):
        return {}

    try:
        with open(ZONE_TAGS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Erro ao ler mapa de tags por zona: {e}")
        return {}

    if not isinstance(data, dict):
        return {}

    cleaned = {}
    for zone, tags in data.items():
        zone_key = str(zone).strip().upper()
        if not zone_key:
            continue
        if not isinstance(tags, list):
            tags = []

        tag_keys = []
        for tag in tags:
            tag_key = normalize_tag_key(tag)
            if tag_key and tag_key not in tag_keys:
                tag_keys.append(tag_key)

        if tag_keys:
            cleaned[zone_key] = tag_keys
    return cleaned

def save_zone_tags_map(zone_tags_map):
    """Salva relacao zona -> tags."""
    safe_data = {}
    for zone, tags in (zone_tags_map or {}).items():
        zone_key = str(zone).strip().upper()
        if not zone_key:
            continue

        tag_keys = []
        for tag in (tags or []):
            tag_key = normalize_tag_key(tag)
            if tag_key and tag_key not in tag_keys:
                tag_keys.append(tag_key)

        if tag_keys:
            safe_data[zone_key] = tag_keys

    tmp_path = f"{ZONE_TAGS_PATH}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(safe_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, ZONE_TAGS_PATH)

def upsert_tag_definition(tag_name, rule, extra_rules=''):
    """Cria ou atualiza definicao de uma tag."""
    tag_key = normalize_tag_key(tag_name)
    display_name = (tag_name or '').strip()
    tag_rule = (rule or 'none').strip().lower()

    if not tag_key or not display_name:
        return False
    if tag_rule not in TAG_RULES:
        tag_rule = 'none'

    tag_catalog = load_tag_catalog()
    tag_catalog[tag_key] = {
        'name': display_name,
        'rule': tag_rule,
        'extra_rules': (extra_rules or '').strip()
    }
    save_tag_catalog(tag_catalog)
    return True

def attach_tags_to_zone(zone, selected_tag_keys):
    """Anexa tags a uma zona (sem duplicar)."""
    zone_key = (zone or '').strip().upper()
    if not zone_key:
        return

    normalized_keys = []
    for key in (selected_tag_keys or []):
        tag_key = normalize_tag_key(key)
        if tag_key and tag_key not in normalized_keys:
            normalized_keys.append(tag_key)

    if not normalized_keys:
        return

    zone_tags_map = load_zone_tags_map()
    current = zone_tags_map.get(zone_key, [])

    for tag_key in normalized_keys:
        if tag_key not in current:
            current.append(tag_key)

    zone_tags_map[zone_key] = current
    save_zone_tags_map(zone_tags_map)

def remove_zone_tags(zone):
    """Remove vinculos de tags de uma zona apagada."""
    zone_key = (zone or '').strip().upper()
    if not zone_key:
        return

    zone_tags_map = load_zone_tags_map()
    if zone_key in zone_tags_map:
        del zone_tags_map[zone_key]
        save_zone_tags_map(zone_tags_map)

def detach_tags_from_zone(zone, selected_tag_keys):
    """Remove tags especificas de uma zona."""
    zone_key = (zone or '').strip().upper()
    if not zone_key:
        return 0

    zone_tags_map = load_zone_tags_map()
    current = zone_tags_map.get(zone_key, [])
    if not current:
        return 0

    to_remove = []
    for key in (selected_tag_keys or []):
        normalized = normalize_tag_key(key)
        if normalized:
            to_remove.append(normalized)

    if not to_remove:
        return 0

    updated = [key for key in current if key not in to_remove]
    removed_count = len(current) - len(updated)

    if updated:
        zone_tags_map[zone_key] = updated
    else:
        zone_tags_map.pop(zone_key, None)

    save_zone_tags_map(zone_tags_map)
    return removed_count

def delete_tag_definition(tag_key):
    """Exclui uma tag do catalogo e remove de todas as zonas."""
    normalized = normalize_tag_key(tag_key)
    if not normalized:
        return False

    tag_catalog = load_tag_catalog()
    if normalized not in tag_catalog:
        return False

    del tag_catalog[normalized]
    save_tag_catalog(tag_catalog)

    zone_tags_map = load_zone_tags_map()
    changed = False
    for zone, tags in list(zone_tags_map.items()):
        filtered = [tag for tag in tags if tag != normalized]
        if len(filtered) != len(tags):
            changed = True
            if filtered:
                zone_tags_map[zone] = filtered
            else:
                del zone_tags_map[zone]

    if changed:
        save_zone_tags_map(zone_tags_map)

    return True

def zone_has_rule(zone, rule, tag_catalog=None, zone_tags_map=None):
    """Valida se uma zona possui ao menos uma tag com a regra solicitada."""
    zone_key = (zone or '').strip().upper()
    rule_key = (rule or '').strip().lower()
    if not zone_key or not rule_key:
        return False

    tag_catalog = tag_catalog if tag_catalog is not None else load_tag_catalog()
    zone_tags_map = zone_tags_map if zone_tags_map is not None else load_zone_tags_map()
    tag_keys = zone_tags_map.get(zone_key, [])

    for tag_key in tag_keys:
        info = tag_catalog.get(tag_key, {})
        if info.get('rule') == rule_key:
            return True
    return False

def sort_zones_by_priority(zones, tag_catalog=None, zone_tags_map=None):
    """Ordena zonas priorizando as que possuem regra de prioridade."""
    tag_catalog = tag_catalog if tag_catalog is not None else load_tag_catalog()
    zone_tags_map = zone_tags_map if zone_tags_map is not None else load_zone_tags_map()

    def zone_sort_key(zone):
        priority_rank = 0 if zone_has_rule(zone, 'priority', tag_catalog, zone_tags_map) else 1
        return (priority_rank, zone)

    return sorted(zones, key=zone_sort_key)

def get_best_position_for_zone(zone):
    """
    Retorna a melhor posição para armazenar um pedido em uma zona específica.
    Regras de prioridade:
    1. Menor módulo para maior módulo
    2. Dentro do módulo, maior andar para menor andar
    3. Dentro do mesmo andar, menor coluna para maior coluna
    4. Retorna a primeira posição com vaga
    """
    if zone_has_rule(zone, 'maintenance'):
        return None

    unit = get_current_unit()
    sector = get_current_sector()
    shelves = db_mdb.get_all_shelves(unit=unit, sector=sector)
    position_counts = db_mdb.count_all_orders_in_positions(unit=unit, sector=sector)
    
    # Filtrar prateleiras da zona especificada
    zone_shelves = [s for s in shelves if s.get('zone', '').upper() == zone.upper()]
    
    if not zone_shelves:
        return None

    # Ordenar módulos do menor para o maior (fallback para string se não for numérico).
    def module_sort_key(shelf):
        module = str(shelf.get('module', '')).strip()
        return (0, int(module)) if module.isdigit() else (1, module)

    zone_shelves = sorted(zone_shelves, key=module_sort_key)

    for shelf in zone_shelves:
        zone_code = shelf.get('zone', '')
        module = shelf.get('module', '')
        levels = shelf.get('levels', 1)
        columns = shelf.get('columns', 1)
        slots = shelf.get('slots', 7)
        
        # Gerar todas as posições desta prateleira
        positions = get_shelf_positions(zone_code, module, levels, columns)
        
        # get_shelf_positions ja retorna do maior andar para o menor.
        # Para colunas, ja retorna da menor para a maior.
        for position in positions:
            count = position_counts.get(position, 0)
            
            # Pular posições cheias
            if count >= slots:
                continue

            return position

    return None

# ============================================================================
# ROTAS DE API (JSON)
# ============================================================================

@app.route('/api/best-position/<zone>')
@login_required
def api_best_position(zone):
    """Retorna a melhor posição disponível em uma zona (JSON)"""
    if zone_has_rule(zone, 'maintenance'):
        return jsonify({'success': False, 'message': f'Zona {zone} está em manutenção e foi ignorada na alocação'})

    position = get_best_position_for_zone(zone)
    if position:
        return jsonify({'success': True, 'position': position, 'zone': zone})
    return jsonify({'success': False, 'message': f'Nenhuma posição disponível na zona {zone}'})

@app.route('/logo')
def get_logo():
    """Serve a logo da empresa do diretorio local configurado"""
    logo_paths = [
        r"C:\APPS MASTER\IMG\Master_Logo_1.png",
        r"C:\APPS MASTER\IMG\Master_logo_1.png",
        r"\\192.168.1.210\apps master\IMG\Master_Logo_1.png",
        r"\\192.168.1.210\apps master\IMG\Master_logo_1.png",
    ]
    
    try:
        for logo_path in logo_paths:
            if os.path.exists(logo_path):
                return send_file(logo_path, mimetype='image/png')
    except Exception as e:
        print(f"Erro ao acessar logo: {e}")
    
    # Fallback: Retornar SVG inline
    svg_content = '''<svg width="400" height="100" xmlns="http://www.w3.org/2000/svg">
        <rect width="400" height="100" fill="#ff9800"/>
        <text x="50%" y="50%" font-size="48" font-weight="bold" fill="white" text-anchor="middle" dy=".3em">WMS</text>
    </svg>'''
    
    return Response(svg_content, mimetype='image/svg+xml')

# ============================================================================
# ROTAS DE AUTENTICAÇÃO
# ============================================================================

@app.route('/')
def index():
    """Página inicial - redireciona para dashboard ou login"""
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        unit = db_mdb.normalize_unit(request.form.get('unit', ''))

        if not is_valid_unit(unit):
            flash('Selecione uma unidade válida', 'danger')
            return render_template(
                'login.html',
                default_unit=DEFAULT_UNIT,
                selected_unit=DEFAULT_UNIT,
                available_units=AVAILABLE_UNITS
            ), 400

        try:
            # Admin pode fazer login em qualquer unidade sem restrição de unit no BD
            search_unit = None if username.lower() == 'admin' else unit
            user = find_user(username, unit=search_unit)
        except RuntimeError as exc:
            # Erro esperado quando driver ODBC do Access nao esta instalado.
            flash(f'Erro de infraestrutura do banco: {exc}', 'danger')
            return render_template(
                'login.html',
                default_unit=DEFAULT_UNIT,
                selected_unit=unit,
                available_units=AVAILABLE_UNITS
            ), 503
        
        if user and db_mdb.verify_password(password, user.get('password', '')):
            session['user'] = username
            session['sector'] = user.get('sector', '')
            # Admin usa a unidade selecionada no login; outros usam a unidade do cadastro
            if username.lower() == 'admin':
                session['unit'] = unit
                session['sector'] = 'ALL'  # Admin vê todos os setores por padrão
            else:
                session['unit'] = db_mdb.normalize_unit(user.get('unit', unit))
                session['sector'] = user.get('sector', DEFAULT_SECTOR) or DEFAULT_SECTOR
            flash(f'Bem-vindo, {username}!', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Usuário ou senha incorretos', 'danger')
    
    return render_template(
        'login.html',
        default_unit=DEFAULT_UNIT,
        selected_unit=DEFAULT_UNIT,
        available_units=AVAILABLE_UNITS
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Página de registro de novo usuário"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        sector = request.form.get('sector', 'geral').strip()
        unit = db_mdb.normalize_unit(request.form.get('unit', ''))

        if not is_valid_unit(unit):
            flash('Selecione uma unidade válida', 'danger')
            return redirect(url_for('register'))
        
        # Validações
        valid, msg = validate_username(username)
        if not valid:
            flash(msg, 'danger')
            return redirect(url_for('register'))
        
        valid, msg = validate_password(password)
        if not valid:
            flash(msg, 'danger')
            return redirect(url_for('register'))
        
        if password != password_confirm:
            flash('As senhas não coincidem', 'danger')
            return redirect(url_for('register'))
        
        if find_user(username, unit=unit):
            flash(f'Este usuário já existe na unidade {unit}', 'danger')
            return redirect(url_for('register'))
        
        # Criar novo usuário no MDB
        db_mdb.add_user(
            username=username,
            password=password,
            sector=sector,
            created_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            active=True,
            unit=unit
        )
        
        flash(f'Usuário {username} registrado com sucesso na unidade {unit}! Faça login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', available_units=AVAILABLE_UNITS, default_unit=DEFAULT_UNIT,
                           available_sectors=get_active_sector_keys())

@app.route('/logout')
def logout():
    """Faz logout do usuário"""
    username = session.get('user', 'Usuário')
    session.clear()
    flash(f'{username} desconectado com sucesso', 'info')
    return redirect(url_for('login'))


@app.route('/switch-unit/<unit_name>')
@login_required
def switch_unit(unit_name):
    """Troca a unidade ativa na sessão (apenas admin)"""
    if not is_admin_user():
        flash('Apenas o admin pode trocar de unidade', 'danger')
        return redirect(url_for('dashboard'))
    unit_name = db_mdb.normalize_unit(unit_name)
    if not is_valid_unit(unit_name):
        flash('Unidade inválida', 'danger')
        return redirect(url_for('dashboard'))
    session['unit'] = unit_name
    flash(f'Unidade alterada para {unit_name}', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/switch-sector/<sector_name>')
@login_required
def switch_sector(sector_name):
    """Troca o setor ativo na sessão (apenas admin)"""
    if not is_admin_user():
        flash('Apenas o admin pode trocar de setor', 'danger')
        return redirect(url_for('dashboard'))
    if sector_name != 'ALL':
        sectors = load_sectors()
        if sector_name not in sectors:
            flash('Setor inválido', 'danger')
            return redirect(url_for('dashboard'))
    session['sector'] = sector_name
    label = 'Todos os setores' if sector_name == 'ALL' else sector_name
    flash(f'Setor alterado para {label}', 'success')
    return redirect(request.referrer or url_for('dashboard'))


# ============================================================================
# ROTAS DE GERENCIAMENTO DE CÉLULAS/SETORES
# ============================================================================

@app.route('/cells')
@login_required
def list_cells():
    """Lista todas as células/setores cadastrados"""
    sectors = load_sectors()
    return render_template('cells.html', sectors=sectors)


@app.route('/cells/add', methods=['POST'])
@login_required
def add_cell():
    """Cria uma nova célula/setor"""
    master_key = request.form.get('master_key', '')
    if not is_master(master_key):
        flash('Senha mestre incorreta', 'danger')
        return redirect(url_for('list_cells'))

    name = request.form.get('name', '').strip().upper()
    description = request.form.get('description', '').strip()

    if not name:
        flash('Nome do setor é obrigatório', 'danger')
        return redirect(url_for('list_cells'))

    if not re.match(r'^[A-Z0-9_-]+$', name):
        flash('Nome do setor deve conter apenas letras, números, hífen e underscore', 'danger')
        return redirect(url_for('list_cells'))

    sectors = load_sectors()
    if name in sectors:
        flash(f'Setor {name} já existe', 'warning')
        return redirect(url_for('list_cells'))

    sectors[name] = {
        'name': name,
        'description': description,
        'status': 'active',
        'created_at': datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }
    save_sectors(sectors)

    db_mdb.add_movement(
        username=session.get('user'),
        action='sector_create',
        details=f'Setor {name} criado',
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        unit=get_current_unit(),
        sector=DEFAULT_SECTOR
    )

    flash(f'Setor {name} criado com sucesso!', 'success')
    return redirect(url_for('list_cells'))


@app.route('/cells/edit', methods=['POST'])
@login_required
def edit_cell():
    """Edita descrição ou status de um setor"""
    master_key = request.form.get('master_key', '')
    if not is_master(master_key):
        flash('Senha mestre incorreta', 'danger')
        return redirect(url_for('list_cells'))

    name = request.form.get('name', '').strip().upper()
    description = request.form.get('description', '').strip()
    status = request.form.get('status', 'active').strip()

    sectors = load_sectors()
    if name not in sectors:
        flash(f'Setor {name} não encontrado', 'danger')
        return redirect(url_for('list_cells'))

    sectors[name]['description'] = description
    sectors[name]['status'] = status if status in ('active', 'inactive') else 'active'
    save_sectors(sectors)

    flash(f'Setor {name} atualizado com sucesso!', 'success')
    return redirect(url_for('list_cells'))


@app.route('/cells/delete', methods=['POST'])
@login_required
def delete_cell():
    """Remove um setor (apenas se não for o padrão)"""
    master_key = request.form.get('master_key', '')
    if not is_master(master_key):
        flash('Senha mestre incorreta', 'danger')
        return redirect(url_for('list_cells'))

    name = request.form.get('name', '').strip().upper()

    if name == DEFAULT_SECTOR:
        flash(f'O setor padrão {DEFAULT_SECTOR} não pode ser removido', 'danger')
        return redirect(url_for('list_cells'))

    sectors = load_sectors()
    if name not in sectors:
        flash(f'Setor {name} não encontrado', 'warning')
        return redirect(url_for('list_cells'))

    del sectors[name]
    save_sectors(sectors)

    db_mdb.add_movement(
        username=session.get('user'),
        action='sector_delete',
        details=f'Setor {name} removido',
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        unit=get_current_unit(),
        sector=DEFAULT_SECTOR
    )

    flash(f'Setor {name} removido com sucesso!', 'success')
    return redirect(url_for('list_cells'))

# ============================================================================
# ROTAS DO DASHBOARD PRINCIPAL
# ============================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard principal com visualização de prateleiras e pedidos"""
    try:
        unit = get_current_unit()
        sector = get_current_sector()
        shelves = db_mdb.get_all_shelves(unit=unit, sector=sector)
        orders = db_mdb.get_all_orders(status_filter='add', unit=unit, sector=sector)
        
        # Agrupar pedidos ativos por posição
        order_map = {}
        for order in orders:
            pos = order.get('position', '').strip()
            if pos:  # já filtramos apenas 'add' na query
                order_map.setdefault(pos, []).append(order)
        
        # Obter contagem de pedidos para TODAS as posições em uma única query
        position_counts = db_mdb.count_all_orders_in_positions(unit=unit, sector=sector)
        
        # Preparar dados das prateleiras (otimizado - evita N+1 queries)
        shelf_data = []
        for shelf in shelves:
            zone = shelf.get('zone', '').strip()
            module = shelf.get('module', '').strip()
            levels = int(shelf.get('levels', 1) or 1)
            columns = int(shelf.get('columns', 1) or 1)
            slots = int(shelf.get('slots', 7) or 7)
            
            positions = get_shelf_positions(zone, module, levels, columns)
            
            # Usar o dicionário de contagens ao invés de fazer queries individuais
            occupancy = sum(position_counts.get(pos, 0) for pos in positions)
            capacity = len(positions) * slots
            
            shelf_data.append({
                'zone': zone,
                'module': module,
                'levels': levels,
                'columns': columns,
                'slots': slots,
                'positions': positions,
                'occupancy': occupancy,
                'capacity': capacity,
                'usage_percent': int((occupancy / capacity * 100) if capacity > 0 else 0)
            })
        
        # Agrupar prateleiras por zona e coletar nomes/tags
        zone_names = load_zone_metadata()
        tag_catalog = load_tag_catalog()
        zone_tags_map = load_zone_tags_map()

        shelves_by_zone = {}
        for shelf in shelf_data:
            zone = shelf.get('zone', '')
            shelves_by_zone.setdefault(zone, []).append(shelf)

        zone_tags_display = {}
        zone_tag_entries = {}
        zone_rule_flags = {}
        ordered_zones = sort_zones_by_priority(list(shelves_by_zone.keys()), tag_catalog, zone_tags_map)
        zones_data = {}

        for zone in ordered_zones:
            zones_data[zone] = shelves_by_zone.get(zone, [])
            tag_names = []
            tag_entries = []
            for tag_key in zone_tags_map.get(zone, []):
                tag_info = tag_catalog.get(tag_key)
                if tag_info:
                    display_name = tag_info.get('name', tag_key.title())
                    tag_names.append(display_name)
                    tag_entries.append({
                        'key': tag_key,
                        'name': display_name,
                        'rule': tag_info.get('rule', 'none')
                    })
            zone_tags_display[zone] = tag_names
            zone_tag_entries[zone] = tag_entries
            zone_rule_flags[zone] = {
                'maintenance': zone_has_rule(zone, 'maintenance', tag_catalog, zone_tags_map),
                'priority': zone_has_rule(zone, 'priority', tag_catalog, zone_tags_map)
            }

        tag_options = [
            {
                'key': key,
                'name': info.get('name', key.title()),
                'rule': info.get('rule', 'none'),
                'extra_rules': info.get('extra_rules', '')
            }
            for key, info in sorted(tag_catalog.items(), key=lambda item: item[1].get('name', item[0]))
        ]
        all_zone_codes = ordered_zones
        
        # ── Visualização de prateleiras (tema Prateleiras) ───────────────────────
        preview_zones_dash = {}
        for shelf in shelf_data:
            z = shelf['zone']
            m = shelf['module']
            lv = shelf['levels']
            cl = shelf['columns']
            sl = shelf['slots']
            rows_vis = []
            for level in range(lv, 0, -1):
                cells = []
                for col in range(1, cl + 1):
                    if cl == 1:
                        position = f"{z}-{m}-{level:02d}"
                    else:
                        position = f"{z}-{m}-{level:02d}-{col:02d}"
                    raw_boxes = [o.get('box') or o.get('order_id', '') for o in order_map.get(position, [])]
                    raw_boxes = list(reversed(raw_boxes))  # mais antiga primeiro → fundo-esquerda
                    cells.append({'position': position, 'boxes': raw_boxes, 'count': len(raw_boxes)})
                rows_vis.append({'level': level, 'cells': cells})
            preview_zones_dash.setdefault(z, []).append({
                'zone': z,
                'module': m,
                'levels': lv,
                'columns': cl,
                'has_modules': cl > 1,
                'slots': sl,
                'vis_slots': min(sl, 7),
                'rows': rows_vis,
                'occupancy_percent': shelf['usage_percent'],
            })
        ordered_preview_zones_dash = [
            {'zone': z, 'shelves': sorted(preview_zones_dash[z], key=shelf_sort_key)}
            for z in sorted(preview_zones_dash.keys())
        ]

        return render_template('dashboard.html',
                             current_user=session.get('user'),
                             zones=zones_data,
                             zone_names=zone_names,
                             zone_tags=zone_tags_display,
                             zone_tag_entries=zone_tag_entries,
                             zone_rule_flags=zone_rule_flags,
                             tag_rules=TAG_RULES,
                             tag_options=tag_options,
                             order_map=order_map,
                             total_orders=len(orders),
                             preview_zones=ordered_preview_zones_dash)
    except Exception as e:
        flash(f'Erro ao carregar dashboard: {str(e)}', 'danger')
        print(f"ERRO NO DASHBOARD: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('index'))


@app.route('/prototype/shelves')
def shelf_preview():
    """Protótipo público de visualização física das prateleiras."""
    unit = get_current_unit()
    sector = get_current_sector()
    shelves = db_mdb.get_all_shelves(unit=unit, sector=sector)
    active_orders = db_mdb.get_all_orders(status_filter='add', unit=unit, sector=sector)
    source_shelves = shelves if shelves else [
        {'zone': 'A', 'module': '01', 'levels': 6, 'columns': 1, 'slots': 7},
        {'zone': 'A', 'module': '02', 'levels': 6, 'columns': 3, 'slots': 3},
        {'zone': 'A', 'module': '03', 'levels': 6, 'columns': 4, 'slots': 3},
        {'zone': 'A', 'module': '04', 'levels': 6, 'columns': 2, 'slots': 4},
        {'zone': 'A', 'module': '05', 'levels': 6, 'columns': 1, 'slots': 7},
    ]

    orders_by_position = {}
    for order in active_orders:
        position = order.get('position', '').strip().upper()
        if not position:
            continue
        box_label = str(order.get('box', '') or order.get('order_id', '')).strip()
        if not box_label:
            box_label = order.get('order_id', '')
        orders_by_position.setdefault(position, []).append(box_label)

    demo_mode = not bool(active_orders)
    demo_positions = {}

    if demo_mode:
        # Preenche ~70% com variação. Módulos de coluna única recebem até 4 colunas
        # visuais de 'slots' caixas — o template distribui horizontalmente (spreading).
        fill_pattern = [1.0, 1.0, 0.75, 0.5, 1.0, 0.75, 0.0, 1.0, 0.5, 0.75]
        box_num = 1000
        pos_idx = 0
        for s in source_shelves:
            z = str(s.get('zone', '')).strip().upper()
            m = str(s.get('module', '')).strip().upper()
            lv = int(s.get('levels', 1) or 1)
            cl = int(s.get('columns', 1) or 1)
            sl = int(s.get('slots', 7) or 7)
            # coluna única: preenche até 4 × slots boxes por posição para mostrar spreading
            vis_cols = 4 if cl == 1 else 1
            for pos in get_shelf_positions(z, m, lv, cl):
                ratio = fill_pattern[pos_idx % len(fill_pattern)]
                count = round(sl * vis_cols * ratio)
                if count > 0:
                    demo_positions[pos] = [f'CX-{box_num + j}' for j in range(count)]
                    box_num += count
                pos_idx += 1

    preview_zones = {}
    for shelf in source_shelves:
        zone = str(shelf.get('zone', '')).strip().upper() or 'SEM ZONA'
        module = str(shelf.get('module', '')).strip().upper() or '01'
        levels = int(shelf.get('levels', 1) or 1)
        columns = int(shelf.get('columns', 1) or 1)
        slots = int(shelf.get('slots', 7) or 7)

        rows = []
        shelf_display_count = 0
        for level in range(levels, 0, -1):
            cells = []
            for col in range(1, columns + 1):
                if columns == 1:
                    position = f"{zone}-{module}-{level:02d}"
                else:
                    position = f"{zone}-{module}-{level:02d}-{col:02d}"

                raw_boxes = orders_by_position.get(position, [])
                if demo_mode and not raw_boxes:
                    raw_boxes = demo_positions.get(position, [])
                else:
                    raw_boxes = list(reversed(raw_boxes))  # mais antiga primeiro → fundo-esquerda

                shelf_display_count += min(len(raw_boxes), slots)

                cells.append({
                    'position': position,
                    'boxes': raw_boxes,
                    'count': len(raw_boxes)
                })

            rows.append({
                'level': level,
                'cells': cells,
            })

        preview_zones.setdefault(zone, []).append({
            'zone': zone,
            'module': module,
            'levels': levels,
            'columns': columns,
            'has_modules': columns > 1,
            'slots': slots,
            'vis_slots': min(slots, 7),
            'rows': rows,
            'position_count': levels * columns,
            'occupied_count': shelf_display_count,
            'capacity': levels * columns * slots,
            'occupancy_percent': min(100, int((shelf_display_count / (levels * columns * slots)) * 100)) if (levels * columns * slots) > 0 else 0
        })

    ordered_preview_zones = []
    for zone in sorted(preview_zones.keys()):
        ordered_preview_zones.append({
            'zone': zone,
            'shelves': sorted(preview_zones[zone], key=shelf_sort_key)
        })

    return render_template(
        'shelf_preview.html',
        preview_zones=ordered_preview_zones,
        shelf_total=sum(len(item['shelves']) for item in ordered_preview_zones),
        order_total=len(active_orders),
        demo_mode=demo_mode,
        unit=unit,
        sector=sector or DEFAULT_SECTOR,
    )

@app.route('/zone/add', methods=['POST'])
@login_required
def add_zone():
    """Cria uma nova zona (apenas para registrar metadados)"""
    master_key = request.form.get('master_key', '')
    
    if not is_master(master_key):
        flash('Senha mestre incorreta', 'danger')
        return redirect(url_for('dashboard'))
    
    zone = request.form.get('zone', '').strip().upper()
    zone_name = request.form.get('zone_name', '').strip()
    
    if not zone:
        flash('Código da zona é obrigatório', 'danger')
        return redirect(url_for('dashboard'))

    unit = get_current_unit()

    if zone_name:
        upsert_zone_name(zone, zone_name)
    
    # Registrar movimento de criação de zona
    db_mdb.add_movement(
        username=session.get('user'),
        action='zone_create',
        position=zone,
        order_id='',
        box='',
        details=f'Nova zona criada: {zone_name}' if zone_name else f'Nova zona: {zone}',
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        unit=unit,
        sector=get_current_sector() or DEFAULT_SECTOR
    )
    
    flash(f'Zona {zone} criada com sucesso!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/tag/add', methods=['POST'])
@login_required
def add_tag():
    """Cria ou atualiza uma TAG com regra de negocio."""
    master_key = request.form.get('master_key', '')

    if not is_master(master_key):
        flash('Senha mestre incorreta', 'danger')
        return redirect(url_for('dashboard'))

    unit = get_current_unit()

    tag_name = request.form.get('tag_name', '').strip()
    tag_rule = request.form.get('tag_rule', 'none').strip().lower()
    extra_rules = request.form.get('extra_rules', '').strip()

    if not tag_name:
        flash('Nome da TAG é obrigatório', 'danger')
        return redirect(url_for('dashboard'))

    if tag_rule not in TAG_RULES:
        flash('Regra da TAG inválida', 'danger')
        return redirect(url_for('dashboard'))

    saved = upsert_tag_definition(tag_name, tag_rule, extra_rules)
    if not saved:
        flash('Não foi possível salvar a TAG', 'danger')
        return redirect(url_for('dashboard'))

    db_mdb.add_movement(
        username=session.get('user'),
        action='tag_upsert',
        position='',
        order_id='',
        box='',
        details=f'TAG {tag_name} ({tag_rule}) criada/atualizada',
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        unit=unit,
        sector=get_current_sector() or DEFAULT_SECTOR
    )

    flash(f'TAG {tag_name} salva com sucesso', 'success')
    return redirect(url_for('dashboard'))

@app.route('/tag/remove-zone', methods=['POST'])
@login_required
def remove_tag_from_zone():
    """Remove o vinculo de uma ou mais TAGs de uma zona."""
    zone = request.form.get('zone', '').strip().upper()
    tag_keys = request.form.getlist('tag_keys')
    single_tag_key = request.form.get('tag_key', '').strip()
    if single_tag_key:
        tag_keys.append(single_tag_key)

    if not zone:
        flash('Zona é obrigatória para remover TAG', 'danger')
        return redirect(url_for('dashboard'))

    if not tag_keys:
        flash('Selecione ao menos uma TAG para remover da zona', 'warning')
        return redirect(url_for('dashboard'))

    unit = get_current_unit()

    removed_count = detach_tags_from_zone(zone, tag_keys)
    if removed_count == 0:
        flash(f'Nenhuma TAG removida da zona {zone}', 'warning')
        return redirect(url_for('dashboard'))

    db_mdb.add_movement(
        username=session.get('user'),
        action='tag_zone_remove',
        position=zone,
        order_id='',
        box='',
        details=f'{removed_count} TAG(s) removida(s) da zona {zone}',
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        unit=unit,
        sector=get_current_sector() or DEFAULT_SECTOR
    )

    flash(f'{removed_count} TAG(s) removida(s) da zona {zone}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/tag/attach-zone', methods=['POST'])
@login_required
def attach_tag_to_zone():
    """Anexa uma tag existente em uma zona."""
    zone = request.form.get('zone', '').strip().upper()
    tag_key = request.form.get('tag_key', '').strip()

    if not zone:
        flash('Zona é obrigatória', 'danger')
        return redirect(url_for('dashboard'))

    unit = get_current_unit()

    normalized_tag_key = normalize_tag_key(tag_key)
    tag_catalog = load_tag_catalog()
    if normalized_tag_key not in tag_catalog:
        flash('TAG selecionada não existe no catálogo', 'warning')
        return redirect(url_for('dashboard'))

    attach_tags_to_zone(zone, [normalized_tag_key])
    tag_name = tag_catalog[normalized_tag_key].get('name', normalized_tag_key.title())

    db_mdb.add_movement(
        username=session.get('user'),
        action='tag_zone_attach',
        position=zone,
        order_id='',
        box='',
        details=f'TAG {tag_name} anexada na zona {zone}',
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        unit=unit,
        sector=get_current_sector() or DEFAULT_SECTOR
    )

    flash(f'TAG {tag_name} adicionada na zona {zone}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/tag/create-attach-zone', methods=['POST'])
@login_required
def create_and_attach_tag_to_zone():
    """Cria uma TAG e anexa diretamente em uma zona."""
    zone = request.form.get('zone', '').strip().upper()
    tag_name = request.form.get('tag_name', '').strip()
    tag_rule = request.form.get('tag_rule', 'none').strip().lower()
    extra_rules = request.form.get('extra_rules', '').strip()

    if not zone:
        flash('Zona é obrigatória', 'danger')
        return redirect(url_for('dashboard'))

    unit = get_current_unit()

    if not tag_name:
        flash('Nome da TAG é obrigatório', 'danger')
        return redirect(url_for('dashboard'))

    if tag_rule not in TAG_RULES:
        flash('Regra da TAG inválida', 'danger')
        return redirect(url_for('dashboard'))

    saved = upsert_tag_definition(tag_name, tag_rule, extra_rules)
    if not saved:
        flash('Não foi possível criar a TAG', 'danger')
        return redirect(url_for('dashboard'))

    normalized_tag_key = normalize_tag_key(tag_name)
    attach_tags_to_zone(zone, [normalized_tag_key])

    db_mdb.add_movement(
        username=session.get('user'),
        action='tag_zone_create_attach',
        position=zone,
        order_id='',
        box='',
        details=f'TAG {tag_name} ({tag_rule}) criada e anexada na zona {zone}',
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        unit=unit,
        sector=get_current_sector() or DEFAULT_SECTOR
    )

    flash(f'TAG {tag_name} criada e adicionada na zona {zone}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/tag/delete', methods=['POST'])
@login_required
def delete_tag():
    """Exclui TAG do catalogo e remove vinculos nas zonas."""
    master_key = request.form.get('master_key', '')

    if not is_master(master_key):
        flash('Senha mestre incorreta', 'danger')
        return redirect(url_for('dashboard'))

    unit = get_current_unit()

    tag_key = request.form.get('tag_key', '').strip()
    if not tag_key:
        flash('Selecione uma TAG para excluir', 'danger')
        return redirect(url_for('dashboard'))

    deleted = delete_tag_definition(tag_key)
    if not deleted:
        flash('TAG não encontrada no catálogo', 'warning')
        return redirect(url_for('dashboard'))

    db_mdb.add_movement(
        username=session.get('user'),
        action='tag_delete',
        position='',
        order_id='',
        box='',
        details=f'TAG {normalize_tag_key(tag_key)} excluida do catálogo',
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        unit=unit,
        sector=get_current_sector() or DEFAULT_SECTOR
    )

    flash('TAG excluída do catálogo com sucesso', 'success')
    return redirect(url_for('dashboard'))

# ============================================================================
# ROTAS DE GERENCIAMENTO DE PRATELEIRAS
# ============================================================================

@app.route('/shelf/add', methods=['POST'])
@login_required
def add_shelf():
    """Adiciona nova prateleira (requer senha mestre)"""
    master_key = request.form.get('master_key', '')
    
    if not is_master(master_key):
        flash('Senha mestre incorreta', 'danger')
        return redirect(url_for('dashboard'))
    
    zone = request.form.get('zone', '').strip().upper()
    zone_name = request.form.get('zone_name', '').strip()
    selected_tags = request.form.getlist('zone_tags')
    module = request.form.get('module', '').strip().zfill(2)
    levels = max(1, int(request.form.get('levels', 1) or 1))
    columns = max(1, int(request.form.get('columns', 1) or 1))
    slots = max(1, int(request.form.get('slots', 7) or 7))
    
    if not zone or not module:
        flash('Zona e Módulo são obrigatórios', 'danger')
        return redirect(url_for('dashboard'))

    if zone_name:
        upsert_zone_name(zone, zone_name)

    if selected_tags:
        tag_catalog = load_tag_catalog()
        valid_tag_keys = []
        for tag_key in selected_tags:
            normalized = normalize_tag_key(tag_key)
            if normalized in tag_catalog and normalized not in valid_tag_keys:
                valid_tag_keys.append(normalized)
        attach_tags_to_zone(zone, valid_tag_keys)
    
    unit = get_current_unit()

    # Verificar se já existe
    existing = find_shelf(zone, module, unit=unit, sector=get_current_sector())
    if existing:
        if zone_name:
            flash(f'Descrição da zona {zone} atualizada com sucesso', 'info')
        flash(f'Prateleira {zone}-{module} já existe', 'warning')
    else:
        db_mdb.add_shelf(zone, module, levels, columns, slots, unit=unit, sector=get_current_sector())
        db_mdb.add_movement(
            username=session.get('user'),
            action='shelf_add',
            position=f'{zone}-{module}',
            order_id='',
            box='',
            details=f'Nova prateleira ({zone_name})' if zone_name else 'Nova prateleira',
            timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            unit=unit,
            sector=get_current_sector() or DEFAULT_SECTOR
        )
        flash(f'Prateleira {zone}-{module} criada com sucesso', 'success')
    
    return redirect(url_for('dashboard'))

@app.route('/shelf/remove', methods=['POST'])
@login_required
def remove_shelf():
    """Remove prateleira (requer senha mestre)"""
    master_key = request.form.get('master_key', '')
    
    if not is_master(master_key):
        flash('Senha mestre incorreta', 'danger')
        return redirect(url_for('dashboard'))
    
    zone = request.form.get('zone', '').strip().upper()
    module = request.form.get('module', '').strip().zfill(2)
    
    unit = get_current_unit()
    sector = get_current_sector()
    shelf = find_shelf(zone, module, unit=unit, sector=sector)
    if shelf:
        # ANTES de deletar a prateleira, remover todos os pedidos dela
        levels = shelf.get('levels', 1)
        columns = shelf.get('columns', 1)
        positions = get_shelf_positions(zone, module, levels, columns)
        
        removed_count = 0
        current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        current_user = session.get('user', 'admin')
        
        for position in positions:
            orders = db_mdb.get_orders_by_position(position, unit=unit, sector=sector)
            for order in orders:
                order_id = order.get('order_id', '')
                box = order.get('box', '')
                db_mdb.update_order_status(order_id=order_id, status='removed', removed_at=current_time, removed_by=current_user, unit=unit)
                db_mdb.clear_order_position(order_id, unit=unit)
                db_mdb.add_movement(username=current_user, action='order_checkout', position=position, order_id=order_id, box=box,
                    details=f'Pedido removido automaticamente - Prateleira {zone}-{module} deletada', timestamp=current_time, unit=unit, sector=sector or DEFAULT_SECTOR)
                removed_count += 1
        
        all_orders = db_mdb.get_all_orders(unit=unit, sector=sector)
        orphaned_shelf_orders = [
            o for o in all_orders 
            if o.get('status') == 'add' and 
            o.get('position', '').upper().startswith(f"{zone}-{module}-")
            and o.get('position', '').upper() not in positions
        ]
        
        for order in orphaned_shelf_orders:
            order_id = order.get('order_id', '')
            box = order.get('box', '')
            position = order.get('position', '')
            db_mdb.update_order_status(order_id=order_id, status='removed', removed_at=current_time, removed_by=current_user, unit=unit)
            db_mdb.add_movement(username=current_user, action='order_checkout', position=position, order_id=order_id, box=box,
                details=f'Pedido removido automaticamente - Prateleira {zone}-{module} deletada (posição órfã)', timestamp=current_time, unit=unit, sector=sector or DEFAULT_SECTOR)
            removed_count += 1
        
        db_mdb.delete_shelf(zone, module, unit=unit)
        db_mdb.add_movement(username=current_user, action='shelf_remove', position=f'{zone}-{module}', order_id='', box='',
            details=f'Prateleira removida - {removed_count} pedido(s) foram dados saída automaticamente', timestamp=current_time, unit=unit, sector=sector or DEFAULT_SECTOR)
        
        if removed_count > 0:
            flash(f'Prateleira {zone}-{module} removida com sucesso. {removed_count} pedido(s) foram dados saída do sistema.', 'success')
        else:
            flash(f'Prateleira {zone}-{module} removida com sucesso', 'success')
    else:
        flash('Prateleira não encontrada', 'warning')
    
    return redirect(url_for('dashboard'))

@app.route('/zone/remove', methods=['POST'])
@login_required
def remove_zone():
    """Remove zona inteira com todos seus módulos e pedidos (requer senha mestre)"""
    master_key = request.form.get('master_key', '')
    
    if not is_master(master_key):
        flash('Senha mestre incorreta', 'danger')
        return redirect(url_for('dashboard'))
    
    zone = request.form.get('zone', '').strip().upper()
    
    if not zone:
        flash('Zona não informada', 'danger')
        return redirect(url_for('dashboard'))
    
    # Buscar todas as prateleiras da zona
    unit = get_current_unit()
    sector = get_current_sector()
    shelves = db_mdb.get_all_shelves(unit=unit, sector=sector)
    zone_shelves = [s for s in shelves if s.get('zone', '').upper() == zone]
    
    # Remover todos os pedidos de todas as prateleiras da zona
    total_removed_orders = 0
    current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    current_user = session.get('user', 'admin')
    
    for shelf in zone_shelves:
        zone_code = shelf.get('zone', '')
        module = shelf.get('module', '')
        levels = shelf.get('levels', 1)
        columns = shelf.get('columns', 1)
        
        positions = get_shelf_positions(zone_code, module, levels, columns)
        
        # Para cada posição da prateleira
        for position in positions:
            # Buscar pedidos ativos naquela posição
            orders = db_mdb.get_orders_by_position(position, unit=unit)
            
            for order in orders:
                order_id = order.get('order_id', '')
                box = order.get('box', '')
                
                # Marcar pedido como removido
                db_mdb.update_order_status(
                    order_id=order_id,
                    status='removed',
                    removed_at=current_time,
                    removed_by=current_user,
                    unit=unit
                )
                
                # Registrar movimento de saída
                db_mdb.add_movement(
                    username=current_user,
                    action='order_checkout',
                    position=position,
                    order_id=order_id,
                    box=box,
                    details=f'Pedido removido automaticamente - Zona {zone_code} deletada',
                    timestamp=current_time,
                    unit=unit,
                    sector=sector or DEFAULT_SECTOR
                )
                
                total_removed_orders += 1
        
        # Deletar a prateleira
        db_mdb.delete_shelf(zone_code, module, unit=unit)
    
    # IMPORTANTE: Também remover QUALQUER pedido que esteja na zona mas em posições órfãs
    # (posições sem prateleira associada)
    all_orders = db_mdb.get_all_orders(unit=unit)
    orphaned_zone_orders = [
        o for o in all_orders 
        if o.get('status') == 'add' and o.get('position', '').strip().upper().startswith(f"{zone}-")
    ]
    
    for order in orphaned_zone_orders:
        order_id = order.get('order_id', '')
        box = order.get('box', '')
        position = order.get('position', '')
        
        # Marcar pedido como removido
        db_mdb.update_order_status(
            order_id=order_id,
            status='removed',
            removed_at=current_time,
            removed_by=current_user,
            unit=unit
        )
        db_mdb.clear_order_position(order_id, unit=unit)
        
        # Registrar movimento de saída
        db_mdb.add_movement(
            username=current_user,
            action='order_checkout',
            position=position,
            order_id=order_id,
            box=box,
            details=f'Pedido removido automaticamente - Zona {zone} deletada (posição órfã)',
            timestamp=current_time,
            unit=unit,
            sector=sector or DEFAULT_SECTOR
        )
        
        total_removed_orders += 1

    if not zone_shelves and total_removed_orders == 0:
        flash('Nenhuma prateleira ou pedido ativo encontrado para esta zona', 'warning')
        return redirect(url_for('dashboard'))
    
    # Registrar movimento de zona removida
    db_mdb.add_movement(
        username=current_user,
        action='zone_remove',
        position=zone,
        order_id='',
        box='',
        details=f'Zona removida - {len(zone_shelves)} módulo(s), {total_removed_orders} pedido(s) foram dados saída automaticamente',
        timestamp=current_time,
        unit=unit,
        sector=sector or DEFAULT_SECTOR
    )

    delete_zone_name(zone)
    remove_zone_tags(zone)
    
    flash(f'Zona {zone} removida com sucesso. {len(zone_shelves)} módulo(s) e {total_removed_orders} pedido(s) foram dados saída do sistema.', 'success')
    
    return redirect(url_for('dashboard'))

# ============================================================================

@app.route('/order/add', methods=['GET', 'POST'])
@login_required
def add_order():
    """Adiciona novo pedido"""
    unit = get_current_unit()
    sector = get_current_sector()
    shelves = db_mdb.get_all_shelves(unit=unit, sector=sector)
    position_counts = db_mdb.count_all_orders_in_positions(unit=unit, sector=sector)
    quick_mode_from_query = request.args.get('quick', '0') == '1'

    def redirect_add_order(zone_value='', bipador=False, quick=False):
        """Redireciona para o formulario preservando contexto do modo bipador."""
        params = {}
        if zone_value:
            params['zone'] = zone_value
        if bipador:
            params['bipador'] = '1'
        if quick:
            params['quick'] = '1'
        return redirect(url_for('add_order', **params))
    
    if request.method == 'POST':
        order_id = request.form.get('order_id', '').strip()
        box = request.form.get('box', '').strip()
        zone = request.form.get('zone', '').strip().upper()
        bipador_mode = request.form.get('bipador_mode', '0') == '1'
        quick_mode = request.form.get('quick_mode', '0') == '1'
        
        if not zone:
            flash('Selecione uma zona para alocar o pedido', 'danger')
            return redirect_add_order(bipador=bipador_mode, quick=quick_mode)
        
        if not order_id:
            flash('ID do Pedido é obrigatório', 'danger')
            return redirect_add_order(zone_value=zone, bipador=bipador_mode, quick=quick_mode)
        
        # Regra de negocio: o backend sempre define o endereco automaticamente.
        # Isso evita que o front-end envie uma posicao desatualizada.
        position = get_best_position_for_zone(zone)
        if not position:
            flash(f'Nenhuma posição disponível na zona {zone}', 'warning')
            return redirect_add_order(zone_value=zone, bipador=bipador_mode, quick=quick_mode)
        
        # Verificar se pedido ja existe
        existing_order = db_mdb.get_order_by_id(order_id, unit=unit)
        if existing_order and existing_order.get('status', 'add') == 'add':
            flash(f'Pedido {order_id} já existe no sistema!', 'danger')
            return redirect_add_order(zone_value=zone, bipador=bipador_mode, quick=quick_mode)
        
        # Validar capacidade usando o dicionário de contagens
        count = position_counts.get(position, 0)
        shelf_info = None
        for s in shelves:
            positions = get_shelf_positions(s.get('zone'), s.get('module'),
                                          s.get('levels', 1), s.get('columns', 1))
            if position in positions:
                shelf_info = s
                break
        
        if shelf_info and count >= shelf_info.get('slots', 7):
            flash(f'Posição {position} está cheia', 'danger')
            return redirect_add_order(zone_value=zone, bipador=bipador_mode, quick=quick_mode)
        
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        try:
            # Se ja existe como removed, reativa o registro existente.
            if existing_order and existing_order.get('status') == 'removed':
                db_mdb.reactivate_order(
                    order_id=order_id,
                    position=position,
                    box=box,
                    timestamp=now_str,
                    unit=unit
                )
                movement_action = 'order_reactivate'
                movement_details = 'Pedido reativado'
            else:
                # Novo pedido: insere normalmente.
                db_mdb.add_order(
                    position=position,
                    order_id=order_id,
                    box=box,
                    date=now_str,
                    timestamp=now_str,
                    created_by=session.get('user', 'Sistema'),
                    status='add',
                    unit=unit,
                    sector=sector
                )
                movement_action = 'order_add'
                movement_details = 'Pedido adicionado'
        except Exception:
            flash(f'Falha ao salvar o pedido {order_id}. Tente novamente.', 'danger')
            return redirect_add_order(zone_value=zone, bipador=bipador_mode, quick=quick_mode)
        
        # Registrar movimento
        db_mdb.add_movement(
            username=session.get('user'),
            action=movement_action,
            position=position,
            order_id=order_id,
            box=box,
            details=movement_details,
            timestamp=now_str,
            unit=unit,
            sector=sector or DEFAULT_SECTOR
        )
        
        flash(f'Pedido {order_id} adicionado à posição {position}', 'success')
        if bipador_mode or quick_mode:
            return redirect_add_order(zone_value=zone, bipador=bipador_mode, quick=quick_mode)
        return redirect(url_for('position_detail', code=position))
    
    # GET - Preparar dados para form
    positions = []
    zones = set()
    tag_catalog = load_tag_catalog()
    zone_tags_map = load_zone_tags_map()
    for shelf in shelves:
        zone = shelf.get('zone', '')
        if not zone_has_rule(zone, 'maintenance', tag_catalog, zone_tags_map):
            zones.add(zone)
        module = shelf.get('module', '')
        levels = shelf.get('levels', 1)
        columns = shelf.get('columns', 1)
        positions.extend(get_shelf_positions(zone, module, levels, columns))
    
    requested_zone = request.args.get('zone', '').strip().upper()
    suggested_position = None
    
    if requested_zone and not zone_has_rule(requested_zone, 'maintenance', tag_catalog, zone_tags_map):
        suggested_position = get_best_position_for_zone(requested_zone)
    
    return render_template('order_form.html', 
                         positions=positions, 
                         zones=sort_zones_by_priority(list(zones), tag_catalog, zone_tags_map),
                         suggested_position=suggested_position,
                         requested_zone=requested_zone,
                         quick_mode=quick_mode_from_query)

@app.route('/position/<code>')
@login_required
def position_detail(code):
    """Página detalhada de uma posição"""
    unit = get_current_unit()
    sector = get_current_sector()
    orders = db_mdb.get_orders_by_position(code, unit=unit, sector=sector)
    
    # Obter todas as posições disponíveis
    shelves = db_mdb.get_all_shelves(unit=unit, sector=sector)
    all_positions = []
    for shelf in shelves:
        zone = shelf.get('zone', '')
        module = shelf.get('module', '')
        levels = shelf.get('levels', 1)
        columns = shelf.get('columns', 1)
        all_positions.extend(get_shelf_positions(zone, module, levels, columns))
    
    return render_template('position_detail.html',
                         code=code,
                         orders=orders,
                         all_positions=all_positions,
                         current_user=session.get('user'))

@app.route('/order/checkout', methods=['GET', 'POST'])
@login_required
def checkout_order():
    """Dar saída em pedido pelo ID"""
    unit = get_current_unit()
    if request.method == 'POST':
        order_id = request.form.get('order_id', '').strip()
        
        if not order_id:
            flash('Digite o ID do pedido', 'danger')
            return redirect(url_for('checkout_order'))
        
        order = db_mdb.get_order_by_id(order_id, unit=unit)
        
        if not order or order.get('status', 'add') != 'add':
            flash(f'Pedido {order_id} não encontrado ou já foi removido', 'warning')
            return redirect(url_for('checkout_order'))
        
        # Atualizar status para removido
        position = order.get('position', '')
        box = order.get('box', '')
        
        db_mdb.update_order_status(
            order_id=order_id,
            status='removed',
            removed_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            removed_by=session.get('user', 'Sistema'),
            unit=unit
        )
        
        # Registrar movimento
        db_mdb.add_movement(
            username=session.get('user'),
            action='order_checkout',
            position=position,
            order_id=order_id,
            box=box,
            details=f'Saída do sistema - estava em {position}',
            timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            unit=unit,
            sector=get_current_sector() or DEFAULT_SECTOR
        )
        
        flash(f'✅ Pedido {order_id} retirado com sucesso da posição {position}!', 'success')
        return redirect(url_for('checkout_order'))
    
    return render_template('checkout.html')

@app.route('/order/remove', methods=['POST'])
@login_required
def remove_order():
    """Remove um pedido (muda status para removed)"""
    unit = get_current_unit()
    position = request.form.get('position', '').strip().upper()
    order_id = request.form.get('order_id', '').strip()
    
    order = db_mdb.get_order_by_id(order_id, unit=unit)
    
    if order and order.get('position') == position:
        db_mdb.update_order_status(order_id, 'removed', unit=unit)
        db_mdb.add_movement(
            username=session.get('user'),
            action='order_remove',
            position=position,
            order_id=order_id,
            box=order.get('box', ''),
            details='Pedido removido',
            timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            unit=unit,
            sector=get_current_sector() or DEFAULT_SECTOR
        )
        flash(f'Pedido {order_id} removido', 'success')
    else:
        flash('Pedido não encontrado', 'warning')
    
    return redirect(url_for('position_detail', code=position))

@app.route('/order/move', methods=['POST'])
@login_required
def move_order():
    """Move um pedido para outra posição (apenas admin)"""
    unit = get_current_unit()
    # Verificar se o usuário é admin
    current_user = session.get('user', '')
    if current_user.lower() != 'admin':
        flash('Apenas o usuário admin pode mover pedidos!', 'danger')
        position = request.form.get('position', '').strip().upper()
        return redirect(url_for('position_detail', code=position))
    
    position = request.form.get('position', '').strip().upper()
    order_id = request.form.get('order_id', '').strip()
    destination = request.form.get('destination', '').strip().upper()
    
    # Validar se destino foi selecionado
    if not destination:
        flash('Selecione um local para mover o pedido', 'warning')
        return redirect(url_for('position_detail', code=position))
    
    if position == destination:
        flash('Origem e destino são iguais', 'warning')
        return redirect(url_for('position_detail', code=position))
    
    # Buscar pedido
    order = db_mdb.get_order_by_id(order_id, unit=unit)
    
    if not order or order.get('position') != position:
        flash('Pedido não encontrado', 'danger')
        return redirect(url_for('position_detail', code=position))
    
    # Verificar capacidade do destino
    dest_count = count_orders_at_position(destination, unit=unit, sector=get_current_sector())
    shelves = db_mdb.get_all_shelves(unit=unit, sector=get_current_sector())
    
    dest_capacity = 7  # default
    for shelf in shelves:
        positions = get_shelf_positions(shelf.get('zone'), shelf.get('module'),
                                       shelf.get('levels', 1), shelf.get('columns', 1))
        if destination in positions:
            dest_capacity = shelf.get('slots', 7)
            break
    
    if dest_count >= dest_capacity:
        flash(f'Posição {destination} está cheia', 'danger')
        return redirect(url_for('position_detail', code=position))
    
    # Mover pedido usando UPDATE
    # Para isso, precisamos apenas atualizar a posição do pedido.
    try:
        db_mdb.update_order_position(order_id, destination, unit=unit)
        
        # Registrar movimento
        db_mdb.add_movement(
            username=session.get('user'),
            action='order_move',
            position=f'{position}→{destination}',
            order_id=order_id,
            box=order.get('box', ''),
            details=f'Pedido movido de {position} para {destination}',
            timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            unit=unit,
            sector=get_current_sector() or DEFAULT_SECTOR
        )
        
        flash(f'Pedido {order_id} movido de {position} para {destination}', 'success')
    except Exception as e:
        flash(f'Erro ao mover pedido: {str(e)}', 'danger')
        return redirect(url_for('position_detail', code=position))
    
    return redirect(url_for('position_detail', code=destination))

# ============================================================================
# ROTAS DE VISUALIZAÇÃO
# ============================================================================

@app.route('/movements')
@login_required
def view_movements():
    """Visualiza histórico de movimentos"""
    movements = db_mdb.get_all_movements(unit=get_current_unit(), sector=get_current_sector())
    return render_template('movements.html', movements=movements)

@app.route('/api/level/<zone>/<module>/<int:level>')
@login_required
def api_level_detail(zone, module, level):
    """API que retorna pedidos ativos de um andar em JSON"""
    unit = get_current_unit()
    sector = get_current_sector()
    shelves = db_mdb.get_all_shelves(unit=unit, sector=sector)
    
    # Encontrar a prateleira
    shelf = None
    for s in shelves:
        if s.get('zone') == zone and s.get('module') == module:
            shelf = s
            break
    
    if not shelf:
        return jsonify({'error': 'Prateleira não encontrada'}), 404
    
    # Gerar posições do andar
    columns = shelf.get('columns', 1)
    positions_in_level = []
    if columns == 1:
        positions_in_level.append(f"{zone}-{module}-{level:02d}")
    else:
        for col in range(1, columns + 1):
            positions_in_level.append(f"{zone}-{module}-{level:02d}-{col:02d}")
    
    # Obter pedidos ativos deste andar
    all_orders = db_mdb.get_all_orders(status_filter='add', unit=unit, sector=sector)
    level_orders = [o for o in all_orders if o.get('position', '').strip().upper() in positions_in_level]
    
    return jsonify({
        'level': level,
        'zone': zone,
        'module': module,
        'shelf': shelf,
        'orders': level_orders,
        'total': len(level_orders)
    })

@app.route('/search', methods=['GET'])
@login_required
def search_orders():
    """Página de busca de pedidos"""
    unit = get_current_unit()
    sector = get_current_sector()
    all_orders = db_mdb.get_all_orders(status_filter='add', unit=unit, sector=sector)
    
    # Busca por query string
    query = request.args.get('q', '').strip().upper()
    
    if query:
        filtered_orders = db_mdb.search_orders(query, unit=unit, sector=sector)
        all_orders = filtered_orders
    
    return render_template('search.html', 
                         orders=all_orders, 
                         total=len(all_orders),
                         query=query)

@app.route('/api/search/autocomplete')
@login_required
def search_autocomplete():
    """API de autocomplete para busca de pedidos (apenas ativos)"""
    query = request.args.get('q', '').strip().upper()
    
    if not query or len(query) < 2:
        return jsonify({'suggestions': []})
    
    orders = db_mdb.get_all_orders(status_filter='add', unit=get_current_unit(), sector=get_current_sector())
    
    suggestions = []
    seen = set()
    
    for order in orders:
        order_id = order.get('order_id', '')
        position = order.get('position', '')
        box = order.get('box', '')
        
        if order_id.upper().startswith(query) and order_id not in seen:
            suggestions.append({
                'value': order_id,
                'label': f"📦 Pedido: {order_id}",
                'type': 'order_id'
            })
            seen.add(order_id)
        
        if position.upper().startswith(query) and position not in seen:
            suggestions.append({
                'value': position,
                'label': f"📍 Posição: {position}",
                'type': 'position'
            })
            seen.add(position)
        
        if box and box.upper().startswith(query) and box not in seen:
            suggestions.append({
                'value': box,
                'label': f"📦 Caixa: {box}",
                'type': 'box'
            })
            seen.add(box)
    
    suggestions = suggestions[:10]
    
    return jsonify({'suggestions': suggestions})

@app.route('/users')
@login_required
def list_users():
    """Lista todos os usuários"""
    unit = get_current_unit()
    users = db_mdb.get_all_users(unit=unit)
    current_user = session.get('user')
    
    return render_template('users.html', users=users, current_user=current_user, current_unit=unit)

@app.route('/user/reset-password', methods=['POST'])
@login_required
def reset_user_password():
    """Reseta a senha de um usuário (apenas admin)"""
    unit = get_current_unit()
    target_username = request.form.get('username', '').strip()
    new_password = request.form.get('new_password', '').strip()
    master_pass = request.form.get('master_password', '').strip()
    
    # Validar senha mestre
    if not is_master(master_pass):
        flash('Senha mestre incorreta!', 'danger')
        return redirect(url_for('list_users'))
    
    # Validar nova senha
    valid, msg = validate_password(new_password)
    if not valid:
        flash(msg, 'danger')
        return redirect(url_for('list_users'))
    
    # Verificar se usuário existe
    user = find_user(target_username, unit=unit)
    if not user:
        flash(f'Usuário "{target_username}" não encontrado!', 'danger')
        return redirect(url_for('list_users'))
    
    # Atualizar senha
    try:
        db_mdb.update_user(target_username, unit=unit, password=new_password)
        flash(f'Senha de "{target_username}" alterada com sucesso!', 'success')
        
        # Registrar auditoria
        db_mdb.add_movement(
            username=session.get('user'),
            action='reset_password',
            details=f'Senha do usuário "{target_username}" foi resetada',
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            unit=unit,
            sector=get_current_sector() or DEFAULT_SECTOR
        )
    except Exception as e:
        flash(f'Erro ao resetar senha: {str(e)}', 'danger')
    
    return redirect(url_for('list_users'))

@app.route('/user/toggle-status', methods=['POST'])
@login_required
def toggle_user_status():
    """Ativa ou desativa um usuário (apenas admin)"""
    unit = get_current_unit()
    target_username = request.form.get('username', '').strip()
    master_pass = request.form.get('master_password', '').strip()
    
    # Validar senha mestre
    if not is_master(master_pass):
        flash('Senha mestre incorreta!', 'danger')
        return redirect(url_for('list_users'))
    
    # Não permitir desativar o próprio usuário
    if target_username == session.get('user'):
        flash('Você não pode desativar sua própria conta!', 'warning')
        return redirect(url_for('list_users'))
    
    # Verificar se usuário existe
    user = find_user(target_username, unit=unit)
    if not user:
        flash(f'Usuário "{target_username}" não encontrado!', 'danger')
        return redirect(url_for('list_users'))
    
    # Alternar status
    try:
        new_status = not bool(user.get('active', True))
        db_mdb.update_user(target_username, unit=unit, active=new_status)
        
        status_text = 'ativado' if new_status else 'desativado'
        flash(f'Usuário "{target_username}" {status_text} com sucesso!', 'success')
        
        # Registrar auditoria
        db_mdb.add_movement(
            username=session.get('user'),
            action='toggle_user_status',
            details=f'Usuário "{target_username}" {status_text}',
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            unit=unit,
            sector=get_current_sector() or DEFAULT_SECTOR
        )
    except Exception as e:
        flash(f'Erro ao alterar status: {str(e)}', 'danger')
    
    return redirect(url_for('list_users'))

@app.route('/user/delete', methods=['POST'])
@login_required
def delete_user():
    """Deleta um usuário do sistema (apenas admin)"""
    unit = get_current_unit()
    target_username = request.form.get('username', '').strip()
    master_pass = request.form.get('master_password', '').strip()
    
    # Validar senha mestre
    if not is_master(master_pass):
        flash('Senha mestre incorreta!', 'danger')
        return redirect(url_for('list_users'))
    
    # Não permitir deletar o próprio usuário
    if target_username == session.get('user'):
        flash('Você não pode deletar sua própria conta!', 'warning')
        return redirect(url_for('list_users'))
    
    # Verificar se usuário existe
    user = find_user(target_username, unit=unit)
    if not user:
        flash(f'Usuário "{target_username}" não encontrado!', 'danger')
        return redirect(url_for('list_users'))
    
    # Deletar usuário
    try:
        db_mdb.delete_user(target_username, unit=unit)
        flash(f'Usuário "{target_username}" deletado com sucesso!', 'success')
        
        # Registrar auditoria
        db_mdb.add_movement(
            username=session.get('user'),
            action='delete_user',
            details=f'Usuário "{target_username}" foi deletado do sistema',
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            unit=unit,
            sector=get_current_sector() or DEFAULT_SECTOR
        )
    except Exception as e:
        flash(f'Erro ao deletar usuário: {str(e)}', 'danger')
    
    return redirect(url_for('list_users'))

@app.route('/user/edit-sector', methods=['POST'])
@login_required
def edit_user_sector():
    """Edita o setor de um usuário (apenas admin)"""
    unit = get_current_unit()
    target_username = request.form.get('username', '').strip()
    new_sector = request.form.get('sector', '').strip()
    master_pass = request.form.get('master_password', '').strip()
    
    # Validar senha mestre
    if not is_master(master_pass):
        flash('Senha mestre incorreta!', 'danger')
        return redirect(url_for('list_users'))
    
    # Verificar se usuário existe
    user = find_user(target_username, unit=unit)
    if not user:
        flash(f'Usuário "{target_username}" não encontrado!', 'danger')
        return redirect(url_for('list_users'))
    
    # Atualizar setor
    try:
        db_mdb.update_user(target_username, unit=unit, sector=new_sector)
        flash(f'Setor de "{target_username}" atualizado para "{new_sector or "Geral"}"!', 'success')
        
        # Registrar auditoria
        db_mdb.add_movement(
            username=session.get('user'),
            action='edit_user_sector',
            details=f'Setor do usuário "{target_username}" alterado para "{new_sector or "Geral"}"',
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            unit=unit,
            sector=get_current_sector() or DEFAULT_SECTOR
        )
    except Exception as e:
        flash(f'Erro ao editar setor: {str(e)}', 'danger')
    
    return redirect(url_for('list_users'))

@app.route('/about')
def about():
    """Página de informações"""
    return render_template('about.html')

# ============================================================================
# MANIPULAÇÃO DE ERROS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Página não encontrada"""
    return render_template('error.html', 
                         title='404 - Página não encontrada',
                         message='A página que você procura não existe.'), 404

@app.errorhandler(500)
def internal_error(error):
    """Erro interno do servidor"""
    return render_template('error.html',
                         title='500 - Erro interno',
                         message='Ocorreu um erro interno no servidor.'), 500

# ============================================================================
# INICIALIZAÇÃO
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("WMS Web Application (MDB Edition)")
    print("=" * 60)
    try:
        stats = db_mdb.get_database_stats()
        print("[OK] Banco de dados MDB conectado com sucesso!")
        print(f"   - Usuarios: {stats['users']}")
        print(f"   - Prateleiras: {stats['shelves']}")
        print(f"   - Pedidos ativos: {stats['active_orders']}")
        print(f"   - Pedidos removidos: {stats['removed_orders']}")
    except Exception as e:
        print(f"[ERRO] Erro ao conectar ao banco: {e}")
        print("   Verifique se wms_database.mdb existe e está acessível")
    
    print(f"Acesse: http://localhost:5000")
    print("=" * 60)
    
    app.run(debug=False, host='0.0.0.0', port=5000)
