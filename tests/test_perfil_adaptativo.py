"""
Testes do fluxo adaptativo: coleta, modelo, geração, pré-visualização e aprovação.

Regra destes testes: nenhum toca a rede. Onde a API do GitHub seria chamada
(consulta de metadados e upload), entra um dublê que finge a resposta — o mesmo
princípio de `tests/test_generate.py`, para o teste rodar igual com internet
desligada e no GitHub Actions.

O que se procura provar aqui, em ordem de importância:
1. senha, token e chave nunca são gravados, nem por acidente de digitação;
2. o README não inventa dado que o perfil não tem;
3. a pré-visualização local renderiza de verdade (tabela, código, página HTML);
4. não existe caminho de publicação sem as duas aprovações do mesmo conteúdo.
"""

from __future__ import annotations

import base64
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

# Garante que os módulos do projeto sejam encontráveis quando o pytest roda da raiz.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import perfil  # noqa: E402  (import depois do ajuste de sys.path, de propósito)
from perfil_adaptativo import (  # noqa: E402
    analise,
    aprovacao,
    coleta,
    estatisticas,
    graficos,
    importacao,
    modelo,
    preview,
)

RAIZ = Path(__file__).resolve().parents[1]
PERFIL_EXEMPLO = RAIZ / "examples" / "perfil.exemplo.yaml"
CURADORIA_ANTIGA = RAIZ / "examples" / "projects.exemplo.yaml"

# Segredos falsos montados por concatenação: assim o arquivo de teste não contém
# nenhuma sequência que pareça uma chave real para o gancho de pré-commit.
SEGREDO_GITHUB = "ghp_" + "A" * 36
SEGREDO_GENERICO = "sk-" + "b" * 32


class RespostaFalsa:
    """Imita o mínimo de uma resposta `requests`: status, JSON e conteúdo."""

    def __init__(self, dados=None, status_code: int = 200) -> None:
        self._dados = dados if dados is not None else {}
        self.status_code = status_code

    def json(self):
        """Devolve o corpo já "decodificado"."""
        return self._dados


def perfil_de_teste() -> modelo.Perfil:
    """Perfil mínimo válido, usado nos testes de aprovação e publicação."""
    return modelo.de_dicionario(
        {
            "nome": "Ana Exemplo",
            "github": "ana-exemplo",
            "bio": "Python e dados",
            "projetos": [
                {"repo": "projeto-a", "destaque": True, "prova": "ETL", "stack": ["Python"], "status": "publicado"}
            ],
        }
    )


def publicos_de_teste() -> list[modelo.Projeto]:
    """Dois repositórios públicos como a API devolveria, já convertidos em projeto."""
    return [
        modelo.Projeto(
            repo="projeto-a",
            prova="ETL de indicadores",
            stack=["Python"],
            url="https://github.com/ana-exemplo/projeto-a",
        ),
        modelo.Projeto(
            repo="projeto-b",
            prova="",
            stack=[],
            url="https://github.com/ana-exemplo/projeto-b",
        ),
    ]


@pytest.fixture
def registro(tmp_path) -> Path:
    """Caminho de registro de aprovações dentro da pasta temporária do teste."""
    return tmp_path / "aprovacoes.json"


@pytest.fixture
def readme(tmp_path) -> Path:
    """README já "gerado" (texto qualquer) para os testes de aprovação."""
    caminho = tmp_path / "README.md"
    caminho.write_text("# Ana Exemplo\n\nREADME de teste\n", encoding="utf-8")
    return caminho


# ---------------------------------------------------------------------------
# Segurança: segredo nunca entra no perfil
# ---------------------------------------------------------------------------
def test_validacao_recusa_segredo_em_qualquer_campo():
    """Token colado na bio é apontado como erro, sem repetir o valor na mensagem."""
    perfil_suspeito = modelo.de_dicionario(
        {
            "nome": "Ana",
            "github": "ana-exemplo",
            "bio": SEGREDO_GITHUB,
            "projetos": [{"repo": "p", "destaque": True, "prova": "x", "stack": ["Python"], "status": "MVP"}],
        }
    )

    laudo = modelo.validar(perfil_suspeito)

    assert not laudo.valido
    assert any("token do GitHub" in erro for erro in laudo.erros)
    assert all(SEGREDO_GITHUB not in erro for erro in laudo.erros)


def test_salvar_recusa_segredo_e_nao_cria_arquivo(tmp_path):
    """`salvar` é a última barreira: sem passar nela, nada vai para o disco."""
    perfil_suspeito = perfil_de_teste()
    perfil_suspeito.bio = SEGREDO_GENERICO
    destino = tmp_path / "perfil.yaml"

    with pytest.raises(modelo.ErroPerfil):
        modelo.salvar(perfil_suspeito, destino)

    assert not destino.exists()


def test_coleta_recusa_segredo_e_segue_sem_guardar():
    """Na entrevista, a resposta com cara de chave é recusada três vezes e descartada."""
    respostas = iter(
        [
            "Ana Exemplo",  # nome
            "ana-exemplo",  # github
            SEGREDO_GITHUB,
            SEGREDO_GITHUB,
            SEGREDO_GITHUB,  # bio: recusada nas três tentativas
            "",  # local
            "",  # site
            "",  # encerra links
            "",  # conquistas
            "",  # encerra projetos
        ]
    )
    escritos: list[str] = []

    resultado = coleta.entrevistar(
        perguntar=lambda _pergunta: next(respostas),
        escrever=escritos.append,
    )

    assert resultado.bio == ""
    assert SEGREDO_GITHUB not in json.dumps(resultado.para_dicionario())
    assert any("recusado" in linha for linha in escritos)


# ---------------------------------------------------------------------------
# Modelo: formato novo e formato antigo convivem
# ---------------------------------------------------------------------------
def test_modelo_aceita_formato_novo():
    """O YAML em pt-BR com bloco de links vira o formulário oficial."""
    perfil_lido = modelo.carregar(PERFIL_EXEMPLO)

    assert perfil_lido.nome == "Ana Exemplo"
    assert perfil_lido.github == "ana-exemplo"
    assert len(perfil_lido.projetos) == 3
    assert [link["rotulo"] for link in perfil_lido.links] == ["LinkedIn", "Blog"]
    assert perfil_lido.projetos[0].stack == ["Python", "ETL", "SQLite"]


def test_modelo_aceita_curadoria_antiga():
    """`config/projects.yaml` (chaves em inglês) continua legível: nada se perde."""
    perfil_lido = modelo.carregar(CURADORIA_ANTIGA)

    assert perfil_lido.github == "ana-exemplo"
    assert len(perfil_lido.projetos) == 3
    assert perfil_lido.projetos[0].destaque is True
    assert perfil_lido.projetos[0].prova.startswith("Pipeline que baixa indicadores")


