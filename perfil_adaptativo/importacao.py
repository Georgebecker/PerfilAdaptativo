"""
importacao.py — baixa os dados públicos de um usuário do GitHub e preenche o perfil.

O problema que este arquivo resolve: ninguém quer digitar à mão o nome de doze
repositórios. O GitHub já sabe nome, descrição, linguagem e data de cada um, e
essa informação é pública. Aqui ela é lida uma vez e vira ponto de partida do
perfil — a pessoa só completa o que a API não sabe (o que cada projeto prova).

A analogia é a matrícula que vem pré-preenchida: o sistema traz o que já tem, a
pessoa confere e corrige. Nada é inventado: campo que a API não informou fica em
branco e o README mostra "não declarado".

Privacidade: só se baixa o que já é público (perfil e repositórios públicos). O
token, se existir, viaja no cabeçalho e nunca é gravado — e a chave não vai
para o perfil.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from . import modelo, seguranca

URL_USUARIO = "https://api.github.com/users/{usuario}"
URL_REPOS = "https://api.github.com/users/{usuario}/repos?per_page=100&sort=pushed"
URL_ATOM_COMMITS = "https://github.com/{dono}/{repo}/commits/HEAD.atom"
MAX_PROJETOS_PADRAO = 12
MAX_DESTAQUES = 3


def _cabecalhos(token: str | None) -> dict[str, str]:
    """Monta os cabeçalhos da API; o token só entra quando existe."""
    cabecalhos = {"Accept": "application/vnd.github+json", "User-Agent": "perfil-adaptativo"}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    return cabecalhos


def data_da_ultima_atualizacao(dono: str, repo: str, tempo_limite: float = 10.0) -> str:
    """
    Lê a data do último commit pelo feed Atom público do repositório.

    Entra: dono, nome do repositório e tempo limite.
    Sai: data em ISO ("2026-10-18T22:30:48Z") ou "" quando não foi possível.

    Por que existe: a API do GitHub tem cota (60 consultas por hora sem token) e,
    quando ela acaba, toda consulta recebe HTTP 403 até o reset. O feed Atom de
    commits é público, não consome essa cota e devolve a informação que interessa
    ao README — quando o repositório foi mexido pela última vez. É a segunda
    rota: se a estrada principal está bloqueada, existe a lateral.

    Nunca levanta exceção: sem data, o README diz "não declarado". Fonte
    alternativa que derruba a geração seria pior que fonte alternativa nenhuma.
    """
    try:
        resposta = requests.get(
            URL_ATOM_COMMITS.format(dono=dono, repo=repo),
            headers={"User-Agent": "perfil-adaptativo"},
            timeout=tempo_limite,
        )
    except requests.RequestException:
        return ""

    if resposta.status_code != 200:
        return ""

    # O primeiro <updated> do feed é o commit mais recente. Não vale montar um
    # leitor de XML completo para ler um campo: a expressão regular resolve e
    # não adiciona dependência.
    achado = re.search(r"<updated>\s*([^<\s]+)\s*</updated>", resposta.text)
    return achado.group(1) if achado else ""


def baixar(usuario: str, token: str | None = None, tempo_limite: float = 15.0) -> dict[str, Any]:
    """
    Baixa os dados públicos do usuário e a lista dos repositórios dele.

    Entra: usuário do GitHub, token opcional e tempo limite por requisição.
    Sai: {"usuario": {...}, "repos": [...]}.
    Levanta modelo.ErroPerfil com mensagem em português quando o usuário não
    existe, o limite de consultas estourou ou a rede caiu.

    As duas chamadas são separadas porque uma pode falhar sozinha: sem a lista de
    repositórios ainda dá para aproveitar nome, bio e site do perfil.
    """
    usuario = modelo.normalizar_usuario(usuario)
    if not usuario:
        raise modelo.ErroPerfil("informe o usuário do GitHub para importar (ex.: --github ana-exemplo)")

    try:
        resposta_usuario = requests.get(
            URL_USUARIO.format(usuario=usuario),
            headers=_cabecalhos(token),
            timeout=tempo_limite,
        )
    except requests.RequestException as erro:
        # Só o tipo: a mensagem crua do requests pode expor cabeçalhos.
        raise modelo.ErroPerfil(
            f"não consegui falar com o GitHub ({type(erro).__name__}). "
            "Confira a conexão e tente de novo, ou preencha o perfil com 'python perfil.py iniciar'."
        ) from erro

    if resposta_usuario.status_code == 404:
        raise modelo.ErroPerfil(f"usuário do GitHub não encontrado: {usuario}")
    if resposta_usuario.status_code == 403:
        raise modelo.ErroPerfil(
            "o GitHub limitou as consultas por hora (HTTP 403). "
            "Defina a variável GITHUB_TOKEN para aumentar o limite, ou aguarde alguns minutos."
        )
    if resposta_usuario.status_code != 200:
        raise modelo.ErroPerfil(f"o GitHub respondeu HTTP {resposta_usuario.status_code} ao buscar o usuário")

    try:
        dados_usuario = resposta_usuario.json()
    except ValueError as erro:
        raise modelo.ErroPerfil("o GitHub devolveu uma resposta que não é JSON; tente de novo") from erro

    repos: list[dict[str, Any]] = []
    try:
        resposta_repos = requests.get(
            URL_REPOS.format(usuario=usuario),
            headers=_cabecalhos(token),
            timeout=tempo_limite,
        )
        if resposta_repos.status_code == 200:
            conteudo = resposta_repos.json()
            if isinstance(conteudo, list):
                repos = [item for item in conteudo if isinstance(item, dict)]
    except (requests.RequestException, ValueError):
        # Sem a lista de repositórios a importação continua útil: dá para herdar
        # nome, bio e site. Perder tudo por causa de uma chamada seria pior.
        repos = []

    return {"usuario": dados_usuario if isinstance(dados_usuario, dict) else {}, "repos": repos}


def repos_utilizaveis(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Filtra a lista crua da API no que pode virar projeto do portfólio.

    Entra: lista de repositórios como o GitHub devolve.
    Sai: lista sem fork, sem arquivado e sem item sem nome.

    Fork não é trabalho do dono e repositório arquivado não representa o que
    está ativo: os dois ficariam fora das tabelas de qualquer jeito, mas filtrar
    já aqui evita mostrar no menu de escolha algo que nunca entraria no README.
    """
    return [
        repo
        for repo in repos
        if isinstance(repo, dict)
        and not repo.get("fork")
        and not repo.get("archived")
        and str(repo.get("name") or "").strip()
    ]


