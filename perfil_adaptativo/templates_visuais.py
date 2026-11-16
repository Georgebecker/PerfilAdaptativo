"""
templates_visuais.py — o catálogo de visuais do README (e o menu para escolher).

O problema que este arquivo resolve: com três (ou dez) templates, alguém precisa
dizer qual vale, conferir se ele existe e avisar quando o nome foi digitado
errado. Espalhar essa checagem pelo código é o caminho mais curto para gerar um
arquivo vazio e culpar o usuário.

Analogia: é o cardápio do restaurante. O cliente escolhe pelo nome do prato, o
garçom confere se existe na cozinha e, se não existe, oferece as opções — em vez
de trazer um prato vazio.

Regra de segurança: o caminho do template precisa ficar DENTRO de `templates/`.
Um catálogo editado por engano não deve conseguir carregar arquivo de fora do
projeto (é o mesmo cuidado de conferir se a encomenda pertence ao prédio).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

from . import modelo

RAIZ = Path(__file__).resolve().parents[1]
PASTA_TEMPLATES = RAIZ / "templates"
CAMINHO_CATALOGO = RAIZ / "config" / "templates.yaml"
ID_PADRAO = "minimal"


def carregar_catalogo(caminho: Path | None = None) -> list[dict[str, Any]]:
    """
    Lê o catálogo de templates e confere o mínimo de cada entrada.

    Entra: caminho do YAML (padrão: config/templates.yaml).
    Sai: lista de dicionários com id, name, description, path, license e inspired_by.
    Levanta modelo.ErroPerfil quando o arquivo não existe, não é YAML ou não tem
    nenhum template válido.

    Entrada sem `id` ou sem `path` é descartada com aviso invisível: catálogo
    quebrado não deve derrubar a geração inteira, mas template inexistente não
    pode passar como se existisse.
    """
    caminho = caminho or CAMINHO_CATALOGO
    if not caminho.exists():
        raise modelo.ErroPerfil(
            f"catálogo de templates não encontrado em {caminho}. "
            "Restaure o arquivo config/templates.yaml."
        )

    try:
        with caminho.open(encoding="utf-8") as arquivo:
            dados = yaml.safe_load(arquivo)
    except (OSError, yaml.YAMLError) as erro:
        raise modelo.ErroPerfil(f"não foi possível ler {caminho}: {erro}") from erro

    brutos = (dados or {}).get("templates") if isinstance(dados, dict) else None
    if not isinstance(brutos, list):
        raise modelo.ErroPerfil(
            "config/templates.yaml precisa ter uma lista 'templates:' com id, name, description e path"
        )

    catalogo: list[dict[str, Any]] = []
    for bruto in brutos:
        if not isinstance(bruto, dict):
            continue
        identificador = str(bruto.get("id") or "").strip()
        caminho_do_template = str(bruto.get("path") or "").strip()
        if not identificador or not caminho_do_template:
            continue
        catalogo.append(
            {
                "id": identificador,
                "name": str(bruto.get("name") or identificador).strip(),
                "description": str(bruto.get("description") or "").strip(),
                "path": caminho_do_template,
                "license": str(bruto.get("license") or "MIT").strip(),
                "inspired_by": str(bruto.get("inspired_by") or "").strip(),
            }
        )

    if not catalogo:
        raise modelo.ErroPerfil(f"nenhum template válido em {caminho} (faltou 'id' ou 'path')")

    return catalogo


def padrao() -> str:
    """
    Devolve o id do template padrão: `minimal` quando existir, senão o primeiro.

    Entra: nada.
    Sai: id do template padrão.
    """
    catalogo = carregar_catalogo()
    ids = [item["id"] for item in catalogo]
    return ID_PADRAO if ID_PADRAO in ids else ids[0]


def obter(identificador: str | None) -> dict[str, Any]:
    """
    Devolve a entrada do catálogo para o id pedido, validando o caminho do arquivo.

    Entra: id do template (None vira o padrão).
    Sai: entrada do catálogo com a chave extra `arquivo` (Path absoluto).
    Levanta modelo.ErroPerfil listando os ids válidos quando o id não existe —
    mensagem de erro é aula: precisa dizer o que fazer agora.
    """
    catalogo = carregar_catalogo()
    escolhido = (identificador or padrao()).strip()

    for entrada in catalogo:
        if entrada["id"] == escolhido:
            arquivo = (RAIZ / entrada["path"]).resolve()
            try:
                arquivo.relative_to(PASTA_TEMPLATES.resolve())
            except ValueError:
                raise modelo.ErroPerfil(
                    f"o caminho do template '{escolhido}' aponta para fora de templates/. "
                    "Corrija config/templates.yaml."
                ) from None
            if not arquivo.is_file():
                raise modelo.ErroPerfil(
                    f"o arquivo do template '{escolhido}' não existe ({entrada['path']}). "
                    "Restaure o arquivo ou remova a entrada do catálogo."
                )
            return dict(entrada, arquivo=arquivo)

    validos = ", ".join(item["id"] for item in catalogo)
    raise modelo.ErroPerfil(
        f"template '{escolhido}' não existe. Disponíveis: {validos}. "
        "Use --template <id> ou rode sem --template para ver o menu."
    )


def nome_do_arquivo(identificador: str | None) -> str:
    """
    Devolve o nome usado pelo Jinja2 para carregar o template ("minimal/profile.md.j2").

    Entra: id do template.
    Sai: caminho relativo à pasta templates/, no formato POSIX (barra normal).
    """
    entrada = obter(identificador)
    return Path(entrada["path"]).relative_to("templates").as_posix()


def menu(escrever: Callable[[str], None] | None = None) -> str:
    """
    Mostra o menu de templates e devolve o id escolhido.

    Entra: função de escrita (padrão: print).
    Sai: id do template; cai no padrão quando a resposta não serve.

    A escolha é por número, como em cardápio de balcão: digitar "2" é mais fácil
    do que lembrar se o nome é "dark-terminal" ou "dark_terminal".
    """
    escrever = escrever or print
    catalogo = carregar_catalogo()

    escrever("Escolha o template:")
    for indice, entrada in enumerate(catalogo, start=1):
        escrever(f"  [{indice}] {entrada['name']} — {entrada['description']}")

    try:
        resposta = input("Número (Enter usa o padrão): ").strip()
    except (EOFError, KeyboardInterrupt):
        return padrao()

    if not resposta:
        return padrao()

    try:
        indice_escolhido = int(resposta)
    except ValueError:
        indice_escolhido = 0

    if 1 <= indice_escolhido <= len(catalogo):
        return catalogo[indice_escolhido - 1]["id"]

    escrever(f"  opção inválida; usando o padrão: {padrao()}")
    return padrao()


def nomes() -> list[str]:
    """Lista os ids disponíveis (útil em ajuda de linha de comando e em teste)."""
    return [entrada["id"] for entrada in carregar_catalogo()]
