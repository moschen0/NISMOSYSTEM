Importar clientes do Excel para a tabela `etiq_clients`

Passos rápidos:

1. Instale dependências no ambiente Python usado pelo projeto:

```bash
pip install -r WMS_SISTEMA/tools/requirements_import_clients.txt
```

2. Execute o script passando o arquivo Excel (pode usar caminhos absolutos):

```bash
python WMS_SISTEMA/tools/import_clients_from_excel.py --excel Clientes.xlsx
```

3. Para especificar bancos manualmente:

```bash
python WMS_SISTEMA/tools/import_clients_from_excel.py --excel Clientes.xlsx --db WMS_BD/wms_database_test.mdb --db WMS_BD/wms_database.mdb
```

Notas:
- O script tenta detectar automaticamente uma coluna de chave (`numero_cliente`, `cliente_codigo`, `id`, ...).
- Colunas faltantes em `etiq_clients` serão adicionadas como `TEXT(255)`.
- Faça backup dos arquivos `.mdb` antes de executar em produção.
