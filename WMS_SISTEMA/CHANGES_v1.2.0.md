# Alterações v1.2.0 - 05/03/2026

## Correções Implementadas

### 1. Remoção de Zona - Pedidos Órfãos
**Problema:** Ao apagar uma zona e recriá-la, pedidos antigos reapareciam.

**Causa:** Pedidos em posições sem prateleira associada (órfãos) não eram removidos.

**Solução:**
- Modificada rota `/zone/remove` em `web_app.py`
- Após deletar prateleiras, busca TODOS os pedidos ativos com posição iniciando pela zona
- Remove pedidos órfãos também (não apenas os de prateleiras existentes)
- Limpa o campo `position` do pedido ao marcar como `removed`

**Arquivos alterados:**
- `web_app.py`: função `remove_zone()` - linhas ~464-580
- `db_mdb.py`: nova função `clear_order_position(order_id)`

### 2. Pedidos Sumirem de Andar e Posição
**Problema:** Pedidos removidos ainda apareciam nas visualizações de andar/posição.

**Solução:**
- Criada função `clear_order_position()` em `db_mdb.py`
- Ao remover pedido por deleção de zona, limpa o campo `position` no banco
- Isso garante que queries por posição não encontrem pedidos removidos

**Arquivos alterados:**
- `db_mdb.py`: função `clear_order_position()` - linha ~179
- `web_app.py`: chamadas a `db_mdb.clear_order_position()` em `remove_zone()` - linhas ~513, ~549

### 3. Correção de Encoding no Console
**Problema:** Aplicação não iniciava devido a `UnicodeEncodeError` com emojis em `print`.

**Solução:**
- Substituídos emojis (✅ ❌ →) por texto ASCII ([OK] [ERRO] -)
- Garante compatibilidade com console Windows cp1252

**Arquivos alterados:**
- `web_app.py`: seção de inicialização - linhas ~1009-1017

### 4. Remoção de Prateleira Individual
**Problema:** Similar ao de zona, pedidos órfãos não eram removidos.

**Solução:**
- Função `remove_shelf()` também busca e remove pedidos órfãos da prateleira
- Utiliza mesma lógica de limpeza de posição

**Arquivos alterados:**
- `web_app.py`: função `remove_shelf()` - linhas ~349-461

## Melhorias de Desempenho

Mantidas as otimizações anteriores:
- Connection pooling com `threading.local()`
- Queries em batch com `count_all_orders_in_positions()`
- Filtros `status='add'` em todas as queries de listagem

## Testes Realizados

1. Criada zona QA com pedido órfão
2. Removida zona QA
3. Validado: pedido ficou `status='removed'` e `position=''`
4. Confirmado: pedido não reaparece em dashboard, andar ou posição

## Próximos Passos Recomendados

1. Trocar credenciais hardcoded por variáveis de ambiente
2. Implementar backup automático do `.mdb`
3. Considerar migração para SQL Server/PostgreSQL em médio prazo
4. Adicionar logs estruturados (não apenas movimentos)
5. Implementar controle de versão do banco de dados