def test_normalizar_stack_remove_repeticao_e_espaco():
    """'Python, sql , SQL' é a mesma stack de ['Python', 'sql']."""
    assert modelo.normalizar_stack("Python, sql , SQL") == ["Python", "sql"]
    assert modelo.normalizar_stack(["Python", "PYTHON", " "]) == ["Python"]


def test_normalizar_repo_separa_nome_e_endereco():
    """Nome, dono/nome e URL inteira levam ao mesmo par (nome, endereço)."""
    assert modelo.normalizar_repo("meu-projeto") == ("meu-projeto", "")
    assert modelo.normalizar_repo("fulano/meu-projeto") == (
        "meu-projeto",
        "https://github.com/fulano/meu-projeto",
    )
    assert modelo.normalizar_repo("https://github.com/fulano/meu-projeto") == (
        "meu-projeto",
        "https://github.com/fulano/meu-projeto",
    )


def test_validacao_aponta_o_que_falta_e_mede_completude():
    """Perfil sem nome e sem GitHub: erro em cada um, completude baixa, projeto em falta é aviso."""
    laudo = modelo.validar(modelo.Perfil(nome="", github=""))

    assert not laudo.valido
    assert len(laudo.erros) == 2
    assert 0.0 <= laudo.completude < 100.0
    # Zero projeto não é erro: o README começa enxuto e cresce depois.
    assert any("sem projetos" in aviso for aviso in laudo.avisos)


def test_validacao_remove_repositorio_repetido_com_aviso():
    """Repetir o mesmo repositório duplicaria linha na tabela; o aviso explica."""
    perfil_repetido = modelo.de_dicionario(
        {
            "nome": "Ana",
            "github": "ana-exemplo",
            "projetos": [
                {"repo": "igual", "destaque": True, "prova": "a", "stack": ["Python"], "status": "MVP"},
                {"repo": "IGUAL", "destaque": False, "prova": "b", "stack": ["SQL"], "status": "MVP"},
            ],
        }
    )

    laudo = modelo.validar(perfil_repetido)

    assert laudo.valido
    assert len(perfil_repetido.projetos) == 1
    assert any("repetido" in aviso for aviso in laudo.avisos)


# ---------------------------------------------------------------------------
# Geração do README e relatório
# ---------------------------------------------------------------------------
def test_gerar_readme_e_relatorio_sem_inventar_dado(tmp_path):
    """Modo offline gera README + relatório e diz "não verificado" onde não há prova."""
    codigo = perfil.main(
        ["gerar", "--perfil", str(PERFIL_EXEMPLO), "--saida", str(tmp_path), "--offline"]
    )

    assert codigo == 0
    texto = (tmp_path / "README.md").read_text(encoding="utf-8")
    relatorio = json.loads((tmp_path / "relatorio.json").read_text(encoding="utf-8"))

    assert "# Ana Exemplo" in texto
    assert "| exemplo-etl |" in texto
    assert relatorio["numeros"]["projetos"] == 3
    assert relatorio["numeros"]["destaques"] == 2
    assert relatorio["modo"] == "offline"
    # Sem consulta à API, link e data não podem ser afirmados — e o README não
    # escreve marcador nenhum: a célula fica vazia.
    assert "não verificado" not in texto
    assert "não declarado" not in texto
    assert "## Estatísticas" in texto
    assert "## Conquistas" in texto


def test_gerar_recusa_perfil_invalido(tmp_path):
    """Perfil sem usuário do GitHub não gera README e o comando sai com 1."""
    caminho = tmp_path / "perfil.yaml"
    caminho.write_text("nome: Ana\n", encoding="utf-8")

    codigo = perfil.main(["gerar", "--perfil", str(caminho), "--saida", str(tmp_path / "saida")])

    assert codigo == 1
    assert not (tmp_path / "saida" / "README.md").exists()


def test_analise_avisa_projeto_sem_prova():
    """Projeto sem 'prova' gera aviso no relatório, não erro, e o README segue."""
    perfil_simples = perfil_de_teste()
    perfil_simples.projetos[0].prova = ""

    preparacao = analise.preparar(perfil_simples, offline=True)

    assert preparacao.laudo.valido
    assert preparacao.relatorio["numeros"]["projetos_sem_prova"] == 1
    assert any("prova" in aviso for aviso in preparacao.laudo.avisos)


# ---------------------------------------------------------------------------
# Pré-visualização local
# ---------------------------------------------------------------------------
def test_preview_renderiza_tabela_e_bloco_de_codigo():
    """O HTML da pré-visualização precisa trazer tabela (com rolagem) e código."""
    pagina = preview.renderizar_html(
        "# Título\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\npython perfil.py\n```\n",
        titulo="README.md",
    )

    assert '<div class="tabela-rolavel"><table>' in pagina
    assert "</table></div>" in pagina
    assert "<code>python perfil.py" in pagina
    assert "<title>README.md</title>" in pagina
    assert "/raw" in pagina


def test_preview_grava_html_autonomo(tmp_path, readme):
    """O .html gerado abre sem servidor: CSS embutido e conteúdo convertido."""
    destino = preview.salvar_html(readme, tmp_path / "preview.html", titulo="Ana — README")
    conteudo = destino.read_text(encoding="utf-8")

    assert destino.exists()
    assert "<style>" in conteudo
    assert "Ana Exemplo" in conteudo


def test_html_autonomo_pode_fixar_o_tema(tmp_path, readme):
    """Exportar com tema fixo é o que permite abrir o arquivo já em claro ou escuro."""
    destino = preview.salvar_html(readme, tmp_path / "claro.html", tema="claro")
    conteudo = destino.read_text(encoding="utf-8")

    assert '<html lang="pt-BR" data-tema="claro">' in conteudo


def test_preview_servidor_responde_na_maquina_local(tmp_path):
    """Sobe o servidor, pede a página e o Markdown cru, e desliga."""
    arquivo = tmp_path / "README.md"
    arquivo.write_text("# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")

    servidor = preview.criar_servidor(arquivo, porta=0)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()

    try:
        host, porta = servidor.server_address[0], servidor.server_address[1]
        assert host == "127.0.0.1"

        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=5) as resposta:
            status_pagina = resposta.status
            pagina = resposta.read().decode("utf-8")

        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/raw", timeout=5) as resposta:
            cru = resposta.read().decode("utf-8")
    finally:
        servidor.shutdown()
        servidor.server_close()
        thread.join(timeout=5)

    assert status_pagina == 200
    assert "<table>" in pagina
    assert cru.startswith("# T")


def test_preview_sem_readme_mostra_instrucao(tmp_path):
    """Arquivo ausente devolve 404 com instrução, em vez de erro feio."""
    servidor = preview.criar_servidor(tmp_path / "nao-existe.md", porta=0)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()

    try:
        porta = servidor.server_address[1]
        with pytest.raises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=5)
        corpo = erro.value.read().decode("utf-8")
    finally:
        servidor.shutdown()
        servidor.server_close()
        thread.join(timeout=5)

    assert erro.value.code == 404
    assert "perfil.py gerar" in corpo


