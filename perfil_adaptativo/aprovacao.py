"""
aprovacao.py — o cadeado de duas voltas: só publica depois de dois aceites.

O problema que este arquivo resolve: o README gerado descreve uma pessoa e, ao
subir para o GitHub, fica público. Um clique errado no comando de upload não tem
"desfazer" — então o programa exige duas aprovações explícitas, e as duas ficam
amarradas ao conteúdo exato que foi aprovado.

Como funciona, em analogia de banco: ninguém abre o cofre com uma chave só.
A primeira volta confere os dados ("o que vai aparecer"); a segunda, o texto
final ("como vai aparecer"). Se qualquer coisa mudar depois, o envelope muda de
peso e as duas assinaturas deixam de valer — é a "impressão digital" (SHA-256)
gravada em `data/processed/aprovacoes.json`.

O que este arquivo NÃO faz: guardar token. O token do GitHub é lido da variável
de ambiente no instante do upload e nunca é escrito em arquivo, log ou mensagem.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from . import graficos, modelo

ROTULOS_DE_ETAPA = {
    1: "dados revisados",
    2: "texto final aprovado",
}
ETAPAS_OBRIGATORIAS = (1, 2)

NOME_REGISTRO = "aprovacoes.json"
URL_CONTEUDO_GITHUB = "https://api.github.com/repos/{repo}/contents/{caminho}"


def digital_arquivo(caminho: Path) -> str:
    """
    Calcula o SHA-256 do arquivo, lendo em blocos.

    Entra: caminho do arquivo.
    Sai: 64 caracteres hexadecimais, ou "" quando o arquivo não existe.

    Ler em blocos (e não de uma vez) é como conferir um livro página por página:
    funciona igual para o README de 20 linhas e para um arquivo enorme.
    """
    if not caminho.exists():
        return ""

    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(65536), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def digital_conjunto(caminhos: list[Path]) -> str:
    """
    Calcula uma digital única para um conjunto de arquivos.

    Entra: lista de caminhos (README e gráficos).
    Sai: 64 caracteres hexadecimais, ou "" quando a lista está vazia.

    A digital leva o NOME junto do conteúdo, e a lista vai ordenada: assim
    renomear um gráfico também invalida a aprovação. Sem isso, o lacre diria
    "igual" para um conjunto que mudou de nome — como uma etiqueta de mala
    trocada, que faz o passageiro embarcar no voo errado.
    """
    if not caminhos:
        return ""

    resumo = hashlib.sha256()
    for caminho in sorted(caminhos, key=lambda item: item.name):
        resumo.update(caminho.name.encode("utf-8"))
        resumo.update(b"\0")
        resumo.update(digital_arquivo(caminho).encode("utf-8"))
        resumo.update(b"\0")
    return resumo.hexdigest()


def carregar_registro(caminho: Path) -> dict[str, Any]:
    """
    Lê o registro de aprovações; se não existir ou estiver corrompido, começa vazio.

    Entra: caminho do JSON.
    Sai: dicionário com as etapas e as publicações já feitas.

    Registro ilegível vira registro vazio de propósito: um arquivo pela metade
    nunca deve liberar publicação; no pior caso, a pessoa aprova de novo.
    """
    vazio: dict[str, Any] = {
        "sha256_readme": "",
        "sha256_perfil": "",
        "sha256_graficos": "",
        "etapas": [],
        "publicacoes": [],
    }
    if not caminho.exists():
        return vazio

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return vazio

    if not isinstance(dados, dict):
        return vazio

    for chave, padrao in vazio.items():
        dados.setdefault(chave, padrao)
    if not isinstance(dados["etapas"], list):
        dados["etapas"] = []
    if not isinstance(dados["publicacoes"], list):
        dados["publicacoes"] = []
    return dados


def salvar_registro(registro: dict[str, Any], caminho: Path) -> Path:
    """Grava o registro de aprovações em JSON UTF-8 (cria a pasta quando falta)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return caminho


