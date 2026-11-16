"""
coleta.py — a entrevista que junta os dados do novo usuário, uma pergunta por vez.

O problema que este arquivo resolve: o projeto nasceu com os dados de uma pessoa
escritos à mão num YAML. Para servir a qualquer pessoa, alguém precisa perguntar
— e perguntar bem, explicando termo técnico ("o que este projeto prova?"),
aceitando deixa em branco e recusando, na hora, o que parecer senha.

A analogia é a ficha de matrícula preenchida no balcão: quem atende faz uma
pergunta, confere a resposta e só então passa para a próxima linha. Nada é
adivinhado, nada é obrigado além do essencial (nome, usuário do GitHub e pelo
menos um projeto).

O arquivo é testável porque a função de perguntar é injetável: nos testes entra
uma função que devolve respostas prontas, no terminal entra a leitura real.
"""

from __future__ import annotations

from typing import Callable

from . import modelo, seguranca

# Limite de tentativas por pergunta: erro de digitação acontece, insistência
# eterna não ajuda ninguém. Depois de três, a pergunta fica em branco e o laudo
# de validação mostra o que faltou.
LIMITE_TENTATIVAS = 3

FRASE_DE_SEGURANCA = (
    "Este programa não pede senha, token nem chave de API — e recusa qualquer resposta "
    "com essa cara. Chave, quando existir, fica na variável de ambiente do seu usuário."
)

Perguntar = Callable[[str], str]
Escrever = Callable[[str], None]
LocalizarPublicos = Callable[[str], list[modelo.Projeto]]

TEXTO_SEM_DESCRICAO = "sem descrição no GitHub"


def _perguntar_texto(
    perguntar: Perguntar,
    escrever: Escrever,
    rotulo: str,
    padrao: str = "",
    obrigatorio: bool = False,
) -> str:
    """
    Faz uma pergunta, valida a resposta e repete quando ela não serve.

    Entra: função de leitura, função de escrita, texto da pergunta, valor atual
           (Enter mantém, como num formulário web) e se a resposta é obrigatória.
    Sai: resposta limpa; "" quando a pessoa deixou em branco (ou desistiu).

    Segredo é recusado aqui, no ato: se a pessoa colar uma chave, a resposta não
    entra no perfil, nem por engano.
    """
    sufixo = f" [{padrao}]" if padrao else ""
    for _ in range(LIMITE_TENTATIVAS):
        resposta = perguntar(f"{rotulo}{sufixo}: ").strip()

        if not resposta:
            if padrao:
                return padrao
            if obrigatorio:
                escrever("  (obrigatório — sem esta resposta não dá para gerar o README)")
                continue
            return ""

        recusa = seguranca.recusar_se_necessario(resposta, rotulo)
        if recusa:
            escrever(f"  recusado: {recusa}. Tente de novo.")
            continue

        return resposta

    escrever(f"  sem resposta válida para '{rotulo}'; seguindo em frente.")
    return ""


def _perguntar_sim_nao(perguntar: Perguntar, escrever: Escrever, rotulo: str, padrao: bool = False) -> bool:
    """
    Converte a resposta em sim/não, aceitando s, sim, y, yes, n e não.

    Entra: função de leitura/escrita, pergunta e valor padrão.
    Sai: True para sim, False para não.

    Sem resposta: vale o padrão. Com resposta estranha: avisa e vale o padrão —
    adivinhar "talvez" como "sim" seria inventar dado, o que o projeto proíbe.
    """
    marca = "S/n" if padrao else "s/N"
    resposta = perguntar(f"{rotulo} ({marca}): ").strip().casefold()

    if not resposta:
        return padrao
    if resposta in {"s", "sim", "y", "yes", "1"}:
        return True
    if resposta in {"n", "nao", "não", "no", "0"}:
        return False

    escrever(f"  resposta não reconhecida; usando o padrão ({'sim' if padrao else 'não'}).")
    return padrao