# ---------------------------------------------------------------------------
# Estatísticas e conquistas
# ---------------------------------------------------------------------------
def test_estatisticas_so_mostram_o_que_tem_base():
    """Número sai do perfil: com dois projetos, a lista reflete exatamente isso."""
    perfil_dois = modelo.de_dicionario(
        {
            "nome": "Ana",
            "github": "ana-exemplo",
            "projetos": [
                {"repo": "a", "destaque": True, "prova": "ETL", "stack": ["Python"], "estrelas": 3},
                {"repo": "b", "destaque": False, "prova": "", "stack": ["Python", "SQL"]},
            ],
        }
    )
    preparacao = analise.preparar(perfil_dois, offline=True)

    numeros = estatisticas.numeros(perfil_dois, preparacao)
    por_rotulo = {item["rotulo"]: item["valor"] for item in numeros}

    assert por_rotulo["Projetos no portfólio"] == "2"
    assert por_rotulo["Em destaque"] == "1 de 2"
    assert por_rotulo["Tecnologias distintas"] == "2"
    assert por_rotulo["Projetos com descrição"] == "1 de 2"
    assert por_rotulo["Estrelas recebidas"] == "3"


def test_estatisticas_sem_projeto_ficam_vazias():
    """Perfil sem projeto não inventa seção de estatística."""
    perfil_vazio = modelo.Perfil(nome="Ana", github="ana-exemplo")
    preparacao = analise.preparar(perfil_vazio, offline=True)

    assert estatisticas.numeros(perfil_vazio, preparacao) == []


def test_conquista_declarada_aparece_antes_das_automaticas():
    """O que a pessoa declarou vem primeiro; os marcos medidos vêm depois."""
    perfil_conquistas = modelo.de_dicionario(
        {
            "nome": "Ana",
            "github": "ana-exemplo",
            "conquistas": ["Certificação em Análise de Dados — SENAI"],
            "projetos": [
                {"repo": "a", "destaque": True, "prova": "ETL", "stack": ["Python"]},
            ],
        }
    )
    preparacao = analise.preparar(perfil_conquistas, offline=True)
    lista = estatisticas.conquistas(perfil_conquistas, preparacao)

    assert lista[0]["titulo"] == "Certificação em Análise de Dados — SENAI"
    assert lista[0]["detalhe"] == "declarada no perfil"
    assert any(item["titulo"] == "Primeiro projeto no portfólio" for item in lista)


def test_marco_so_aparece_quando_atingido_e_vem_so_o_maior():
    """Com 12 projetos aparece só o marco de dez — repetir 1, 3, 5 e 10 é enchimento."""
    perfil_doze = modelo.Perfil(
        nome="Ana",
        github="ana-exemplo",
        projetos=[
            modelo.Projeto(repo=f"p{indice}", destaque=indice == 0, prova="ETL", stack=["Python"])
            for indice in range(12)
        ],
    )
    preparacao = analise.preparar(perfil_doze, offline=True)
    titulos = [item["titulo"] for item in estatisticas.conquistas(perfil_doze, preparacao)]

    assert "Dez projetos no portfólio" in titulos
    assert "Primeiro projeto no portfólio" not in titulos
    assert "Cinco projetos no portfólio" not in titulos


def test_readme_omite_campos_sem_dado(tmp_path):
    """Projeto sem prova, status ou stack gera linha sem marcador e sem invenção."""
    caminho = tmp_path / "perfil.yaml"
    modelo.salvar(
        modelo.Perfil(
            nome="Ana Exemplo",
            github="ana-exemplo",
            projetos=[modelo.Projeto(repo="so-o-nome", destaque=True)],
        ),
        caminho,
    )

    assert perfil.main(
        ["gerar", "--perfil", str(caminho), "--saida", str(tmp_path), "--offline"]
    ) == 0
    texto = (tmp_path / "README.md").read_text(encoding="utf-8")

    assert "so-o-nome" in texto
    assert "não declarado" not in texto
    assert "não verificado" not in texto


def test_readme_mostra_conquistas_e_estatisticas_do_perfil(tmp_path):
    """As duas seções nascem dos dados: estatística medida e conquista declarada."""
    caminho = tmp_path / "perfil.yaml"
    modelo.salvar(
        modelo.Perfil(
            nome="Ana Exemplo",
            github="ana-exemplo",
            conquistas=["Prêmio de inovação interna"],
            projetos=[
                modelo.Projeto(
                    repo="projeto-a",
                    destaque=True,
                    prova="ETL",
                    stack=["Python"],
                    status="publicado",
                    atualizado_em="2026-10-26T12:06:19Z",
                )
            ],
        ),
        caminho,
    )

    assert perfil.main(
        ["gerar", "--perfil", str(caminho), "--saida", str(tmp_path), "--offline"]
    ) == 0
    texto = (tmp_path / "README.md").read_text(encoding="utf-8")

    assert "## Estatísticas" in texto
    assert "| Projetos no portfólio | 1 |" in texto
    assert "## Conquistas" in texto
    assert "**Prêmio de inovação interna**" in texto


def test_importacao_guarda_estrelas(monkeypatch):
    """Estrela informada pela API entra no perfil e vira estatística real."""
    repos = [
        {
            "name": "projeto-a",
            "description": "ETL",
            "language": "Python",
            "html_url": "https://github.com/ana-exemplo/projeto-a",
            "fork": False,
            "archived": False,
            "stargazers_count": 7,
            "pushed_at": "2026-10-26T12:06:19Z",
        }
    ]
    monkeypatch.setattr(importacao.requests, "get", lambda *a, **k: RespostaFalsa(repos))

    projetos = importacao.listar_publicos("ana-exemplo")

    assert projetos[0].estrelas == 7


def test_coleta_pergunta_conquistas():
    """A entrevista aceita conquistas separadas por ponto e vírgula."""
    respostas = iter(
        ["Ana Exemplo", "ana-exemplo", "", "", "", "", "Certificação A; Prêmio B", "", ""]
    )

    perfil_coletado = coleta.entrevistar(
        perguntar=lambda _pergunta: next(respostas),
        escrever=lambda _linha: None,
    )

    assert perfil_coletado.conquistas == ["Certificação A", "Prêmio B"]


# ---------------------------------------------------------------------------
# Dupla aprovação e publicação
# ---------------------------------------------------------------------------
def test_aprovacao_exige_etapa_1_antes_da_2(readme, registro):
    """A etapa 2 sem a etapa 1 é recusada: são conferências diferentes."""
    perfil_teste = perfil_de_teste()

    deu_certo, mensagem = aprovacao.conceder(2, readme, perfil_teste, registro)

    assert deu_certo is False
    assert "etapa 1" in mensagem


