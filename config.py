"""
Configurações globais do pipeline de automação financeira.

"""

import os #comunicação com Sistema Operacional
from pathlib import Path #pathlib lida com caminhos de arquivos e pastas

#"MOCK" (simulador local) ou "PROD" (API real)
#env define em qual modo está: mock ou prod
ENV = os.getenv("AUTOMACAO_ENV", "MOCK") #evitar senhas expostas no código

PROTHEUS_API_BASE_URL = os.getenv(
    "PROTHEUS_API_BASE_URL", "https://protheus.empresa.com.br/rest/api/fin/v1"
)
PROTHEUS_TOKEN = os.getenv("PROTHEUS_TOKEN", "seu_token_aqui")

# Timeout (segundos) para as chamadas HTTP 
PROTHEUS_TIMEOUT = 15


# Regras de negócio
# Tolerância de centavos para considerar dois valores "iguais"
TOLERANCIA_CENTAVOS = 0.01


# Caminhos de arquivo padrão

PASTA_DOWNLOADS = Path(os.getenv("PASTA_DOWNLOADS", str(Path.home() / "Downloads")))
PASTA_DOWNLOADS.mkdir(parents=True, exist_ok=True)

ARQUIVO_ENTRADA_PADRAO = "encargos.xlsx"
ARQUIVO_SAIDA_PADRAO = str(PASTA_DOWNLOADS / "relatorio_final_processado.xlsx")


# Nomes das colunas do modelo interno "achatado" (usado internamente pelo
# etl_pipeline, depois que qualquer formato de planilha de entrada é lido).

COL_ID_TITULO = "ID_TITULO"
COL_OPERADORA = "OPERADORA"
COL_DATA = "DATA_REFERENCIA"
COL_VALOR_OPERACAO = "VALOR_OPERACAO"
COL_ENCARGOS = "ENCARGOS"
COL_TOTAL_PLANILHA = "TOTAL_PLANILHA"
COL_STATUS = "STATUS"
COL_DETALHES = "DETALHES"

COLUNAS_OBRIGATORIAS = [
    COL_ID_TITULO,
    COL_VALOR_OPERACAO,
    COL_ENCARGOS,
    COL_TOTAL_PLANILHA,
]


# Configuração específica da planilha "Planilha1" (Tabela Dinâmica),

PIVOT_NOME_ABA_PADRAO = "Planilha1"
# Primeira linha de dados (a linha 4 tem os cabeçalhos "Rótulos de Linha /
# OPERADORA / ENCARGOS / Total Geral"; os dados começam na linha seguinte)
PIVOT_LINHA_INICIAL_DADOS = 5
# Colunas (índice 0 = A) usadas: A = rótulo (data/operadora/título),
# C = valor operadora, D = encargos, E = total geral. Coluna F é ignorada.
PIVOT_COL_ROTULO = 0
PIVOT_COL_VALOR_OPERACAO = 2
PIVOT_COL_ENCARGOS = 3
PIVOT_COL_TOTAL_GERAL = 4