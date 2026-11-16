"""
modelo.py — o formato do perfil: como ele é lido, normalizado, conferido e salvo.

O problema que este arquivo resolve: cada pessoa descreve o próprio portfólio de
um jeito ("stack", "tecnologias", "repo", "repositório"). Se o gerador do README
entendesse só uma grafia, o projeto voltaria a servir a uma pessoa só.

A solução é a mesma de um formulário de banco: existe UM formulário oficial
(`Perfil`), e o atendente (`normalizar`) transcreve para ele o que cada pessoa
escreveu, venha o dado com o nome que vier. Depois disso, todo o resto do
programa lida apenas com o formulário oficial — nunca com o rascunho.

Regras permanentes deste módulo:
- dado ausente nunca vira dado inventado: campo vazio continua vazio e o README
  mostra "não declarado";
- o que parece senha, token ou chave é recusado antes de gravar (ver `seguranca`);
- toda escrita usa UTF-8, porque o README tem acento e travessão.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from . import seguranca

VERSAO_DO_FORMATO = 1

# Nome de repositório no GitHub: letras, números, ponto, hífen e sublinhado.
PADRAO_REPO = re.compile(r"^[A-Za-z0-9._-]+$")
# Usuário do GitHub: começa com letra/número, até 39 caracteres no total.
PADRAO_USUARIO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")

TEXTO_NAO_DECLARADO = "não declarado"


class ErroPerfil(Exception):
    """Erro de perfil com mensagem pronta para o usuário (sem stack trace)."""


@dataclass
class Projeto:
    """Um projeto do portfólio, já no formato oficial."""

    repo: str
    destaque: bool = False
    prova: str = ""
    stack: list[str] = field(default_factory=list)
    status: str = ""
    url: str = ""
    # Data da última atualização informada pela API na importação (ISO, ex.:
    # "2026-10-26T12:06:19Z"). Guardar o valor é o que permite dizer a data
    # também sem rede: sem isso, gerar --offline mostraria "não declarado" para
    # um dado que já era conhecido.
    atualizado_em: str = ""
    # Estrelas que a API informou na importação. Só entram nas estatísticas com
    # o número real lido; nunca estimadas.
    estrelas: int = 0

    def para_dicionario(self) -> dict[str, Any]:
        """Devolve o projeto em dicionário, para gravar em YAML ou comparar."""
        return {
            "repo": self.repo,
            "destaque": self.destaque,
            "prova": self.prova,
            "stack": list(self.stack),
            "status": self.status,
            "url": self.url,
            "atualizado_em": self.atualizado_em,
            "estrelas": self.estrelas,
        }


@dataclass
class Perfil:
    """O formulário oficial: tudo que o README pode usar, e nada além disso."""

    nome: str
    github: str
    bio: str = ""
    local: str = ""
    site: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    projetos: list[Projeto] = field(default_factory=list)
    # Conquistas declaradas pelo dono (certificação, prêmio, formação). O programa
    # nunca inventa uma: só entra o que a pessoa escreveu. As conquistas medidas
    # a partir dos dados são calculadas em `estatisticas.py`.
    conquistas: list[str] = field(default_factory=list)
    # Visual escolhido pelo dono (id do catálogo). Fica no perfil para a próxima
    # geração lembrar a escolha: quem escolheu "animated" não quer voltar ao
    # padrão só porque rodou `gerar` sem argumento.
    template: str = ""
    versao: int = VERSAO_DO_FORMATO

    def para_dicionario(self) -> dict[str, Any]:
        """Devolve o perfil inteiro em dicionário (mesma ordem do arquivo YAML)."""
        return {
            "versao": self.versao,
            "nome": self.nome,
            "github": self.github,
            "bio": self.bio,
            "local": self.local,
            "site": self.site,
            "template": self.template,
            "links": [dict(link) for link in self.links],
            "conquistas": list(self.conquistas),
            "projetos": [projeto.para_dicionario() for projeto in self.projetos],
        }


@dataclass
class ResultadoValidacao:
    """
    O laudo da conferência: o que impede o README e o que apenas merece aviso.

    `erros` bloqueiam (o README não sai com dado quebrado). `avisos` não bloqueiam
    (o README sai, e a pessoa decide se quer completar). `completude` é a
    porcentagem de campos preenchidos — número real, medido, não estimado.
    """

    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    completude: float = 0.0

    @property
    def valido(self) -> bool:
        """True quando nada impede a geração do README."""
        return not self.erros


def _texto(valor: Any) -> str:
    """Converte qualquer valor em texto sem espaços nas pontas (None vira "")."""
    if valor is None:
        return ""
    return str(valor).strip()


def _lista_de_textos(valor: Any) -> list[str]:
    """
    Converte uma lista (ou texto separado por ;) em lista de textos limpos.

    Entra: lista, texto com ";" ou None.
    Sai: lista sem itens vazios e sem repetição.

    Serve para as conquistas, que a pessoa pode digitar de qualquer jeito. Repetir
    a mesma conquista duas vezes no README passaria impressão de descuido.
    """
    if valor is None:
        return []

    itens: list[str] = []
    if isinstance(valor, str):
        itens = valor.split(";")
    elif isinstance(valor, (list, tuple)):
        itens = [str(item) for item in valor]
    else:
        itens = [str(valor)]

    vistos: dict[str, str] = {}
    for item in itens:
        limpo = item.strip().lstrip("-*").strip()
        if limpo:
            vistos.setdefault(limpo.casefold(), limpo)
    return list(vistos.values())


def _inteiro(valor: Any) -> int:
    """
    Converte um valor em número inteiro, devolvendo 0 quando não dá.

    Entra: qualquer valor vindo do YAML ou da API (texto, None, número).
    Sai: inteiro >= 0.

    Número negativo não faz sentido para estrela, e texto solto derrubaria a
    geração por um detalhe irrelevante — melhor tratar como zero.
    """
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return 0


def _primeiro(dados: dict[str, Any], *chaves: str) -> Any:
    """
    Devolve o primeiro valor existente entre os nomes aceitos.

    É o "apelido" dos campos: o perfil novo usa `nome`, o YAML antigo usava
    `github_user` para outra ideia, e o usuário pode digitar `name`. Aceitar os
    apelidos aqui evita um tradutor espalhado pelo resto do programa.
    """
    for chave in chaves:
        if chave in dados and dados[chave] not in (None, ""):
            return dados[chave]
    return None


def normalizar_link(valor: Any) -> dict[str, str] | None:
    """
    Transforma um link solto ou um mapa em {"rotulo": ..., "url": ...}.

    Entra: "https://x.com", {"rotulo": "Blog", "url": "https://x.com"} ou
           {"label": "Blog", "href": "..."}.
    Sai: dicionário com rótulo e url, ou None quando o valor não serve.

    Sem rótulo, o próprio endereço vira rótulo legível (o domínio). Isso evita
    a tabela de links com a coluna vazia, que parece descuido.
    """
    if isinstance(valor, dict):
        url = _texto(_primeiro(valor, "url", "href", "link", "endereco", "endereço"))
        rotulo = _texto(_primeiro(valor, "rotulo", "rótulo", "label", "nome"))
    else:
        url = _texto(valor)
        rotulo = ""

    if not url:
        return None

    if not rotulo:
        dominio = urlparse(url).netloc.replace("www.", "")
        rotulo = dominio or "link"

    return {"rotulo": rotulo, "url": url}


def normalizar_stack(valor: Any) -> list[str]:
    """
    Transforma a lista de tecnologias em lista limpa, sem repetição.

    Entra: lista, texto com vírgulas ("Python, SQL") ou None.
    Sai: lista sem espaços sobrando, com a primeira grafia de cada tecnologia.

    A comparação ignora maiúsculas/minúsculas porque "SQL", "sql" e "Sql" são a
    mesma tecnologia — do mesmo jeito que "José" e "jose" são a mesma pessoa no
    cadastro. A grafia guardada é a primeira que apareceu, para respeitar a
    escolha do dono.
    """
    if valor is None:
        return []

    partes: list[str] = []
    if isinstance(valor, str):
        partes = re.split(r"[,;\n]", valor)
    elif isinstance(valor, (list, tuple, set)):
        for item in valor:
            partes.extend(re.split(r"[,;\n]", _texto(item)))
    else:
        partes = [str(valor)]

    vistos: dict[str, str] = {}
    for parte in partes:
        limpa = parte.strip()
        if not limpa:
            continue
        chave = limpa.casefold()
        vistos.setdefault(chave, limpa)
    return list(vistos.values())


def normalizar_repo(valor: Any) -> tuple[str, str]:
    """
    Separa "nome do repositório" de "endereço do projeto".

    Entra: "meu-projeto", "fulano/meu-projeto" ou "https://github.com/fulano/meu-projeto".
    Sai: (nome, url) — url vazia quando não veio endereço nenhum.

    Essa função existe porque a mesma coisa chega escrita de três jeitos. Como
    um endereço de encomenda: o que interessa para a etiqueta é o nome, mas não
    se joga fora o remetente quando ele vem escrito.
    """
    texto = _texto(valor)
    if not texto:
        return "", ""

    if texto.startswith(("http://", "https://")):
        endereco = texto
        partes = [p for p in urlparse(texto).path.split("/") if p]
        return (partes[-1] if partes else ""), endereco

    if "/" in texto:
        dono, _, nome = texto.rpartition("/")
        return nome.strip(), f"https://github.com/{dono.strip()}/{nome.strip()}"

    return texto, ""


def normalizar_usuario(valor: Any) -> str:
    """
    Devolve só o nome de usuário do GitHub, mesmo que venha com @ ou URL inteira.

    Entra: "@fulano", "fulano", "https://github.com/fulano".
    Sai: "fulano" (sem arroba, sem endereço).
    """
    texto = _texto(valor).lstrip("@")
    if texto.startswith(("http://", "https://")):
        partes = [p for p in urlparse(texto).path.split("/") if p]
        return partes[0] if partes else ""
    return texto


def de_dicionario(dados: Any) -> Perfil:
    """
    Transforma o mapa lido do YAML no formulário oficial (sem validar).

    Entra: dicionário cru (novo formato em pt-BR ou o antigo de `config/projects.yaml`).
    Sai: Perfil normalizado.
    Levanta ErroPerfil quando o arquivo nem é um mapa.

    A validação fica em `validar`, de propósito: normalizar é transcrição,
    conferir é conferência. Misturar as duas etapas faria a pessoa receber erro
    de campo antes de o dado terminar de ser lido.
    """
    if dados is None:
        raise ErroPerfil("o arquivo de perfil está vazio")
    if not isinstance(dados, dict):
        raise ErroPerfil("o perfil precisa ser um mapa YAML com chave: valor")

    usuario = dados.get("usuario") if isinstance(dados.get("usuario"), dict) else {}

    def campo(*chaves: str) -> Any:
        """
        Procura a chave no bloco `usuario`; não achando, procura no topo do arquivo.

        Esse dois-níveis é o que faz o formato novo (com `usuario:` aninhado) e o
        antigo (campos soltos no topo) conviverem no mesmo leitor.
        """
        valor = _primeiro(usuario, *chaves) if usuario else None
        return valor if valor is not None else _primeiro(dados, *chaves)

    nome = _texto(campo("nome", "name"))
    github = normalizar_usuario(campo("github", "github_user", "usuario_github", "usuario", "login"))

    # Formato antigo (`config/projects.yaml`) não tinha campo de nome. Em vez de
    # recusar o arquivo, o título do README usa o usuário do GitHub — que é dado
    # real e público — e a validação avisa que o nome de exibição está faltando.
    if not nome and github:
        nome = github

    bio = _texto(campo("bio", "descricao", "descrição", "headline"))
    local = _texto(campo("local", "localidade", "cidade", "location"))
    site = _texto(campo("site", "website", "blog"))

    links_brutos = campo("links", "contatos", "redes") or []
    if isinstance(links_brutos, (str, dict)):
        links_brutos = [links_brutos]
    links: list[dict[str, str]] = []
    for bruto in links_brutos:
        link = normalizar_link(bruto)
        if link:
            links.append(link)

    projetos_brutos = dados.get("projetos") or dados.get("projects") or []
    if not isinstance(projetos_brutos, list):
        raise ErroPerfil("o campo 'projetos' precisa ser uma lista (cada item com '- repo:')")

    projetos: list[Projeto] = []
    for bruto in projetos_brutos:
        if not isinstance(bruto, dict):
            raise ErroPerfil("cada projeto precisa ser um mapa com pelo menos 'repo'")
        repo, url = normalizar_repo(_primeiro(bruto, "repo", "repositorio", "repositório", "nome"))
        url = _texto(_primeiro(bruto, "url", "link", "endereco", "endereço")) or url
        projetos.append(
            Projeto(
                repo=repo,
                destaque=bool(_primeiro(bruto, "destaque", "featured", "principal")),
                prova=_texto(_primeiro(bruto, "prova", "proof", "resumo", "descricao", "descrição")),
                stack=normalizar_stack(_primeiro(bruto, "stack", "tecnologias", "tech")),
                status=_texto(bruto.get("status")),
                url=url,
                atualizado_em=_texto(
                    _primeiro(bruto, "atualizado_em", "atualizado", "pushed_at", "ultima_atualizacao")
                ),
                estrelas=_inteiro(bruto.get("estrelas")),
            )
        )

    try:
        versao = int(dados.get("versao") or VERSAO_DO_FORMATO)
    except (TypeError, ValueError):
        versao = VERSAO_DO_FORMATO

    return Perfil(
        nome=nome,
        github=github,
        bio=bio,
        local=local,
        site=site,
        links=links,
        conquistas=_lista_de_textos(dados.get("conquistas") or dados.get("achievements")),
        projetos=projetos,
        template=_texto(dados.get("template")),
        versao=versao,
    )


def carregar(caminho: Path) -> Perfil:
    """
    Lê o arquivo de perfil do disco e devolve o formulário oficial.

    Entra: caminho do YAML.
    Sai: Perfil normalizado.
    Levanta ErroPerfil com mensagem em português quando o arquivo não existe, não
    é YAML ou nem chega a ser um perfil.
    """
    if not caminho.exists():
        raise ErroPerfil(
            f"perfil não encontrado em {caminho}. "
            "Rode 'python perfil.py iniciar' para preencher os seus dados."
        )

    try:
        with caminho.open(encoding="utf-8") as arquivo:
            dados = yaml.safe_load(arquivo)
    except OSError as erro:
        raise ErroPerfil(f"não foi possível ler {caminho}: {erro}") from erro
    except yaml.YAMLError as erro:
        raise ErroPerfil(f"{caminho} não é um YAML válido: {erro}") from erro

    return de_dicionario(dados)


def validar(perfil: Perfil) -> ResultadoValidacao:
    """
    Confere o perfil e devolve o laudo (erros, avisos e completude).

    Entra: Perfil normalizado.
    Sai: ResultadoValidacao. Nunca levanta exceção: quem chama decide o que fazer.

    A ordem das checagens segue o checklist de qualidade de dados do projeto:
    o dado existe? está no formato certo? é único? é coerente? E o que falta,
    quanto por cento ficou de fora?
    """
    resultado = ResultadoValidacao()

    if not perfil.nome:
        resultado.erros.append("falta o nome que vai aparecer no README (campo 'nome')")

    if not perfil.github:
        resultado.erros.append("falta o usuário do GitHub (campo 'github')")
    elif not PADRAO_USUARIO.match(perfil.github):
        resultado.erros.append(
            f"usuário do GitHub inválido ({perfil.github!r}): use letras, números e hífen, "
            "sem espaço (ex.: ana-exemplo)"
        )

    if not perfil.projetos:
        # Zero projeto é um estado válido, não um erro: o README começa enxuto,
        # com a apresentação, e cresce a cada projeto cadastrado.
        resultado.avisos.append(
            "ainda sem projetos: o README sai com a apresentação e cresce quando você cadastrar"
        )

    vistos: set[str] = set()
    for indice, projeto in enumerate(perfil.projetos):
        onde = f"projetos[{indice}]"
        if not projeto.repo:
            resultado.erros.append(f"{onde}: falta o nome do repositório")
            continue
        if not PADRAO_REPO.match(projeto.repo):
            resultado.erros.append(
                f"{onde}: nome de repositório inválido ({projeto.repo!r}) — "
                "use letras, números, ponto, hífen ou sublinhado"
            )
        if projeto.url and not projeto.url.startswith(("http://", "https://")):
            resultado.erros.append(f"{onde}: o link precisa começar com http:// ou https://")
        if not projeto.prova:
            resultado.avisos.append(f"{onde} ({projeto.repo}): sem 'prova' — a linha fica só com o essencial")
        if not projeto.stack:
            resultado.avisos.append(f"{onde} ({projeto.repo}): sem stack declarada")
        if not projeto.status:
            resultado.avisos.append(f"{onde} ({projeto.repo}): sem status — o README omite o estágio")

    # Unicidade: o mesmo repositório repetido apareceria duas vezes na tabela e
    # somaria duas vezes na stack consolidada — erro silencioso clássico de base
    # de dados. Aqui se avisa e se mantém só a primeira ocorrência.
    unicos: list[Projeto] = []
    for projeto in perfil.projetos:
        chave = projeto.repo.casefold()
        if chave and chave in vistos:
            resultado.avisos.append(f"repositório repetido removido: {projeto.repo}")
            continue
        if chave:
            vistos.add(chave)
        unicos.append(projeto)
    perfil.projetos = unicos

    if perfil.projetos and not any(projeto.destaque for projeto in perfil.projetos):
        resultado.avisos.append(
            "nenhum projeto marcado como destaque: a seção de destaque fica fora do README"
        )

    if not perfil.bio:
        resultado.avisos.append("sem bio: o README abre sem a frase de apresentação")
    if perfil.nome and perfil.nome.casefold() == perfil.github.casefold():
        resultado.avisos.append(
            "sem nome de exibição: o título do README usa o usuário do GitHub"
        )
    if not perfil.local:
        resultado.avisos.append("sem local: a linha de cidade/estado fica fora do README")
    if not perfil.site:
        resultado.avisos.append("sem site: o README mostra só o link do GitHub")
    if not perfil.links:
        resultado.avisos.append("sem links extras: a seção de links fica só com GitHub e site")

    resultado.erros.extend(seguranca.verificar_campos(perfil.para_dicionario()))
    resultado.completude = medir_completude(perfil)
    return resultado


def medir_completude(perfil: Perfil) -> float:
    """
    Calcula a porcentagem de campos preenchidos (0 a 100, com uma casa decimal).

    Entra: Perfil normalizado.
    Sai: número de 0 a 100.

    O cálculo é simples de propósito: cada campo que o README usa vale 1 ponto,
    e o total inclui, por projeto, prova + stack + status. Assim a pessoa vê o
    número subir quando completa o cadastro — progresso real, não promessa.
    """
    pontos = [bool(perfil.nome), bool(perfil.github), bool(perfil.bio), bool(perfil.local), bool(perfil.site)]
    pontos.append(bool(perfil.links))
    pontos.append(bool(perfil.projetos))
    for projeto in perfil.projetos:
        pontos.extend([bool(projeto.prova), bool(projeto.stack), bool(projeto.status)])

    total = len(pontos)
    preenchidos = sum(1 for ponto in pontos if ponto)
    return round(100.0 * preenchidos / total, 1) if total else 0.0


def como_dicionario(perfil: Perfil) -> dict[str, Any]:
    """Atalho para gravar/comparar o perfil: o perfil em dicionário."""
    return perfil.para_dicionario()


def impressao_digital(perfil: Perfil) -> str:
    """
    Calcula a "impressão digital" do perfil (SHA-256 dos dados normalizados).

    Entra: Perfil normalizado.
    Sai: 64 caracteres hexadecimais.

    Serve para o sistema de dupla aprovação saber se o perfil mudou depois que
    alguém aprovou: se a digital não bate, a aprovação antiga não vale mais.
    É o lacre do pote — abriu e trocou o conteúdo, o lacre antigo não serve.
    """
    texto = json.dumps(perfil.para_dicionario(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def salvar(perfil: Perfil, caminho: Path) -> Path:
    """
    Grava o perfil no disco de forma segura (UTF-8 e escrita atômica).

    Entra: Perfil validado e caminho de destino.
    Sai: o caminho gravado.
    Levanta ErroPerfil se o conteúdo parecer conter segredo ou se o disco falhar.

    "Escrita atômica" quer dizer: grava num arquivo temporário ao lado e só
    então troca o original de uma vez. Se faltar luz no meio, o perfil antigo
    continua inteiro — melhor um perfil velho do que um arquivo pela metade.
    """
    problemas = seguranca.verificar_campos(perfil.para_dicionario())
    if problemas:
        raise ErroPerfil("perfil recusado: " + "; ".join(problemas))

    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")

    conteudo = yaml.safe_dump(
        perfil.para_dicionario(),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    cabecalho = (
        "# Perfil local — gerado pela coleta do PerfilAdaptativo\n"
        "# Este arquivo fica fora do git (data/processed/) e não guarda senha nem chave.\n"
    )

    try:
        temporario.write_text(cabecalho + conteudo, encoding="utf-8")
        os.replace(temporario, caminho)
    except OSError as erro:
        raise ErroPerfil(f"não foi possível gravar {caminho}: {erro}") from erro

    return caminho


def resumo(perfil: Perfil) -> str:
    """
    Monta um resumo curto do perfil para o comando `status`.

    Entra: Perfil normalizado.
    Sai: texto de várias linhas, pronto para imprimir.
    """
    destaques = sum(1 for projeto in perfil.projetos if projeto.destaque)
    linhas = [
        f"nome:    {perfil.nome or TEXTO_NAO_DECLARADO}",
        f"github:  {perfil.github or TEXTO_NAO_DECLARADO}",
        f"local:   {perfil.local or TEXTO_NAO_DECLARADO}",
        f"site:    {perfil.site or TEXTO_NAO_DECLARADO}",
        f"links:   {len(perfil.links)}",
        f"projetos: {len(perfil.projetos)} ({destaques} em destaque)",
        f"atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
    ]
    return "\n".join(linhas)
