# Sincronizador de Calendário macOS (Outlook/Exchange) para Google Calendar

Este projeto realiza a sincronização automática de via única de eventos de um calendário corporativo local do macOS (como Microsoft Exchange/Outlook) para uma agenda secundária dedicada no Google Calendar pessoal. 

A solução foi projetada especificamente para contornar restrições severas de TI corporativas (como bloqueios de OAuth externos do Azure Active Directory e desativação de compartilhamento de link ICS), lendo os eventos diretamente do banco de dados local do macOS e enviando-os para a API do Google.

## Como Funciona

1. **Leitura Local (Mac):** O script acessa a API nativa do macOS (`EventKit` via PyObjC) para ler os eventos de um calendário local filtrado por conta (ex: conta corporativa `"IBM"`).
2. **Integração Google Calendar:** O script conecta-se ao Google Calendar usando a API oficial (v3). Ele busca ou cria uma agenda secundária chamada `"IBM"` para manter seus compromissos pessoais e profissionais totalmente separados.
3. **Mapeamento Unívoco:** Cada evento do Mac é mapeado de forma exclusiva no Google usando metadados privados (`mac_event_id` nas propriedades estendidas). Reuniões recorrentes (como *Dailies*) são tratadas de forma individual combinando o ID único da reunião com o timestamp de início (`ID_timestamp`).
4. **Sincronização de Status de Resposta:** O script lê o seu status de participação no Mac (Aceito, Recusado, Talvez, Pendente) e o replica visualmente na agenda do Google.
5. **Automação de Cancelados:** Se uma reunião for cancelada na origem (Outlook), o script marcará a resposta como `Não` ("Você vai? Não") automaticamente no Google.
6. **Dados Adicionais:** O nome do organizador original da reunião corporativa é injetado no topo das notas do evento no Google.
7. **Logs Otimizados:** O log de execuções (`sync.log`) é formatado em árvore indentada para fácil agrupamento (folding) em editores. A lista completa de calendários disponíveis no Mac é exportada para um arquivo separado `calendars.txt` apenas quando há alterações na configuração de calendários locais.

---

## Estrutura do Projeto

* `app.py`: Script Python principal contendo a lógica de sincronização.
* `requirements.txt`: Dependências Python necessárias.
* `.gitignore`: Configuração para impedir o versionamento de chaves e dados pessoais.
* `credentials.json`: Arquivo de credenciais de aplicativo desktop do Google Cloud (gerado por você - **não versionar**).
* `token.json`: Token de acesso OAuth gerado após o primeiro login (gerado automaticamente - **não versionar**).
* `sync.log`: Log de execuções automatizadas em segundo plano, estruturado em árvore recuada para agrupamento automático em editores.
* `calendars.txt`: Lista de contas e calendários locais mapeados no macOS (atualizado inteligentemente apenas se houver alterações de calendário - **não versionar**).

---

## Requisitos de Instalação

1. **Python 3.10+** instalado no macOS.
2. Crie o ambiente virtual e instale as dependências:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

---

## Configuração das Credenciais do Google

Para conectar o script ao seu Google Agenda, você precisará gerar um arquivo `credentials.json` no Google Cloud:

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um novo projeto (ex: `Sincronizador Calendario`).
3. Vá em **APIs e Serviços** > **Biblioteca** e ative a **Google Calendar API**.
4. Vá em **Tela de consentimento OAuth** (*OAuth Consent Screen*):
   * Escolha o tipo de usuário **Externo** (*External*).
   * Preencha as informações básicas do aplicativo.
   * Em **Escopos** (*Scopes*), adicione o escopo `.../auth/calendar` (permissão de leitura/escrita completa de calendários).
   * Em **Usuários de teste** (*Test users*), adicione o seu e-mail do Gmail pessoal.
5. Vá em **Credenciais** > **Criar credenciais** > **ID do cliente OAuth** (*OAuth Client ID*):
   * Escolha o tipo de aplicativo **App de desktop** (*Desktop app*).
   * Baixe o arquivo JSON gerado, renomeie para `credentials.json` e coloque-o na pasta raiz deste repositório.

---

## Execução

### Execução Manual (Primeira vez)
Na primeira execução, o script abrirá uma página do navegador pedindo consentimento de login na sua conta do Google.
```bash
.venv/bin/python app.py
```
*Nota: Ao rodar pela primeira vez no terminal do Mac, o sistema operacional exibirá uma janela pop-up solicitando permissão para o Terminal acessar o seu Calendário. Você deve aceitar.*

---

## Automação com Launch Agent (macOS)

Para que a sincronização ocorra automaticamente de hora em hora entre as **8h da manhã e as 18h da tarde** (horário comercial), configuramos um Launch Agent do macOS. Ele é muito mais estável do que o `cron` pois garante a execução do script caso o computador esteja dormindo no horário marcado (rodando assim que você abrir a tampa do Mac).

O arquivo de configuração está localizado em:
`~/Library/LaunchAgents/com.cassio.caldavsync.plist`

### Comandos úteis do Launch Agent:

* **Carregar/Ativar o agendamento no macOS:**
  ```bash
  launchctl load ~/Library/LaunchAgents/com.cassio.caldavsync.plist
  ```

* **Descarregar/Parar o agendamento:**
  ```bash
  launchctl unload ~/Library/LaunchAgents/com.cassio.caldavsync.plist
  ```

* **Forçar uma execução de teste agora:**
  ```bash
  launchctl start com.cassio.caldavsync
  ```
  *(Os logs dessa execução serão gravados no arquivo `sync.log` na pasta do projeto).*
