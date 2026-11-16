"""
preview.py — mostra o README gerado como o GitHub mostraria, mas na sua máquina.

O problema que este arquivo resolve: ler Markdown cru no editor não é o mesmo que
ver o documento pronto. Tabela desalinhada, badge quebrada e linha vazia que
"come" o título seguinte só aparecem renderizados. Antes de aprovar e publicar,
a pessoa precisa ver o que o visitante vai ver.

Duas formas de olhar, porque nem todo mundo quer servidor:
- `servir()` sobe uma página em http://127.0.0.1:<porta> (só na própria máquina);
- `salvar_html()` grava um .html que abre com dois cliques, sem servidor.

A página é montada sem buscar nada na internet: CSS e HTML viajam juntos. Assim a
pré-visualização funciona com a rede desligada — as imagens de badge, que vêm do
shields.io, só aparecem quando há conexão.

Segurança: o servidor escuta apenas 127.0.0.1 (não 0.0.0.0) e serve somente o
arquivo pedido. Não há listagem de pasta nem caminho vindo da URL.
"""

from __future__ import annotations

import html
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import modelo

# Estilo no espírito do GitHub (fonte do sistema, tabela com moldura, código com
# fundo claro). Escrito para este projeto: nada é copiado de folha de estilo
# alheia, e nenhuma fonte externa é carregada — a página abre offline.
#
# O tema é trocado por um clique: o botão na faixa grava a escolha em
# localStorage e o CSS inteiro lê variáveis. Trocar de claro para escuro é
# redefinir as variáveis em `[data-tema="escuro"]` — o resto da folha não muda,
# do mesmo jeito que trocar a lâmpada do quarto não muda os móveis de lugar.
CSS = """
:root {
  color-scheme: light;
  --texto: #1f2328;
  --suave: #59636e;
  --borda: #d1d9e0;
  --borda-suave: #e6eaef;
  --fundo: #ffffff;
  --fundo-suave: #f6f8fa;
  --zebra: #fbfcfd;
  --codigo: rgba(129, 139, 152, .12);
  --link: #0969da;
  --faixa: #24292f;
  --faixa-texto: #ffffff;
  --faixa-dica: #c3ccd6;
  --faixa-botao: #57606a;
  --faixa-hover: #30363d;
  --aviso-fundo: #fff8c5;
  --aviso-borda: #bf8700;
  --aviso-texto: #1f2328;
}
:root[data-tema="escuro"] {
  color-scheme: dark;
  --texto: #e6edf3;
  --suave: #9198a1;
  --borda: #3d444d;
  --borda-suave: #30363d;
  --fundo: #0d1117;
  --fundo-suave: #151b23;
  --zebra: #12181f;
  --codigo: rgba(110, 118, 129, .4);
  --link: #4493f8;
  --faixa: #010409;
  --faixa-texto: #e6edf3;
  --faixa-dica: #9198a1;
  --faixa-botao: #3d444d;
  --faixa-hover: #151b23;
  --aviso-fundo: #2d2611;
  --aviso-borda: #bb8009;
  --aviso-texto: #e6edf3;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--fundo);
  color: var(--texto);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.5;
}
/* ---- cabeçalho que imita a página do GitHub, para fins didáticos ---- */
.gh-topo {
  background: var(--faixa);
  color: var(--faixa-texto);
  position: sticky;
  top: 0;
  z-index: 10;
  border-bottom: 1px solid var(--borda);
}
.gh-linha {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  font-size: 14px;
  flex-wrap: wrap;
}
.gh-marca { width: 22px; height: 22px; flex: 0 0 auto; color: var(--faixa-texto); }
.gh-repo { font-weight: 600; }
.gh-sep { color: var(--faixa-dica); }
.gh-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--faixa-botao);
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 12px;
  color: var(--faixa-dica);
}
.gh-pill svg { width: 12px; height: 12px; color: currentColor; }
.gh-acoes { margin-left: auto; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.gh-botao {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--faixa-botao);
  border-radius: 6px;
  padding: 4px 10px;
  background: transparent;
  color: var(--faixa-texto);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  text-decoration: none;
}
.gh-botao svg { width: 14px; height: 14px; color: currentColor; }
.gh-botao:hover { background: var(--faixa-hover); }
.gh-botao:focus-visible { outline: 2px solid var(--link); outline-offset: 2px; }
.gh-abas {
  display: flex;
  gap: 18px;
  padding: 0 20px;
  font-size: 13px;
  color: var(--faixa-dica);
  overflow-x: auto;
}
.gh-aba {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 0 10px;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
}
.gh-aba svg { width: 14px; height: 14px; }
.gh-aba.ativa { color: var(--faixa-texto); border-bottom-color: #fd8c73; font-weight: 600; }
.gh-arquivo {
  max-width: 980px;
  margin: 20px auto 0;
  padding: 10px 16px;
  border: 1px solid var(--borda);
  border-bottom: 0;
  border-radius: 6px 6px 0 0;
  background: var(--fundo-suave);
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}
.gh-arquivo svg { width: 16px; height: 16px; color: var(--suave); }
.gh-arquivo .gh-dica { margin-left: auto; font-weight: 400; font-size: 12px; color: var(--suave); }
.gh-legenda {
  max-width: 980px;
  margin: 10px auto 0;
  padding: 0 20px;
  font-size: 12px;
  color: var(--suave);
}
@media (max-width: 640px) {
  .gh-abas { gap: 12px; }
  .gh-legenda { font-size: 11px; }
  .gh-linha { padding: 8px 12px; }
  .gh-abas { padding: 0 12px; }
  .gh-arquivo, .gh-legenda { margin-left: 8px; margin-right: 8px; }
  main { padding: 16px 12px 48px; }
  .gh-acoes { margin-left: 0; }
}
main {
  max-width: 980px;
  margin: 0 auto;
  padding: 20px 20px 64px;
  border: 1px solid var(--borda);
  border-top: 0;
  border-radius: 0 0 6px 6px;
}
@media (max-width: 1019px) { main { border-left: 0; border-right: 0; border-radius: 0; } }
.markdown-body h1, .markdown-body h2 {
  border-bottom: 1px solid var(--borda-suave);
  padding-bottom: .3em;
  margin-top: 1.6em;
  margin-bottom: .6em;
  line-height: 1.25;
}
.markdown-body h1 { font-size: 2em; margin-top: 0; }
.markdown-body h2 { font-size: 1.5em; }
.markdown-body h3 { font-size: 1.25em; }
.markdown-body p { margin: 0 0 16px; }
.markdown-body a { color: var(--link); text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body img { max-width: 100%; vertical-align: middle; }
.markdown-body ul, .markdown-body ol { padding-left: 2em; margin: 0 0 16px; }
.markdown-body li { margin: 4px 0; }
.markdown-body table { border-collapse: collapse; width: 100%; margin: 0 0 16px; font-size: 14px; }
/* A tabela de projetos tem seis colunas e nunca cabe num celular. Em vez de
   deixar a página inteira rolar de lado (o que corta o cabeçalho e esconde o
   texto), a rolagem fica dentro da caixa da tabela — como folhear um mapa na
   horizontal sem sair da mesa. */
.tabela-rolavel { overflow-x: auto; margin: 0 0 16px; }
.tabela-rolavel table { margin: 0; min-width: 560px; }
.markdown-body th, .markdown-body td { border: 1px solid var(--borda); padding: 6px 13px; }
.markdown-body th { background: var(--fundo-suave); font-weight: 600; text-align: left; }
.markdown-body tr:nth-child(2n) td { background: var(--zebra); }
.markdown-body code {
  background: var(--codigo);
  border-radius: 6px;
  padding: .2em .4em;
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 85%;
}
.markdown-body pre {
  background: var(--fundo-suave);
  border-radius: 6px;
  padding: 16px;
  overflow: auto;
  margin: 0 0 16px;
}
.markdown-body pre code { background: none; padding: 0; font-size: 85%; }
.markdown-body blockquote {
  margin: 0 0 16px;
  padding: 0 1em;
  color: var(--suave);
  border-left: .25em solid var(--borda);
}
.markdown-body hr { border: 0; border-top: 1px solid var(--borda-suave); margin: 24px 0; }
.aviso {
  max-width: 980px;
  margin: 32px auto;
  padding: 16px 20px;
  border: 1px solid var(--borda);
  border-left: 4px solid var(--aviso-borda);
  border-radius: 6px;
  background: var(--aviso-fundo);
  color: var(--aviso-texto);
}
"""