def projetos_a_partir_de(
    repos: list[dict[str, Any]],
    max_projetos: int = MAX_PROJETOS_PADRAO,
) -> list[modelo.Projeto]:
    """
    Converte repositórios públicos em projetos do perfil.

    Entra: lista de repositórios da API e quantos no máximo converter.
    Sai: lista de `modelo.Projeto`, na ordem em que vieram.

    Regras de honestidade aplicadas aqui:
    - `prova` recebe a descrição pública, e só ela (sem descrição, fica vazia);
    - `status` fica vazio: a API não sabe em que estágio o projeto está;
    - `stack` recebe a linguagem principal, quando declarada;
    - `destaque` prioriza quem tem descrição — um repositório sem descrição na
      vitrine mostraria "não declarado" justamente na parte mais visível.

    A ordem é preservada de propósito: a consulta já vem ordenada por último
    push, então o projeto mais recente é o primeiro da lista.
    """
    candidatos = repos_utilizaveis(repos)[: max(1, max_projetos)]

    # Destaque é a vitrine: prefere repositório que TEM descrição (a "prova" que
    # o README mostra) e, entre esses, o mais estrelado e mais recente. Antes, um
    # repositório com estrela e sem descrição ia para a vitrine exibindo "não
    # declarado" — vitrine vazia é pior que vitrine menor.
    com_descricao = [repo for repo in candidatos if str(repo.get("description") or "").strip()]
    base_para_destaque = com_descricao or candidatos

    def _peso(repo: dict[str, Any]) -> tuple[int, str]:
        """Ordena por estrela (maior primeiro) e, no empate, pelo push mais recente."""
        return (int(repo.get("stargazers_count") or 0), str(repo.get("pushed_at") or ""))

    destaques = {
        str(repo.get("name"))
        for repo in sorted(base_para_destaque, key=_peso, reverse=True)[:MAX_DESTAQUES]
    }

    projetos: list[modelo.Projeto] = []
    for repo in candidatos:
        nome_repo = str(repo.get("name") or "").strip()
        linguagem = str(repo.get("language") or "").strip()
        projetos.append(
            modelo.Projeto(
                repo=nome_repo,
                destaque=nome_repo in destaques,
                prova=str(repo.get("description") or "").strip(),
                stack=[linguagem] if linguagem else [],
                status="",
                url=str(repo.get("html_url") or "").strip(),
                # A data vem da API agora e fica guardada: assim o README mostra
                # a data real mesmo em `gerar --offline`, sem inventar nada.
                atualizado_em=str(repo.get("pushed_at") or "").strip(),
                estrelas=int(repo.get("stargazers_count") or 0),
            )
        )
    return projetos


def listar_publicos(
    usuario: str,
    token: str | None = None,
    max_projetos: int = MAX_PROJETOS_PADRAO,
) -> list[modelo.Projeto]:
    """
    Baixa a conta pública do usuário e devolve os projetos prontos para uso.

    Entra: usuário do GitHub, token opcional e quantos projetos no máximo.
    Sai: lista de `modelo.Projeto` (vazia quando a conta não tem repositório).
    Levanta modelo.ErroPerfil nos casos de conta inexistente, limite de consultas
    ou rede fora — com mensagem dizendo o que fazer.

    Esta é a função que permite à coleta preencher o portfólio sozinha: o dado já
    é público, então pedir para a pessoa digitar o que o GitHub já sabe é trabalho
    manual sem motivo.
    """
    dados = baixar(usuario, token=token)
    return projetos_a_partir_de(dados.get("repos") or [], max_projetos=max_projetos)


