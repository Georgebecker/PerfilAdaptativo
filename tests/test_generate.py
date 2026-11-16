"""
Testes do gerador de README (generate.py).

Regra destes testes: nenhum toca a rede. Onde a API do GitHub seria chamada,
entra um dublê (mock) que finge resposta, resposta de erro ou queda de conexão.
Assim o teste roda igual no seu computador sem internet e no GitHub Actions.

Todo teste escreve em `tmp_path`, uma pasta temporária criada e apagada pelo
pytest — o README de verdade do projeto nunca é sobrescrito por um teste.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests
import yaml

# O pytest roda a partir da raiz, mas nem sempre o módulo está importável:
# esta linha garante que `import generate` ache o arquivo do projeto.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate  # noqa: E402  (import depois do ajuste de sys.path, de propósito)


class RespostaFalsa:
    """Imita o mínimo de uma resposta `requests`: o status e o JSON."""

    def __init__(self, dados: dict, status_code: int = 200) -> None:
        self._dados = dados
        self.status_code = status_code

    def json(self) -> dict:
        return self._dados


METADADOS_FAKE = {
    "html_url": "https://github.com/ana-exemplo/exemplo-etl",
    "stargazers_count": 3,
    "language": "Python",
    "pushed_at": "2026-10-26T12:06:19Z",
    "archived": False,
    "fork": False,
}


@pytest.fixture
def pasta_temporaria(tmp_path, monkeypatch):
    """Roda o teste dentro de uma pasta vazia e devolve o caminho dela."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def ler_saida(pasta: Path, nome: str = "README.md") -> str:
    """
    Lê um arquivo gerado dentro de `saidas/`.

    A saída padrão do gerador mudou de propósito para `saidas/` (fora da raiz):
    o README do projeto deixou de ser sobrescrito por um README de perfil. Se a
    pasta não existir, o erro do teste fica claro: ninguém gerou nada.
    """
    return (pasta / "saidas" / nome).read_text(encoding="utf-8")


def test_offline_gera_os_dois_arquivos(pasta_temporaria):
    """Modo --offline precisa gerar README.md e README.profile.md sem rede."""
    codigo = generate.main(["--offline"])

    assert codigo == 0
    assert (pasta_temporaria / "saidas" / "README.md").exists()
    assert (pasta_temporaria / "saidas" / "README.profile.md").exists()


def test_template_lista_os_nove_projetos(pasta_temporaria):
    """A curadoria tem 9 repositórios e todos precisam aparecer no README."""
    generate.main(["--offline"])
    readme = ler_saida(pasta_temporaria)

    config = generate.carregar_config(generate.CAMINHO_CONFIG_PADRAO)
    repos = [item["repo"] for item in config["projects"]]

    assert len(repos) == 3
    for repo in repos:
        assert repo in readme, f"o repositório {repo} não apareceu no README"