# Ícones desenhados aqui, em SVG inline: nada vem de CDN, nada depende de rede e
# o traço acompanha a cor do texto (`currentColor`) nos dois temas.
#
# São desenhos próprios e simples, com função didática: mostram onde ficam a
# marca, a estrela, o fork e as abas na página real do GitHub. Não são os
# desenhos oficiais do GitHub — e nem precisam ser: o objetivo é ensinar a
# anatomia da página, não copiar o material da empresa.
ICONES = {
    "marca": (
        '<svg class="gh-marca" viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.2"/>'
        '<path d="M4.4 4.9 5.9 6.3M11.6 4.9 10.1 6.3" stroke="currentColor" stroke-width="1.3" '
        'stroke-linecap="round"/>'
        '<circle cx="6" cy="8.3" r=".9" fill="currentColor"/>'
        '<circle cx="10" cy="8.3" r=".9" fill="currentColor"/>'
        '<path d="M6.2 10.6c1 .9 2.6.9 3.6 0" fill="none" stroke="currentColor" stroke-width="1.2" '
        'stroke-linecap="round"/></svg>'
    ),
    "globo": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<circle cx="8" cy="8" r="5.6" fill="none" stroke="currentColor" stroke-width="1.2"/>'
        '<path d="M2.6 8h10.8M8 2.6c2.6 3 2.6 7.8 0 10.8M8 2.6C5.4 5.6 5.4 10.4 8 13.4" fill="none" '
        'stroke="currentColor" stroke-width="1.2"/></svg>'
    ),
    "estrela": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<path d="M8 2.4 9.8 6l3.9.5-2.9 2.7.8 3.9L8 11.2 4.4 13.1l.8-3.9L2.3 6.5 6.2 6z" '
        'fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>'
    ),
    "garfo": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<circle cx="4" cy="3.6" r="1.7" fill="none" stroke="currentColor" stroke-width="1.3"/>'
        '<circle cx="12" cy="3.6" r="1.7" fill="none" stroke="currentColor" stroke-width="1.3"/>'
        '<circle cx="8" cy="12.4" r="1.7" fill="none" stroke="currentColor" stroke-width="1.3"/>'
        '<path d="M4 5.4v1.4c0 1 .8 1.8 1.8 1.8h4.4c1 0 1.8-.8 1.8-1.8V5.4M8 8.7v2" fill="none" '
        'stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>'
    ),
    "ponto": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.3"/>'
        '<circle cx="8" cy="8" r="2" fill="currentColor"/></svg>'
    ),
    "play": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.3"/>'
        '<path d="M6.6 5.6 10.6 8l-4 2.4z" fill="currentColor"/></svg>'
    ),
    "tabela": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<rect x="2.4" y="3.4" width="11.2" height="9.2" rx="1.2" fill="none" stroke="currentColor" '
        'stroke-width="1.3"/><path d="M2.6 6.6h10.8M6.4 6.7v5.8" fill="none" stroke="currentColor" '
        'stroke-width="1.2"/></svg>'
    ),
    "livro": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<path d="M3 3.2h6.4L12.6 6.4v6.4H3z" fill="none" stroke="currentColor" stroke-width="1.3" '
        'stroke-linejoin="round"/><path d="M9.2 3.4v3.2h3.2" fill="none" stroke="currentColor" '
        'stroke-width="1.3" stroke-linejoin="round"/></svg>'
    ),
    "escudo": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<path d="M8 2.2 13 4v4c0 3-2.2 5.3-5 6.1C5.2 13.3 3 11 3 8V4z" fill="none" '
        'stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>'
    ),
    "grafico": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<path d="M2.5 13.2h11" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>'
        '<rect x="3.6" y="8.4" width="2.2" height="3.4" fill="currentColor"/>'
        '<rect x="7" y="5.4" width="2.2" height="6.4" fill="currentColor"/>'
        '<rect x="10.4" y="7" width="2.2" height="4.8" fill="currentColor"/></svg>'
    ),
    "lua": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<path d="M11 10.2A4.8 4.8 0 0 1 5.8 4.2 4.9 4.9 0 1 0 11 10.2z" fill="none" '
        'stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>'
    ),
    "aviso": (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<path d="M8 2.6 14 12.6H2z" fill="none" stroke="currentColor" stroke-width="1.3" '
        'stroke-linejoin="round"/><path d="M8 6.4v3.1" stroke="currentColor" stroke-width="1.4" '
        'stroke-linecap="round"/><circle cx="8" cy="11.1" r=".8" fill="currentColor"/></svg>'
    ),
}

