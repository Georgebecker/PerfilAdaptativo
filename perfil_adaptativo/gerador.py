"""
gerador.py — a linha de montagem única: perfil entra, Markdown sai.

O problema que este arquivo resolve: existem dois comandos de entrada
(`perfil.py`, adaptativo, e `generate.py`, o antigo preso à curadoria) e três
visuais. Se cada comando tivesse a própria sequência de "validar → desenhar →
renderizar", uma correção feita num deles não chegaria ao outro — e os dois
começariam a gerar READMEs diferentes para o mesmo dado.

Aqui a sequência existe uma vez só:

    validar -> medir -> desenhar gráficos -> escolher banner -> renderizar

Todo template recebe exatamente o mesmo contexto. Trocar o visual muda a
arrumação, nunca o conteúdo — é a mesma comida em prato diferente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import analise, graficos, modelo, render, templates_visuais

# Templates que usam a faixa de apresentação em SVG. O minimal não usa: é o
# visual "sóbrio", e banner colorido contradiria a proposta dele.
TEMPLATES_COM_BANNER = ("dark-terminal", "animated")


@dataclass
class Saida:
    """
    O resultado da geração, antes de ir para o disco.

    `texto_completo` é o README da raiz do projeto; `texto_perfil` é a versão
    enxuta, sem a seção de bastidores, usada no repositório de perfil. Os dois
    saem do mesmo dado e do mesmo template — só a seção de método é omitida.
    """

    template_id: str
    template_nome: str
    texto_completo: str
    texto_perfil: str
    preparacao: analise.Preparacao
    desenhos: list[dict[str, Any]] = field(default_factory=list)


def gerar(
    perfil: modelo.Perfil,
    pasta: Path,
    offline: bool = False,
    template_id: str | None = None,
) -> Saida:
    """
    Executa a linha de montagem inteira e devolve os textos (sem gravar o README).

    Entra: perfil normalizado, pasta de saída (onde os gráficos vão), se deve
           evitar a rede e o id do template.
    Sai: Saida com os dois textos, a preparação e a lista de gráficos.
    Levanta modelo.ErroPerfil quando o template não existe, quando o perfil não
    passa na validação ou quando o template está quebrado.

    Os gráficos são gravados aqui porque o README os referencia por caminho
    relativo: desenhar antes do texto evita a primeira versão com imagem
    quebrada.
    """
    # Valida o template ANTES de tudo: descobrir que o visual escolhido não
    # existe só depois de consultar a API do GitHub seria desperdício de tempo
    # e de cota de requisição.
    entrada = templates_visuais.obter(template_id)

    preparacao = analise.preparar(perfil, offline=offline)
    desenhos = graficos.gerar(preparacao, pasta)

    banner = ""
    if entrada["id"] in TEMPLATES_COM_BANNER:
        banner = graficos.gerar_banner(
            perfil.nome,
            perfil.github,
            pasta,
            animado=entrada["id"] == "animated",
        )

    texto_completo = render.renderizar(
        perfil, preparacao, desenhos, entrada["id"], modo_perfil=False, banner=banner
    )
    texto_perfil = render.renderizar(
        perfil, preparacao, desenhos, entrada["id"], modo_perfil=True, banner=banner
    )

    return Saida(
        template_id=entrada["id"],
        template_nome=entrada["name"],
        texto_completo=texto_completo,
        texto_perfil=texto_perfil,
        preparacao=preparacao,
        desenhos=desenhos,
    )