def test_publicacao_bloqueada_sem_duas_aprovacoes(readme, registro, monkeypatch):
    """Sem duas aprovações, `publicar` recusa e nem chega a chamar a rede."""
    perfil_teste = perfil_de_teste()
    chamadas: list[str] = []

    def nao_deveria_chamar(*args, **kwargs):
        chamadas.append("chamou")
        return RespostaFalsa()

    monkeypatch.setattr(aprovacao.requests, "get", nao_deveria_chamar)
    monkeypatch.setattr(aprovacao.requests, "put", nao_deveria_chamar)
    monkeypatch.setenv("GITHUB_TOKEN", "token-de-teste-nao-real")

    deu_certo, mensagem = aprovacao.publicar(readme, perfil_teste, registro)

    assert deu_certo is False
    assert "bloqueada" in mensagem
    assert chamadas == []

    aprovacao.conceder(1, readme, perfil_teste, registro)
    deu_certo, mensagem = aprovacao.publicar(readme, perfil_teste, registro)
    assert deu_certo is False
    assert chamadas == []

    aprovacao.conceder(2, readme, perfil_teste, registro)
    situacao = aprovacao.estado(readme, perfil_teste, registro)
    assert situacao["liberado"] is True


def test_aprovacao_zera_quando_o_readme_muda(readme, registro):
    """Regeerar o README depois do aceite invalida as aprovações anteriores."""
    perfil_teste = perfil_de_teste()
    aprovacao.conceder(1, readme, perfil_teste, registro)
    aprovacao.conceder(2, readme, perfil_teste, registro)
    assert aprovacao.estado(readme, perfil_teste, registro)["liberado"] is True

    readme.write_text("# Ana Exemplo\n\nREADME alterado depois do aceite\n", encoding="utf-8")

    situacao = aprovacao.estado(readme, perfil_teste, registro)
    assert situacao["liberado"] is False
    assert "mudou" in situacao["motivo"]


def test_aprovacao_zera_quando_o_perfil_muda(readme, registro):
    """Mudar um dado do perfil também invalida: o README aprovado é outro."""
    perfil_teste = perfil_de_teste()
    aprovacao.conceder(1, readme, perfil_teste, registro)
    aprovacao.conceder(2, readme, perfil_teste, registro)

    perfil_teste.bio = "Bio alterada"

    assert aprovacao.estado(readme, perfil_teste, registro)["liberado"] is False


def test_publicar_exige_token(readme, registro, monkeypatch):
    """Sem token no ambiente, nada é enviado e a mensagem ensina onde definir."""
    perfil_teste = perfil_de_teste()
    aprovacao.conceder(1, readme, perfil_teste, registro)
    aprovacao.conceder(2, readme, perfil_teste, registro)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    deu_certo, mensagem = aprovacao.publicar(readme, perfil_teste, registro)

    assert deu_certo is False
    assert "GITHUB_TOKEN" in mensagem


def test_publicar_envia_conteudo_aprovado_e_nao_vaza_token(readme, registro, monkeypatch):
    """Com as duas aprovações, o PUT leva o README em base64 e o token só no cabeçalho."""
    perfil_teste = perfil_de_teste()
    aprovacao.conceder(1, readme, perfil_teste, registro)
    aprovacao.conceder(2, readme, perfil_teste, registro)

    token_falso = "token-de-teste-nao-real"
    monkeypatch.setenv("GITHUB_TOKEN", token_falso)

    capturado: dict = {}

    def get_falso(url, headers=None, timeout=None):
        capturado["headers_get"] = headers
        return RespostaFalsa({}, status_code=404)

    def put_falso(url, headers=None, json=None, timeout=None):
        capturado["url"] = url
        capturado["headers"] = headers
        capturado["corpo"] = json
        return RespostaFalsa(
            {"content": {"html_url": "https://github.com/ana-exemplo/ana-exemplo/blob/HEAD/README.md"}},
            status_code=201,
        )

    monkeypatch.setattr(aprovacao.requests, "get", get_falso)
    monkeypatch.setattr(aprovacao.requests, "put", put_falso)

    deu_certo, mensagem = aprovacao.publicar(
        readme, perfil_teste, registro, mensagem="docs: perfil aprovado"
    )

    assert deu_certo is True
    assert "ana-exemplo" in mensagem
    assert capturado["url"].endswith("/repos/ana-exemplo/ana-exemplo/contents/README.md")
    assert capturado["headers"]["Authorization"] == f"Bearer {token_falso}"
    assert base64.b64decode(capturado["corpo"]["content"]) == readme.read_bytes()
    assert capturado["corpo"]["message"] == "docs: perfil aprovado"
    assert token_falso not in json.dumps(
        aprovacao.carregar_registro(registro), ensure_ascii=False
    )


def test_cli_publicar_sem_confirmar_nao_grava(readme, registro, tmp_path, monkeypatch):
    """`publicar` sem --confirmar mostra o estado e sai com 1 (proteção extra)."""
    perfil_teste = perfil_de_teste()
    caminho_perfil = tmp_path / "perfil.yaml"
    modelo.salvar(perfil_teste, caminho_perfil)
    aprovacao.conceder(1, readme, perfil_teste, registro)
    aprovacao.conceder(2, readme, perfil_teste, registro)

    monkeypatch.setattr(
        aprovacao.requests,
        "put",
        lambda *a, **k: pytest.fail("não deveria enviar nada sem --confirmar"),
    )

    codigo = perfil.main(
        [
            "publicar",
            "--perfil",
            str(caminho_perfil),
            "--saida",
            str(tmp_path),
            "--registro",
            str(registro),
        ]
    )

    assert codigo == 1


# ---------------------------------------------------------------------------
# Coleta que lê a conta pública do GitHub sozinha
# ---------------------------------------------------------------------------
def test_coleta_inclui_os_repositorios_publicos_por_padrao():
    """Ao informar o usuário do GitHub, a coleta já traz os projetos públicos."""
    # nome, github, bio, local, site, fim dos links, "incluir todos?" (Enter), fim do manual
    respostas = iter(["Ana Exemplo", "ana-exemplo", "", "", "", "", "", "", ""])
    escritos: list[str] = []

    perfil_coletado = coleta.entrevistar(
        perguntar=lambda _pergunta: next(respostas),
        escrever=escritos.append,
        localizar_publicos=lambda _usuario: publicos_de_teste(),
    )

    assert [projeto.repo for projeto in perfil_coletado.projetos] == ["projeto-a", "projeto-b"]
    assert any("encontrei 2 repositório" in linha for linha in escritos)
    # O dado veio da API, então o endereço também: nada de "não verificado".
    assert perfil_coletado.projetos[0].url == "https://github.com/ana-exemplo/projeto-a"


