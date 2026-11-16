"""
Testes do suporte a múltiplos templates visuais.

O que se prova aqui:
1. o catálogo (`config/templates.yaml`) é a fonte de verdade e é validado;
2. os três visuais geram README com o MESMO conteúdo;
3. pedir um template inexistente dá erro claro com a lista dos válidos;
4. sem `--template`, o padrão `minimal` é usado e o aviso aparece no log;
5. as atribuições de terceiros existem e não prometem licença que não foi
   confirmada.

Nenhum teste toca a rede: todos usam `--offline`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate  # noqa: E402
import perfil  # noqa: E402
from perfil_adaptativo import modelo, templates_visuais  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
PERFIL_EXEMPLO = RAIZ / "examples" / "perfil.exemplo.yaml"
IDS = ["minimal", "dark-terminal", "animated"]


def test_catalogo_registra_os_tres_templates():
    """O catálogo existe, é lido e aponta para arquivos que existem de verdade."""
    catalogo = templates_visuais.carregar_catalogo()

    assert [entrada["id"] for entrada in catalogo] == IDS
    for entrada in catalogo:
        assert (RAIZ / entrada["path"]).is_file(), entrada["path"]
        assert entrada["description"], "todo template precisa de descrição para o menu"
        assert entrada["license"] == "MIT"


def test_template_inexistente_mostra_os_validos():
    """Erro de template é aula: diz o que foi pedido e o que existe."""
    with pytest.raises(modelo.ErroPerfil) as erro:
        templates_visuais.obter("neon-inexistente")

    mensagem = str(erro.value)
    assert "neon-inexistente" in mensagem
    for identificador in IDS:
        assert identificador in mensagem


def test_catalogo_nao_carrega_arquivo_fora_de_templates(tmp_path, monkeypatch):
    """Caminho relativo que sai de templates/ é recusado (proteção de catálogo)."""
    catalogo = tmp_path / "templates.yaml"
    catalogo.write_text(
        "templates:\n"
        "  - id: invasor\n"
        "    name: Invasor\n"
        "    description: fora da pasta\n"
        "    path: ../README.md\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(templates_visuais, "CAMINHO_CATALOGO", catalogo)

    with pytest.raises(modelo.ErroPerfil) as erro:
        templates_visuais.obter("invasor")

    assert "fora de templates" in str(erro.value)


def test_menu_escolhe_pelo_numero(monkeypatch, capsys):
    """No terminal, o menu numerado devolve o id correspondente."""
    monkeypatch.setattr("builtins.input", lambda _pergunta: "2")

    assert templates_visuais.menu() == "dark-terminal"
    assert "Dark Terminal" in capsys.readouterr().out


def test_menu_com_resposta_invalida_cai_no_padrao(monkeypatch, capsys):
    """Resposta estranha não quebra: avisa e usa o padrão."""
    monkeypatch.setattr("builtins.input", lambda _pergunta: "nove")

    assert templates_visuais.menu() == "minimal"
    assert "opção inválida" in capsys.readouterr().out


@pytest.mark.parametrize("template_id", IDS)
def test_perfil_gerar_com_cada_template(tmp_path, template_id):
    """Os três visuais geram README com o mesmo dado e os gráficos próprios."""
    codigo = perfil.main(
        [
            "gerar",
            "--perfil",
            str(PERFIL_EXEMPLO),
            "--saida",
            str(tmp_path),
            "--template",
            template_id,
            "--offline",
        ]
    )

    assert codigo == 0
    texto = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Ana Exemplo" in texto
    assert "exemplo-etl" in texto
    assert "Tecnologias por número de projetos" in texto
    assert (tmp_path / "graficos" / "tecnologias.svg").exists()

    # Só os visuais "de impacto" ganham banner; o minimal é sóbrio por definição.
    banner = tmp_path / "graficos" / "banner.svg"
    assert banner.exists() is (template_id != "minimal")


@pytest.mark.parametrize("template_id", IDS)
def test_generate_aceita_cada_template(tmp_path, template_id):
    """Critério de aceite: `generate.py --offline --template <id>` funciona."""
    codigo = generate.main(
        [
            "--offline",
            "--template",
            template_id,
            "--output",
            str(tmp_path / "README.md"),
            "--profile-output",
            str(tmp_path / "README.profile.md"),
        ]
    )

    assert codigo == 0
    assert (tmp_path / "README.md").read_text(encoding="utf-8").strip()
    assert (tmp_path / "README.profile.md").read_text(encoding="utf-8").strip()


def test_generate_sem_template_usa_minimal_e_avisa(tmp_path, capsys):
    """Sem `--template`, o padrão minimal é usado — e o log diz isso."""
    codigo = generate.main(
        [
            "--offline",
            "--output",
            str(tmp_path / "README.md"),
            "--profile-output",
            str(tmp_path / "README.profile.md"),
        ]
    )

    avisos = capsys.readouterr().err
    assert codigo == 0
    assert "sem --template" in avisos
    assert "minimal" in avisos


def test_templates_recebem_o_mesmo_conteudo(tmp_path):
    """Trocar de visual muda a arrumação; o dado tem de ser idêntico."""
    saidas = {}
    for template_id in IDS:
        pasta = tmp_path / template_id
        assert perfil.main(
            [
                "gerar",
                "--perfil",
                str(PERFIL_EXEMPLO),
                "--saida",
                str(pasta),
                "--template",
                template_id,
                "--offline",
            ]
        ) == 0
        saidas[template_id] = (pasta / "README.md").read_text(encoding="utf-8")

    for trecho in ("Ana Exemplo", "exemplo-etl", "exemplo-bot", "exemplo-painel", "## Estatísticas"):
        for template_id, texto in saidas.items():
            assert trecho in texto, f"'{trecho}' sumiu no template {template_id}"
    # Nenhum visual imprime marcador de ausência.
    for template_id, texto in saidas.items():
        assert "não declarado" not in texto, f"marcador sobrou no template {template_id}"
        assert "não verificado" not in texto, f"marcador sobrou no template {template_id}"


def test_notices_tem_as_tres_atribuicoes_e_nao_inventa_licenca():
    """O arquivo de licenças cita as três fontes e é honesto sobre a terceira."""
    texto = (RAIZ / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "DMS-ranil/Profile-Templetes" in texto
    assert "morgan-mordata/morgan-mordata" in texto
    assert "Jenesyx/pretty-github" in texto
    assert "MIT" in texto
    # A terceira referência não declara licença reconhecível: o arquivo assume isso.
    assert "NOASSERTION" in texto
    assert "nenhum arquivo" in texto.lower()


def test_readme_do_projeto_aponta_para_as_licencas():
    """O README tem a seção obrigatória de licenças de terceiros."""
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")

    assert "## Licenças de Terceiros" in texto
    assert "THIRD_PARTY_NOTICES.md" in texto
    assert "## Templates visuais" in texto