# Abas da página de repositório: só ilustração. Ficam como <span> (e não <a>)
# porque não levam a lugar nenhum — link que não abre seria pior que rótulo.
ABAS_DO_GITHUB = (
    ("ponto", "Código", True),
    ("ponto", "Issues", False),
    ("garfo", "Pull requests", False),
    ("play", "Ações", False),
    ("tabela", "Projetos", False),
    ("livro", "Wiki", False),
    ("escudo", "Segurança", False),
    ("grafico", "Insights", False),
)

# Botão de tema + memória da escolha. Vai embutido na página porque precisa
# funcionar também no arquivo .html aberto com dois cliques (file://), onde não
# existe servidor para guardar estado. A escolha vive no localStorage; quando ela
# não existe, vale a preferência do sistema operacional.
SCRIPT_DO_TEMA = """
(function () {
  var raiz = document.documentElement;
  var chave = 'perfil-adaptativo-tema';
  var botao = document.getElementById('botao-tema');
  var rotulo = document.getElementById('rotulo-tema');

  function lembrar(valor) {
    try { localStorage.setItem(chave, valor); } catch (erro) { /* file:// sem storage */ }
  }

  function lerMemoria() {
    try { return localStorage.getItem(chave); } catch (erro) { return null; }
  }

  function aplicar(tema) {
    raiz.setAttribute('data-tema', tema);
    if (rotulo) {
      // O rótulo diz o que o clique FAZ, não o estado atual: menos dúvida.
      rotulo.textContent = tema === 'escuro' ? 'modo claro' : 'modo escuro';
    }
    if (botao) {
      botao.setAttribute('aria-pressed', tema === 'escuro' ? 'true' : 'false');
      botao.title = tema === 'escuro'
        ? 'Trocar para o tema claro (um clique)'
        : 'Trocar para o tema escuro (um clique)';
    }
  }

  var salvo = lerMemoria();
  var prefereEscuro = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  // Ordem de precedência: tema fixado no HTML (?tema=) > escolha salva > sistema.
  var fixo = raiz.getAttribute('data-tema');
  aplicar(fixo || salvo || (prefereEscuro ? 'escuro' : 'claro'));

  if (botao) {
    botao.addEventListener('click', function () {
      var proximo = raiz.getAttribute('data-tema') === 'escuro' ? 'claro' : 'escuro';
      aplicar(proximo);
      lembrar(proximo);
    });
  }
})();
"""