def test_coleta_deixa_escolher_quais_publicos_entram():
    """Responder "n" abre a escolha por número; só o escolhido entra."""
    respostas = iter(["Ana Exemplo", "ana-exemplo", "", "", "", "", "", "n", "2", ""])
    escritos: list[str] = []

    perfil_coletado = coleta.entrevistar(
        perguntar=lambda _pergunta: next(respostas),
        escrever=escritos.append,
        localizar_publicos=lambda _usuario: publicos_de_teste(),
    )

    assert [projeto.repo for projeto in perfil_coletado.projetos] == ["projeto-b"]
    assert any("1 projeto(s) incluído" in linha for linha in escritos)


def test_coleta_nao_morre_quando_a_conta_nao_pode_ser_lida():
    """Erro de rede vira aviso: a entrevista continua e o cadastro manual segue valendo."""
    respostas = iter(["Ana Exemplo", "ana-exemplo", "", "", "", "", "", ""])
    escritos: list[str] = []

    def localizar_que_falha(_usuario: str) -> list[modelo.Projeto]:
        raise modelo.ErroPerfil("usuário do GitHub não encontrado: ana-exemplo")

    perfil_coletado = coleta.entrevistar(
        perguntar=lambda _pergunta: next(respostas),
        escrever=escritos.append,
        localizar_publicos=localizar_que_falha,
    )

    assert perfil_coletado.projetos == []
    assert any("não consegui ler a conta" in linha for linha in escritos)


def test_coleta_nao_duplica_projeto_que_ja_estava_no_perfil():
    """Reeditar o perfil não repete os repositórios já cadastrados."""
    existente = perfil_de_teste()
    respostas = iter([""] * 9)

    perfil_coletado = coleta.entrevistar(
        perfil_inicial=existente,
        perguntar=lambda _pergunta: next(respostas),
        escrever=lambda _linha: None,
        localizar_publicos=lambda _usuario: publicos_de_teste(),
    )

    assert [projeto.repo for projeto in perfil_coletado.projetos] == ["projeto-a", "projeto-b"]


def test_escolha_por_numero_ignora_lixo_e_repeticao():
    """Número repetido, fora da faixa ou palavra solta não quebra a escolha."""
    projetos = publicos_de_teste()

    escolhidos = coleta._escolher_por_numero(projetos, "1, 3, 1, x, 99")

    assert [projeto.repo for projeto in escolhidos] == ["projeto-a"]


