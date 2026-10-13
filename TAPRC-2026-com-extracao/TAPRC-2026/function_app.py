import logging
import os

import azure.functions as func
import pymssql

app = func.FunctionApp()

# Todas as tabelas do banco de origem (schema "itsm").
# Lista fixa no código: assim nenhum nome de tabela vem de fora (evita SQL injection).
TABELAS = [
    "analista",
    "categoria",
    "chamado",
    "chamado_sla",
    "chamado_status_historico",
    "cliente_organizacao",
    "csat_avaliacao",
    "fila",
    "sla",
    "solicitante",
]

TAMANHO_LOTE = 5000  # linhas lidas por vez, para não estourar a memória


def _conectar():
    """Abre conexão usando SOMENTE variáveis de ambiente (nada de credencial no código)."""
    return pymssql.connect(
        server=os.environ["DB_SERVER"],
        port=os.environ.get("DB_PORT", "1433"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        login_timeout=30,
    )


def extrair_tabela(conn, tabela: str):
    """Lê uma tabela inteira e devolve (colunas, linhas)."""
    # Nome vem da lista fixa TABELAS, então é seguro montar a query assim.
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {tabela}")
    colunas = [c[0] for c in cursor.description]
    linhas = []
    while True:
        lote = cursor.fetchmany(TAMANHO_LOTE)
        if not lote:
            break
        linhas.extend(lote)
    cursor.close()
    return colunas, linhas


# O horário vem da variável de ambiente TIMER_SCHEDULE (formato NCRONTAB: s m h d M dia-da-semana)
@app.timer_trigger(
    schedule="%TIMER_SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=False,
)
def extrair_todas_tabelas(timer: func.TimerRequest) -> None:
    logging.info("Iniciando extração das tabelas do banco de origem.")

    resultado = {}
    conn = _conectar()
    try:
        for tabela in TABELAS:
            try:
                colunas, linhas = extrair_tabela(conn, tabela)
                resultado[tabela] = (colunas, linhas)
                logging.info("Tabela %-28s -> %d linhas, %d colunas",
                             tabela, len(linhas), len(colunas))
            except Exception:
                # Se uma tabela falhar, registra e continua com as outras.
                logging.exception("Falha ao extrair a tabela %s", tabela)
    finally:
        conn.close()

    logging.info("Extração finalizada: %d/%d tabelas.", len(resultado), len(TABELAS))

    # PRÓXIMO PASSO (outra atividade): gravar `resultado` no SQL Database / Data Lake.


@app.route(route="http_trigger", auth_level=func.AuthLevel.FUNCTION)
def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )