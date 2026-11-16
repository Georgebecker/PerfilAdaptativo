"""
render.py — monta o Markdown do README a partir do perfil de qualquer pessoa.

O problema que este arquivo resolve: o texto do perfil não pode ser escrito para
uma pessoa específica. Aqui o Python entrega ao template (Jinja2) tudo já
mastigado — nome, bio, linhas da tabela, badges — e o template só decide ONDE
cada coisa aparece. Regra de negócio fica no Python; o texto não pensa.

Analogia: o Python é a cozinha (decide o que vai no prato) e o template é o
prato (arruma o que recebeu). Se a cozinha decidisse no prato, cada mudança de
regra exigiria mexer no texto — e uma delas sempre escaparia.

Nada é inventado: campo vazio vira "não declarado" e seção sem dado simplesmente
não aparece. README de portfólio com link inventado é pior que README curto.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import generate

from . import analise, estatisticas, modelo, templates_visuais

# Estilo das badges: o padrão é discreto (flat-square) e o "forte" usa o formato
# largo com cores saturadas, pensado para os templates escuro e animado.
ESTILO_PADRAO = "padrao"
ESTILO_FORTE = "forte"

PALETA_FORTE = ("7B2FF7", "00A3FF", "E0007A", "0F9D58", "D97706", "C12127")

# Badges conhecidas: rótulo técnico -> (texto do badge, cor hexadecimal, logo).
# Só entram tecnologias cujo badge a pessoa reconhece de imediato; o resto usa a
# paleta abaixo, com cor estável derivada do nome.
BADGES_CONHECIDAS: dict[str, tuple[str, str, str]] = {
    "python": ("Python", "3776AB", "python"),
    "fastapi": ("FastAPI", "009688", "fastapi"),
    "flask": ("Flask", "000000", "flask"),
    "sql": ("SQL", "4479A1", "postgresql"),
    "sqlite": ("SQLite", "003B57", "sqlite"),
    "postgresql": ("PostgreSQL", "4169E1", "postgresql"),
    "mysql": ("MySQL", "4479A1", "mysql"),
    "pandas": ("pandas", "150458", "pandas"),
    "numpy": ("NumPy", "013243", "numpy"),
    "jupyter": ("Jupyter", "F37626", "jupyter"),
    "dados": ("Dados", "2F74C0", ""),
    "etl": ("ETL", "6E4B9E", ""),
    "javascript": ("JavaScript", "F7DF1E", "javascript"),
    "typescript": ("TypeScript", "3178C6", "typescript"),
    "node.js": ("Node.js", "339933", "nodedotjs"),
    "node": ("Node.js", "339933", "nodedotjs"),
    "react": ("React", "61DAFB", "react"),
    "html": ("HTML", "E34F26", "html5"),
    "css": ("CSS", "1572B6", "css3"),
    "front-end": ("Front-end", "B45CD6", ""),
    "php": ("PHP", "777BB4", "php"),
    "wordpress": ("WordPress", "21759B", "wordpress"),
    "git": ("Git", "F05032", "git"),
    "github actions": ("GitHub Actions", "2088FF", "githubactions"),
    "docker": ("Docker", "2496ED", "docker"),
    "playwright": ("Playwright", "2EAD33", "playwright"),
    "telegram": ("Telegram", "26A5E4", "telegram"),
    "api": ("API", "009688", ""),
    "llm": ("LLM", "6E4B9E", ""),
    "agentes": ("Agentes", "7B4BD6", ""),
    "ollama": ("Ollama", "000000", ""),
    "deepseek": ("DeepSeek", "4D6BFE", ""),
    "gemini": ("Gemini", "8E75B2", "googlegemini"),
    "openai": ("OpenAI", "412991", "openai"),
    "chrome extension": ("Chrome Extension", "4285F4", "googlechrome"),
    "rust": ("Rust", "000000", "rust"),
    "go": ("Go", "00ADD8", "go"),
    "java": ("Java", "ED8B00", ""),
    "c#": ("C#", "512BD4", "csharp"),
    ".net": (".NET", "512BD4", "dotnet"),
    "linux": ("Linux", "FCC624", "linux"),
    "bash": ("Bash", "4EAA25", "gnubash"),
    "powershell": ("PowerShell", "5391FE", "powershell"),
}

# Paleta de reserva: cores estáveis para tecnologia sem badge conhecida. A cor é
# escolhida pelo nome, então o mesmo "Excel" aparece sempre com a mesma cor —
# diferente de sortear cor a cada geração, que deixaria o README instável.
PALETA_RESERVA = (
    "3776AB",
    "009688",
    "2F74C0",
    "6E4B9E",
    "C12127",
    "B45CD6",
    "0B7285",
    "8E44AD",
)

LIMITE_BADGES = 6


def _escapar_badge(texto: str) -> str:
    """
    Prepara o texto para o endereço do shields.io.

    Entra: rótulo humano ("Node.js", "C#").
    Sai: texto no formato que o serviço de badges entende.

    O shields.io usa hífen como separador de campos e sublinhado como espaço, por
    isso "C++" e "C#" precisam de tradução — é o mesmo cuidado de escapar "&" numa
    URL de busca.
    """
    return texto.replace("-", "--").replace("_", "__").replace(" ", "_")


def badges_da_stack(stack: list[str], estilo: str = ESTILO_PADRAO) -> list[dict[str, str]]:
    """
    Cria as badges (selos visuais) do topo do README a partir da stack.

    Entra: lista consolidada de tecnologias, na ordem de aparição, e o estilo
           ("padrao" discreto ou "forte" largo e colorido).
    Sai: lista de {"rotulo", "url"} com no máximo LIMITE_BADGES itens.

    O limite existe porque README com vinte selos deixa de informar e vira
    enfeite; seis já contam a história da stack.

    A cor do estilo forte é derivada do nome (e não sorteada), para o perfil
    manter a mesma cara em toda geração — cor que muda a cada rodada parece
    defeito.
    """
    resultado: list[dict[str, str]] = []
    for indice, tecnologia in enumerate(stack[:LIMITE_BADGES]):
        chave = tecnologia.casefold()
        texto = _escapar_badge(tecnologia)
        logo = ""

        if chave in BADGES_CONHECIDAS:
            rotulo, cor, logo = BADGES_CONHECIDAS[chave]
            texto = _escapar_badge(rotulo)

        if estilo == ESTILO_FORTE:
            cor = PALETA_FORTE[indice % len(PALETA_FORTE)]
            url = f"https://img.shields.io/badge/{texto}-{cor}?style=for-the-badge"
        else:
            if chave not in BADGES_CONHECIDAS:
                cor = PALETA_RESERVA[sum(ord(letra) for letra in tecnologia) % len(PALETA_RESERVA)]
            url = f"https://img.shields.io/badge/{texto}-{cor}?style=flat-square"

        if logo:
            url += f"&logo={logo}&logoColor=white"

        resultado.append({"rotulo": tecnologia, "url": url})
    return resultado


def montar_contexto(
    perfil: modelo.Perfil,
    preparacao: analise.Preparacao,
    graficos: list[dict[str, Any]] | None = None,
    template_id: str | None = None,
    modo_perfil: bool = False,
    banner: str = "",
) -> dict[str, Any]:
    """
    Reúne num dicionário tudo que qualquer template pode usar.

    Entra: perfil normalizado, a preparação (linhas + relatório), a lista de
    gráficos já gravados, o id do template, se é a versão enxuta de perfil e o
    caminho do banner (vazio quando o template não usa).
    Sai: contexto do Jinja2.

    O contexto é o MESMO para os três visuais — trocar de template não pode
    mudar o dado, só a arrumação. Por isso tudo que é visual já vem resolvido
    aqui, e o .j2 não calcula nada.
    """
    todas_as_stack = [
        tecnologia
        for linha in preparacao.destacados + preparacao.outros
        for tecnologia in linha["stack"]
    ]
    stack_consolidada = generate.consolidar_stack(preparacao.destacados + preparacao.outros)
    medidos = estatisticas.calcular(perfil, preparacao)

    return {
        "nome": perfil.nome,
        "bio": perfil.bio,
        "local": perfil.local,
        "site": perfil.site,
        "github": perfil.github,
        "links": perfil.links,
        "destaques": preparacao.destacados,
        "outros": preparacao.outros,
        "stack_consolidada": stack_consolidada,
        "badges": badges_da_stack(stack_consolidada, ESTILO_PADRAO),
        "badges_fortes": badges_da_stack(stack_consolidada, ESTILO_FORTE),
        "graficos": graficos or [],
        "banner": banner,
        "estatisticas": medidos["numeros"],
        "conquistas": medidos["conquistas"],
        # Só faz sentido mostrar a coluna de link se algum projeto tem link: em
        # modo offline sem endereço confirmado, a coluna sairia toda vazia.
        "tem_links": any(
            linha.get("link_texto") for linha in preparacao.destacados + preparacao.outros
        ),
        "template_id": template_id or templates_visuais.padrao(),
        "modo_perfil": modo_perfil,
        "tecnologias": len({tecnologia.casefold() for tecnologia in todas_as_stack}),
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "modo": (
            "offline (sem consulta à API do GitHub)"
            if preparacao.relatorio["modo"] == "offline"
            else "com dados públicos do GitHub"
        ),
        "modo_curto": "offline" if preparacao.relatorio["modo"] == "offline" else "online",
        "completude": preparacao.laudo.completude,
    }


def renderizar(
    perfil: modelo.Perfil,
    preparacao: analise.Preparacao,
    graficos: list[dict[str, Any]] | None = None,
    template_id: str | None = None,
    modo_perfil: bool = False,
    banner: str = "",
) -> str:
    """
    Gera o texto Markdown do README com o template escolhido.

    Entra: perfil normalizado, preparação já validada, gráficos, id do template,
           se é a versão de perfil e o caminho do banner.
    Sai: texto completo em Markdown.
    Levanta modelo.ErroPerfil quando o template não existe ou está com problema —
    é erro de projeto, não do usuário, e a mensagem diz o caminho de saída.
    """
    from jinja2 import TemplateError

    nome_do_template = templates_visuais.nome_do_arquivo(template_id)
    ambiente = generate.criar_ambiente()
    try:
        template = ambiente.get_template(nome_do_template)
        return template.render(
            **montar_contexto(perfil, preparacao, graficos, template_id, modo_perfil, banner)
        )
    except TemplateError as erro:
        raise modelo.ErroPerfil(
            f"o template {nome_do_template} está com problema ({erro}). "
            "Restaure o arquivo da pasta templates/ ou escolha outro com --template."
        ) from erro


def gravar(texto: str, caminho: Path) -> Path:
    """
    Grava o README em UTF-8, criando a pasta de destino quando preciso.

    Entra: texto do README e caminho de destino.
    Sai: caminho gravado.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    return caminho
