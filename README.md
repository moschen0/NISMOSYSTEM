# WMS — Sistema de Gerenciamento de Armazém

Sistema web para controle de estoque e movimentação de pedidos em armazém, desenvolvido com Flask + Microsoft Access (`.mdb`) e interface Bootstrap 5.

## Funcionalidades

- Cadastro e gerenciamento de prateleiras por zona/módulo
- Entrada e saída de pedidos com rastreamento por posição
- Histórico completo de movimentações
- Suporte a múltiplas unidades (`MASTER / WR / AMX`) e setores (ex.: `AR`, `VTA`)
- Sistema de usuários com controle de acesso por setor
- TAGs e metadados de zonas
- Painel administrativo com auditoria de ações

## Requisitos

- Python 3.10+
- Driver ODBC para Microsoft Access (`Microsoft Access Database Engine`)
- Dependências listadas em `WMS_SITEMA/requirements.txt`:
  - Flask 3.1.3
  - Waitress 3.0.2
  - pyodbc 5.3.0

## Como executar

```bash
cd WMS_SITEMA
pip install -r requirements.txt
python run_production.py
```

Acesse em: http://localhost:5000

## Configuração de segredos

Crie o arquivo `WMS_SITEMA/.env` (não versionado):

```
WMS_SECRET_KEY=sua-chave-secreta-aqui
WMS_MASTER_PASSWORD=sua-senha-mestre-aqui
```

Se o arquivo não existir, o sistema usa valores padrão de desenvolvimento (**não adequados para produção**).

## Estrutura do projeto

```
WMS/
├── WMS_BD/              # Banco de dados Microsoft Access (.mdb)
├── WMS_SITEMA/
│   ├── web_app.py       # Aplicação Flask (rotas e lógica)
│   ├── db_mdb.py        # Camada de acesso ao banco (pyodbc)
│   ├── run_production.py# Servidor Waitress (produção)
│   ├── templates/       # Templates Jinja2 (Bootstrap 5)
│   ├── static/          # Arquivos estáticos (CSS, imagens)
│   └── .env             # Segredos locais (não versionado)
└── README.md
```

## Modelo de dados

Cada registro está associado a uma **unidade** (`[unit]`) e um **setor** (`[sector]`), permitindo isolamento total entre filiais e departamentos. A migração de schema é automática na primeira execução.

## Credenciais padrão

| Usuário | Senha | Nível |
|---------|-------|-------|
| admin   | admin | Admin |

> Altere a senha após o primeiro acesso.

## Changelog

Consulte [WMS_SITEMA/CHANGELOG.md](WMS_SITEMA/CHANGELOG.md) para o histórico de versões.