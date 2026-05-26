# 👥 Sistema de Gerenciamento de Usuários - WMS v1.2.2

## 📋 Funcionalidades Implementadas

Sistema completo de gerenciamento de usuários com controle administrativo através de senha mestre.

---

## ✨ Novas Funcionalidades

### 1. **Editar Setor** 🏢
- Alterar o setor de qualquer usuário
- Exemplos: Produção, Expedição, Administrativo, etc.
- Valor padrão: "Geral"

### 2. **Resetar Senha** 🔑
- Redefinir senha de qualquer usuário
- Validação de força da senha (mínimo 4 caracteres)
- Auditoria automática registrada

### 3. **Ativar/Desativar Usuário** 🔄
- Alternar status de ativo/inativo
- Usuários inativos não podem fazer login
- Proteção: não pode desativar sua própria conta

### 4. **Deletar Usuário** 🗑️
- Remover permanentemente um usuário do sistema
- Confirmação obrigatória
- Proteção: não pode deletar sua própria conta
- Ação irreversível com alerta visual

---

## 🔐 Segurança

### Senha Mestre
Todas as operações administrativas exigem a **senha mestre**:
```
Senha Mestre: masterkey
```

### Proteções Implementadas
- ✅ Validação de senha mestre em todas as operações
- ✅ Impossível alterar/deletar sua própria conta
- ✅ Auditoria completa de todas as ações
- ✅ Registro automático em `movements` (banco de dados)

---

## 🎯 Como Usar

### Acessar Gerenciamento de Usuários
1. Fazer login no sistema
2. No menu superior, clicar em **"Usuários"**
3. Visualizar lista de todos os usuários cadastrados

### Realizar Ações Administrativas

#### Editar Setor
1. Clicar no botão azul **[✏️]** na linha do usuário
2. Digitar o novo setor (ou deixar em branco para "Geral")
3. Inserir a senha mestre
4. Confirmar

#### Resetar Senha
1. Clicar no botão amarelo **[🔑]** na linha do usuário
2. Digitar a nova senha (mínimo 4 caracteres)
3. Inserir a senha mestre
4. Confirmar

#### Ativar/Desativar
1. Clicar no botão cinza/verde **[❌/✅]** na linha do usuário
2. Confirmar a ação
3. Inserir a senha mestre
4. Confirmar

#### Deletar Usuário
1. Clicar no botão vermelho **[🗑️]** na linha do usuário
2. Ler o alerta de ação irreversível
3. Inserir a senha mestre
4. Confirmar permanentemente

---

## 📊 Interface

### Tabela de Usuários

| Coluna | Descrição |
|--------|-----------|
| **Usuário** | Nome de login + badge "Você" se for o usuário atual |
| **Setor** | Departamento/área do usuário |
| **Data de Criação** | Timestamp de registro |
| **Status** | Ativo (verde) ou Inativo (cinza) |
| **Ações** | Botões de gerenciamento (4 operações) |

### Botões de Ação

| Cor | Ícone | Função |
|-----|-------|--------|
| 🔵 Azul | ✏️ | Editar Setor |
| 🟡 Amarelo | 🔑 | Resetar Senha |
| ⚪ Cinza/Verde | ❌/✅ | Ativar/Desativar |
| 🔴 Vermelho | 🗑️ | Deletar |

---

## 🛠️ Arquivos Modificados

### Backend
- **db_mdb.py** (+6 linhas)
  - `delete_user(username)` - Nova função para remover usuário

- **web_app.py** (+160 linhas)
  - `reset_user_password()` - Rota POST para alterar senha
  - `toggle_user_status()` - Rota POST para ativar/desativar
  - `delete_user()` - Rota POST para deletar
  - `edit_user_sector()` - Rota POST para editar setor

### Frontend
- **templates/users.html** (Reescrito completamente)
  - Interface de gerenciamento com 4 modais Bootstrap 5
  - Scripts JavaScript para preencher modais dinamicamente
  - Validações client-side
  - Design responsivo

---

## 📝 Auditoria

Todas as operações são registradas na tabela `movements`:

```sql
username     | action              | details
-------------|---------------------|-------------------------------------
admin        | reset_password      | Senha do usuário "joao" foi resetada
admin        | toggle_user_status  | Usuário "maria" desativado
admin        | delete_user         | Usuário "pedro" foi deletado do sistema
admin        | edit_user_sector    | Setor do usuário "ana" alterado para "Produção"
```

---

## ✅ Checklist de Testes

- [x] Editar setor de um usuário
- [x] Resetar senha com validação
- [x] Ativar usuário inativo
- [x] Desativar usuário ativo
- [x] Deletar usuário
- [x] Proteção: tentar alterar própria conta (bloqueado)
- [x] Senha mestre incorreta (erro exibido)
- [x] Auditoria registrada no banco
- [x] Interface responsiva em mobile/desktop
- [x] Mensagens de sucesso/erro com flash

---

## 🚀 Próximos Passos

### Melhorias Futuras (Opcional)
1. Alterar senha mestre via interface
2. Permissões granulares (roles: admin/user/viewer)
3. Exportar lista de usuários para Excel
4. Histórico de alterações por usuário
5. Recuperação de senha via email
6. Two-Factor Authentication (2FA)

---

## 🎓 Notas Técnicas

### Banco de Dados (MDB)
- Tabela: `users`
- Campos utilizados: `username`, `password`, `sector`, `active`, `created_at`
- Operações: SELECT, UPDATE, DELETE

### Framework
- Flask (Python)
- Bootstrap 5 (CSS/JS)
- Bootstrap Icons
- Modais dinâmicos com JavaScript vanilla

---

**Data de Implementação:** 09/03/2026  
**Versão:** 1.2.2  
**Desenvolvido por:** GitHub Copilot  
**Status:** ✅ Pronto para Produção
