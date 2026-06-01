# WMS - Instruções para Produção

## **Opção 1: Rodar Manualmente (Modo Simples)**

### Instalar Waitress:
```powershell
pip install waitress
```

### Iniciar o servidor:
```powershell
python run_production.py
```
Ou simplesmente clique duas vezes em: **start_wms.bat**

O servidor ficará rodando e acessível em:
- Local: http://localhost:5000
- Rede: http://192.168.1.210:5000

---

## **Opção 2: Rodar como Serviço do Windows (Recomendado)**

### 1. Instalar NSSM (Non-Sucking Service Manager):
- Baixe de: https://nssm.cc/download
- Extraia o arquivo nssm.exe para uma pasta (ex: C:\nssm)

### 2. Instalar como serviço:
Abra PowerShell como **Administrador** e execute:

```powershell
# Navegue até a pasta do NSSM
cd C:\nssm\win64

# Instale o serviço
.\nssm.exe install WMS-Service "C:\Users\Maste\AppData\Local\Python\pythoncore-3.14-64\python.exe" "C:\Users\Maste\OneDrive\Área de Trabalho\wms ar\run_production.py"

# Configure o diretório de trabalho
.\nssm.exe set WMS-Service AppDirectory "C:\Users\Maste\OneDrive\Área de Trabalho\wms ar"

# Configure para reiniciar automaticamente
.\nssm.exe set WMS-Service AppExit Default Restart
.\nssm.exe set WMS-Service AppRestartDelay 5000

# Inicie o serviço
.\nssm.exe start WMS-Service
```

### 3. Gerenciar o serviço:
```powershell
# Ver status
nssm status WMS-Service

# Parar
nssm stop WMS-Service

# Reiniciar
nssm restart WMS-Service

# Remover serviço
nssm remove WMS-Service confirm
```

---

## **Opção 3: Tarefa Agendada do Windows**

### 1. Abra o **Agendador de Tarefas** (Task Scheduler)

### 2. Crie uma nova tarefa:
- Nome: WMS Service
- Descrição: Warehouse Management System
- **Disparadores**: Na inicialização do sistema
- **Ações**: 
  - Programa: `python.exe`
  - Argumentos: `run_production.py`
  - Iniciar em: `C:\Users\Maste\OneDrive\Área de Trabalho\wms ar`
- **Configurações**:
  - ✅ Permitir que a tarefa seja executada sob demanda
  - ✅ Executar tarefa assim que possível após uma inicialização agendada ter sido perdida
  - ✅ Se a tarefa falhar, reiniciar a cada: 1 minuto

---

## **Opção 4: IIS (Internet Information Services)**

Se você quiser usar o IIS do Windows:

### 1. Instalar wfastcgi:
```powershell
pip install wfastcgi
wfastcgi-enable
```

### 2. Configure o IIS com FastCGI apontando para sua aplicação Flask

---

## **Recomendações de Segurança**

### 1. Altere a SECRET_KEY em produção:
No arquivo `web_app.py`, linha 19:
```python
app.secret_key = "SUBSTITUA-POR-UMA-CHAVE-FORTE-ALEATORIA"
```

Gere uma chave forte:
```python
import secrets
print(secrets.token_hex(32))
```

### 2. Configure senha mestre forte:
No arquivo `web_app.py`, linha 20:
```python
MASTER_PASSWORD = "SUA-SENHA-FORTE-AQUI"
```

### 3. Configure firewall:
```powershell
# Abrir porta 5000 no firewall do Windows
New-NetFirewallRule -DisplayName "WMS Server" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```

### 4. Backup automático:
Configure backups regulares do arquivo `wms_database.mdb`

---

## **Acesso Remoto**

Para acessar de outros computadores na rede:
1. Certifique-se de que o firewall permite conexões na porta 5000
2. Acesse usando o IP do servidor: `http://192.168.2.28:5000`
3. Considere configurar um nome DNS local para facilitar o acesso

---

## **Monitoramento**

Para verificar se o serviço está rodando:
```powershell
# Verificar se a porta está aberta
Test-NetConnection -ComputerName localhost -Port 5000

# Ver processos Python
Get-Process python

# Testar acesso HTTP
Invoke-WebRequest -Uri "http://localhost:5000/" -UseBasicParsing
```
