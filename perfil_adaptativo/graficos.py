"""
graficos.py — desenha os gráficos do perfil em SVG, sem biblioteca e sem internet.

O problema que este arquivo resolve: um README de perfil só com tabelas fica
cinza. Mas gráfico que depende de imagem hospedada em serviço alheio quebra
quando o serviço cai, e gráfico que depende de JavaScript não abre no GitHub.

A solução é desenhar SVG aqui mesmo, com a biblioteca padrão do Python. SVG é
texto: o arquivo é pequeno, escala sem perder nitidez e o GitHub exibe como
imagem. Como o desenho é gerado a partir dos mesmos dados da tabela, gráfico e
texto nunca discordam — diferente de colar um print, que envelhece sozinho.

Detalhe de tema: o SVG carrega um bloco de estilo com `prefers-color-scheme`.
Assim o gráfico troca de cor sozinho no GitHub claro ou escuro, do mesmo jeito
que os gráficos nativos da página.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import analise

# Medidas do desenho, em pixels. Ficam em constantes para o gráfico crescer em
# altura conforme o número de itens, sem nunca cortar rótulo.
LARGURA_PADRAO = 560
ALTURA_DA_LINHA = 26
TOPO = 34
RODAPE = 24
COLUNA_DO_ROTULO = 168
ESPACO_DO_VALOR = 58
CINZA_NAO_DECLARADO = "não declarado"


def _escapar_xml(texto: str) -> str:
    """
    Troca os três caracteres que quebram um XML: &, < e >.

    Entra: texto qualquer (nome de tecnologia, rótulo).
    Sai: texto seguro para ir dentro de <text>.

    Sem isso, uma tecnologia chamada "C#" até passa, mas "Gerência & Dados"
    derrubaria a imagem inteira: o XML fica inválido e o navegador mostra um
    quadro quebrado em vez do gráfico.
    """
    return (
        str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def grafico_de_barras(titulo: str, itens: list[tuple[str, int]], largura: int = LARGURA_PADRAO) -> str:
    """
    Desenha um gráfico de barras horizontais em SVG.

    Entra: título, lista de (rótulo, valor) já ordenada e a largura em pixels.
    Sai: texto do SVG; "" quando não há item para desenhar.

    Barras horizontais (e não verticais) porque os rótulos são palavras —
    "PostgreSQL", "GitHub Actions". Nome longo cabe na horizontal; na vertical
    ele teria de ser girado, e texto girado ninguém lê.
    """
    itens = [(rotulo, int(valor)) for rotulo, valor in itens if valor]
    if not itens:
        return ""

    altura = TOPO + ALTURA_DA_LINHA * len(itens) + RODAPE
    base_da_barra = COLUNA_DO_ROTULO
    largura_maxima = max(20, largura - base_da_barra - ESPACO_DO_VALOR)
    maior = max(valor for _, valor in itens) or 1

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" '
        f'viewBox="0 0 {largura} {altura}" role="img" aria-label="{_escapar_xml(titulo)}">',
        f"<title>{_escapar_xml(titulo)}</title>",
        "<style>",
        'text{font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif}',
        "text.titulo{fill:#1f2328;font-size:14px;font-weight:600}",
        "text.rotulo{fill:#59636e;font-size:12px}",
        "text.valor{fill:#59636e;font-size:12px}",
        "rect.barra{fill:#0969da}",
        "@media (prefers-color-scheme: dark){",
        "text.titulo{fill:#e6edf3}text.rotulo{fill:#9198a1}text.valor{fill:#9198a1}rect.barra{fill:#4493f8}",
        "}",
        "</style>",
        f'<text class="titulo" x="6" y="20">{_escapar_xml(titulo)}</text>',
    ]

    for indice, (rotulo, valor) in enumerate(itens):
        topo = TOPO + indice * ALTURA_DA_LINHA
        comprimento = max(3, round(largura_maxima * valor / maior))
        rotulo_curto = rotulo if len(rotulo) <= 22 else rotulo[:21] + "..."
        partes.extend(
            [
                f'<text class="rotulo" x="6" y="{topo + 13}">{_escapar_xml(rotulo_curto)}</text>',
                f'<rect class="barra" x="{base_da_barra}" y="{topo + 4}" width="{comprimento}" '
                f'height="12" rx="3" />',
                f'<text class="valor" x="{base_da_barra + comprimento + 8}" y="{topo + 14}">{valor}</text>',
            ]
        )

    partes.append("</svg>")
    return "\n".join(partes) + "\n"


def contagem_por_tecnologia(preparacao: analise.Preparacao) -> list[tuple[str, int]]:
    """
    Conta em quantos projetos cada tecnologia aparece.

    Entra: preparação com as linhas já montadas.
    Sai: lista (tecnologia, quantidade) da mais usada para a menos usada.

    A ordem de desempate é alfabética: sem isso, dois gráficos gerados do mesmo
    dado poderiam sair com barras trocadas e parecer que algo mudou.
    """
    contagem: dict[str, int] = {}
    for linha in preparacao.destacados + preparacao.outros:
        for tecnologia in linha["stack"]:
            contagem[tecnologia] = contagem.get(tecnologia, 0) + 1

    return sorted(contagem.items(), key=lambda par: (-par[1], par[0].casefold()))


def contagem_por_ano(preparacao: analise.Preparacao) -> list[tuple[str, int]]:
    """
    Conta quantos projetos foram atualizados em cada ano (dado confirmado).

    Entra: preparação com as linhas já montadas.
    Sai: lista (ano, quantidade) em ordem crescente; vazia quando nenhuma linha
         tem data confirmada.

    Só entra data que veio da API: "não declarado" não é ano, e transformar
    ausência em 2026 seria inventar informação.
    """
    contagem: dict[str, int] = {}
    for linha in preparacao.destacados + preparacao.outros:
        data = str(linha.get("atualizado_em") or "")
        achado = re.match(r"^\d{2}/\d{2}/(\d{4})$", data)
        if achado:
            ano = achado.group(1)
            contagem[ano] = contagem.get(ano, 0) + 1

    return sorted(contagem.items())


def gerar(preparacao: analise.Preparacao, pasta: Path) -> list[dict[str, Any]]:
    """
    Gera os arquivos de gráfico e devolve o que o README deve referenciar.

    Entra: preparação validada e a pasta de saída (o README fica nela).
    Sai: lista de dicionários {"arquivo", "titulo", "legenda"} dos gráficos
         criados; lista vazia quando ainda não há dado para desenhar.

    Os arquivos vão para `<pasta>/graficos/` porque o README os referencia por
    caminho relativo. É o mesmo contrato do GitHub: imagem com caminho relativo
    aparece se o arquivo estiver no repositório.
    """
    pasta_dos_graficos = pasta / "graficos"
    criados: list[dict[str, Any]] = []

    tecnologias = contagem_por_tecnologia(preparacao)
    if tecnologias:
        desenho = grafico_de_barras("Tecnologias por número de projetos", tecnologias)
        destino = pasta_dos_graficos / "tecnologias.svg"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(desenho, encoding="utf-8")
        criados.append(
            {
                "arquivo": "graficos/tecnologias.svg",
                "titulo": "Tecnologias por número de projetos",
                "legenda": "Cada barra conta em quantos projetos declarados a tecnologia aparece.",
            }
        )

    anos = contagem_por_ano(preparacao)
    if anos:
        desenho = grafico_de_barras("Projetos por ano da última atualização", anos)
        destino = pasta_dos_graficos / "atualizacoes.svg"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(desenho, encoding="utf-8")
        criados.append(
            {
                "arquivo": "graficos/atualizacoes.svg",
                "titulo": "Projetos por ano da última atualização",
                "legenda": "Conta só data confirmada na API do GitHub; projeto sem confirmação fica fora.",
            }
        )

    return criados


def arquivos(pasta: Path) -> list[Path]:
    """
    Lista os SVGs de gráfico já gravados na pasta de saída.

    Entra: pasta de saída.
    Sai: lista ordenada de caminhos (vazia quando não há gráfico).

    Ordem alfabética fixa para que a assinatura de aprovação seja sempre a mesma
    para o mesmo conjunto de arquivos — ordem variável faria o "lacre" mudar
    sozinho.
    """
    pasta_dos_graficos = pasta / "graficos"
    if not pasta_dos_graficos.is_dir():
        return []
    return sorted(caminho for caminho in pasta_dos_graficos.glob("*.svg") if caminho.is_file())


def gerar_banner(
    nome: str,
    github: str,
    pasta: Path,
    animado: bool = False,
    arquivo: str = "banner.svg",
) -> str:
    """
    Desenha a faixa de apresentação usada pelos templates escuro e animado.

    Entra: nome, usuário do GitHub, pasta de saída e se o banner deve animar.
    Sai: caminho relativo para o README ("graficos/banner.svg"), ou "" quando não
         há nome para desenhar.

    O banner é SVG próprio: fundo escuro, janela de terminal e o nome. A versão
    animada acrescenta dois detalhes discretos (cursor piscando e barra que
    percorre a base) — o suficiente para dar vida sem virar carnaval, e o desenho
    continua legível quando o navegador não anima.
    """
    if not str(nome).strip():
        return ""

    largura, altura = 720, 140
    cursor = (
        '<rect x="24" y="18" width="8" height="14" fill="#3fb950">'
        '<animate attributeName="opacity" values="1;1;0;0;1" dur="1.2s" repeatCount="indefinite"/>'
        "</rect>"
        if animado
        else '<rect x="24" y="18" width="8" height="14" fill="#3fb950"/>'
    )
    barra = (
        '<rect x="0" y="136" width="120" height="4" fill="#3fb950">'
        '<animate attributeName="x" values="-120;720;720" dur="6s" repeatCount="indefinite"/>'
        "</rect>"
        if animado
        else '<rect x="0" y="137" width="720" height="3" fill="#30363d"/>'
    )

    desenho = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}" role="img" aria-label="Banner de {_escapar_xml(nome)}">
<title>Banner de {_escapar_xml(nome)}</title>
<style>
text{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}}
</style>
<rect x="0" y="0" width="{largura}" height="{altura}" rx="10" fill="#0d1117" stroke="#30363d"/>
<circle cx="24" cy="16" r="4" fill="#ff5f56"/><circle cx="40" cy="16" r="4" fill="#ffbd2e"/><circle cx="56" cy="16" r="4" fill="#27c93f"/>
<text x="40" y="30" fill="#3fb950" font-size="13">$ whoami</text>
{cursor}
<text x="24" y="76" fill="#e6edf3" font-size="28" font-weight="700">{_escapar_xml(nome)}</text>
<text x="24" y="104" fill="#8b949e" font-size="14">github.com/{_escapar_xml(github)}</text>
{barra}
</svg>
"""

    destino = pasta / "graficos" / arquivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(desenho, encoding="utf-8")
    return f"graficos/{arquivo}"