def _perguntar_links(perguntar: Perguntar, escrever: Escrever, atuais: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Coleta links extras (blog, LinkedIn, e-mail público) até a linha em branco.

    Entra: funções de leitura/escrita e os links que já existiam no perfil.
    Sai: lista de {"rotulo", "url"}.

    Aceita "Rótulo | endereço" ou só o endereço. O canal é livre porque a vida de
    cada pessoa é diferente: quem não tem blog tem LinkedIn, quem não tem os dois
    deixa em branco.
    """
    escrever("Links extras (Enter em branco encerra). Formato: Rótulo | endereço")
    links = [dict(link) for link in atuais]

    for _ in range(10):
        resposta = perguntar("  link: ").strip()
        if not resposta:
            break

        recusa = seguranca.recusar_se_necessario(resposta, "link")
        if recusa:
            escrever(f"  recusado: {recusa}.")
            continue

        if "|" in resposta:
            rotulo, _, endereco = resposta.partition("|")
            bruto = {"rotulo": rotulo.strip(), "url": endereco.strip()}
        else:
            bruto = resposta

        link = modelo.normalizar_link(bruto)
        if link is None:
            escrever("  link vazio; ignorado.")
            continue

        links.append(link)
        escrever(f"  {len(links)} link(s) registrado(s).")

    return links


def _perguntar_projeto(
    perguntar: Perguntar,
    escrever: Escrever,
    indice: int,
) -> modelo.Projeto | None:
    """
    Faz o bloco de perguntas de UM projeto.

    Entra: funções de leitura/escrita e o número do projeto (1, 2, 3...).
    Sai: Projeto preenchido, ou None quando a pessoa deixa o repositório em branco.

    A ordem segue o que é mais fácil de responder: primeiro o nome que a pessoa
    já conhece, depois o julgamento ("o que ele prova?"), depois as tags.
    """
    escrever(f"\nProjeto {indice}")
    repo_bruto = _perguntar_texto(perguntar, escrever, "  Repositório (ou endereço do projeto)")
    if not repo_bruto:
        return None

    repo, url = modelo.normalizar_repo(repo_bruto)
    destaque = _perguntar_sim_nao(perguntar, escrever, "  É destaque no perfil?", padrao=indice == 1)
    prova = _perguntar_texto(
        perguntar,
        escrever,
        "  O que este projeto prova? (uma frase, ex.: 'ETL de indicadores com API e painel')",
    )
    stack = modelo.normalizar_stack(
        _perguntar_texto(perguntar, escrever, "  Tecnologias (separe por vírgula)")
    )
    status = _perguntar_texto(
        perguntar,
        escrever,
        "  Estágio do projeto (ex.: publicado, MVP, rascunho — Enter se não declarar)",
    )

    # Só pergunta o endereço quando o projeto não é um repositório do próprio
    # usuário: pedir de novo o que já foi respondido cansa quem preenche.
    if not url and "/" not in repo_bruto:
        endereco = _perguntar_texto(
            perguntar,
            escrever,
            "  Endereço do projeto (Enter se for repositório na sua conta do GitHub)",
        )
        if endereco:
            url = endereco

    return modelo.Projeto(repo=repo, destaque=destaque, prova=prova, stack=stack, status=status, url=url)


def _listar_para_escolha(projetos: list[modelo.Projeto], escrever: Escrever) -> None:
    """
    Mostra os repositórios encontrados em lista numerada, para a pessoa escolher.

    Entra: projetos achados na conta e a função de escrita.
    Sai: nada (só imprime).

    Nome, linguagem e um resumo curto bastam para reconhecer o projeto. A
    descrição é cortada em 60 caracteres porque o terminal não é lugar de
    parágrafo — e continua sendo evidência do que existe, não resumo inventado.
    """
    for indice, projeto in enumerate(projetos, start=1):
        linguagem = " · ".join(projeto.stack) or "linguagem não declarada"
        resumo = projeto.prova or TEXTO_SEM_DESCRICAO
        if len(resumo) > 60:
            resumo = resumo[:59] + "…"
        escrever(f"  [{indice:>2}] {projeto.repo} — {linguagem} — {resumo}")


def _escolher_por_numero(projetos: list[modelo.Projeto], resposta: str) -> list[modelo.Projeto]:
    """
    Traduz "1,3,4" na lista de projetos correspondentes.

    Entra: projetos oferecidos e o texto digitado.
    Sai: lista escolhida (vazia quando nada serve).

    Número fora da faixa e palavra solta são ignorados em vez de derrubar a
    coleta: erro de digitação acontece, e repetir a pergunta inteira por causa
    de um "12" a mais é pior. Número repetido também não duplica projeto.
    """
    escolhidos: list[modelo.Projeto] = []
    vistos: set[int] = set()

    for pedaco in resposta.replace(";", ",").replace(" ", ",").split(","):
        pedaco = pedaco.strip()
        if not pedaco.isdigit():
            continue
        indice = int(pedaco)
        if indice in vistos or not 1 <= indice <= len(projetos):
            continue
        vistos.add(indice)
        escolhidos.append(projetos[indice - 1])

    return escolhidos


def _incluir_publicos(
    localizar: LocalizarPublicos,
    perguntar: Perguntar,
    escrever: Escrever,
    usuario: str,
    atuais: list[modelo.Projeto],
) -> list[modelo.Projeto]:
    """
    Busca os repositórios públicos do usuário e deixa a pessoa confirmar o que entra.

    Entra: função de busca, leitura, escrita, usuário do GitHub e os projetos que
           já estavam no perfil.
    Sai: lista de projetos atualizada.

    Por que perguntar mesmo já tendo buscado: o GitHub tem repositório que a
    pessoa não quer no portfólio (teste, curso incompleto, experimento). Buscar
    sozinho poupa digitação; confirmar evita publicar o que não é vitrine — é o
    mesmo cuidado de uma vitrine de loja, onde nem tudo do estoque vai para a
    janela.

    Nada aqui é obrigatório: sem rede, sem repositório público ou resposta "não",
    a coleta segue exatamente como antes.
    """
    escrever(f"\nBuscando os repositórios públicos de {usuario} no GitHub...")

    try:
        encontrados = localizar(usuario)
    except Exception as erro:  # noqa: BLE001 - falha de rede não pode matar a entrevista
        # Qualquer problema (conta inexistente, limite de consultas, rede fora)
        # vira aviso: a pessoa continua e cadastra à mão se quiser.
        escrever(f"  aviso: não consegui ler a conta ({erro})")
        escrever("  você pode cadastrar os projetos manualmente logo abaixo.")
        return list(atuais)

    if not encontrados:
        escrever("  nenhum repositório público encontrado; siga para a inclusão manual.")
        return list(atuais)

    conhecidos = {projeto.repo.casefold() for projeto in atuais}
    novos = [projeto for projeto in encontrados if projeto.repo.casefold() not in conhecidos]

    sem_segredo: list[modelo.Projeto] = []
    for projeto in novos:
        if seguranca.tem_segredo(projeto.prova) or seguranca.tem_segredo(projeto.url):
            # Descrição pública com cara de chave não entra: o mesmo critério da
            # coleta manual vale para dado que veio da API.
            escrever(f"  aviso: {projeto.repo} descartado (texto com cara de segredo)")
            continue
        sem_segredo.append(projeto)
    novos = sem_segredo

    if not novos:
        escrever("  todos os repositórios públicos já estão no perfil.")
        return list(atuais)

    escrever(f"  encontrei {len(novos)} repositório(s) público(s):")
    _listar_para_escolha(novos, escrever)

    if _perguntar_sim_nao(perguntar, escrever, f"  Incluir os {len(novos)} no perfil?", padrao=True):
        escrever(f"  {len(novos)} projeto(s) incluído(s) a partir do GitHub.")
        return list(atuais) + novos

    resposta = perguntar("  Quais? números separados por vírgula (Enter não inclui nenhum): ").strip()
    escolhidos = _escolher_por_numero(novos, resposta) if resposta else []

    if not escolhidos:
        escrever("  nenhum repositório incluído; pode cadastrar à mão agora.")
        return list(atuais)

    escrever(f"  {len(escolhidos)} projeto(s) incluído(s) a partir do GitHub.")
    return list(atuais) + escolhidos


def entrevistar(
    perfil_inicial: modelo.Perfil | None = None,
    perguntar: Perguntar | None = None,
    escrever: Escrever | None = None,
    localizar_publicos: LocalizarPublicos | None = None,
) -> modelo.Perfil:
    """
    Conduz a entrevista completa e devolve o perfil preenchido (ainda sem validar).

    Entra: perfil existente (para editar sem perder dados), função de leitura,
           função de escrita e a função que busca os repositórios públicos —
           as três últimas opcionais.
    Sai: Perfil normalizado, pronto para `modelo.validar` e `modelo.salvar`.

    Valor existente aparece entre colchetes e Enter mantém: quem preencheu ontem
    não precisa digitar tudo de novo só porque quer acrescentar um projeto.

    Com `localizar_publicos`, a lista de projetos nasce preenchida com o que já
    é público na conta do GitHub — o dado existe, então pedir digitação seria
    trabalho inútil. Sem ela (modo --offline, por exemplo), a coleta pergunta
    tudo à mão, como antes.
    """
    perguntar = perguntar or input
    escrever = escrever or print
    inicial = perfil_inicial or modelo.Perfil(nome="", github="")

    escrever("PerfilAdaptativo — coleta de dados do perfil")
    escrever(FRASE_DE_SEGURANCA)
    escrever("")

    nome = _perguntar_texto(perguntar, escrever, "Seu nome (como aparece no README)", inicial.nome, True)
    github = modelo.normalizar_usuario(
        _perguntar_texto(perguntar, escrever, "Usuário do GitHub (sem @)", inicial.github, True)
    )
    bio = _perguntar_texto(
        perguntar,
        escrever,
        "Bio em uma linha (ex.: 'Python, dados e automação')",
        inicial.bio,
    )
    local = _perguntar_texto(perguntar, escrever, "Cidade/UF", inicial.local)
    site = _perguntar_texto(perguntar, escrever, "Site ou blog (Enter se não tiver)", inicial.site)

    links = _perguntar_links(perguntar, escrever, inicial.links)

    # Conquista é declaração, não medição: o programa não sabe de certificação,
    # prêmio ou formação. Perguntar uma vez é o caminho mais curto; a seção só
    # aparece no README se houver algo aqui.
    conquistas_texto = _perguntar_texto(
        perguntar,
        escrever,
        "Conquistas, certificações ou prêmios (separe por ; — Enter se não tiver)",
        "; ".join(inicial.conquistas),
    )
    conquistas = modelo._lista_de_textos(conquistas_texto)

    projetos: list[modelo.Projeto] = list(inicial.projetos)
    if localizar_publicos and github:
        projetos = _incluir_publicos(localizar_publicos, perguntar, escrever, github, projetos)

    if projetos:
        escrever(
            f"\nAgora os projetos que não estão no GitHub (Enter no repositório encerra). "
            f"Você já tem {len(projetos)}:"
        )
    else:
        escrever("\nProjetos: um por vez. Enter no repositório encerra a lista.")

    while True:
        projeto = _perguntar_projeto(perguntar, escrever, len(projetos) + 1)
        if projeto is None:
            break
        projetos.append(projeto)
        escrever(f"  {len(projetos)} projeto(s) cadastrado(s).")

    return modelo.Perfil(
        nome=nome,
        github=github,
        bio=bio,
        local=local,
        site=site,
        links=links,
        conquistas=conquistas,
        projetos=projetos,
    )