def _assinaturas(arquivo_readme: Path, perfil: modelo.Perfil) -> tuple[str, str, str]:
    """
    Devolve as três digitais que identificam o que está sendo aprovado.

    Entra: README gerado e perfil.
    Sai: (digital do README, digital do perfil, digital dos gráficos).

    Os gráficos entram na conta porque também vão para o GitHub: aprovar um
    pacote e publicar outro seria furar o próprio lacre.
    """
    return (
        digital_arquivo(arquivo_readme),
        modelo.impressao_digital(perfil),
        digital_conjunto(graficos.arquivos(arquivo_readme.parent)),
    )


def estado(arquivo_readme: Path, perfil: modelo.Perfil, caminho_registro: Path) -> dict[str, Any]:
    """
    Diz se a publicação está liberada e, quando não está, o motivo exato.

    Entra: README gerado, perfil e caminho do registro.
    Sai: dicionário com `liberado`, `etapas` registradas, `faltando` e `motivo`.

    Este é o coração da regra "aprovado 2X": duas etapas, mesmo conteúdo. Se o
    README foi regerado depois do primeiro aceite, a digital não bate e o estado
    volta a zero — como um selo que se rompe quando o pacote é aberto.
    """
    registro = carregar_registro(caminho_registro)
    digital_readme, digital_perfil, digital_graficos = _assinaturas(arquivo_readme, perfil)

    registradas = {
        int(etapa.get("etapa", 0))
        for etapa in registro.get("etapas", [])
        if isinstance(etapa, dict)
    }
    mesmo_conteudo = (
        digital_readme != ""
        and registro.get("sha256_readme") == digital_readme
        and registro.get("sha256_perfil") == digital_perfil
        and registro.get("sha256_graficos") == digital_graficos
    )

    validas = sorted(etapa for etapa in registradas if mesmo_conteudo and etapa in ETAPAS_OBRIGATORIAS)
    faltando = [etapa for etapa in ETAPAS_OBRIGATORIAS if etapa not in validas]

    if not arquivo_readme.exists():
        motivo = "o README ainda não foi gerado; rode 'python perfil.py gerar'"
    elif not mesmo_conteudo and registradas:
        motivo = "o README ou o perfil mudou depois da aprovação: as aprovações anteriores não valem mais"
    elif faltando:
        pendente = ROTULOS_DE_ETAPA[faltando[0]]
        motivo = f"falta a aprovação {faltando[0]} de 2 ({pendente})"
    else:
        motivo = "duas aprovações válidas para este conteúdo"

    return {
        "liberado": not faltando and mesmo_conteudo,
        "etapas_validas": validas,
        "faltando": faltando,
        "motivo": motivo,
        "sha256_readme": digital_readme,
        "sha256_perfil": digital_perfil,
        "sha256_graficos": digital_graficos,
        "mesmo_conteudo": mesmo_conteudo,
    }


def conceder(
    etapa: int,
    arquivo_readme: Path,
    perfil: modelo.Perfil,
    caminho_registro: Path,
) -> tuple[bool, str]:
    """
    Registra UMA aprovação e devolve (deu certo?, mensagem para o usuário).

    Entra: etapa (1 ou 2), README gerado, perfil e caminho do registro.
    Sai: (True, "aprovação 1 de 2 registrada...") ou (False, motivo).

    Regras de ordem, iguais às de uma esteira de conferência:
    - o README precisa existir;
    - a etapa 1 vem antes da etapa 2;
    - conteúdo alterado zera as aprovações anteriores;
    - repetir a mesma etapa não conta duas vezes.
    """
    if etapa not in ROTULOS_DE_ETAPA:
        return False, f"etapa inválida ({etapa}): use 1 (dados) ou 2 (texto final)"

    if not arquivo_readme.exists():
        return False, "o README ainda não existe; rode 'python perfil.py gerar' antes de aprovar"

    registro = carregar_registro(caminho_registro)
    digital_readme, digital_perfil, digital_graficos = _assinaturas(arquivo_readme, perfil)
    mesmo_conteudo = (
        registro.get("sha256_readme") == digital_readme
        and registro.get("sha256_perfil") == digital_perfil
        and registro.get("sha256_graficos") == digital_graficos
    )

    if not mesmo_conteudo:
        registro["sha256_readme"] = digital_readme
        registro["sha256_perfil"] = digital_perfil
        registro["sha256_graficos"] = digital_graficos
        registro["etapas"] = []

    registradas = {int(item.get("etapa", 0)) for item in registro["etapas"] if isinstance(item, dict)}
    if etapa in registradas:
        return False, f"a aprovação {etapa} de 2 já estava registrada para este conteúdo"

    if etapa == 2 and 1 not in registradas:
        salvar_registro(registro, caminho_registro)
        return False, "aprove primeiro a etapa 1 (dados revisados); a etapa 2 é a do texto final"

    registro["etapas"].append(
        {
            "etapa": etapa,
            "rotulo": ROTULOS_DE_ETAPA[etapa],
            "quando": datetime.now().isoformat(timespec="seconds"),
            "sha256_readme": digital_readme,
            "sha256_perfil": digital_perfil,
            "sha256_graficos": digital_graficos,
        }
    )
    salvar_registro(registro, caminho_registro)

    total = len({item["etapa"] for item in registro["etapas"]})
    if total >= 2:
        return True, "aprovação 2 de 2 registrada: publicação liberada para este conteúdo"
    return True, "aprovação 1 de 2 registrada: revise o texto final e aprove a etapa 2"


