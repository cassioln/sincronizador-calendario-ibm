# Developer Agent Guide (AGENTS.md)

Este documento é voltado para Agentes de IA e Engenheiros de Software que darão manutenção, configurarão ou estenderão as funcionalidades deste sincronizador de calendário no futuro. 

---

## ⚠️ Regras Cruciais de Segurança (Segredos)

1. **Nunca versionar segredos:** Os arquivos `credentials.json` (credenciais da API do Google) e `token.json` (token OAuth de acesso temporário/refresh) **NUNCA** devem ser adicionados ao controle de versão Git. Eles estão cadastrados no `.gitignore` e devem permanecer lá.
2. **Prevenir vazamento de convites externos:** Ao chamar métodos da API do Google Calendar (`insert` ou `patch`), o parâmetro **`sendUpdates='none'`** deve ser explicitamente definido. Isso impede que o Google envie notificações de e-mail acidentais para os organizadores corporativos da IBM ou participantes das reuniões originais ao sincronizar o status.

---

## 🛠️ Arquitetura e Detalhes do EventKit (macOS / PyObjC)

O script interage diretamente com o banco de dados do calendário local do Mac usando a biblioteca PyObjC.

### 1. Manipulação do `EKEntityType` e Constantes do EventKit
O PyObjC expõe enums do macOS como tipos C opacos (`NewType`). Propriedades como `EKEntityTypeEvent` não podem ser acessadas diretamente do objeto.
* **Correto:** Use o valor inteiro diretamente: `0` representa `EKEntityTypeEvent` (compromissos) e `1` representa `EKEntityTypeReminder` (lembretes).
* Exemplo: `store.calendarsForEntityType_(0)`

### 2. Status do Evento (Event Status)
O status de um evento no Mac é obtido via `m_ev.status()`. O valor retornado é um inteiro correspondente ao enum `EKEventStatus`:
* `1` = Confirmado (`EKEventStatusConfirmed`)
* `2` = Provisório (`EKEventStatusTentative`)
* `3` = Cancelado (`EKEventStatusCanceled`)
* Para marcar reuniões como recusadas no Google Agenda quando são canceladas no Outlook, o script valida se `m_ev.status() == 3` ou se o título limpo do evento começa com `"cancelado:"` / `"canceled:"`.

### 3. Status de Resposta do Usuário (Participant Status)
O status de resposta do próprio usuário (se ele aceitou ou não a reunião) é encontrado iterando sobre os participantes:
```python
participante_status = None
if m_ev.attendees():
    for part in m_ev.attendees():
        if part.isCurrentUser():
            participante_status = part.participantStatus()
            break
```
Os valores de retorno de `part.participantStatus()` mapeiam para:
* `1` = Pendente (`EKParticipantStatusPending`)
* `2` = Aceito (`EKParticipantStatusAccepted`)
* `3` = Recusado (`EKParticipantStatusDeclined`)
* `4` = Provisório / Talvez (`EKParticipantStatusTentative`)

---

## 📅 Mapeamento no Google Calendar

### 1. Unicidade de Eventos Recorrentes (Evitando Sobrescrita)
O predicado de busca do EventKit expande automaticamente as recorrências de reuniões repetitivas (como *Dailies*), mas todas as instâncias compartilham exatamente o mesmo `uniqueIdentifier()`. 
Para evitar que a sincronização sobrescreva o mesmo evento repetidamente no Google (resultando em apenas um evento no passado), o ID de mapeamento do Google (`mac_event_id` gravado na propriedade estendida privada `extendedProperties.private`) é gerado de forma composta:
```python
timestamp_start = int(m_ev.startDate().timeIntervalSince1970())
mac_id = f"{m_ev.uniqueIdentifier()}_{timestamp_start}"
```

### 2. Status Nativos de Resposta em Agendas Secundárias (Attendees)
Ao atualizar o status do evento ("Você vai? Sim/Não/Talvez") na agenda secundária dedicados ("IBM"):
* **Erro Comum:** Adicionar o e-mail principal do usuário (`cassiolima.n@gmail.com`) na lista de participantes. Isso faz com que o Google crie um convite duplicado na agenda principal do usuário.
* **Correto:** Use o ID/e-mail da **própria agenda secundária** (`google_calendar_id`) no campo `email` do participante com `'self': True`. Isso aplica o status visual (como tracejado de provisório) diretamente no calendário "IBM" e impede qualquer duplicação na agenda principal:
```python
event_body['attendees'] = [
    {
        'email': google_calendar_id, # ID do próprio calendário secundário
        'responseStatus': google_status, # 'accepted', 'declined', 'tentative', 'needsAction'
        'self': True
    }
]
```

---

## 🚀 Ambientes e Execução em Background (Launch Agent)

### 1. Caminhos Absolutos (CWD do Launchd)
O Launch Agent roda a partir da raiz do sistema operacional, o que significa que o diretório de trabalho (`os.getcwd()`) do script em background **não** será a pasta do projeto.
* Todos os acessos a arquivos (como `credentials.json` e `token.json`) devem obrigatoriamente utilizar caminhos absolutos gerados a partir do local físico do script:
```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
```

### 2. Sincronização Incremental (Produção vs Carga)
* **Carga Inicial:** Feita buscando um histórico longo no passado (`DIAS_PASSADO = 1095`) e futuro (`DIAS_FUTURO = 365`).
* **Produção Diária:** Deve operar em janela móvel curta (`DIAS_PASSADO = 7` e `DIAS_FUTURO = 90`) para otimizar velocidade de execução e evitar consumo excessivo de cotas da API.
* Os eventos que já foram sincronizados no passado fora da janela móvel de produção **não são apagados** pelo script, pois a lógica de deleção só atua no intervalo de busca ativo.

### 3. Estruturação de Logs em Árvore (Code Folding)
Para manter o arquivo de log `sync.log` legível e recolhível em editores de texto como o VS Code:
* Cada execução de sincronização deve iniciar com uma linha de cabeçalho sem recuo, contendo a data/hora e o nome do calendário (ex: `[dd/mm/aaaa hh:mm:ss] Sincronização IBM:`).
* Todas as mensagens subsequentes impressas (`print`) ao longo do script devem possuir obrigatoriamente um recuo de 2 espaços no início (`  `). Isso aninha os dados sob a execução e habilita a dobra em árvore do editor.
* Evite rotinas manuais de gravação no final de `sync.log` por dentro do Python; confie no redirecionamento transparente do stdout do Launch Agent (`StandardOutPath`).

### 4. Escrita Inteligente de Calendários Disponíveis (calendars.txt)
* A lista com todos os calendários do sistema e calendários ativos não é impressa no terminal para evitar poluir o log.
* Essa listagem é ordenada e gravada de forma absoluta no arquivo separado `calendars.txt` na raiz do projeto.
* O arquivo `calendars.txt` é atualizado sobrescrevendo o conteúdo (`w`) apenas se for detectada alguma alteração real nas configurações ou nomes de calendários no macOS, minimizando escritas desnecessárias no disco. Esse arquivo deve permanecer no `.gitignore`.

---

## 🛠️ Diretrizes de Fluxo de Trabalho (Git Workflow)

1. **Commit e Push Automático:** Após as alterações propostas serem aprovadas pelo usuário e validadas nos testes, o agente de desenvolvimento deve **obrigatoriamente** realizar o `git commit` com uma mensagem descritiva (preferencialmente seguindo o padrão de Conventional Commits, ex: `feat(...)`, `fix(...)`, `style(...)`) e disparar o `git push` para sincronizar as mudanças com o repositório remoto.


