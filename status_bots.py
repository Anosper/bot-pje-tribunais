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

    "desde" só é atualizado quando o status realmente MUDA em
    relação ao que já estava salvo — assim "rodando desde 08:00"
    não fica se atualizando a cada ciclo, só quando volta a rodar
    depois de um erro/pausa/fora do horário.
    """

    ref = _db_status.collection(COLECAO_STATUS).document(tribunal)

    try:
        doc_atual = ref.get()
        status_anterior = doc_atual.to_dict().get("status") if doc_atual.exists else None
    except Exception as erro:
        print(f"[status] Erro ao ler status atual de {tribunal}: {erro}")
        status_anterior = None

    dados = {
        "tribunal": tribunal,
        "grupo": grupo,
        "status": status,
        "detalheErro": detalhe_erro if status == "erro" else None,
        "atualizadoEm": datetime.now(timezone.utc),
    }

    if status != status_anterior:
        dados["desde"] = datetime.now(timezone.utc)

    try:
        ref.set(dados, merge=True)
    except Exception as erro:
        print(f"[status] Erro ao gravar status de {tribunal}: {erro}")