def _importar_markdown():
    """Importa a biblioteca de Markdown com mensagem amigável quando ela falta."""
    try:
        import markdown
    except ImportError as erro:  # pragma: no cover - só acontece sem instalação
        raise modelo.ErroPerfil(
            "a pré-visualização precisa da biblioteca Markdown. "
            "Rode: pip install -r requirements.txt"
        ) from erro
    return markdown


def markdown_para_html(texto: str) -> str:
    """
    Converte Markdown em HTML com os recursos que o GitHub também entende.

    Entra: texto Markdown.
    Sai: HTML (sem o <body>, apenas o conteúdo).

    As extensões escolhidas espelham o GitHub: `extra` traz tabela, bloco de
    código com cerca, lista e nota de rodapé; `sane_lists` impede que uma lista
    engula o parágrafo seguinte; `nl2br` reproduz o README, onde cada quebra de
    linha vale um <br> — é o que mantém cada badge na sua própria linha.

    Depois da conversão, cada `<table>` ganha um contêiner com rolagem própria.
    O motivo é prático: a tabela de projetos tem seis colunas e, sem isso, num
    celular ela empurra a página inteira para o lado, cortando cabeçalho e texto.
    """
    markdown = _importar_markdown()
    html_convertido = markdown.markdown(texto, extensions=["extra", "sane_lists", "nl2br"])

    # Troca simples de tags: o python-markdown gera <table> e </table> sem
    # atributos, então não há risco de mexer em tabela de dentro de código
    # (código sai escapado como &lt;table&gt;).
    return html_convertido.replace("<table>", '<div class="tabela-rolavel"><table>').replace(
        "</table>", "</table></div>"
    )


