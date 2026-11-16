"""
generate.py — gera o README de portfólio a partir da curadoria em YAML.

O problema que este arquivo resolve: o README do perfil precisa estar sempre
atualizado (link do repositório, data da última atualização), mas também
precisa dizer *o que cada projeto prova* — e isso só o dono sabe.

Solução em duas camadas, como uma lista de convidados: os nomes e o parentesco
são escritos à mão (config/projects.yaml), e a confirmação de presença vem do
sistema (API pública do GitHub). Se o sistema estiver fora do ar, a lista à mão
continua valendo; o README sai incompleto em detalhe, nunca quebrado.

Uso:
    python generate.py --offline                          # sem rede e sem token
    python generate.py --template dark-terminal           # escolhe o visual
    python generate.py                                    # consulta a API do GitHub
    python generate.py --output saidas/README.md --profile-output saidas/README.profile.md

Este é o gerador do formato de curadoria `config/projects.yaml`. A montagem
(validar, medir, desenhar, renderizar) fica em `perfil_adaptativo/gerador.py` e
é a mesma usada por `python perfil.py` — dois comandos, uma só verdade.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml
from jinja2 import Environment, FileSystemLoader

# A raiz é calculada a partir do próprio arquivo, não do diretório atual:
# assim "python generate.py" funciona mesmo se você rodar de outra pasta.
RAIZ = Path(__file__).resolve().parent
CAMINHO_CONFIG_PADRAO = RAIZ / "examples" / "projects.exemplo.yaml"
PASTA_TEMPLATES = RAIZ / "templates"
URL_API_GITHUB = "https://api.github.com/repos/{dono}/{repo}"

# Dois jeitos de dizer a mesma coisa: no YAML fica sem acento (mais fácil de
# digitar e de comparar) e no README sai com acento, porque é texto lido por gente.
STATUS_SEM_EVIDENCIA_YAML = "nao_declarado"
STATUS_SEM_EVIDENCIA_README = "não declarado"
TEXTO_LINK_NAO_VERIFICADO = "não verificado"


# ---------------------------------------------------------------------------
# Mensagens
# ---------------------------------------------------------------------------
# Aviso vai para stderr: o README é o produto (stdout), o aviso é conversa de
# bastidor. Separá-los permite ler a saída do gerador sem ruído.
def _avisar(mensagem: str) -> None:
    """Mostra um aviso sem interromper a geração (rede caiu, repo arquivado...)."""
    print(f"aviso: {mensagem}", file=sys.stderr)


def _erro(mensagem: str) -> None:
    """Mostra um erro fatal de configuração ou template, em português e sem stack trace."""
    print(f"erro: {mensagem}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Leitura da curadoria e do token
# ---------------------------------------------------------------------------
def carregar_config(caminho: Path) -> dict[str, Any]:
    """
    Lê o YAML de curadoria e confirma o mínimo necessário para gerar o README.

    Entra: caminho do arquivo YAML.
    Sai: dicionário já validado.
    Levanta FileNotFoundError, yaml.YAMLError ou ValueError — quem chama decide
    se isso é erro fatal (na CLI, sim).
    """
    with caminho.open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)

    if not isinstance(dados, dict):
        raise ValueError("o conteúdo do arquivo não é um mapa YAML (chave: valor)")

    if not str(dados.get("github_user") or "").strip():
        raise ValueError("falta o campo obrigatório 'github_user'")

    if not isinstance(dados.get("projects"), list):
        raise ValueError("falta a lista obrigatória 'projects'")

    return dados


def obter_token() -> str | None:
    """
    Devolve o token do GitHub, se existir no ambiente, ou None.

    Aceita os dois nomes usuais (GITHUB_TOKEN no Actions, GH_TOKEN na CLI do
    GitHub). O valor nunca é impresso, logado ou incluído em mensagem de erro:
    o token é tratado como senha, não como configuração.
    """
    return os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or None


# ---------------------------------------------------------------------------
# Conversão de dados
# ---------------------------------------------------------------------------
def formatar_data(valor: Any) -> str:
    """
    Converte uma data ISO do GitHub ("2024-05-17T12:06:19Z") em DD/MM/AAAA.

    Entra: texto ISO ou qualquer coisa vazia/inválida.
    Sai: "17/05/2024" ou "não declarado".

    Por que não usar strftime direto no texto cru: o GitHub manda fuso em UTC
    com a letra Z, enquanto o Python espera "+00:00". São o mesmo conceito
    escrito de dois jeitos — como "17/05" e "17 de maio".
    """
    if not valor:
        return STATUS_SEM_EVIDENCIA_README

    texto = str(valor).strip()
    if not texto:
        return STATUS_SEM_EVIDENCIA_README

    try:
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        _avisar(f"data em formato inesperado ({texto}); marcando como não declarado")
        return STATUS_SEM_EVIDENCIA_README

    return momento.strftime("%d/%m/%Y")


def traduzir_status(valor: Any) -> str:
    """
    Traduz o status da curadoria para o texto que aparece no README.

    Entra: o campo `status` do YAML (pode faltar).
    Sai: o texto do README; ausência ou `nao_declarado` vira "não declarado".

    Regra de integridade do projeto: sem evidência, o README diz que não sabe.
    Status inventado é pior que status ausente, porque engana quem lê.
    """
    if valor is None:
        return STATUS_SEM_EVIDENCIA_README

    texto = str(valor).strip()
    if not texto:
        return STATUS_SEM_EVIDENCIA_README

    # Aceita as três grafias que alguém pode digitar para dizer "não sei".
    marcadores = {STATUS_SEM_EVIDENCIA_YAML, "nao declarado", "não declarado"}
    if texto.lower() in marcadores:
        return STATUS_SEM_EVIDENCIA_README

    return texto


# ---------------------------------------------------------------------------
# Consulta à API do GitHub
# ---------------------------------------------------------------------------
def buscar_metadados_github(
    dono: str,
    repo: str,
    token: str | None = None,
    tempo_limite: float = 10.0,
) -> dict[str, Any] | None:
    """
    Pede à API pública do GitHub os fatos sobre um repositório.

    Entra: dono, nome do repositório, token opcional e tempo limite.
    Sai: dicionário com html_url, stargazers_count, language, pushed_at,
         archived e fork; ou None quando não foi possível confirmar (rede
         fora, HTTP diferente de 200, resposta estranha).

    Esta função nunca levanta exceção de rede: quem chama precisa conseguir
    gerar o README mesmo com a internet fora do ar. É o mesmo princípio de uma
    consulta ao banco que devolve "indisponível" em vez de derrubar a tela.
    """
    cabecalhos = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "perfil-adaptativo",
    }
    # Só manda o cabeçalho de autorização quando existe token; sem ele a API
    # continua respondendo, apenas com limite menor de consultas por hora.
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"

    try:
        resposta = requests.get(
            URL_API_GITHUB.format(dono=dono, repo=repo),
            headers=cabecalhos,
            timeout=tempo_limite,
        )
    except requests.RequestException as erro:
        # Só o tipo do erro aparece: a mensagem crua do requests pode conter
        # cabeçalhos, e o cabeçalho pode conter o token.
        _avisar(f"{repo}: falha de rede ({type(erro).__name__}); usando o YAML")
        return None

    if resposta.status_code != 200:
        _avisar(f"{repo}: API respondeu HTTP {resposta.status_code}; usando o YAML")
        return None

    try:
        dados = resposta.json()
    except ValueError:
        _avisar(f"{repo}: resposta da API não é JSON válido; usando o YAML")
        return None

    if not isinstance(dados, dict):
        _avisar(f"{repo}: resposta da API em formato inesperado; usando o YAML")
        return None

    return {
        "html_url": dados.get("html_url"),
        "stargazers_count": dados.get("stargazers_count") or 0,
        "language": dados.get("language"),
        "pushed_at": dados.get("pushed_at"),
        "archived": bool(dados.get("archived")),
        "fork": bool(dados.get("fork")),
    }


# ---------------------------------------------------------------------------
# Montagem dos dados que o template consome
# ---------------------------------------------------------------------------
def montar_projeto(
    item: dict[str, Any],
    dono: str,
    metadados: dict[str, Any] | None,
    incluir_links_nao_verificados: bool,
) -> dict[str, Any] | None:
    """
    Transforma uma entrada do YAML + metadados em uma linha pronta da tabela.

    Entra: item da curadoria, dono do GitHub, metadados (ou None) e a decisão
           sobre mostrar link não confirmado.
    Sai: dicionário com os campos que o template usa, ou None se o item não
         tiver nem nome de repositório.
    """
    nome = str(item.get("repo") or "").strip()
    if not nome:
        _avisar("entrada sem 'repo' na curadoria; ignorada")
        return None

    link: str | None = None
    if metadados and metadados.get("html_url"):
        # Link confirmado pela API: é fato.
        link = str(metadados["html_url"])
    elif incluir_links_nao_verificados:
        # Sem confirmação, mas o dono autorizou mostrar o endereço provável.
        link = f"https://github.com/{dono}/{nome}"

    stack = [str(item_tec).strip() for item_tec in (item.get("stack") or []) if str(item_tec).strip()]

    return {
        "repo": nome,
        "nome": nome,
        "prova": str(item.get("proof") or "").strip() or STATUS_SEM_EVIDENCIA_README,
        "stack": stack,
        "stack_texto": " · ".join(stack) or STATUS_SEM_EVIDENCIA_README,
        "status": traduzir_status(item.get("status")),
        "atualizado_em": formatar_data(metadados.get("pushed_at")) if metadados else STATUS_SEM_EVIDENCIA_README,
        "link": link,
        "link_texto": f"[abrir]({link})" if link else TEXTO_LINK_NAO_VERIFICADO,
        "destacado": bool(item.get("featured")),
        "estrelas": int(metadados.get("stargazers_count") or 0) if metadados else 0,
        "linguagem": metadados.get("language") if metadados else None,
    }



def consolidar_stack(projetos: list[dict[str, Any]]) -> list[str]:
    """
    Junta as tecnologias de todos os projetos, sem repetir, na ordem de aparição.

    Entra: lista de projetos montados.
    Sai: lista de nomes de tecnologia.

    O dicionário é usado como "caderninho de presença": a chave marca quem já
    entrou, e a ordem de inserção do Python 3.7+ preserva a sequência original.
    """
    vistos: dict[str, None] = {}
    for projeto in projetos:
        for tecnologia in projeto["stack"]:
            vistos.setdefault(tecnologia, None)
    return list(vistos)


# ---------------------------------------------------------------------------
# Renderização e CLI
# ---------------------------------------------------------------------------
def criar_ambiente() -> Environment:
    """Prepara o Jinja2 apontando para a pasta de templates do projeto."""
    # autoescape=False de propósito: a saída é Markdown, não HTML. Escapar
    # aqui transformaria "&" em "&amp;" e sujaria a tabela.
    return Environment(
        loader=FileSystemLoader(str(PASTA_TEMPLATES)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _criar_analisador() -> argparse.ArgumentParser:
    """Define os argumentos de linha de comando do gerador."""
    analisador = argparse.ArgumentParser(
        prog="generate.py",
        description="Gera o README de portfólio a partir de config/projects.yaml.",
    )
    analisador.add_argument(
        "--offline",
        action="store_true",
        help="não consulta a API do GitHub (funciona sem rede e sem token)",
    )
    analisador.add_argument(
        "--output",
        default="saidas/README.md",
        help=(
            "arquivo do README completo (padrão: saidas/README.md). "
            "A saída fica fora da raiz de propósito: o README do projeto não é "
            "sobrescrito por um README de perfil."
        ),
    )
    analisador.add_argument(
        "--profile-output",
        default="saidas/README.profile.md",
        help="arquivo da versão para o perfil do GitHub (padrão: saidas/README.profile.md)",
    )
    analisador.add_argument(
        "--config",
        default=str(CAMINHO_CONFIG_PADRAO),
        help="caminho do YAML de curadoria (padrão: config/projects.yaml)",
    )
    analisador.add_argument(
        "--template",
        default="",
        help=(
            "visual do README: minimal, dark-terminal ou animated "
            "(padrão: o do catálogo config/templates.yaml; sem o argumento, um aviso é impresso)"
        ),
    )
    return analisador


def main(argv: list[str] | None = None) -> int:
    """
    Entra: argumentos de linha de comando (ou None, para ler do sys.argv).
    Sai: 0 quando o README foi gerado; 1 em erro de configuração, perfil ou template.

    A montagem é delegada a `perfil_adaptativo/gerador.py` — o mesmo caminho usado
    por `python perfil.py`. Assim o README do formato antigo e o do perfil
    adaptativo nunca divergem na regra, só no dado de entrada.
    """
    # Import tardio de propósito: `analise` e `render` importam este módulo; trazer
    # o pacote no topo criaria importação circular.
    from perfil_adaptativo import gerador, modelo, templates_visuais

    argumentos = _criar_analisador().parse_args(argv)
    caminho_config = Path(argumentos.config)

    try:
        perfil = modelo.carregar(caminho_config)
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return 1

    # Sem --template, avisa e usa o padrão do catálogo (o addendo pede o aviso);
    # num terminal interativo, `perfil.py` oferece o menu.
    template_id = argumentos.template
    if not template_id:
        template_id = templates_visuais.padrao()
        _avisar(f"sem --template; usando o padrão '{template_id}'")

    pasta_saida = Path(argumentos.output).parent

    try:
        resultado = gerador.gerar(
            perfil,
            pasta_saida,
            offline=argumentos.offline,
            template_id=template_id,
        )
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return 1
    except OSError as erro:
        _erro(f"não foi possível gravar os gráficos: {erro}")
        return 1

    try:
        destino_completo = Path(argumentos.output)
        destino_perfil = Path(argumentos.profile_output)
        # A pasta de saída pode não existir na primeira execução (saidas/ nasce
        # vazia e nem entra no git); criar aqui evita o erro de "caminho não existe".
        destino_completo.parent.mkdir(parents=True, exist_ok=True)
        destino_perfil.parent.mkdir(parents=True, exist_ok=True)
        destino_completo.write_text(resultado.texto_completo, encoding="utf-8")
        destino_perfil.write_text(resultado.texto_perfil, encoding="utf-8")
        # O relatório com os números vai junto: medir é parte de gerar.
        import json

        (pasta_saida / "relatorio.json").write_text(
            json.dumps(resultado.preparacao.relatorio, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as erro:
        _erro(f"não foi possível gravar a saída: {erro}")
        return 1

    modo = "offline" if argumentos.offline else "online"
    numeros = resultado.preparacao.relatorio.get("numeros", {})
    # Mensagem só com caracteres ASCII: o console do Windows em cp850 trocaria
    # travessão e acento por "?", e a saída ficaria ilegível.
    print(
        f"README gerado ({modo}, template {resultado.template_id}): "
        f"{argumentos.output} e {argumentos.profile_output} "
        f"- {numeros.get('destaques', 0)} destaque(s), {numeros.get('outros', 0)} outro(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
