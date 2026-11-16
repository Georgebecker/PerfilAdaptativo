"""
seguranca.py — a catraca do perfil: recusa senha, token e chave antes de gravar.

O problema que este arquivo resolve: pedir dados a uma pessoa é pedir que ela
digite coisas no terminal, e gente cansada cola chave de API no lugar da bio.
Se o programa aceitasse, o segredo entraria num arquivo do projeto e, mais
tarde, possivelmente num commit — e chave exposta é chave queimada.

A analogia é a catraca de estúdio: todo mundo passa por ela, ninguém entra pela
porta lateral. Aqui, todo texto que vai ser salvo (bio, "o que o projeto prova",
link, nome de projeto) passa por `encontrar_segredo` antes de tocar o disco.

Regra de ouro respeitada: nada neste arquivo imprime, registra ou devolve o
valor do segredo — só o TIPO ("token do GitHub", "chave da AWS") e o campo onde
ele apareceu. Assim a mensagem de erro orienta sem vazar.
"""

from __future__ import annotations

import re
from typing import Any

# Cada padrão é uma "impressão digital" de segredo conhecido. A descrição existe
# para a mensagem de erro falar a língua do usuário: "isto parece um token do
# GitHub", e não "regex casou".
# Ordem importa: o primeiro que casar define o rótulo mostrado.
PADROES_SEGREDO: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "token do GitHub"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "token do GitHub"),
    (re.compile(r"gh[osur]_[A-Za-z0-9]{20,}"), "token do GitHub"),
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "chave de API (formato OpenAI/DeepSeek)"),
    (re.compile(r"AIza[0-9A-Za-z_-]{30,}"), "chave do Google"),
    (re.compile(r"hf_[A-Za-z0-9]{25,}"), "token do Hugging Face"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "chave da AWS"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "chave privada"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{10,}"), "cabeçalho de autorização"),
    (
        re.compile(
            r"(?i)\b(?:senha|password|passwd|secret|token|api[ _-]?key|chave)\b\s*[:=]\s*\S{4,}"
        ),
        "valor com cara de senha",
    ),
)

# Texto que aparece nas mensagens de recusa. Fica em um lugar só para que a
# entrevista, a validação e o salvamento falem exatamente a mesma língua.
AVISO_DE_SEGREDO = (
    "não guardo senha, token nem chave de API. "
    "A chave fica na variável de ambiente do seu usuário, nunca no arquivo do perfil"
)


def encontrar_segredo(texto: Any) -> str | None:
    """
    Diz QUE TIPO de segredo existe no texto, ou None quando não há nada suspeito.

    Entra: qualquer valor (texto, número, None).
    Sai: o rótulo do tipo encontrado ("token do GitHub", por exemplo) ou None.

    Devolver o tipo, e nunca o valor, é de propósito: a mensagem de erro pode
    citar "isto parece um token do GitHub" sem repetir o segredo na tela, no log
    ou no histórico do terminal.
    """
    if texto is None:
        return None

    valor = str(texto)
    for padrao, descricao in PADROES_SEGREDO:
        if padrao.search(valor):
            return descricao
    return None


def tem_segredo(texto: Any) -> bool:
    """Atalho legível para quem só precisa saber se há segredo (sim/não)."""
    return encontrar_segredo(texto) is not None


def verificar_campos(dados: Any, caminho: str = "") -> list[str]:
    """
    Varre o perfil inteiro (mapas, listas, textos) procurando segredo.

    Entra: estrutura já carregada (dicionário, lista, texto) e o caminho inicial.
    Sai: lista de problemas no formato
         "campo projetos[2].prova: parece um token do GitHub".

    A varredura é recursiva porque o perfil tem dado aninhado: uma senha pode se
    esconder tanto na bio quanto na lista de tecnologias de um projeto. É como
    revistar todas as malas de um ônibus, não só a primeira.
    """
    problemas: list[str] = []

    if isinstance(dados, dict):
        for chave, valor in dados.items():
            caminho_filho = f"{caminho}.{chave}" if caminho else str(chave)
            problemas.extend(verificar_campos(valor, caminho_filho))
        return problemas

    if isinstance(dados, (list, tuple)):
        for indice, valor in enumerate(dados):
            problemas.extend(verificar_campos(valor, f"{caminho}[{indice}]"))
        return problemas

    tipo = encontrar_segredo(dados)
    if tipo:
        campo = caminho or "conteúdo"
        problemas.append(f"campo {campo}: parece um {tipo} — {AVISO_DE_SEGREDO}")

    return problemas


def recusar_se_necessario(texto: Any, nome_do_campo: str) -> str | None:
    """
    Devolve a mensagem de recusa de UM campo, ou None quando o campo está limpo.

    É o que a entrevista usa a cada resposta: em vez de perguntar tudo e recusar
    no fim, ela recusa na hora, do mesmo jeito que o caixa do mercado devolve o
    item com preço errado no instante da leitura.
    """
    tipo = encontrar_segredo(texto)
    if tipo is None:
        return None
    return f"campo {nome_do_campo}: parece um {tipo} — {AVISO_DE_SEGREDO}"