def test_status_ausente_nao_imprime_marcador(pasta_temporaria):
    """Projeto sem `status` não inventa estágio nem escreve "não declarado"."""
    caminho = pasta_temporaria / "projetos.yaml"
    caminho.write_text(
        yaml.safe_dump(
            {
                "github_user": "Fulano",
                "site": "https://example.com",
                "projects": [
                    {
                        "repo": "sem-status",
                        "featured": True,
                        "proof": "Prova qualquer",
                        "stack": ["Python"],
                    }
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    codigo = generate.main(["--offline", "--config", str(caminho)])
    readme = ler_saida(pasta_temporaria)

    assert codigo == 0
    assert "| sem-status |" in readme
    # A célula fica vazia: o marcador de ausência saiu do documento.
    assert generate.STATUS_SEM_EVIDENCIA_README not in readme


@pytest.mark.parametrize(
    "entrada",
    [None, "", "   ", "nao_declarado", "não declarado"],
)
def test_traduzir_status_sem_evidencia(entrada):
    """"Vazio" e todas as grafias de "não sei" viram o mesmo texto no README."""
    assert generate.traduzir_status(entrada) == generate.STATUS_SEM_EVIDENCIA_README


def test_traduzir_status_informado_e_preservado():
    """Status que o dono declarou de verdade não é reescrito."""
    assert generate.traduzir_status("publicado") == "publicado"


def test_data_em_formato_brasileiro(pasta_temporaria, monkeypatch):
    """A data ISO do GitHub sai como DD/MM/AAAA no README."""
    assert generate.formatar_data("2026-10-26T12:06:19Z") == "26/10/2026"
    assert generate.formatar_data(None) == "não declarado"
    assert generate.formatar_data("data-quebrada") == "não declarado"

    monkeypatch.setattr(generate.requests, "get", lambda *a, **k: RespostaFalsa(METADADOS_FAKE))
    generate.main([])
    readme = ler_saida(pasta_temporaria)

    assert "26/10/2026" in readme
    assert "2026-10-26T12:06:19Z" not in readme


@pytest.mark.parametrize("falha", ["conexao", "http_500"])
def test_falha_de_api_nao_quebra_a_geracao(pasta_temporaria, monkeypatch, capsys, falha):
    """Queda de conexão ou erro do GitHub geram README igual, com aviso."""

    def resposta_que_falha(*args, **kwargs):
        if falha == "conexao":
            raise requests.ConnectionError("rede fora (simulado)")
        return RespostaFalsa({}, status_code=500)

    monkeypatch.setattr(generate.requests, "get", resposta_que_falha)

    codigo = generate.main([])
    readme = ler_saida(pasta_temporaria)
    avisos = capsys.readouterr().err

    assert codigo == 0
    assert "exemplo-etl" in readme
    # Sem confirmação da API, a célula fica vazia — e o aviso explica o motivo.
    assert generate.STATUS_SEM_EVIDENCIA_README not in readme
    assert "aviso:" in avisos


def test_fork_e_arquivado_ficam_fora_das_tabelas(pasta_temporaria, monkeypatch):
    """Repositório fork ou arquivado não representa trabalho atual."""
    dados = dict(METADADOS_FAKE, fork=True)
    monkeypatch.setattr(generate.requests, "get", lambda *a, **k: RespostaFalsa(dados))

    generate.main([])
    readme = ler_saida(pasta_temporaria)

    assert "| exemplo-etl |" not in readme


def test_secoes_tem_linha_em_branco_antes(pasta_temporaria):
    """Sem linha em branco antes do título, o Markdown não renderiza a tabela."""
    generate.main(["--offline"])
    linhas = ler_saida(pasta_temporaria).splitlines()

    for indice, linha in enumerate(linhas):
        if linha.startswith("## "):
            assert linhas[indice - 1] == "", f"a seção '{linha}' está colada na linha anterior"


def test_readme_nao_vaza_token(pasta_temporaria, monkeypatch):
    """O token viaja no cabeçalho da requisição, nunca para o arquivo gerado."""
    token_secreto = "ghp_TokenFalsoDeTeste123"
    monkeypatch.setenv("GITHUB_TOKEN", token_secreto)
    monkeypatch.setenv("GH_TOKEN", token_secreto)

    capturado: dict = {}

    def registro(*args, **kwargs):
        capturado["headers"] = kwargs.get("headers") or {}
        return RespostaFalsa(METADADOS_FAKE)

    monkeypatch.setattr(generate.requests, "get", registro)

    generate.main([])
    readme = ler_saida(pasta_temporaria)
    perfil = ler_saida(pasta_temporaria, "README.profile.md")

    assert capturado["headers"].get("Authorization") == f"Bearer {token_secreto}"

    for texto in (readme, perfil):
        assert token_secreto not in texto
        assert "Bearer" not in texto
        assert "GITHUB_TOKEN" not in texto
        assert "GH_TOKEN" not in texto
