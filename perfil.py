"""
perfil.py — a porta de entrada: coleta, gera, pré-visualiza, aprova e publica.

O problema que este arquivo resolve: o projeto tem sete peças (segurança, modelo,
coleta, análise, render, preview, aprovação) e ninguém deveria precisar decorar
qual chamar. Aqui cada passo do caminho vira um subcomando, na ordem em que a
pessoa realmente trabalha:

    python perfil.py iniciar     # pergunta os dados (uma vez)
    python perfil.py importar    # baixa o que o GitHub já sabe do seu perfil
    python perfil.py validar     # confere o que ficou de fora
    python perfil.py gerar       # escreve saidas/README.md e os gráficos
    python perfil.py preview     # abre o README no navegador, como no GitHub
    python perfil.py aprovar --etapa 1
    python perfil.py aprovar --etapa 2
    python perfil.py publicar --confirmar

Regras que a linha de comando garante:
- nenhum comando grava senha, token ou chave (a barreira está em `seguranca`);
- nada é publicado antes das duas aprovações (a trava está em `aprovacao`);
- o upload é o único passo que fala com a internet em modo de escrita, e o token
  vem da variável de ambiente do usuário.

Sai com 0 quando deu certo e 1 quando o problema é do dado ou do ambiente — assim
o comando também serve dentro de um script ou de uma esteira de CI.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from perfil_adaptativo import (
    analise,
    aprovacao,
    coleta,
    gerador,
    graficos,
    importacao,
    modelo,
    preview,
    render,
    templates_visuais,
)

# A raiz é calculada a partir do próprio arquivo, não do diretório atual: assim o
# comando funciona mesmo quando roda de outra pasta.
RAIZ = Path(__file__).resolve().parent
PERFIL_PADRAO = RAIZ / "data" / "processed" / "perfil.yaml"
SAIDA_PADRAO = RAIZ / "saidas"
REGISTRO_PADRAO = RAIZ / "data" / "processed" / "aprovacoes.json"
PORTA_PADRAO = 8765
NOME_DO_README = "README.md"


def _erro(mensagem: str) -> None:
    """
    Imprime erro em português, no formato curto que a pessoa entende.

    Vai para stderr porque erro não é produto: permite separar a saída útil
    (caminhos, números) da conversa de bastidor num script.
    """
    print(f"erro: {mensagem}", file=sys.stderr)


def _carregar(argumentos: argparse.Namespace) -> modelo.Perfil | None:
    """
    Lê o perfil indicado e devolve None (já com erro impresso) quando não dá.

    Centralizar isso evita repetir o mesmo `try/except` em seis comandos e
    garante que todos falem a mesma língua quando o arquivo não existe.
    """
    try:
        return modelo.carregar(Path(argumentos.perfil))
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return None


def _caminho_readme(argumentos: argparse.Namespace) -> Path:
    """Devolve o caminho do README gerado dentro da pasta de saída."""
    return Path(argumentos.saida) / NOME_DO_README


def _ajustar_saida_do_console() -> None:
    """
    Força UTF-8 na saída quando ela é capturada por pipe ou arquivo.

    Por que existe: no Windows, o Python assume cp1252 ao escrever em pipe, e o
    "próximo passo" sai como "pr?ximo". Numa janela de terminal de verdade o
    Windows usa a API de console e o acento continua certo; aqui só se corrige o
    caso de redirecionamento. Se a versão do Python não permitir o ajuste, segue
    em frente: é cosmético e não pode derrubar o comando.
    """
    for fluxo in (sys.stdout, sys.stderr):
        reconfigure = getattr(fluxo, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _resolver_template(argumentos: argparse.Namespace, perfil: modelo.Perfil | None = None) -> str | None:
    """
    Decide qual template usar: argumento, escolha lembrada, menu ou padrão.

    Entra: argumentos já interpretados (precisa de `template` e `comando`) e, quando
           existir, o perfil carregado (para lembrar o visual escolhido antes).
    Sai: id do template válido, ou None quando o id pedido não existe (o erro já
    foi impresso e quem chamou deve sair com código 1).

    A ordem é a do balcão: se o cliente escolheu agora, respeita; se não escolheu
    mas já tinha escolhido antes, mantém; se está ali na frente (terminal), mostra
    o menu; se não há como perguntar (script, pipe), usa o padrão e avisa.
    Avisar importa: gerar com visual diferente do esperado sem dizer nada parece
    defeito.
    """
    if argumentos.template:
        try:
            templates_visuais.obter(argumentos.template)
        except modelo.ErroPerfil as erro:
            _erro(str(erro))
            return None
        return argumentos.template

    lembrado = (perfil.template if perfil else "").strip()
    if lembrado:
        try:
            templates_visuais.obter(lembrado)
            print(f"template: usando o visual escolhido antes ('{lembrado}')")
            return lembrado
        except modelo.ErroPerfil:
            # Visual lembrado não existe mais (catálogo mudou): segue para o menu
            # ou o padrão em vez de travar a geração.
            print(f"aviso: o visual '{lembrado}' não existe mais; escolha outro")

    if sys.stdin.isatty() and argumentos.comando in ("iniciar", "gerar", "importar"):
        return templates_visuais.menu()

    try:
        padrao = templates_visuais.padrao()
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return None

    print(f"aviso: sem --template; usando o padrão '{padrao}'")
    return padrao


def _gerar_arquivos(
    perfil: modelo.Perfil,
    saida: Path,
    offline: bool,
    template_id: str,
) -> analise.Preparacao:
    """
    Executa a montagem completa e grava README + relatório, mostrando os números.

    Entra: perfil validado, pasta de saída, se deve evitar a rede e o template.
    Sai: a preparação (para quem quiser o relatório em memória).
    Levanta modelo.ErroPerfil quando o perfil não passa na validação ou o
    template não existe.

    A ordem importa: os gráficos são desenhados antes do texto porque o README os
    referencia pelo caminho. Gerar o texto primeiro deixaria a primeira versão do
    README com imagem quebrada.
    """
    resultado = gerador.gerar(perfil, saida, offline=offline, template_id=template_id)
    destino = render.gravar(resultado.texto_completo, saida / NOME_DO_README)
    analise.salvar_relatorio(resultado.preparacao.relatorio, saida / "relatorio.json")

    print(f"README gerado: {destino}")
    print(f"template: {resultado.template_id} — {resultado.template_nome}")
    print(analise.formatar_relatorio(resultado.preparacao.relatorio))
    print(f"gráficos: {len(resultado.desenhos)}")
    return resultado.preparacao


def _mostrar_estado(perfil: modelo.Perfil, argumentos: argparse.Namespace) -> dict:
    """Imprime o estado das aprovações e devolve o dicionário para reuso."""
    situacao = aprovacao.estado(
        _caminho_readme(argumentos), perfil, Path(argumentos.registro)
    )
    etapas = ", ".join(str(etapa) for etapa in situacao["etapas_validas"]) or "nenhuma"
    print(f"aprovações válidas: {etapas} de 2")
    print(f"publicação: {'liberada' if situacao['liberado'] else 'bloqueada'} — {situacao['motivo']}")
    return situacao


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------
def _localizador_de_publicos(argumentos: argparse.Namespace):
    """
    Devolve a função que busca os repositórios públicos, ou None quando não deve buscar.

    Entra: argumentos do comando `iniciar`.
    Sai: função `usuario -> list[modelo.Projeto]`, ou None.

    Duas situações desligam a busca, e as duas têm motivo:
    - `--offline`: o usuário pediu para não tocar a rede;
    - `--sem-importar`: o usuário quer digitar tudo (portfólio com projeto que
      não está no GitHub, ou conta que não deve ser lida).

    O token do ambiente é usado quando existe, só para elevar o limite de
    consultas: sem ele a leitura continua funcionando (60 por hora).
    """
    if argumentos.offline or argumentos.sem_importar:
        return None

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or None
    maximo = argumentos.max

    def localizar(usuario: str) -> list[modelo.Projeto]:
        """Busca os projetos públicos do usuário (delega a `importacao`)."""
        return importacao.listar_publicos(usuario, token=token, max_projetos=maximo)

    return localizar


def comando_iniciar(argumentos: argparse.Namespace) -> int:
    """
    Roda a entrevista, preenche o que o GitHub já sabe e grava o perfil.

    Sai: 0 quando o perfil foi gravado; 1 quando a validação reprovou (nada é gravado).

    A entrevista já nasce com os repositórios públicos da conta: pedir para
    digitar o que o GitHub expõe publicamente seria trabalho manual sem motivo.
    A pessoa confirma o que entra e pode acrescentar projeto de fora do GitHub.
    """
    caminho = Path(argumentos.perfil)
    inicial: modelo.Perfil | None = None
    if caminho.exists():
        try:
            inicial = modelo.carregar(caminho)
            print(f"editando o perfil existente em {caminho} (Enter mantém o valor atual)\n")
        except modelo.ErroPerfil:
            print(f"o perfil em {caminho} não pôde ser lido; a coleta começa do zero\n")

    if not sys.stdin.isatty():
        _erro(
            "este terminal não é interativo. Rode 'iniciar' num terminal de verdade "
            "ou copie examples/perfil.exemplo.yaml para data/processed/perfil.yaml "
            "e edite os campos à mão."
        )
        return 1

    try:
        perfil = coleta.entrevistar(
            perfil_inicial=inicial,
            localizar_publicos=_localizador_de_publicos(argumentos),
        )
    except (EOFError, KeyboardInterrupt):
        print("")
        _erro("coleta interrompida; nada foi gravado")
        return 1
    laudo = modelo.validar(perfil)

    if laudo.erros:
        print("")
        _erro("perfil não gravado; corrija e rode de novo:")
        for erro in laudo.erros:
            print(f"  - {erro}", file=sys.stderr)
        return 1

    # O visual é resolvido ANTES de gravar: a escolha fica registrada no perfil e
    # as próximas gerações lembram dela, sem precisar repetir --template.
    # Com --sem-gerar e nenhuma escolha ainda, não faz sentido abrir o menu: não
    # há README para gerar agora, então o padrão vale na próxima vez.
    template_id: str | None = None
    if not (argumentos.sem_gerar and not argumentos.template and not perfil.template):
        template_id = _resolver_template(argumentos, perfil)
        if template_id is None:
            return 1
        perfil.template = template_id

    try:
        modelo.salvar(perfil, caminho)
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return 1

    print(f"\nperfil gravado em {caminho}")
    print(f"completude: {laudo.completude}% dos campos usados no README")
    for aviso in laudo.avisos:
        print(f"aviso: {aviso}")

    if argumentos.sem_gerar:
        print("\npróximo passo: python perfil.py gerar")
        return 0

    # Aqui `template_id` nunca é None: o único caminho que o deixaria vazio é o
    # --sem-gerar, que já retornou acima.
    template_id = template_id or templates_visuais.padrao()

    # Incremental de propósito: cada rodada da coleta atualiza o README na hora.
    # Se a pessoa cadastrou um projeto, ela já sai vendo o resultado.
    try:
        _gerar_arquivos(
            perfil,
            Path(argumentos.saida),
            offline=argumentos.offline,
            template_id=template_id,
        )
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return 1
    except OSError as erro:
        _erro(f"não foi possível gravar a saída: {erro}")
        return 1

    print("\npróximo passo: python perfil.py preview (ver no navegador)")
    return 0


def comando_importar(argumentos: argparse.Namespace) -> int:
    """
    Baixa os dados públicos do GitHub, mescla com o perfil atual e regera o README.

    Sai: 0 quando importou (e gerou, se pedido); 1 em erro de rede, usuário
    inexistente ou perfil inválido.
    """
    caminho = Path(argumentos.perfil)
    existente: modelo.Perfil | None = None
    if caminho.exists():
        try:
            existente = modelo.carregar(caminho)
        except modelo.ErroPerfil as erro:
            _erro(str(erro))
            return 1

    usuario = argumentos.github or (existente.github if existente else "")
    if not usuario:
        _erro("informe o usuário do GitHub: python perfil.py importar --github seu-usuario")
        return 1

    try:
        perfil, dados = importacao.importar(
            usuario,
            perfil_existente=existente,
            token=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or None,
            max_projetos=argumentos.max,
        )
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return 1

    laudo = modelo.validar(perfil)
    if laudo.erros:
        _erro("perfil importado não passou na validação:")
        for erro in laudo.erros:
            print(f"  - {erro}", file=sys.stderr)
        return 1

    try:
        modelo.salvar(perfil, caminho)
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return 1

    print(f"perfil atualizado em {caminho}")
    print(
        f"importado do GitHub: {len(dados.get('repos') or [])} repositório(s) público(s) lido(s), "
        f"{len(perfil.projetos)} projeto(s) no perfil"
    )
    for aviso in laudo.avisos:
        print(f"aviso: {aviso}")

    if argumentos.sem_gerar:
        print("\npróximo passo: python perfil.py gerar")
        return 0

    template_id = _resolver_template(argumentos, perfil)
    if template_id is None:
        return 1
    try:
        _gerar_arquivos(
            perfil,
            Path(argumentos.saida),
            offline=argumentos.offline,
            template_id=template_id,
        )
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return 1
    except OSError as erro:
        _erro(f"não foi possível gravar a saída: {erro}")
        return 1

    print("\npróximo passo: python perfil.py preview (ver no navegador)")
    return 0


def comando_validar(argumentos: argparse.Namespace) -> int:
    """Confere o perfil e mostra o laudo; sai com 1 quando há erro bloqueante."""
    perfil = _carregar(argumentos)
    if perfil is None:
        return 1

    laudo = modelo.validar(perfil)
    print(modelo.resumo(perfil))
    print(f"completude: {laudo.completude}%")

    for aviso in laudo.avisos:
        print(f"aviso: {aviso}")
    for erro in laudo.erros:
        _erro(erro)

    if laudo.erros:
        return 1

    print("perfil válido: pode gerar o README")
    return 0


def comando_gerar(argumentos: argparse.Namespace) -> int:
    """Gera README.md e relatorio.json na pasta de saída."""
    perfil = _carregar(argumentos)
    if perfil is None:
        return 1

    digitais_antes = modelo.impressao_digital(perfil)

    template_id = _resolver_template(argumentos, perfil)
    if template_id is None:
        return 1
    try:
        _gerar_arquivos(
            perfil,
            Path(argumentos.saida),
            offline=argumentos.offline,
            template_id=template_id,
        )
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return 1
    except OSError as erro:
        _erro(f"não foi possível gravar a saída: {erro}")
        return 1

    # A geração pode descobrir a data de atualização pela segunda rota (feed de
    # commits). Guardar isso no perfil evita repetir as consultas na próxima vez.
    if modelo.impressao_digital(perfil) != digitais_antes:
        try:
            modelo.salvar(perfil, Path(argumentos.perfil))
            print(f"datas de atualização guardadas em {argumentos.perfil}")
        except modelo.ErroPerfil as erro:
            _erro(str(erro))
            return 1

    print("\npróximo passo: python perfil.py preview")
    return 0


def comando_preview(argumentos: argparse.Namespace) -> int:
    """
    Abre a pré-visualização local do README (servidor ou arquivo .html).

    Sai: 0 quando a página foi servida/gravada; 1 em erro de arquivo ou porta.
    """
    perfil = _carregar(argumentos)
    if perfil is None:
        return 1

    if argumentos.gerar:
        template_id = _resolver_template(argumentos, perfil)
        if template_id is None:
            return 1
        try:
            _gerar_arquivos(
            perfil,
            Path(argumentos.saida),
            offline=argumentos.offline,
            template_id=template_id,
        )
        except modelo.ErroPerfil as erro:
            _erro(str(erro))
            return 1

    arquivo = Path(argumentos.arquivo) if argumentos.arquivo else _caminho_readme(argumentos)

    try:
        if argumentos.html:
            destino = preview.salvar_html(
                arquivo,
                Path(argumentos.html),
                titulo=f"{perfil.nome} — README",
                repositorio=f"{perfil.github}/{perfil.github}",
                tema=argumentos.tema,
            )
            print(f"pré-visualização gravada em {destino}")
            print("abra o arquivo no navegador (dois cliques) para ver o resultado")
            return 0

        preview.servir(
            arquivo,
            porta=argumentos.porta,
            abrir_navegador=argumentos.abrir,
            titulo=f"{perfil.nome} — README",
            repositorio=f"{perfil.github}/{perfil.github}",
        )
    except modelo.ErroPerfil as erro:
        _erro(str(erro))
        return 1

    return 0


def comando_aprovar(argumentos: argparse.Namespace) -> int:
    """Registra a aprovação 1 (dados) ou 2 (texto final) para o conteúdo atual."""
    perfil = _carregar(argumentos)
    if perfil is None:
        return 1

    deu_certo, mensagem = aprovacao.conceder(
        argumentos.etapa,
        _caminho_readme(argumentos),
        perfil,
        Path(argumentos.registro),
    )
    print(mensagem)
    _mostrar_estado(perfil, argumentos)
    return 0 if deu_certo else 1


def comando_status(argumentos: argparse.Namespace) -> int:
    """Mostra o perfil, a completude e se a publicação está liberada."""
    perfil = _carregar(argumentos)
    if perfil is None:
        return 1

    print(modelo.resumo(perfil))
    laudo = modelo.validar(perfil)
    print(f"completude: {laudo.completude}%")
    if laudo.erros:
        for erro in laudo.erros:
            print(f"pendência: {erro}")
    _mostrar_estado(perfil, argumentos)
    print(f"README local: {_caminho_readme(argumentos)}")
    return 0


def comando_publicar(argumentos: argparse.Namespace) -> int:
    """
    Publica o README no repositório de perfil — só com duas aprovações válidas.

    Sai: 0 quando publicou; 1 quando bloqueado (sem as duas aprovações, sem token
    ou com o GitHub recusando).
    """
    perfil = _carregar(argumentos)
    if perfil is None:
        return 1

    if not argumentos.confirmar:
        _mostrar_estado(perfil, argumentos)
        _erro(
            "publicação cancelada: este comando grava no GitHub. "
            "Se é isso mesmo que você quer, repita com --confirmar."
        )
        return 1

    deu_certo, mensagem = aprovacao.publicar(
        _caminho_readme(argumentos),
        perfil,
        Path(argumentos.registro),
        repositorio=argumentos.repo,
        caminho_no_repo=argumentos.caminho,
        mensagem=argumentos.mensagem,
    )
    if not deu_certo:
        _erro(mensagem)
        return 1

    print(mensagem)
    return 0


# ---------------------------------------------------------------------------
# Analisador de argumentos
# ---------------------------------------------------------------------------
def _analisador() -> argparse.ArgumentParser:
    """Monta a interface de linha de comando, com um subcomando por etapa."""
    analisador = argparse.ArgumentParser(
        prog="perfil.py",
        description=(
            "PerfilAdaptativo — coleta os dados do perfil, gera o README, mostra o "
            "resultado localmente e só publica depois de duas aprovações."
        ),
        epilog="Comece por: python perfil.py iniciar",
    )

    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument(
        "--perfil",
        default=str(PERFIL_PADRAO),
        help=f"arquivo do perfil em YAML (padrão: {PERFIL_PADRAO})",
    )
    comum.add_argument(
        "--saida",
        default=str(SAIDA_PADRAO),
        help=f"pasta onde o README gerado é gravado (padrão: {SAIDA_PADRAO})",
    )
    comum.add_argument(
        "--registro",
        default=str(REGISTRO_PADRAO),
        help=f"arquivo de aprovações (padrão: {REGISTRO_PADRAO})",
    )

    def adicionar_template(parser: argparse.ArgumentParser) -> None:
        """Acrescenta --template com a lista de ids do catálogo na ajuda."""
        parser.add_argument(
            "--template",
            default="",
            choices=["", *templates_visuais.nomes()],
            help=(
                "visual do README (minimal, dark-terminal, animated). "
                "Sem o argumento, um terminal interativo mostra o menu e um script usa o padrão."
            ),
        )

    subcomandos = analisador.add_subparsers(dest="comando", required=True)

    iniciar = subcomandos.add_parser(
        "iniciar",
        parents=[comum],
        help="pergunta os dados do perfil (nunca aceita senha ou chave)",
    )
    iniciar.add_argument(
        "--offline",
        action="store_true",
        help="não consulta o GitHub: nem para ler os repositórios públicos, nem ao gerar",
    )
    iniciar.add_argument(
        "--sem-importar",
        action="store_true",
        help="não lê os repositórios públicos da conta; cadastra os projetos à mão",
    )
    iniciar.add_argument(
        "--max",
        type=int,
        default=importacao.MAX_PROJETOS_PADRAO,
        help=(
            "quantos repositórios públicos oferecer para inclusão "
            f"(padrão: {importacao.MAX_PROJETOS_PADRAO})"
        ),
    )
    iniciar.add_argument(
        "--sem-gerar",
        action="store_true",
        help="só grava o perfil, sem gerar o README agora",
    )
    adicionar_template(iniciar)
    iniciar.set_defaults(funcao=comando_iniciar)

    importar = subcomandos.add_parser(
        "importar",
        parents=[comum],
        help="baixa os dados públicos do seu perfil no GitHub e preenche o que falta",
    )
    importar.add_argument(
        "--github",
        default="",
        help="usuário do GitHub (padrão: o usuário já gravado no perfil)",
    )
    importar.add_argument(
        "--max",
        type=int,
        default=importacao.MAX_PROJETOS_PADRAO,
        help=f"quantos projetos trazer (padrão: {importacao.MAX_PROJETOS_PADRAO})",
    )
    importar.add_argument(
        "--offline",
        action="store_true",
        help="ao gerar o README no fim, não consulta a API do GitHub",
    )
    importar.add_argument(
        "--sem-gerar",
        action="store_true",
        help="só grava o perfil, sem gerar o README agora",
    )
    adicionar_template(importar)
    importar.set_defaults(funcao=comando_importar)

    validar = subcomandos.add_parser("validar", parents=[comum], help="confere o perfil")
    validar.set_defaults(funcao=comando_validar)

    gerar = subcomandos.add_parser("gerar", parents=[comum], help="gera o README local")
    gerar.add_argument(
        "--offline",
        action="store_true",
        help="não consulta a API do GitHub (funciona sem rede e sem token)",
    )
    adicionar_template(gerar)
    gerar.set_defaults(funcao=comando_gerar)

    ver = subcomandos.add_parser(
        "preview",
        parents=[comum],
        help="mostra o README renderizado como no GitHub, na sua máquina",
    )
    ver.add_argument("--arquivo", default="", help="caminho de outro README para visualizar")
    ver.add_argument(
        "--porta",
        type=int,
        default=PORTA_PADRAO,
        help=f"porta do servidor local (padrão: {PORTA_PADRAO})",
    )
    ver.add_argument("--abrir", action="store_true", help="abre o navegador no endereço")
    ver.add_argument(
        "--gerar",
        action="store_true",
        help="gera o README antes de visualizar",
    )
    ver.add_argument(
        "--offline",
        action="store_true",
        help="com --gerar: não consulta a API do GitHub",
    )
    ver.add_argument(
        "--html",
        default="",
        help="grava um arquivo .html autônomo em vez de subir o servidor",
    )
    ver.add_argument(
        "--tema",
        default="",
        choices=["", "claro", "escuro"],
        help=(
            "fixa o tema da pré-visualização. Sem o argumento, a página segue o "
            "sistema operacional e o botão de um clique. No servidor também aceita "
            "?tema=claro ou ?tema=escuro na URL"
        ),
    )
    adicionar_template(ver)
    ver.set_defaults(funcao=comando_preview)

    aprovar = subcomandos.add_parser(
        "aprovar",
        parents=[comum],
        help="registra a aprovação 1 (dados) ou 2 (texto final)",
    )
    aprovar.add_argument("--etapa", type=int, choices=(1, 2), required=True, help="1 ou 2")
    aprovar.set_defaults(funcao=comando_aprovar)

    status = subcomandos.add_parser("status", parents=[comum], help="resume perfil e aprovações")
    status.set_defaults(funcao=comando_status)

    publicar = subcomandos.add_parser(
        "publicar",
        parents=[comum],
        help="envia o README ao GitHub (exige duas aprovações válidas)",
    )
    publicar.add_argument(
        "--repo",
        default="",
        help="repositório de destino no formato usuario/repositorio "
        "(padrão: usuario/usuario, o repositório de perfil)",
    )
    publicar.add_argument("--caminho", default="README.md", help="caminho do arquivo no repositório")
    publicar.add_argument("--mensagem", default="", help="mensagem do commit")
    publicar.add_argument(
        "--confirmar",
        action="store_true",
        help="confirma que você quer gravar no GitHub agora",
    )
    publicar.set_defaults(funcao=comando_publicar)

    return analisador


def main(argv: list[str] | None = None) -> int:
    """
    Entra: argumentos de linha de comando (ou None, para ler do sys.argv).
    Sai: 0 em sucesso, 1 em erro de dado/ambiente.
    """
    _ajustar_saida_do_console()
    argumentos = _analisador().parse_args(argv)
    return argumentos.funcao(argumentos)


if __name__ == "__main__":
    sys.exit(main())