def perfil_a_partir_de(dados: dict[str, Any], max_projetos: int = MAX_PROJETOS_PADRAO) -> modelo.Perfil:
    """
    Converte a resposta da API no formulário oficial do perfil.

    Entra: dicionário de `baixar` e quantos projetos no máximo trazer.
    Sai: Perfil normalizado (sem nada inventado).

    A conversão dos repositórios fica em `projetos_a_partir_de`, para a coleta
    interativa usar exatamente a mesma regra do comando `importar`.
    """
    dados_usuario = dados.get("usuario") or {}

    login = modelo.normalizar_usuario(dados_usuario.get("login") or "")
    nome = str(dados_usuario.get("name") or login).strip()

    perfil = modelo.Perfil(
        nome=nome,
        github=login,
        bio=str(dados_usuario.get("bio") or "").strip(),
        local=str(dados_usuario.get("location") or "").strip(),
        site=str(dados_usuario.get("blog") or "").strip(),
    )
    perfil.projetos.extend(
        projetos_a_partir_de(dados.get("repos") or [], max_projetos=max_projetos)
    )
    return perfil


def mesclar(existente: modelo.Perfil | None, importado: modelo.Perfil) -> modelo.Perfil:
    """
    Junta o perfil que já existia com o que veio do GitHub, sem apagar trabalho.

    Entra: perfil atual (pode ser None) e perfil importado.
    Sai: perfil combinado.

    Regra de precedência: o que a pessoa escreveu vence o que a API trouxe. Ela
    pode ter corrigido a bio ou escrito à mão o que o projeto prova; sobrescrever
    isso seria apagar o único dado que a API não tem.

    A exceção é campo que a API prova e que estava vazio no perfil (endereço,
    data de atualização, linguagem): esse é preenchido, porque recusar dado
    verificado só obrigaria a pessoa a digitá-lo à mão.
    """
    if existente is None:
        return importado

    combinado = modelo.Perfil(
        nome=existente.nome or importado.nome,
        github=existente.github or importado.github,
        bio=existente.bio or importado.bio,
        local=existente.local or importado.local,
        site=existente.site or importado.site,
        links=[dict(link) for link in existente.links],
        projetos=[modelo.Projeto(**projeto.para_dicionario()) for projeto in existente.projetos],
        conquistas=list(existente.conquistas),
        template=existente.template,
    )

    urls_conhecidas = {link["url"] for link in combinado.links}
    if importado.site and not combinado.site:
        combinado.site = importado.site

    repos_conhecidos = {projeto.repo.casefold() for projeto in combinado.projetos}
    for projeto in importado.projetos:
        chave = projeto.repo.casefold()
        if chave in repos_conhecidos:
            # Repositório que já estava no perfil: o que a pessoa escreveu (prova,
            # status, destaque) é preservado, mas os campos que vêm da API são
            # atualizados quando estavam vazios. Sem isso, quem importou antes de
            # a data ser guardada ficaria com "não declarado" para sempre — dado
            # que a API entrega de graça.
            existente = next(
                (item for item in combinado.projetos if item.repo.casefold() == chave), None
            )
            if existente is not None:
                if not existente.url:
                    existente.url = projeto.url
                if not existente.atualizado_em:
                    existente.atualizado_em = projeto.atualizado_em
                if not existente.stack and projeto.stack:
                    existente.stack = list(projeto.stack)
                if not existente.estrelas and projeto.estrelas:
                    existente.estrelas = projeto.estrelas
            continue
        combinado.projetos.append(projeto)
        repos_conhecidos.add(chave)

    # Biomarcas de link duplicado: comparar pela URL evita repetir o mesmo blog
    # com dois rótulos diferentes.
    for link in importado.links:
        if link["url"] not in urls_conhecidas:
            combinado.links.append(link)
            urls_conhecidas.add(link["url"])

    return combinado


def importar(
    usuario: str,
    perfil_existente: modelo.Perfil | None = None,
    token: str | None = None,
    max_projetos: int = MAX_PROJETOS_PADRAO,
) -> tuple[modelo.Perfil, dict[str, Any]]:
    """
    Faz o download, converte e mescla com o perfil atual.

    Entra: usuário, perfil atual (opcional), token (opcional) e limite de projetos.
    Sai: (perfil combinado, dados brutos baixados).
    Levanta modelo.ErroPerfil nos casos de usuário inexistente, limite de
    consultas ou rede fora — sempre com mensagem de ação.
    """
    dados = baixar(usuario, token=token)
    importado = perfil_a_partir_de(dados, max_projetos=max_projetos)
    combinado = mesclar(perfil_existente, importado)

    # Última checagem antes de devolver: se qualquer texto baixado trouxer algo
    # com cara de segredo (descrição de repositório, bio), o perfil é recusado.
    problemas = seguranca.verificar_campos(combinado.para_dicionario())
    if problemas:
        raise modelo.ErroPerfil("perfil recusado: " + "; ".join(problemas))

    return combinado, dados
