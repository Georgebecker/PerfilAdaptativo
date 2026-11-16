"""
analise.py — o programa que trata os dados novos: valida, mede e prepara a saída.

O problema que este arquivo resolve: entre "o usuário digitou os dados" e "o
README foi escrito" existe trabalho de verdade — conferir, classificar em destaque
e outros, confirmar links na API do GitHub, contar o que ficou de fora e registrar
números. Sem esse meio de campo, o template viraria terra de ninguém.

Analogia: é a cozinha entre a feira e o prato. A feira entrega o ingrediente cru
(o YAML), a cozinha lava, corta e mede (validação e normalização), e o prato
(README) só é montado com o que passou no controle.

Modo offline x online: sem rede, a coluna de link e a data de atualização dizem
"não verificado"/"não declarado". Inventar endereço ou data seria mentir no
documento que representa a pessoa.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import generate

from . import importacao, modelo


def _avisar(mensagem: str) -> None:
    """Aviso vai para stderr: o README é o produto, o aviso é conversa de bastidor."""
    print(f"aviso: {mensagem}", file=sys.stderr)

# Rótulos usados no relatório e nas mensagens de console.
MODO_OFFLINE = "offline"
MODO_ONLINE = "online"


@dataclass
class Preparacao:
    """
    O que a cozinha entrega ao prato: linhas prontas, laudo e números medidos.

    `destacados` e `outros` já vêm no formato que o template consome. `laudo`
    guarda erros/avisos/completude, e `relatorio` é o mesmo conteúdo em
    dicionário, pronto para virar `relatorio.json`.
    """

    destacados: list[dict[str, Any]] = field(default_factory=list)
    outros: list[dict[str, Any]] = field(default_factory=list)
    laudo: modelo.ResultadoValidacao = field(default_factory=modelo.ResultadoValidacao)
    relatorio: dict[str, Any] = field(default_factory=dict)


def _sem_marcador(valor: Any) -> str:
    """
    Troca o marcador de ausência por texto vazio.

    Entra: valor vindo de `generate.montar_projeto` (pode ser "não declarado" ou
    "não verificado").
    Sai: o mesmo valor, ou "" quando ele só dizia "não sei".

    Por que esconder em vez de escrever: `não declarado` é uma informação sobre a
    EXTRAÇÃO (o dado não veio), não sobre o projeto. Numa tabela de portfólio ela
    ocupa espaço e passa impressão de descuido; quem lê prefere a célula vazia.
    O diagnóstico continua onde é útil — no laudo de `validar` e no relatório.
    """
    texto = str(valor or "").strip()
    if texto in (generate.STATUS_SEM_EVIDENCIA_README, generate.TEXTO_LINK_NAO_VERIFICADO):
        return ""
    return texto


def _montar_linha(
    projeto: modelo.Projeto,
    dono: str,
    metadados: dict[str, Any] | None,
    offline: bool,
) -> dict[str, Any]:
    """
    Converte um projeto do perfil na linha que o template exibe.

    Entra: projeto normalizado, usuário do GitHub, metadados da API (ou None) e
           se estamos em modo offline.
    Sai: dicionário com os campos da tabela. Campo sem dado vem como texto vazio,
    para o template simplesmente não imprimir nada.

    Reaproveita as regras de formatação do gerador antigo (`generate.py`): data
    em DD/MM/AAAA e texto de link. Duplicar essa lógica criaria duas verdades
    sobre o mesmo dado.
    """
    # `generate.montar_projeto` fala a língua da curadoria antiga (repo, proof,
    # featured). A tradução é feita aqui, num lugar só.
    item = {
        "repo": projeto.repo,
        "featured": projeto.destaque,
        "proof": projeto.prova,
        "stack": projeto.stack,
        "status": projeto.status,
    }
    linha = generate.montar_projeto(item, dono, metadados, incluir_links_nao_verificados=False)
    if linha is None:  # projeto sem repositório não chega aqui, mas o gerador é defensivo
        raise modelo.ErroPerfil(f"projeto sem repositório no perfil: {projeto!r}")

    # Endereço declarado pelo dono do perfil tem precedência sobre a API: ele é a
    # evidência de intenção, e pode apontar para fora do GitHub (site, demo).
    if projeto.url:
        linha["link"] = projeto.url
        linha["link_texto"] = f"[abrir]({projeto.url})"
        linha["link_confirmado"] = True
    else:
        linha["link_confirmado"] = bool(metadados and metadados.get("html_url"))

    # Data que veio da importação da API é evidência guardada: usá-la é melhor que
    # deixar a célula vazia para um fato que já foi lido uma vez. Quando há
    # metadados vivos, eles mandam (a data pode ter mudado desde a importação).
    if metadados is None and projeto.atualizado_em:
        linha["atualizado_em"] = generate.formatar_data(projeto.atualizado_em)

    # Zera os marcadores de ausência: o README mostra o dado ou não mostra nada.
    for campo in ("prova", "stack_texto", "status", "atualizado_em", "link_texto"):
        linha[campo] = _sem_marcador(linha.get(campo))

    # "Detalhes" junta só o que existe, na ordem em que se lê: tecnologia,
    # estágio, data. Uma coluna com valores presentes é melhor que quatro
    # colunas com buracos — e o leitor não vê "não declarado" em lugar nenhum.
    partes = [linha["stack_texto"]] if linha["stack_texto"] else []
    if linha["status"]:
        partes.append(f"**{linha['status']}**")
    if linha["atualizado_em"]:
        partes.append(f"atualizado em {linha['atualizado_em']}")
    linha["meta"] = " · ".join(partes)

    return linha


def _repo_do_perfil(projeto: modelo.Projeto, dono: str) -> bool:
    """
    Diz se o projeto é um repositório da própria conta do dono do perfil.

    Entra: projeto e o usuário do GitHub do perfil.
    Sai: True quando a URL aponta para github.com/<dono>/<algo>.

    Serve para decidir quando vale gastar consulta: repositório da própria conta
    pode ser atualizado pela API a cada geração; projeto hospedado fora (site,
    demo) não deve gerar requisição inútil.
    """
    texto = (projeto.url or "").strip().lower()
    if not texto.startswith(("https://github.com/", "http://github.com/")):
        return False
    partes = [parte for parte in texto.split("github.com/", 1)[-1].split("/") if parte]
    return bool(partes) and partes[0].casefold() == (dono or "").strip().casefold()


def preparar(perfil: modelo.Perfil, offline: bool = False) -> Preparacao:
    """
    Roda o pipeline inteiro sobre o perfil e devolve tudo que a saída precisa.

    Entra: perfil normalizado e a opção offline.
    Sai: Preparacao com linhas, laudo e relatório.
    Levanta modelo.ErroPerfil quando há erro de validação (o README não sai com
    dado quebrado) ou quando a gravação do relatório falha mais adiante.

    O laudo é devolvido mesmo com avisos: aviso não impede o README, e quem lê
    precisa saber o que ficou de fora.
    """
    laudo = modelo.validar(perfil)
    if not laudo.valido:
        raise modelo.ErroPerfil("dados incompletos: " + "; ".join(laudo.erros))

    destacados: list[dict[str, Any]] = []
    outros: list[dict[str, Any]] = []

    token = None if offline else generate.obter_token()
    # Disjuntor: quando a API recusa duas consultas seguidas (limite por hora,
    # rede fora), parar de perguntar evita doze avisos iguais e deixa a geração
    # seguir com as datas que o perfil já guardou.
    falhas_seguidas = 0
    parar_consultas = False

    for projeto in perfil.projetos:
        # Consulta quando há rede e o repositório é da conta do perfil: a data de
        # atualização envelhece sozinha, e é justamente ela que o README não pode
        # errar. Projeto hospedado fora do GitHub não gera consulta.
        metadados = None
        if not offline and not parar_consultas and (not projeto.url or _repo_do_perfil(projeto, perfil.github)):
            metadados = generate.buscar_metadados_github(perfil.github, projeto.repo, token)
            if metadados and (metadados.get("fork") or metadados.get("archived")):
                motivo = "fork" if metadados.get("fork") else "arquivado"
                _avisar(f"{projeto.repo}: repositório {motivo}; fora das tabelas")
                continue

            if metadados is None:
                falhas_seguidas += 1
                if falhas_seguidas >= 2:
                    parar_consultas = True
                    _avisar(
                        "a API do GitHub não confirmou os repositórios; tentando a rota "
                        "alternativa (feed de commits) para as datas que faltam"
                    )
            else:
                falhas_seguidas = 0

        # Segunda rota, independente do disjuntor da API: o feed Atom não consome
        # a cota de 60 consultas por hora. Só vale para repositório da própria
        # conta — é onde o endereço do projeto é confiável.
        if (
            not offline
            and metadados is None
            and not projeto.atualizado_em
            and _repo_do_perfil(projeto, perfil.github)
        ):
            data = importacao.data_da_ultima_atualizacao(perfil.github, projeto.repo)
            if data:
                projeto.atualizado_em = data

        linha = _montar_linha(projeto, perfil.github, metadados, offline)
        (destacados if projeto.destaque else outros).append(linha)

    relatorio = _montar_relatorio(perfil, destacados, outros, laudo, offline)
    return Preparacao(destacados=destacados, outros=outros, laudo=laudo, relatorio=relatorio)


def _montar_relatorio(
    perfil: modelo.Perfil,
    destacados: list[dict[str, Any]],
    outros: list[dict[str, Any]],
    laudo: modelo.ResultadoValidacao,
    offline: bool,
) -> dict[str, Any]:
    """
    Mede o que chegou e devolve os números do processamento.

    Entra: perfil, linhas separadas, laudo e o modo.
    Sai: dicionário com números reais e a lista de avisos.

    Números, não adjetivos: é o que permite dizer "9 projetos, 12 stacks, 3 links
    confirmados" em vez de "o perfil está bom". Métrica medida é a regra R26.
    """
    todas = destacados + outros
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "modo": MODO_OFFLINE if offline else MODO_ONLINE,
        "perfil": {
            "nome": perfil.nome,
            "github": perfil.github,
            "completude_percentual": laudo.completude,
        },
        "numeros": {
            "projetos": len(todas),
            "destaques": len(destacados),
            "outros": len(outros),
            "stacks_distintas": len({tecnologia for linha in todas for tecnologia in linha["stack"]}),
            "links_confirmados": sum(1 for linha in todas if linha.get("link_confirmado")),
            "links_nao_verificados": sum(1 for linha in todas if not linha.get("link_confirmado")),
            "projetos_sem_prova": sum(1 for projeto in perfil.projetos if not projeto.prova),
            "projetos_sem_status": sum(1 for projeto in perfil.projetos if not projeto.status),
        },
        "avisos": list(laudo.avisos),
        "erros": list(laudo.erros),
    }


def formatar_relatorio(relatorio: dict[str, Any]) -> str:
    """
    Transforma o relatório em texto legível para o terminal.

    Entra: dicionário produzido por `_montar_relatorio`.
    Sai: bloco de texto com números, modo e avisos.

    A saída evita acento decorativo e símbolos que o console do Windows em cp850
    não desenha; a informação é a mesma, sem risco de aparecer "?" no lugar.
    """
    numeros = relatorio.get("numeros", {})
    perfil = relatorio.get("perfil", {})
    linhas = [
        f"modo: {relatorio.get('modo')}",
        f"projetos: {numeros.get('projetos', 0)} "
        f"({numeros.get('destaques', 0)} destaque, {numeros.get('outros', 0)} outros)",
        f"stacks distintas: {numeros.get('stacks_distintas', 0)}",
        f"links: {numeros.get('links_confirmados', 0)} confirmado(s), "
        f"{numeros.get('links_nao_verificados', 0)} nao verificado(s)",
        f"completude do perfil: {perfil.get('completude_percentual', 0)}%",
    ]
    avisos = relatorio.get("avisos") or []
    if avisos:
        linhas.append(f"avisos ({len(avisos)}):")
        linhas.extend(f"  - {aviso}" for aviso in avisos)
    return "\n".join(linhas)


def salvar_relatorio(relatorio: dict[str, Any], caminho: Path) -> Path:
    """
    Grava o relatório em JSON (UTF-8) ao lado do README gerado.

    Entra: relatório e caminho de destino.
    Sai: caminho gravado.
    Levanta OSError quando o disco não aceita a gravação (quem chama decide).
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return caminho
