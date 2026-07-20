import os
import datetime
import threading
from EventKit import EKEventStore, EKEntityType
from Foundation import NSDate, NSDateFormatter, NSTimeZone

# Bibliotecas do Google API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Escopo necessário para ler, escrever e gerenciar calendários no Google Agenda
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Configurações de sincronização
# Parâmetros de produção: 7 dias passados e 3 meses (90 dias) futuros
DIAS_PASSADO = 7
DIAS_FUTURO = 90

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')

# Nome do calendário que será criado/utilizado no seu Google Agenda para evitar misturar com os pessoais
GOOGLE_CALENDAR_NAME = "IBM"

def obter_servico_google():
    """Autentica o usuário na API do Google Calendar e retorna o serviço ativo."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
    # Se não houver credenciais válidas, solicita login ao usuário
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token do Google expirado. Atualizando token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Falha ao atualizar token: {e}. Iniciando novo login...")
                creds = None
                
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Arquivo {CREDENTIALS_FILE} não encontrado. Por favor, coloque-o nesta pasta."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Salva o token para a próxima execução
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    return build('calendar', 'v3', credentials=creds)

def obter_ou_criar_calendario_google(service, nome_agenda):
    """Busca o ID de um calendário no Google pelo nome. Se não existir, cria um novo."""
    print(f"Verificando se o calendário '{nome_agenda}' existe no seu Google Agenda...")
    calendar_list = service.calendarList().list().execute()
    items = calendar_list.get('items', [])
    
    for item in items:
        if item.get('summary') == nome_agenda:
            print(f"Calendário '{nome_agenda}' encontrado!")
            return item.get('id')
            
    # Se não encontrar, cria um novo
    print(f"Calendário '{nome_agenda}' não encontrado. Criando um novo...")
    calendar_body = {
        'summary': nome_agenda,
        'timeZone': 'America/Sao_Paulo'
    }
    created_calendar = service.calendars().insert(body=calendar_body).execute()
    return created_calendar.get('id')

def formatar_data(ns_date, is_all_day=False):
    """Converte uma NSDate do macOS para formato aceito pelo Google API."""
    formatter = NSDateFormatter.alloc().init()
    # Usamos o fuso horário padrão do sistema
    formatter.setTimeZone_(NSTimeZone.defaultTimeZone())
    
    if is_all_day:
        formatter.setDateFormat_("yyyy-MM-dd")
        return {'date': formatter.stringFromDate_(ns_date)}
    else:
        formatter.setDateFormat_("yyyy-MM-dd'T'HH:mm:ssZZZZZ")
        return {'dateTime': formatter.stringFromDate_(ns_date)}

# Configurações de filtragem de calendário
# Defina aqui qual é o nome da conta/serviço da IBM no seu Mac (ex: "Exchange", "cassio@ibm.com", "IBM")
# Se deixar em branco, o script listará os calendários no terminal para você identificar a palavra correta.
CONTA_CALENDARIO_FILTRO = "IBM" 

# Títulos específicos dos calendários locais que você quer sincronizar (ex: ["Calendário", "Cassio Lima"])
# Se deixar vazio [], ele tentará sincronizar todos os calendários da conta definida acima.
TITULOS_CALENDARIOS_FILTRADOS = ["Calendário"]

def ler_eventos_macos(store, dias_passado, dias_futuro):
    """Busca eventos nos calendários locais do Mac no intervalo especificado, filtrando por conta."""
    start_date = datetime.datetime.now() - datetime.timedelta(days=dias_passado)
    end_date = datetime.datetime.now() + datetime.timedelta(days=dias_futuro)
    
    ns_start = NSDate.dateWithTimeIntervalSince1970_(start_date.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(end_date.timestamp())
    
    # 1. Obter e listar todos os calendários do sistema para ajudar na identificação da conta
    # 0 representa EKEntityTypeEvent
    todos_calendarios = store.calendarsForEntityType_(0)
    
    print("\n=== Calendários Disponíveis no seu Mac ===")
    contas_detectadas = set()
    for cal in todos_calendarios:
        cal_title = cal.title()
        source_title = cal.source().title()
        contas_detectadas.add(source_title)
        print(f"- Nome: '{cal_title}' | Conta (Source): '{source_title}'")
    print("==========================================\n")

    if not CONTA_CALENDARIO_FILTRO:
        print("[AVISO] A variável CONTA_CALENDARIO_FILTRO está vazia.")
        print(f"Por favor, edite o script e escolha uma das contas listadas acima (provavelmente contendo 'ibm' ou 'Exchange').")
        print("Sincronização interrompida para configuração.")
        return []

    # 2. Filtrar os calendários que correspondem à conta corporativa desejada
    calendarios_alvo = []
    for cal in todos_calendarios:
        source_title = cal.source().title().lower()
        cal_title = cal.title().lower()
        
        # Verifica se o calendário pertence à conta IBM/Exchange configurada
        if CONTA_CALENDARIO_FILTRO.lower() in source_title:
            # Se houver filtro de título de calendário (ex: apenas "Calendário")
            if TITULOS_CALENDARIOS_FILTRADOS:
                if any(t.lower() == cal_title for t in TITULOS_CALENDARIOS_FILTRADOS):
                    calendarios_alvo.append(cal)
            else:
                # Caso contrário, adiciona todos os calendários dessa conta
                calendarios_alvo.append(cal)

    if not calendarios_alvo:
        print(f"[ALERTA] Nenhum calendário encontrado para a conta '{CONTA_CALENDARIO_FILTRO}'")
        return []

    print(f"Sincronizando apenas os seguintes calendários locais:")
    for c in calendarios_alvo:
        print(f"  - '{c.title()}' (Conta: '{c.source().title()}')")

    # 3. Buscar os eventos apenas nos calendários filtrados
    # Passamos a lista de calendários em vez de None
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        ns_start, ns_end, calendarios_alvo
    )
    
    eventos_mac = store.eventsMatchingPredicate_(predicate)
    return eventos_mac or []


def obter_eventos_google(service, google_calendar_id, dias_passado, dias_futuro):
    """Lista eventos do Google Calendar no intervalo especificado."""
    now = datetime.datetime.now(datetime.timezone.utc)
    time_min = (now - datetime.timedelta(days=dias_passado)).isoformat()
    time_max = (now + datetime.timedelta(days=dias_futuro)).isoformat()
    
    print("Buscando eventos existentes no Google Agenda...")
    events_result = service.events().list(
        calendarId=google_calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        maxResults=2500
    ).execute()
    
    return events_result.get('items', [])

def sincronizar_agendas():
    store = EKEventStore.alloc().init()
    done_event = threading.Event()
    
    def completion(granted, error):
        if granted:
            print("Acesso ao Calendário do macOS confirmado.")
            try:
                realizar_sincronizacao(store)
            except Exception as e:
                print(f"Erro durante a sincronização: {e}")
        else:
            print("Erro: Permissão de acesso ao calendário local negada.")
        done_event.set()

    # Solicita acesso às APIs do macOS de acordo com a versão do sistema
    try:
        if hasattr(store, 'requestFullAccessToEventsWithCompletion_'):
            store.requestFullAccessToEventsWithCompletion_(completion)
        else:
            # 0 representa EKEntityTypeEvent no EventKit do macOS
            store.requestAccessToEntityType_completion_(0, completion)
    except Exception as e:
        print(f"Erro ao obter permissão via API: {e}")
        # Tenta rodar direto caso já tenha a permissão no terminal
        try:
            realizar_sincronizacao(store)
        except Exception as ex:
            print(f"Falha de execução direta: {ex}")
        done_event.set()
        
    done_event.wait()

def realizar_sincronizacao(store):
    # 1. Conectar à API do Google e obter/criar o calendário específico "IBM"
    google_service = obter_servico_google()
    google_calendar_id = obter_ou_criar_calendario_google(google_service, GOOGLE_CALENDAR_NAME)
    
    # 2. Ler eventos locais do Mac e eventos do calendário específico do Google
    eventos_mac = ler_eventos_macos(store, DIAS_PASSADO, DIAS_FUTURO)
    eventos_google = obter_eventos_google(google_service, google_calendar_id, DIAS_PASSADO, DIAS_FUTURO)
    
    print(f"Lidos {len(eventos_mac)} eventos do Mac.")
    print(f"Lidos {len(eventos_google)} eventos do Google Agenda (Calendário: {GOOGLE_CALENDAR_NAME}).")
    
    # Mapeia eventos do Google usando o metadado 'mac_event_id'
    google_events_map = {}
    for g_ev in eventos_google:
        mac_id = g_ev.get('extendedProperties', {}).get('private', {}).get('mac_event_id')
        if mac_id:
            google_events_map[mac_id] = g_ev

    adicionados = 0
    atualizados = 0
    removidos = 0
    mantidos = 0

    mac_event_ids_ativos = set()

    for m_ev in eventos_mac:
        # Combinamos o ID único do evento com o timestamp de início para gerar chaves exclusivas
        # para cada ocorrência individual de eventos recorrentes (como Dailies e reuniões semanais)
        timestamp_start = int(m_ev.startDate().timeIntervalSince1970())
        mac_id = f"{m_ev.uniqueIdentifier()}_{timestamp_start}"
        mac_event_ids_ativos.add(mac_id)
        
        is_all_day = bool(m_ev.isAllDay())
        start_payload = formatar_data(m_ev.startDate(), is_all_day)
        end_payload = formatar_data(m_ev.endDate(), is_all_day)
        
        # 1. Detectar o status de resposta do usuário atual na IBM
        participante_status = None
        if m_ev.attendees():
            for part in m_ev.attendees():
                if part.isCurrentUser():
                    participante_status = part.participantStatus()
                    break
        
        # Mapeia EKParticipantStatus do Mac para responseStatus do Google:
        # 2=Accepted, 3=Declined, 4=Tentative, 1=Pending, 0=Unknown
        google_status = 'accepted'
        if participante_status == 1:
            google_status = 'needsAction'
        elif participante_status == 3:
            google_status = 'declined'
        elif participante_status == 4:
            google_status = 'tentative'
        elif participante_status == 0:
            google_status = 'needsAction'
            
        # Tratamento especial de Eventos Cancelados:
        # Se o evento foi cancelado no Mac ou o título contém "cancelado:"/"canceled:",
        # marcamos o status do Google como 'declined' (Não)
        is_cancelado = False
        try:
            if m_ev.status() == 3: # 3 representa EKEventStatusCanceled
                is_cancelado = True
        except Exception:
            pass
            
        titulo_limpo = (m_ev.title() or "").strip().lower()
        if titulo_limpo.startswith("cancelado:") or titulo_limpo.startswith("canceled:"):
            is_cancelado = True
            
        if is_cancelado:
            google_status = 'declined'
            
        # Extrair organizador original do Mac de forma resiliente
        organizador_linha = ""
        try:
            m_organizer = m_ev.organizer()
            if m_organizer:
                org_name = m_organizer.name()
                org_email = m_organizer.emailAddress()
                if org_name and org_email:
                    organizador_linha = f"Organizador: {org_name} <{org_email}>\n---\n"
                elif org_name:
                    organizador_linha = f"Organizador: {org_name}\n---\n"
                elif org_email:
                    organizador_linha = f"Organizador: {org_email}\n---\n"
        except Exception:
            pass

        # Constrói o corpo do evento para o Google
        event_body = {
            'summary': m_ev.title() or "(Sem título)",
            'location': m_ev.location() or "",
            'description': organizador_linha + (m_ev.notes() or ""),
            'start': start_payload,
            'end': end_payload,
            'extendedProperties': {
                'private': {
                    'mac_event_id': mac_id
                }
            }
        }
        
        # Configuração: Se False, sincroniza o status de todos os eventos. Se True, apenas eventos com "teste status".
        TESTE_CONTROLADO_STATUS = False
        titulo_evento = (m_ev.title() or "").lower()
        
        if not TESTE_CONTROLADO_STATUS or "teste status" in titulo_evento:
            event_body['attendees'] = [
                {
                    'email': google_calendar_id, # ID da própria agenda secundária (IBM)
                    'responseStatus': google_status,
                    'self': True
                }
            ]
        
        # Verifica se o evento já existe no Google
        if mac_id in google_events_map:
            g_ev = google_events_map[mac_id]
            g_id = g_ev['id']
            
            # Compara se houve mudanças relevantes (incluindo o status do participante)
            g_attendees = g_ev.get('attendees', [])
            g_status = g_attendees[0].get('responseStatus') if g_attendees else 'accepted'
            
            mudou = (
                g_ev.get('summary') != event_body['summary'] or
                g_ev.get('location') != event_body['location'] or
                g_ev.get('description', '') != event_body['description'] or
                g_ev.get('start', {}).get('dateTime') != start_payload.get('dateTime') or
                g_ev.get('start', {}).get('date') != start_payload.get('date') or
                g_ev.get('end', {}).get('dateTime') != end_payload.get('dateTime') or
                g_ev.get('end', {}).get('date') != end_payload.get('date') or
                g_status != google_status
            )
            
            if mudou:
                print(f"Atualizando compromisso: {event_body['summary']}")
                google_service.events().patch(
                    calendarId=google_calendar_id,
                    eventId=g_id,
                    body=event_body,
                    sendUpdates='none'  # Evita envio de notificações/e-mails de alteração
                ).execute()
                atualizados += 1
            else:
                mantidos += 1
        else:
            # Evento novo - Insere no Google Calendar
            print(f"Adicionando novo compromisso: {event_body['summary']}")
            google_service.events().insert(
                calendarId=google_calendar_id,
                body=event_body,
                sendUpdates='none'  # Evita envio de convites por e-mail
            ).execute()
            adicionados += 1

    # 3. Processar remoções (eventos deletados no Mac que ainda estão no Google)
    for mac_id, g_ev in google_events_map.items():
        if mac_id not in mac_event_ids_ativos:
            g_id = g_ev['id']
            summary = g_ev.get('summary', '(Sem título)')
            print(f"Removendo compromisso deletado no Mac: {summary}")
            try:
                google_service.events().delete(
                    calendarId=google_calendar_id,
                    eventId=g_id
                ).execute()
                removidos += 1
            except Exception as e:
                print(f"Erro ao remover evento {summary} do Google: {e}")

    print("\n=== Relatório de Sincronização ===")
    print(f"Novos eventos adicionados: {adicionados}")
    print(f"Eventos atualizados: {atualizados}")
    print(f"Eventos removidos do Google: {removidos}")
    print(f"Eventos inalterados: {mantidos}")
    print("Sincronização concluída com sucesso!")

if __name__ == "__main__":
    sincronizar_agendas()




