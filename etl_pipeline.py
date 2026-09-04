"""
Lógica central do ETL: lê a planilha de entrada, valida os valores,
consulta o Protheus (mock ou real), decide se autoriza a baixa e grava
o relatório final com o status de cada título processado.
Fases:
    E (Extract)  -> ler_planilha()
    T (Transform)-> validar_soma_planilha() + comparar_com_protheus()
    L (Load)     -> processar_planilha() grava o resultado em Excel
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

import config
from protheus_connector import ProtheusService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)



# Resultado estruturado de cada linha processada (facilita testes e leitura)

@dataclass
class ResultadoLinha:
    id_titulo: str
    status: str
    total_calculado: Optional[float] = None
    valor_protheus: Optional[float] = None
    codigo_baixa: Optional[str] = None
    detalhes: str = field(default="")


STATUS_OK = "ok"
STATUS_CONSULTAR = "consultar manualmente"


def ler_planilha(caminho_arquivo: str) -> pd.DataFrame:
    """
    Fase Extract: lê a planilha Excel de entrada e valida se as colunas
    obrigatórias estão presentes.
    """
    logger.info("Lendo planilha de entrada: %s", caminho_arquivo)
    df = pd.read_excel(caminho_arquivo, dtype={config.COL_ID_TITULO: str})

    colunas_faltantes = [
        col for col in config.COLUNAS_OBRIGATORIAS if col not in df.columns
    ]
    if colunas_faltantes:
        raise ValueError(
            f"Planilha inválida. Colunas obrigatórias ausentes: {colunas_faltantes}"
        )

    if config.COL_STATUS not in df.columns:
        df[config.COL_STATUS] = ""

    return df


def _linha_tem_dados_validos(row: pd.Series) -> bool:
    """Confere se os campos numéricos da linha são valores válidos (não nulos/texto)."""
    campos_numericos = [config.COL_VALOR_OPERACAO, config.COL_ENCARGOS, config.COL_TOTAL_PLANILHA]
    for campo in campos_numericos:
        valor = row.get(campo)
        if pd.isna(valor):
            return False
        try:
            float(valor)
        except (TypeError, ValueError):
            return False
    return True


def validar_soma_planilha(valor_operacao: float, encargos: float, total_planilha: float) -> tuple[bool, float]:
    """
    Fase Transform (validação interna): confere se
    VALOR_OPERACAO + ENCARGOS bate com TOTAL_PLANILHA, dentro da tolerância.
    Retorna (bate_ou_nao, total_calculado).
    """
    total_calculado = round(valor_operacao + encargos, 2)
    bate = abs(total_calculado - total_planilha) < config.TOLERANCIA_CENTAVOS
    return bate, total_calculado


def comparar_com_protheus(total_calculado: float, valor_protheus: float) -> bool:
    """
    Fase Transform (validação externa): confere se o total calculado bate
    com o valor retornado pelo Protheus, dentro da tolerância.
    """
    return abs(total_calculado - valor_protheus) < config.TOLERANCIA_CENTAVOS


def processar_linha(row: pd.Series, protheus: ProtheusService) -> ResultadoLinha:
    """
    Processa uma única linha da planilha, aplicando toda a regra de
    negócio (fases T e L para aquele título específico).
    """
    id_titulo = str(row[config.COL_ID_TITULO]).strip()

    # 1) Validação de formato: campos numéricos ausentes/inválidos
    if not id_titulo or id_titulo.lower() == "nan" or not _linha_tem_dados_validos(row):
        logger.warning("Linha com formato inválido: %s", id_titulo)
        return ResultadoLinha(
            id_titulo=id_titulo or "(vazio)",
            status=STATUS_CONSULTAR,
            detalhes="Formato inválido: campos numéricos ausentes ou não numéricos",
        )

    valor_operacao = float(row[config.COL_VALOR_OPERACAO])
    encargos = float(row[config.COL_ENCARGOS])
    total_planilha = float(row[config.COL_TOTAL_PLANILHA])

    # 2) Validação interna da planilha
    bate_planilha, total_calculado = validar_soma_planilha(valor_operacao, encargos, total_planilha)
    if not bate_planilha:
        logger.warning("Título %s: erro de soma na planilha", id_titulo)
        return ResultadoLinha(
            id_titulo=id_titulo,
            status=STATUS_CONSULTAR,
            total_calculado=total_calculado,
            detalhes=(
                f"Erro de soma na planilha: calculado R$ {total_calculado:.2f} "
                f"vs planilha R$ {total_planilha:.2f}"
            ),
        )

    # 3) Consulta ao Protheus
    resposta = protheus.consultar_titulo(id_titulo)
    if not resposta.get("sucesso"):
        logger.warning("Título %s não localizado no Protheus", id_titulo)
        return ResultadoLinha(
            id_titulo=id_titulo,
            status=STATUS_CONSULTAR,
            total_calculado=total_calculado,
            detalhes="Título não localizado no Protheus",
        )

    dados_protheus = resposta["dados"]
    valor_protheus = float(dados_protheus.get("valorTotal", 0.0))

    # 4) Comparação planilha calculada x Protheus
    if not comparar_com_protheus(total_calculado, valor_protheus):
        logger.warning("Título %s com divergência de valores", id_titulo)
        return ResultadoLinha(
            id_titulo=id_titulo,
            status=STATUS_CONSULTAR,
            total_calculado=total_calculado,
            valor_protheus=valor_protheus,
            detalhes=(
                f"Divergência de valores: planilha R$ {total_calculado:.2f} "
                f"vs Protheus R$ {valor_protheus:.2f}"
            ),
        )

    # 5) Valores batem: autoriza a baixa
    resultado_baixa = protheus.realizar_baixa(id_titulo, total_calculado)
    if not resultado_baixa.get("sucesso"):
        logger.error("Falha ao dar baixa no título %s", id_titulo)
        return ResultadoLinha(
            id_titulo=id_titulo,
            status=STATUS_CONSULTAR,
            total_calculado=total_calculado,
            valor_protheus=valor_protheus,
            detalhes=f"Falha ao efetuar baixa no Protheus: {resultado_baixa.get('mensagem', '')}",
        )

    logger.info("Título %s baixado com sucesso", id_titulo)
    return ResultadoLinha(
        id_titulo=id_titulo,
        status=STATUS_OK,
        total_calculado=total_calculado,
        valor_protheus=valor_protheus,
        codigo_baixa=resultado_baixa.get("codigo_baixa"),
        detalhes=f"Valores conferem, baixa efetuada (código {resultado_baixa.get('codigo_baixa')})",
    )


def processar_dataframe(df: pd.DataFrame, protheus: ProtheusService) -> pd.DataFrame:
    """
    Aplica a regra de negócio (fases T e L) em um DataFrame já achatado
    (uma linha por título), independentemente de como ele foi lido
    (planilha simples ou Tabela Dinâmica).

    Grava duas colunas no resultado:
    - STATUS   ("ok" se os valores baterem e a baixa foi efetuada;
                "consultar manualmente" caso contrário)
    - DETALHES (motivo específico, útil para investigar cada caso)
    """
    status_lista = []
    detalhes_lista = []
    for _, row in df.iterrows():
        resultado = processar_linha(row, protheus)
        status_lista.append(resultado.status)
        detalhes_lista.append(resultado.detalhes)

    df = df.copy()
    df[config.COL_STATUS] = status_lista
    df[config.COL_DETALHES] = detalhes_lista
    return df


def processar_planilha_pivot(
    caminho_entrada: str,
    caminho_saida: str,
    protheus: ProtheusService,
    nome_aba: str = None,
) -> pd.DataFrame:
    """
    Executa o pipeline completo (E-T-L) para a planilha real da Fer:
    Tabela Dinâmica agrupada por Data > Operadora > Título (aba "Planilha1").
    """
    from leitor_planilha_pivot import ler_planilha_pivot

    df = ler_planilha_pivot(caminho_entrada, nome_aba=nome_aba)
    df = processar_dataframe(df, protheus)
    df.to_excel(caminho_saida, index=False)
    logger.info("Relatório final gravado em: %s", caminho_saida)
    return df


def processar_planilha(
    caminho_entrada: str,
    caminho_saida: str,
    protheus: ProtheusService,
) -> pd.DataFrame:
    """
    Executa o pipeline completo (E-T-L) para planilhas "achatadas"
    (uma linha por título, sem agrupamento/tabela dinâmica) — mantido
    para compatibilidade com o formato de teste original.
    """
    df = ler_planilha(caminho_entrada)
    df = processar_dataframe(df, protheus)
    df.to_excel(caminho_saida, index=False)
    logger.info("Relatório final gravado em: %s", caminho_saida)
    return df