def test_iniciar_le_a_conta_publica_e_gera_readme_com_os_projetos(tmp_path, monkeypatch):
    """De ponta a ponta: `iniciar` preenche os projetos sozinho e o README sai com eles."""
    monkeypatch.setattr(importacao, "listar_publicos", lambda *a, **k: publicos_de_teste())
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    # nome, github, bio, local, site, fim dos links, incluir todos (Enter), fim do manual
    respostas = iter(["Ana Exemplo", "ana-exemplo", "", "", "", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda _pergunta="": next(respostas))

    caminho_perfil = tmp_path / "perfil.yaml"
    codigo = perfil.main(
        [
            "iniciar",
            "--perfil",
            str(caminho_perfil),
            "--saida",
            str(tmp_path / "saida"),
            "--template",
            "minimal",
        ]
    )

    assert codigo == 0
    perfil_salvo = yaml.safe_load(caminho_perfil.read_text(encoding="utf-8"))
    assert [projeto["repo"] for projeto in perfil_salvo["projetos"]] == ["projeto-a", "projeto-b"]

    readme = (tmp_path / "saida" / "README.md").read_text(encoding="utf-8")
    assert "| projeto-a |" in readme
    assert "O que prova" in readme


def test_iniciar_com_sem_importar_nao_toca_a_rede(tmp_path, monkeypatch):
    """`--sem-importar` mantém a coleta manual, sem consultar o GitHub."""

    def nao_deveria_buscar(*args, **kwargs):
        pytest.fail("não deveria consultar o GitHub com --sem-importar")

    monkeypatch.setattr(importacao, "listar_publicos", nao_deveria_buscar)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    respostas = iter(["Ana Exemplo", "ana-exemplo", "", "", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda _pergunta="": next(respostas))

    codigo = perfil.main(
        [
            "iniciar",
            "--sem-importar",
            "--sem-gerar",
            "--perfil",
            str(tmp_path / "perfil.yaml"),
            "--saida",
            str(tmp_path / "saida"),
        ]
    )

    assert codigo == 0
    perfil_salvo = yaml.safe_load((tmp_path / "perfil.yaml").read_text(encoding="utf-8"))
    assert perfil_salvo["projetos"] == []


def test_importacao_preenche_dado_da_api_que_faltava_no_projeto_existente(monkeypatch):
    """Importar de novo completa endereço e data sem apagar o que foi escrito à mão."""
    existente = modelo.Perfil(
        nome="Ana",
        github="ana-exemplo",
        projetos=[
            modelo.Projeto(repo="projeto-a", destaque=True, prova="texto curado", status="MVP")
        ],
    )
    repos = [
        {
            "name": "projeto-a",
            "description": "descrição da API",
            "language": "Python",
            "html_url": "https://github.com/ana-exemplo/projeto-a",
            "fork": False,
            "archived": False,
            "stargazers_count": 0,
            "pushed_at": "2026-10-26T12:06:19Z",
        }
    ]

    def get_falso(url, headers=None, timeout=None):
        return RespostaFalsa({"login": "ana-exemplo"} if url.endswith("/ana-exemplo") else repos)

    monkeypatch.setattr(importacao.requests, "get", get_falso)

    perfil_mesclado, _ = importacao.importar("ana-exemplo", perfil_existente=existente)
    projeto = perfil_mesclado.projetos[0]

    assert projeto.prova == "texto curado"  # escrito à mão vence
    assert projeto.status == "MVP"
    assert projeto.url == "https://github.com/ana-exemplo/projeto-a"
    assert projeto.atualizado_em == "2026-10-26T12:06:19Z"
    assert projeto.stack == ["Python"]


def test_limite_da_api_nao_multiplica_avisos_e_usa_as_datas_guardadas(monkeypatch):
    """Depois de duas falhas seguidas, a geração para de consultar e usa o perfil."""
    projetos = [
        modelo.Projeto(
            repo=f"projeto-{indice}",
            destaque=indice == 0,
            prova="ETL",
            stack=["Python"],
            url=f"https://github.com/ana-exemplo/projeto-{indice}",
            atualizado_em="2026-10-26T12:06:19Z",
        )
        for indice in range(6)
    ]
    perfil_varios = modelo.Perfil(nome="Ana", github="ana-exemplo", projetos=projetos)

    consultas: list[str] = []

    def sem_resposta(dono, repo, token=None, tempo_limite=10.0):
        consultas.append(repo)
        return None

    monkeypatch.setattr("generate.buscar_metadados_github", sem_resposta)

    preparacao = analise.preparar(perfil_varios, offline=False)

    # Duas tentativas bastam para concluir que a API não responde; as outras ficam
    # com a data guardada em vez de gastar consulta e encher o terminal de aviso.
    assert len(consultas) == 2
    for linha in preparacao.destacados + preparacao.outros:
        assert linha["atualizado_em"] == "26/10/2026"


def test_atom_devolve_a_data_do_ultimo_commit(monkeypatch):
    """A rota alternativa lê o primeiro <updated> do feed de commits."""

    class RespostaAtom:
        status_code = 200

        text = (
            '<?xml version="1.0" encoding="UTF-8"?><feed><entry>'
            "<updated>2026-10-18T22:30:48Z</updated><title>commit</title>"
            "</entry><entry><updated>2026-10-17T10:00:00Z</updated></entry></feed>"
        )

    monkeypatch.setattr(importacao.requests, "get", lambda *a, **k: RespostaAtom())

    assert importacao.data_da_ultima_atualizacao("ana-exemplo", "projeto-a") == "2026-10-18T22:30:48Z"


def test_atom_indisponivel_devolve_vazio(monkeypatch):
    """Feed fora do ar não vira exceção: o README segue dizendo "não declarado"."""

    class RespostaErro:
        status_code = 404
        text = ""

    monkeypatch.setattr(importacao.requests, "get", lambda *a, **k: RespostaErro())

    assert importacao.data_da_ultima_atualizacao("ana-exemplo", "sumiu") == ""


def test_geracao_usa_rota_alternativa_quando_a_api_esta_bloqueada(monkeypatch):
    """Com a API em 403, a data sai do feed de commits e fica guardada no perfil."""
    perfil_bloqueado = modelo.Perfil(
        nome="Ana Exemplo",
        github="ana-exemplo",
        projetos=[
            modelo.Projeto(
                repo="projeto-a",
                destaque=True,
                prova="ETL",
                stack=["Python"],
                url="https://github.com/ana-exemplo/projeto-a",
            )
        ],
    )
    monkeypatch.setattr("generate.buscar_metadados_github", lambda *a, **k: None)
    monkeypatch.setattr(
        importacao, "data_da_ultima_atualizacao", lambda *a, **k: "2026-10-18T22:30:48Z"
    )

    preparacao = analise.preparar(perfil_bloqueado, offline=False)

    assert preparacao.destacados[0]["atualizado_em"] == "18/10/2026"
    assert perfil_bloqueado.projetos[0].atualizado_em == "2026-10-18T22:30:48Z"


def test_iniciar_lembra_o_visual_escolhido(tmp_path, monkeypatch):
    """O template escolhido no `iniciar` fica no perfil e vale nas próximas gerações."""
    monkeypatch.setattr(importacao, "listar_publicos", lambda *a, **k: publicos_de_teste())
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    respostas = iter(["Ana Exemplo", "ana-exemplo", "", "", "", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda _pergunta="": next(respostas))

    caminho_perfil = tmp_path / "perfil.yaml"
    saida = tmp_path / "saida"
    assert perfil.main(
        [
            "iniciar",
            "--perfil",
            str(caminho_perfil),
            "--saida",
            str(saida),
            "--template",
            "dark-terminal",
        ]
    ) == 0

    assert yaml.safe_load(caminho_perfil.read_text(encoding="utf-8"))["template"] == "dark-terminal"

    # Geração sem --template: agora usa o visual lembrado, sem aviso de padrão.
    assert perfil.main(
        ["gerar", "--perfil", str(caminho_perfil), "--saida", str(saida), "--offline"]
    ) == 0
    texto = (saida / "README.md").read_text(encoding="utf-8")
    assert "console" in texto  # bloco característico do dark-terminal


# ---------------------------------------------------------------------------
# README que começa zerado e cresce
# ---------------------------------------------------------------------------
def test_readme_comeca_zerado_e_cresce_com_os_dados(tmp_path):
    """Perfil recém-criado gera README com apresentação e vazio honesto; projeto novo entra depois."""
    caminho = tmp_path / "perfil.yaml"
    modelo.salvar(modelo.Perfil(nome="Ana Exemplo", github="ana-exemplo", bio="Python"), caminho)
    saida = tmp_path / "saida"

    assert perfil.main(["gerar", "--perfil", str(caminho), "--saida", str(saida), "--offline"]) == 0
    texto_zerado = (saida / "README.md").read_text(encoding="utf-8")
    assert "# Ana Exemplo" in texto_zerado
    assert "Nenhum projeto cadastrado ainda" in texto_zerado
    assert not (saida / "graficos").exists()

    # Segundo passo: a pessoa cadastra um projeto e regera. O README cresce.
    perfil_maior = modelo.carregar(caminho)
    perfil_maior.projetos.append(
        modelo.Projeto(repo="projeto-novo", destaque=True, prova="Automação", stack=["Python"], status="MVP")
    )
    modelo.salvar(perfil_maior, caminho)

    assert perfil.main(["gerar", "--perfil", str(caminho), "--saida", str(saida), "--offline"]) == 0
    texto_crescido = (saida / "README.md").read_text(encoding="utf-8")
    assert "| projeto-novo |" in texto_crescido
    assert "Nenhum projeto cadastrado ainda" not in texto_crescido
    assert len(texto_crescido) > len(texto_zerado)


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def test_graficos_gerados_e_referenciados_no_readme(tmp_path):
    """O gráfico existe em disco e o README aponta para ele por caminho relativo."""
    assert perfil.main(
        ["gerar", "--perfil", str(PERFIL_EXEMPLO), "--saida", str(tmp_path), "--offline"]
    ) == 0

    svg = tmp_path / "graficos" / "tecnologias.svg"
    texto = (tmp_path / "README.md").read_text(encoding="utf-8")

    assert svg.exists()
    conteudo = svg.read_text(encoding="utf-8")
    assert conteudo.startswith("<svg")
    assert "Python" in conteudo
    assert "![Tecnologias por número de projetos](graficos/tecnologias.svg)" in texto


def test_grafico_de_barras_escapa_caracteres_de_xml():
    """Tecnologia com & ou < não pode quebrar o SVG."""
    desenho = graficos.grafico_de_barras("Teste", [("Gerência & Dados", 2), ("C<D", 1)])

    assert "&amp;" in desenho
    assert "&lt;" in desenho
    assert "<svg" in desenho


# ---------------------------------------------------------------------------
# Visualizador: tema e ícones
# ---------------------------------------------------------------------------
def test_pagina_tem_botao_de_tema_com_os_dois_css():
    """Um clique troca o tema: a página traz o botão, as variáveis claras e as escuras."""
    pagina = preview.renderizar_html("# T", titulo="README.md")

    assert 'id="botao-tema"' in pagina
    assert 'id="rotulo-tema"' in pagina
    assert 'data-tema="escuro"' in pagina  # regra CSS do tema escuro
    assert "--fundo: #0d1117" in pagina  # fundo escuro
    assert "--fundo: #ffffff" in pagina  # fundo claro
    assert "localStorage" in pagina


def test_tema_pode_ser_escolhido_pela_url():
    """`?tema=claro|escuro` fixa o tema no HTML; valor inválido não fixa nada."""
    claro = preview.renderizar_html("# T", tema="claro")
    escuro = preview.renderizar_html("# T", tema="ESCURO")
    automatico = preview.renderizar_html("# T", tema="roxo")

    assert '<html lang="pt-BR" data-tema="claro">' in claro
    assert '<html lang="pt-BR" data-tema="escuro">' in escuro
    assert '<html lang="pt-BR">' in automatico
    # O script precisa respeitar o tema fixado em vez de sobrescrever com o sistema.
    assert "var fixo = raiz.getAttribute('data-tema');" in claro


def test_servidor_respeita_tema_da_url(tmp_path):
    """Servindo a página com ?tema=escuro, o HTML já vem no tema escuro."""
    arquivo = tmp_path / "README.md"
    arquivo.write_text("# T\n", encoding="utf-8")
    servidor = preview.criar_servidor(arquivo, porta=0)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()

    try:
        porta = servidor.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/?tema=escuro", timeout=5) as resposta:
            pagina = resposta.read().decode("utf-8")
    finally:
        servidor.shutdown()
        servidor.server_close()
        thread.join(timeout=5)

    assert 'data-tema="escuro"' in pagina.split("</head>")[0]


def test_pagina_imita_o_github_com_icones_e_abas():
    """Cabeçalho didático: marca, repositório, estrela, fork e abas ilustrativas."""
    pagina = preview.renderizar_html("# T", titulo="README.md", repositorio="ana-exemplo/ana-exemplo")

    assert "ana-exemplo/ana-exemplo" in pagina
    assert "Estrela" in pagina
    assert "Fork" in pagina
    assert "Pull requests" in pagina
    assert "README.md" in pagina
    assert "Simulação local" in pagina
    assert pagina.count("<svg") >= 5


def test_preview_serve_o_grafico_e_recusa_caminho_fora_da_pasta(tmp_path):
    """A rota /graficos/ entrega SVG da pasta de saída e nunca um arquivo de fora."""
    arquivo = tmp_path / "README.md"
    arquivo.write_text("# T\n", encoding="utf-8")
    pasta = tmp_path / "graficos"
    pasta.mkdir()
    (pasta / "tecnologias.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    (tmp_path / "segredo.txt").write_text("não deveria sair daqui", encoding="utf-8")

    servidor = preview.criar_servidor(arquivo, porta=0)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()

    try:
        porta = servidor.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/graficos/tecnologias.svg", timeout=5) as resposta:
            status_svg = resposta.status
            cabecalho = resposta.headers.get("Content-Type")

        with pytest.raises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/graficos/%2E%2E/segredo.txt", timeout=5)
    finally:
        servidor.shutdown()
        servidor.server_close()
        thread.join(timeout=5)

    assert status_svg == 200
    assert "image/svg+xml" in cabecalho
    assert erro.value.code == 404


# ---------------------------------------------------------------------------
# Importação dos dados públicos do GitHub
# ---------------------------------------------------------------------------
def test_importacao_preenche_o_perfil_com_dados_do_github(monkeypatch):
    """Usuário + repositórios públicos viram perfil, sem inventar status."""
    usuario = {
        "login": "ana-exemplo",
        "name": "Ana Exemplo",
        "bio": "Dados e automação",
        "location": "Florianópolis/SC",
        "blog": "https://ana.example.com",
    }
    repos = [
        {
            "name": "projeto-a",
            "description": "ETL de indicadores",
            "language": "Python",
            "html_url": "https://github.com/ana-exemplo/projeto-a",
            "fork": False,
            "archived": False,
            "stargazers_count": 4,
        },
        {
            "name": "fork-antigo",
            "description": "fork",
            "html_url": "https://github.com/ana-exemplo/fork-antigo",
            "fork": True,
            "archived": False,
            "stargazers_count": 0,
        },
    ]

    def get_falso(url, headers=None, timeout=None):
        return RespostaFalsa(usuario if url.endswith("/ana-exemplo") else repos)

    monkeypatch.setattr(importacao.requests, "get", get_falso)

    perfil_importado, dados = importacao.importar("ana-exemplo")

    assert perfil_importado.nome == "Ana Exemplo"
    assert perfil_importado.local == "Florianópolis/SC"
    assert [projeto.repo for projeto in perfil_importado.projetos] == ["projeto-a"]
    assert perfil_importado.projetos[0].prova == "ETL de indicadores"
    assert perfil_importado.projetos[0].destaque is True
    # A API não sabe o estágio do projeto: nada de inventar "publicado".
    assert perfil_importado.projetos[0].status == ""
    assert len(dados["repos"]) == 2


def test_importacao_mescla_sem_apagar_dado_curado(monkeypatch):
    """O que a pessoa escreveu sobrevive; o projeto novo do GitHub é acrescentado."""
    existente = modelo.de_dicionario(
        {
            "nome": "Ana",
            "github": "ana-exemplo",
            "bio": "minha bio escrita à mão",
            "projetos": [
                {"repo": "projeto-a", "destaque": True, "prova": "texto curado", "stack": ["Python"], "status": "MVP"}
            ],
        }
    )
    repos = [
        {
            "name": "projeto-a",
            "description": "descrição da API",
            "language": "Python",
            "html_url": "https://github.com/ana-exemplo/projeto-a",
            "fork": False,
            "archived": False,
            "stargazers_count": 9,
        },
        {
            "name": "projeto-b",
            "description": "outro projeto",
            "language": "SQL",
            "html_url": "https://github.com/ana-exemplo/projeto-b",
            "fork": False,
            "archived": False,
            "stargazers_count": 0,
        },
    ]

    def get_falso(url, headers=None, timeout=None):
        return RespostaFalsa({"login": "ana-exemplo", "bio": "bio da API"} if url.endswith("/ana-exemplo") else repos)

    monkeypatch.setattr(importacao.requests, "get", get_falso)

    perfil_mesclado, _ = importacao.importar("ana-exemplo", perfil_existente=existente)

    assert perfil_mesclado.bio == "minha bio escrita à mão"
    assert [projeto.repo for projeto in perfil_mesclado.projetos] == ["projeto-a", "projeto-b"]
    assert perfil_mesclado.projetos[0].prova == "texto curado"
    assert perfil_mesclado.projetos[0].status == "MVP"


def test_importacao_nao_destaca_repositorio_sem_descricao(monkeypatch):
    """Vitrine prioriza quem tem descrição: "não declarado" em destaque não informa."""
    repos = [
        {
            "name": "sem-descricao",
            "description": "",
            "language": "Python",
            "html_url": "https://github.com/ana-exemplo/sem-descricao",
            "fork": False,
            "archived": False,
            "stargazers_count": 12,
            "pushed_at": "2026-11-01T00:00:00Z",
        },
        {
            "name": "com-descricao",
            "description": "Painel de dados",
            "language": "Python",
            "html_url": "https://github.com/ana-exemplo/com-descricao",
            "fork": False,
            "archived": False,
            "stargazers_count": 0,
            "pushed_at": "2026-10-01T00:00:00Z",
        },
    ]
    monkeypatch.setattr(importacao.requests, "get", lambda *a, **k: RespostaFalsa(repos))

    projetos = importacao.listar_publicos("ana-exemplo")

    por_nome = {projeto.repo: projeto for projeto in projetos}
    assert por_nome["com-descricao"].destaque is True
    assert por_nome["sem-descricao"].destaque is False


def test_importacao_usuario_inexistente_tem_mensagem_clara(monkeypatch):
    """404 vira explicação em português, não stack trace."""
    monkeypatch.setattr(importacao.requests, "get", lambda *a, **k: RespostaFalsa({}, status_code=404))

    with pytest.raises(modelo.ErroPerfil) as erro:
        importacao.importar("nao-existe-ninguem")

    assert "não encontrado" in str(erro.value)


# ---------------------------------------------------------------------------
# Gráficos entram na aprovação e na publicação
# ---------------------------------------------------------------------------
def test_importacao_guarda_a_data_de_atualizacao(monkeypatch):
    """A data de `pushed_at` fica no perfil, em vez de virar "não declarado"."""
    repos = [
        {
            "name": "projeto-a",
            "description": "ETL",
            "language": "Python",
            "html_url": "https://github.com/ana-exemplo/projeto-a",
            "fork": False,
            "archived": False,
            "stargazers_count": 0,
            "pushed_at": "2026-10-26T12:06:19Z",
        }
    ]
    monkeypatch.setattr(importacao.requests, "get", lambda *a, **k: RespostaFalsa(repos))

    projetos = importacao.listar_publicos("ana-exemplo")

    assert projetos[0].atualizado_em == "2026-10-26T12:06:19Z"


def test_readme_offline_mostra_a_data_guardada_na_importacao(tmp_path):
    """Sem rede, o README usa a data que a importação já trouxe — dado real, não invenção."""
    perfil_importado = modelo.Perfil(
        nome="Ana Exemplo",
        github="ana-exemplo",
        projetos=[
            modelo.Projeto(
                repo="projeto-a",
                destaque=True,
                prova="ETL",
                stack=["Python"],
                url="https://github.com/ana-exemplo/projeto-a",
                atualizado_em="2026-10-26T12:06:19Z",
            )
        ],
    )
    caminho = tmp_path / "perfil.yaml"
    modelo.salvar(perfil_importado, caminho)

    assert perfil.main(
        ["gerar", "--perfil", str(caminho), "--saida", str(tmp_path), "--offline"]
    ) == 0

    texto = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "26/10/2026" in texto
    assert "2026-10-26T12:06:19Z" not in texto


def test_repo_do_perfil_reconhece_so_a_propria_conta():
    """Só repositório da própria conta merece consulta de atualização."""
    dono = "ana-exemplo"

    proprio = modelo.Projeto(repo="p", url="https://github.com/ana-exemplo/p")
    de_outro = modelo.Projeto(repo="p", url="https://github.com/outra-pessoa/p")
    site = modelo.Projeto(repo="p", url="https://ana.example.com/p")

    assert analise._repo_do_perfil(proprio, dono) is True
    assert analise._repo_do_perfil(de_outro, dono) is False
    assert analise._repo_do_perfil(site, dono) is False


def test_geracao_online_atualiza_a_data_de_repositorio_da_propria_conta(monkeypatch):
    """Com rede, a data é reconsultada: a coluna não envelhece."""
    perfil_atual = modelo.Perfil(
        nome="Ana Exemplo",
        github="ana-exemplo",
        projetos=[
            modelo.Projeto(
                repo="projeto-a",
                destaque=True,
                prova="ETL",
                stack=["Python"],
                url="https://github.com/ana-exemplo/projeto-a",
                atualizado_em="2025-01-01T00:00:00Z",
            )
        ],
    )
    consultados: list[str] = []

    def get_falso(url, headers=None, timeout=None):
        consultados.append(url)
        return RespostaFalsa(
            {
                "html_url": "https://github.com/ana-exemplo/projeto-a",
                "stargazers_count": 0,
                "language": "Python",
                "pushed_at": "2026-11-02T10:00:00Z",
                "archived": False,
                "fork": False,
            }
        )

    monkeypatch.setattr("generate.requests.get", get_falso)

    preparacao = analise.preparar(perfil_atual, offline=False)

    assert consultados, "deveria consultar a API para um repositório da própria conta"
    assert preparacao.destacados[0]["atualizado_em"] == "02/11/2026"


def test_aprovacao_invalida_quando_o_grafico_muda(readme, registro):
    """Gráfico alterado depois do aceite quebra o lacre, igual ao README."""
    pasta = readme.parent / "graficos"
    pasta.mkdir()
    desenho = pasta / "tecnologias.svg"
    desenho.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>1</text></svg>', encoding="utf-8")

    perfil_teste = perfil_de_teste()
    aprovacao.conceder(1, readme, perfil_teste, registro)
    aprovacao.conceder(2, readme, perfil_teste, registro)
    assert aprovacao.estado(readme, perfil_teste, registro)["liberado"] is True

    desenho.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>2</text></svg>', encoding="utf-8")

    assert aprovacao.estado(readme, perfil_teste, registro)["liberado"] is False


def test_publicar_envia_readme_e_graficos(readme, registro, monkeypatch):
    """A publicação leva o README e cada SVG que ele referencia."""
    pasta = readme.parent / "graficos"
    pasta.mkdir()
    (pasta / "tecnologias.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><text>1</text></svg>', encoding="utf-8"
    )

    perfil_teste = perfil_de_teste()
    aprovacao.conceder(1, readme, perfil_teste, registro)
    aprovacao.conceder(2, readme, perfil_teste, registro)

    caminhos_enviados: list[str] = []

    monkeypatch.setattr(aprovacao.requests, "get", lambda *a, **k: RespostaFalsa({}, status_code=404))

    def put_falso(url, headers=None, json=None, timeout=None):
        caminhos_enviados.append(url.split("/contents/")[1])
        return RespostaFalsa({"content": {"html_url": "https://github.com/" + caminhos_enviados[-1]}}, status_code=201)

    monkeypatch.setattr(aprovacao.requests, "put", put_falso)
    monkeypatch.setenv("GITHUB_TOKEN", "token-de-teste-nao-real")

    deu_certo, mensagem = aprovacao.publicar(readme, perfil_teste, registro)

    assert deu_certo is True
    assert caminhos_enviados == ["README.md", "graficos/tecnologias.svg"]
    assert "gráfico" in mensagem