def _token_do_github() -> str | None:
    """
    Lê o token do GitHub da variável de ambiente (nunca de arquivo).

    Aceita GITHUB_TOKEN (Actions) e GH_TOKEN (CLI do GitHub). O valor não é
    impresso nem devolvido em mensagem de erro: token é tratado como senha.
    """
    return os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or None


def _erro_http(status: int) -> str:
    """Traduz o código HTTP do GitHub em uma explicação útil para o usuário."""
    if status in (401, 403):
        return (
            "o GitHub recusou o token (HTTP "
            f"{status}). Confira se a variável GITHUB_TOKEN existe no seu ambiente e "
            "se o token tem permissão de escrita no repositório do perfil."
        )
    if status == 404:
        return (
            "repositório do perfil não encontrado (HTTP 404). "
            "Crie no GitHub o repositório com o mesmo nome do seu usuário "
            "(ex.: usuario/usuario) e tente de novo."
        )
    if status in (409, 422):
        return "o GitHub recusou a gravação por conflito (HTTP {0}); tente novamente".format(status)
    return f"o GitHub respondeu HTTP {status}; nada foi publicado"


def _enviar_arquivo(
    repositorio: str,
    caminho_no_repo: str,
    conteudo: bytes,
    cabecalhos: dict[str, str],
    mensagem: str,
) -> tuple[bool, str]:
    """
    Envia UM arquivo ao GitHub, criando ou atualizando.

    Entra: repositório, caminho no repositório, bytes do arquivo, cabeçalhos e
           mensagem de commit.
    Sai: (True, endereço no GitHub) ou (False, motivo em português).

    O GET antes do PUT não é redundância: é como o GitHub diferencia "criar" de
    "atualizar". Enviar sem o `sha` atual seria como entregar uma encomenda sem
    conferir se já existe uma na caixa — o servidor recusa com conflito.
    """
    url = URL_CONTEUDO_GITHUB.format(repo=repositorio, caminho=caminho_no_repo)

    try:
        resposta = requests.get(url, headers=cabecalhos, timeout=15)
    except requests.RequestException as erro:
        # Só o tipo do erro: a mensagem crua pode carregar cabeçalho com token.
        return False, f"falha de rede ao consultar o GitHub ({type(erro).__name__}); nada foi publicado"

    sha_atual: str | None = None
    if resposta.status_code == 200:
        try:
            sha_atual = resposta.json().get("sha")
        except ValueError:
            sha_atual = None
    elif resposta.status_code != 404:
        return False, _erro_http(resposta.status_code)

    corpo: dict[str, Any] = {
        "message": mensagem,
        "content": base64.b64encode(conteudo).decode("ascii"),
    }
    if sha_atual:
        corpo["sha"] = sha_atual

    try:
        envio = requests.put(url, headers=cabecalhos, json=corpo, timeout=30)
    except requests.RequestException as erro:
        return False, f"falha de rede ao enviar ({type(erro).__name__}); nada foi publicado"

    if envio.status_code not in (200, 201):
        return False, _erro_http(envio.status_code)

    endereco = f"https://github.com/{repositorio}/blob/HEAD/{caminho_no_repo}"
    try:
        dados = envio.json()
        endereco = dados.get("content", {}).get("html_url") or endereco
    except ValueError:  # resposta 200 sem JSON: o endereço montado já serve
        pass

    return True, endereco


