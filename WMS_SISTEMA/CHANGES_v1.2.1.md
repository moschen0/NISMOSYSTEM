# Mudanças da Versão 1.2.1
**Data:** 09/03/2026 08:59

## Resumo
Versão de manutenção focada em melhorias de usabilidade e informações institucionais.

## Alterações Principais

### 1. Remoção de Senha Obrigatória para TAGs
- **Removida** validação de `master_key` das rotas de gerenciamento de TAGs:
  - `/tag/attach-zone` - Anexar TAG existente a zona
  - `/tag/remove-zone` - Remover TAG de zona
  - `/tag/create-attach-zone` - Criar e anexar TAG a zona
- **Removidos** campos de senha dos formulários inline de TAG nos cartões de zona
- **Motivação**: Liberar funcionalidade para operadores, mantendo apenas `@login_required`

### 2. Direitos Autorais
- **Adicionada** seção "Direitos Autorais" na página About
- **Desenvolvedores**: Gustavo Detoni e Vitor Moschen
- **Copyright**: WMS Master © 2026

### 3. Informações de Suporte
- **Adicionado** email de contato: suporte@masterlabotico.com.br
- Email clicável com ícone de envelope na página About

### 4. Navegação Aprimorada
- **Adicionado** link "Sobre" no menu dropdown do usuário
- Ícone: bi-info-circle
- Localização: Entre "Histórico" e "Sair"

## Arquivos Modificados

### Backend
- `web_app.py`:
  - Simplificação das rotas de TAG (remoção de validação master_key)

### Frontend
- `templates/dashboard.html`:
  - Remoção de campos `master_key` dos formulários de TAG
  - Ajuste de layout (formulário criar+anexar TAG)
  
- `templates/about.html`:
  - Adição de seção de direitos autorais
  - Adição de email de suporte
  
- `templates/base.html`:
  - Adição do link "Sobre" no dropdown do usuário

### Sincronização
- Todos os templates foram sincronizados para `dist/WMS_Server/templates/`

## Compatibilidade
- ✅ Compatível com versão 1.2.0
- ✅ Não requer migração de dados
- ✅ Banco de dados Access (.mdb) mantido inalterado
- ✅ Estrutura JSON de TAGs mantida

## Notas
- Sistema de TAGs agora acessível para todos os operadores autenticados
- Informações institucionais profissionalizadas
- Facilita contato com suporte técnico
