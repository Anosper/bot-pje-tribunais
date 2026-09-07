import os
from datetime import datetime, timezone, timedelta

import firebase_admin
from firebase_admin import credentials, firestore

# ============================================================
# CONEXÃO COM O PROJETO botorion2 (separado do projeto principal
# que os bots já usam para salvar "processos")
# ============================================================

# Caminho do arquivo de credencial do projeto botorion2. No Render,
# isso deve ser um "Secret File" (veja instruções de deploy) —
# localmente, é o mesmo arquivo .json que os bots eproc já usam.
CAMINHO_CREDENCIAL_BOTORION2 = os.getenv(
    "BOTORION2_CREDENCIAL_PATH", "firebase-service-account-eproc.json"
)

_nome_app = "botorion2_status"

if _nome_app in [a.name for a in firebase_admin._apps.values()]:
    _app_status = firebase_admin.get_app(_nome_app)
else:
    _credencial_status = credentials.Certificate(CAMINHO_CREDENCIAL_BOTORION2)
    _app_status = firebase_admin.initialize_app(
        _credencial_status, name=_nome_app
    )

_db_status = firestore.client(_app_status)

COLECAO_STATUS = "bots_status"

# ============================================================
# HORÁRIO DE FUNCIONAMENTO (dias úteis, 8h às 17h, hora de Brasília)
# ============================================================

FUSO_BRASILIA = timezone(timedelta(hours=-3))

HORA_INICIO = 8
HORA_FIM = 17


def horario_permitido():
    """
    True se agora é dia útil (segunda a sexta) e está entre
    HORA_INICIO e HORA_FIM no horário de Brasília.
    """
    agora = datetime.now(FUSO_BRASILIA)

    if agora.weekday() >= 5:  # 5=sábado, 6=domingo
        return False

    return HORA_INICIO <= agora.hour < HORA_FIM


# ============================================================
# PAUSA MANUAL (controlada pelo site, por tribunal)
# ============================================================

def esta_pausado_manualmente(tribunal):
    try:
        doc = _db_status.collection(COLECAO_STATUS).document(tribunal).get()
        if not doc.exists:
            return False
        return bool(doc.to_dict().get("pausadoManualmente", False))
    except Exception as erro:
        print(f"[status] Erro ao checar pausa de {tribunal}: {erro}")
        return False


# ============================================================
# ATUALIZAR STATUS DE UM TRIBUNAL
# ============================================================

def atualizar_status(tribunal, grupo, status, detalhe_erro=None):
    """
    status: "rodando" | "erro" | "pausado" | "fora_do_horario"

    "desde" é atualizado quando o status MUDA em relação ao que já
    estava salvo, OU quando passou muito tempo desde a última
    atualização daquele tribunal — esse segundo caso cobre o
    cenário em que o processo foi cancelado/reiniciado sem nunca
    escrever outro status no meio (do ponto de vista do Firestore,
    "rodando" nunca deixou de ser "rodando", então só comparar o
    status não seria suficiente para perceber que é um reinício).
    """

    ref = _db_status.collection(COLECAO_STATUS).document(tribunal)

    try:
        doc_atual = ref.get()
        dados_atuais = doc_atual.to_dict() if doc_atual.exists else {}
    except Exception as erro:
        print(f"[status] Erro ao ler status atual de {tribunal}: {erro}")
        dados_atuais = {}

    status_anterior = dados_atuais.get("status")
    atualizado_em_anterior = dados_atuais.get("atualizadoEm")

    agora = datetime.now(timezone.utc)

    LIMITE_REINICIO_MINUTOS = 1
    passou_muito_tempo = False
    if atualizado_em_anterior:
        try:
            minutos_desde_ultima = (agora - atualizado_em_anterior).total_seconds() / 60
            passou_muito_tempo = minutos_desde_ultima > LIMITE_REINICIO_MINUTOS
        except Exception:
            passou_muito_tempo = False

    dados = {
        "tribunal": tribunal,
        "grupo": grupo,
        "status": status,
        "detalheErro": detalhe_erro if status == "erro" else None,
        "atualizadoEm": agora,
    }

    if status != status_anterior or passou_muito_tempo:
        dados["desde"] = agora

    try:
        ref.set(dados, merge=True)
    except Exception as erro:
        print(f"[status] Erro ao gravar status de {tribunal}: {erro}")