def publicar(
    arquivo_readme: Path,
    perfil: modelo.Perfil,
    caminho_registro: Path,
    repositorio: str | None = None,
    caminho_no_repo: str = "README.md",
    mensagem: str | None = None,
    token: str | None = None,
) -> tuple[bool, str]:
    """
    Envia o README aprovado (e os gráficos dele) para o repositório de perfil.

    Entra: README, perfil, registro, repositório ("usuario/usuario"), caminho no
           repositório, mensagem de commit e token (opcional; padrão vem do ambiente).
    Sai: (True, endereço publicado) ou (False, motivo em português).

    Esta é a ÚNICA função do projeto que escreve na internet, e ela se recusa a
    funcionar sem duas aprovações válidas para o conteúdo atual. É o mesmo
    princípio de um cartório: o documento só sai depois das assinaturas, e o
    texto assinado tem de ser o texto entregue.

    Os gráficos viajam junto porque o README os referencia por caminho relativo:
    mandar só o texto deixaria imagem quebrada no perfil publicado — pior que
    não ter gráfico.
    """
    situacao = estado(arquivo_readme, perfil, caminho_registro)
    if not situacao["liberado"]:
        return False, f"publicação bloqueada: {situacao['motivo']}"

    token = token or _token_do_github()
    if not token:
        return False, (
            "falta o token do GitHub. Defina a variável de ambiente GITHUB_TOKEN "
            "(no Windows: segredos.ps1 -Definir GITHUB_TOKEN) e abra um terminal novo."
        )

    repositorio = repositorio or f"{perfil.github}/{perfil.github}"
    if "/" not in repositorio:
        return False, "repositório inválido: use o formato usuario/repositorio"

    cabecalhos = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "perfil-adaptativo",
    }
    texto_do_commit = mensagem or f"docs: atualiza README do perfil em {datetime.now():%d/%m/%Y}"

    arquivos: list[tuple[str, Path]] = [(caminho_no_repo, arquivo_readme)]
    for desenho in graficos.arquivos(arquivo_readme.parent):
        arquivos.append((f"graficos/{desenho.name}", desenho))

    endereco_final = f"https://github.com/{repositorio}/blob/HEAD/{caminho_no_repo}"
    enviados = 0
    for caminho, origem in arquivos:
        deu_certo, resultado = _enviar_arquivo(
            repositorio,
            caminho,
            origem.read_bytes(),
            cabecalhos,
            f"{texto_do_commit} ({caminho})" if caminho != caminho_no_repo else texto_do_commit,
        )
        if not deu_certo:
            if enviados == 0:
                return False, resultado
            # Falha no meio: parte foi publicada. A mensagem diz exatamente o que
            # aconteceu para a pessoa decidir entre repetir ou conferir no GitHub.
            return False, (
                f"o README foi enviado, mas {caminho} falhou: {resultado}. "
                "Rode 'publicar' de novo para completar os gráficos."
            )
        enviados += 1
        if caminho == caminho_no_repo:
            endereco_final = resultado

    registro = carregar_registro(caminho_registro)
    registro["publicacoes"].append(
        {
            "quando": datetime.now().isoformat(timespec="seconds"),
            "repositorio": repositorio,
            "caminho": caminho_no_repo,
            "sha256_readme": situacao["sha256_readme"],
            "sha256_graficos": situacao["sha256_graficos"],
            "arquivos": [caminho for caminho, _ in arquivos],
            "endereco": endereco_final,
        }
    )
    salvar_registro(registro, caminho_registro)

    extra = "" if len(arquivos) == 1 else f" (+{len(arquivos) - 1} gráfico(s))"
    return True, f"publicado em {endereco_final}{extra}"