def _tema_valido(valor: str) -> str:
    """
    Aceita apenas "claro" ou "escuro" como tema forçado pela URL.

    Entra: valor recebido em `?tema=` (pode vir vazio, com maiúsculas ou lixo).
    Sai: "claro", "escuro" ou "" (vazio = deixa o navegador decidir).

    Existir um "tema vazio" é importante: sem `?tema=`, a página continua
    seguindo a preferência do sistema operacional e a escolha salva no botão.
    """
    texto = (valor or "").strip().lower()
    return texto if texto in ("claro", "escuro") else ""


def renderizar_html(
    markdown_texto: str,
    titulo: str = "README.md",
    dica: str = "",
    repositorio: str = "usuario/usuario",
    tema: str = "",
) -> str:
    """
    Monta a página completa de pré-visualização.

    Entra: Markdown, título da aba, dica exibida junto ao arquivo, o nome do
    repositório usado no cabeçalho ilustrativo ("usuario/usuario") e o tema
    forçado ("claro", "escuro" ou vazio).
    Sai: documento HTML completo, pronto para servir ou gravar.

    O cabeçalho imita a página de repositório do GitHub de propósito: quem nunca
    subiu um README precisa reconhecer, na simulação, onde o texto vai aparecer e
    o que é "estrela", "fork" ou aba. É didático, não decorativo.

    Com `tema` preenchido, o `<html>` já nasce com `data-tema`, e o script
    respeita esse valor em vez de sobrescrever. Isso permite abrir a mesma página
    nos dois temas por link (`?tema=escuro`) — útil para captura de tela e para
    mostrar o resultado a alguém sem pedir que clique.
    """
    corpo = markdown_para_html(markdown_texto)
    momento = datetime.now().strftime("%d/%m/%Y %H:%M")
    detalhe = dica or f"pré-visualização local · gerado às {momento}"
    atributo_tema = f' data-tema="{_tema_valido(tema)}"' if _tema_valido(tema) else ""

    abas = "".join(
        f'<span class="gh-aba{" ativa" if ativa else ""}" title="aba ilustrativa: '
        f'nesta simulação nada é clicável">{ICONES[icone]}{html.escape(nome)}</span>'
        for icone, nome, ativa in ABAS_DO_GITHUB
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR"{atributo_tema}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>
<base target="_blank">
<style>{CSS}</style>
</head>
<body>
<header class="gh-topo">
  <div class="gh-linha">
    {ICONES["marca"]}
    <span class="gh-repo">{html.escape(repositorio)}</span>
    <span class="gh-pill" title="a página real mostra se o repositório é público">
      {ICONES["globo"]}Público
    </span>
    <div class="gh-acoes">
      <span class="gh-botao" title="na página real, este botão coloca o repositório na sua lista de favoritos">
        {ICONES["estrela"]}Estrela
      </span>
      <span class="gh-botao" title="na página real, este botão copia o repositório para a sua conta">
        {ICONES["garfo"]}Fork
      </span>
      <button class="gh-botao" id="botao-tema" type="button" aria-pressed="false"
              title="Trocar entre tema claro e escuro (um clique)">
        {ICONES["lua"]}<span id="rotulo-tema">modo escuro</span>
      </button>
      <a class="gh-botao" href="/raw" title="abre o README em Markdown, como está no arquivo">
        {ICONES["livro"]}Markdown cru
      </a>
    </div>
  </div>
  <nav class="gh-abas" aria-label="abas do repositório (ilustrativas)">{abas}</nav>
</header>
<div class="gh-arquivo">
  {ICONES["livro"]}
  README.md
  <span class="gh-dica">{html.escape(detalhe)}</span>
</div>
<main class="markdown-body">
{corpo}
</main>
<p class="gh-legenda">
  Simulação local: o cabeçalho imita a página de um repositório no GitHub — marca,
  nome do repositório, visibilidade, estrela, fork e abas. Nada ali é clicável,
  exceto o botão de tema e o link do Markdown cru. O texto abaixo é o seu
  <code>README.md</code> renderizado.
</p>
<script>{SCRIPT_DO_TEMA}</script>
</body>
</html>
"""


def _pagina_de_erro(mensagem: str) -> str:
    """Devolve uma página explicando o problema, em vez de um 404 seco."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><title>Pré-visualização indisponível</title>
<style>{CSS}</style></head>
<body><div class="aviso"><strong>Pré-visualização indisponível.</strong><br>
{html.escape(mensagem)}</div>
<script>{SCRIPT_DO_TEMA}</script>
</body>
</html>
"""


def _criar_handler(arquivo: Path, titulo: str, repositorio: str = "usuario/usuario") -> type[BaseHTTPRequestHandler]:
    """
    Cria o tratador HTTP que lê o README do disco a cada pedido.

    Entra: caminho do Markdown, título da página e nome do repositório exibido no
           cabeçalho ilustrativo.
    Sai: classe de tratador pronta para o servidor.

    Ler do disco a cada pedido é o que permite editar o README no editor e só
    recarregar a página para ver o efeito — sem reiniciar o servidor.
    """

    pasta_base = arquivo.parent

    def _svg_permitido(caminho: str) -> Path | None:
        """
        Resolve /graficos/algum.svg para um arquivo DENTRO da pasta de saída.

        Entra: caminho pedido pela URL.
        Sai: caminho do arquivo, ou None quando o pedido sai da pasta ou não é SVG.

        A checagem de "dentro da pasta" é a parte que importa: sem ela, um pedido
        como /graficos/../../.env leria arquivo de segredo. É o mesmo cuidado de
        conferir se a encomenda pertence ao prédio antes de entregar.
        """
        relativo = caminho.lstrip("/")
        candidato = (pasta_base / relativo).resolve()
        try:
            candidato.relative_to(pasta_base.resolve())
        except ValueError:
            return None
        if candidato.suffix.lower() != ".svg" or not candidato.is_file():
            return None
        return candidato

    class Tratador(BaseHTTPRequestHandler):
        def _responder(self, status: int, corpo: str, tipo: str) -> None:
            dados = corpo.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{tipo}; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            # no-store: o navegador não guarda a página, então F5 mostra a versão
            # mais nova do arquivo em vez de uma cópia velha do cache.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self) -> None:  # noqa: N802 (nome exigido pela biblioteca)
            partes_da_url = urlparse(self.path)
            caminho = partes_da_url.path
            consulta = parse_qs(partes_da_url.query)
            tema = _tema_valido((consulta.get("tema") or [""])[0])

            if caminho in ("/", "/index.html", "/preview"):
                if not arquivo.exists():
                    self._responder(
                        404,
                        _pagina_de_erro(
                            f"não encontrei {arquivo}. Rode 'python perfil.py gerar' antes de abrir o preview."
                        ),
                        "text/html",
                    )
                    return
                texto = arquivo.read_text(encoding="utf-8")
                self._responder(
                    200,
                    renderizar_html(texto, titulo, repositorio=repositorio, tema=tema),
                    "text/html",
                )
                return

            if caminho in ("/raw", "/README.md"):
                if not arquivo.exists():
                    self._responder(404, f"arquivo não encontrado: {arquivo}", "text/plain")
                    return
                self._responder(200, arquivo.read_text(encoding="utf-8"), "text/plain")
                return

            if caminho.startswith("/graficos/"):
                destino = _svg_permitido(caminho)
                if destino is None:
                    self._responder(404, "gráfico não encontrado", "text/plain")
                    return
                self._responder(200, destino.read_text(encoding="utf-8"), "image/svg+xml")
                return

            self._responder(404, "caminho não existe nesta pré-visualização", "text/plain")

        def log_message(self, formato: str, *args) -> None:  # noqa: A003
            # Silencia o log padrão (uma linha por requisição) para o terminal
            # mostrar só o endereço e as mensagens do próprio programa.
            return

    return Tratador


def criar_servidor(
    arquivo: Path,
    porta: int = 8765,
    host: str = "127.0.0.1",
    titulo: str = "README.md",
    repositorio: str = "usuario/usuario",
) -> ThreadingHTTPServer:
    """
    Prepara o servidor local sem começar a atender.

    Entra: arquivo Markdown, porta (0 escolhe uma livre), host, título e nome do
    repositório exibido no cabeçalho.
    Sai: servidor pronto; quem chama decide entre `serve_forever()` e uma thread.

    Deixar o servidor separado do laço é o que torna o preview testável: o teste
    sobe o servidor numa thread, faz um pedido HTTP de verdade e desliga.
    """
    servidor = ThreadingHTTPServer((host, porta), _criar_handler(arquivo, titulo, repositorio))
    servidor.daemon_threads = True
    return servidor


def salvar_html(
    arquivo_md: Path,
    arquivo_html: Path,
    titulo: str | None = None,
    repositorio: str = "usuario/usuario",
    tema: str = "",
) -> Path:
    """
    Grava a pré-visualização como arquivo .html autônomo.

    Entra: Markdown de origem, caminho do HTML, título opcional, o nome do
    repositório do cabeçalho ilustrativo e o tema ("claro", "escuro" ou vazio
    para seguir o sistema).
    Sai: caminho do HTML gravado.

    É a opção para quem não quer terminal aberto: o arquivo abre com dois
    cliques e o CSS vai embutido, então funciona sem servidor e sem rede.
    """
    if not arquivo_md.exists():
        raise modelo.ErroPerfil(f"não encontrei {arquivo_md}. Rode 'python perfil.py gerar' primeiro.")

    texto = arquivo_md.read_text(encoding="utf-8")
    pagina = renderizar_html(
        texto,
        titulo or arquivo_md.name,
        dica=f"pré-visualização local de {arquivo_md.name}",
        repositorio=repositorio,
        tema=tema,
    )
    arquivo_html.parent.mkdir(parents=True, exist_ok=True)
    arquivo_html.write_text(pagina, encoding="utf-8")
    return arquivo_html


def servir(
    arquivo: Path,
    porta: int = 8765,
    host: str = "127.0.0.1",
    abrir_navegador: bool = False,
    titulo: str = "README.md",
    repositorio: str = "usuario/usuario",
) -> None:
    """
    Sobe a pré-visualização e fica atendendo até Ctrl+C.

    Entra: arquivo Markdown, porta, host, se deve abrir o navegador, o título e o
    nome do repositório exibido no cabeçalho.
    Sai: nada (bloqueia). Levanta modelo.ErroPerfil quando a porta está ocupada.

    O endereço é mostrado por extenso antes de qualquer coisa: quem rodou precisa
    saber exatamente o que digitar no navegador.
    """
    try:
        servidor = criar_servidor(arquivo, porta=porta, host=host, titulo=titulo, repositorio=repositorio)
    except OSError as erro:
        raise modelo.ErroPerfil(
            f"não consegui abrir a porta {porta} ({erro}). "
            "Use outra porta: python perfil.py preview --porta 8899"
        ) from erro

    endereco = f"http://{host}:{servidor.server_address[1]}/"
    print(f"Pré-visualização local em {endereco}")
    print(f"Arquivo servido: {arquivo} (recarregue a página após gerar de novo)")
    print("Ctrl+C para encerrar. Nada sai desta máquina: o servidor escuta só 127.0.0.1.")

    if abrir_navegador:
        webbrowser.open(endereco)

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\npré-visualização encerrada.")
    finally:
        # Só fecha o socket: `shutdown()` esperaria o laço de `serve_forever`,
        # que já saiu — chamar as duas coisas aqui trava o programa.
        servidor.server_close()
