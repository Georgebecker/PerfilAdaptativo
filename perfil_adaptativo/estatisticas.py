"""
estatisticas.py — os números e as conquistas que o README pode provar.

O problema que este arquivo resolve: "estatísticas" e "conquistas" são as seções
onde quase todo portfólio mente. Vira "5+ anos de experiência", "centenas de
projetos", "reconhecido no mercado" — nada disso é verificável, e quem lê aprende
a desconfiar do resto do documento.

Aqui a regra é diferente: **cada número sai do próprio perfil** e cada conquista
automática só aparece quando o dado que a comprova existe. Nada é estimado.

- Estatística: conta os projetos, as tecnologias, os links confirmados, as
  estrelas que a API informou, a completude do cadastro.
- Conquista automática: um marco que já foi atingido, sempre com o número ao lado
  ("10 projetos no portfólio — 12"). Marco não atingido simplesmente não aparece,
  como troféu de vitrine que ainda não foi ganho.
- Conquista declarada: o que a pessoa escreveu no perfil (certificação, prêmio,
  formação). O programa nunca cria uma.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import analise, modelo

# Quantos dias para considerar um projeto "recente". É o mesmo prazo que muita
# gente usa para dizer que um repositório está ativo; fica em constante para o
# texto e o cálculo nunca divergirem.
DIAS_RECENTE = 90

# Marcos automáticos: (quantidade mínima, título, o que ele comemora).
# A ordem é do mais fácil para o mais difícil, para a lista crescer com o tempo.
MARCOS = (
    (1, "Primeiro projeto no portfólio", "o começo de tudo"),
    (3, "Três projetos cadastrados", "portfólio deixou de ser vitrine vazia"),
    (5, "Cinco projetos no portfólio", "variedade para mostrar"),
    (10, "Dez projetos no portfólio", "coleção consistente"),
    (20, "Vinte projetos no portfólio", "trabalho de longa data"),
)


def _data_iso(valor: str) -> datetime | None:
    """
    Converte a data guardada no perfil em datetime com fuso.

    Entra: texto ISO ("2026-10-26T12:06:19Z").
    Sai: datetime em UTC, ou None quando o texto não serve.

    O "Z" do GitHub precisa virar "+00:00" porque é assim que o Python entende
    fuso — mesmo conceito, duas grafias.
    """
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def _projetos_recentes(perfil: modelo.Perfil) -> int:
    """
    Conta quantos projetos foram atualizados nos últimos DIAS_RECENTE dias.

    Entra: perfil normalizado.
    Sai: quantidade (0 quando nenhuma data serve).

    Só conta o que tem data conhecida: projeto sem data não é "antigo", é
    "desconhecido", e somar desconhecido como ativo seria inventar movimento.
    """
    agora = datetime.now(timezone.utc)
    total = 0
    for projeto in perfil.projetos:
        momento = _data_iso(projeto.atualizado_em)
        if momento and (agora - momento).days <= DIAS_RECENTE:
            total += 1
    return total


def numeros(perfil: modelo.Perfil, preparacao: analise.Preparacao) -> list[dict[str, str]]:
    """
    Monta a lista de estatísticas (rótulo + valor já formatado).

    Entra: perfil normalizado e a preparação com as linhas do README.
    Sai: lista de {"rotulo", "valor"}; vazia quando não há nada a contar.

    Cada item só entra se tiver base: estatística de zero projeto não informa
    nada e ocupa espaço — é melhor a seção não aparecer.
    """
    linhas = preparacao.destacados + preparacao.outros
    tecnologias = {tecnologia.casefold() for linha in linhas for tecnologia in linha["stack"]}
    links_confirmados = sum(1 for linha in linhas if linha.get("link_confirmado"))
    estrelas = sum(projeto.estrelas for projeto in perfil.projetos)
    recentes = _projetos_recentes(perfil)
    com_prova = sum(1 for projeto in perfil.projetos if projeto.prova)

    itens: list[dict[str, str]] = []
    if linhas:
        itens.append({"rotulo": "Projetos no portfólio", "valor": str(len(linhas))})
        itens.append(
            {"rotulo": "Em destaque", "valor": f"{len(preparacao.destacados)} de {len(linhas)}"}
        )
    if tecnologias:
        itens.append({"rotulo": "Tecnologias distintas", "valor": str(len(tecnologias))})
    if com_prova:
        itens.append({"rotulo": "Projetos com descrição", "valor": f"{com_prova} de {len(linhas)}"})
    if links_confirmados:
        itens.append({"rotulo": "Links verificados", "valor": f"{links_confirmados} de {len(linhas)}"})
    if estrelas:
        itens.append({"rotulo": "Estrelas recebidas", "valor": str(estrelas)})
    if recentes:
        itens.append({"rotulo": f"Atualizados nos últimos {DIAS_RECENTE} dias", "valor": str(recentes)})
    if perfil.projetos:
        itens.append(
            {"rotulo": "Completude do cadastro", "valor": f"{preparacao.laudo.completude}%"}
        )
    return itens


def conquistas(perfil: modelo.Perfil, preparacao: analise.Preparacao) -> list[dict[str, str]]:
    """
    Junta as conquistas declaradas e as automáticas, sem repetir.

    Entra: perfil normalizado e a preparação.
    Sai: lista de {"titulo", "detalhe"}.

    Ordem: primeiro o que a pessoa declarou (é dela, tem prioridade), depois os
    marcos medidos. Cada marco leva o número que o justifica; marco sem número
    é promessa, e promessa não é dado.
    """
    declaradas = [
        {"titulo": texto, "detalhe": "declarada no perfil"}
        for texto in perfil.conquistas
        if texto.strip()
    ]

    total = len(preparacao.destacados + preparacao.outros)
    automaticas: list[dict[str, str]] = []

    # Só o marco mais alto alcançado: mostrar "1 projeto", "3 projetos", "5" e
    # "10" ao mesmo tempo repete o mesmo número quatro vezes e parece enchimento.
    alcancados = [marco for marco in MARCOS if total >= marco[0]]
    if alcancados:
        _, titulo, detalhe = alcancados[-1]
        automaticas.append({"titulo": titulo, "detalhe": f"{total} no total — {detalhe}"})

    estrelas = sum(projeto.estrelas for projeto in perfil.projetos)
    if estrelas:
        automaticas.append(
            {"titulo": "Projetos com estrelas", "detalhe": f"{estrelas} estrela(s) informada(s) pelo GitHub"}
        )

    if preparacao.laudo.completude >= 100:
        automaticas.append({"titulo": "Cadastro completo", "detalhe": "todos os campos do README preenchidos"})

    return declaradas + automaticas


def calcular(perfil: modelo.Perfil, preparacao: analise.Preparacao) -> dict[str, Any]:
    """
    Reúne os dois blocos num dicionário pronto para o template.

    Entra: perfil e preparação.
    Sai: {"numeros": [...], "conquistas": [...]}.

    Separar em dois dicionários (e não numa lista só) permite o template decidir
    o formato — tabela para números, lista para conquistas — sem reprocessar nada.
    """
    return {
        "numeros": numeros(perfil, preparacao),
        "conquistas": conquistas(perfil, preparacao),
    }
