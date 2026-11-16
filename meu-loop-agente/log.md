# Log de Iterações — Loop Engineering

> O agente escreve aqui. Uma entrada por iteração, com hipótese, arquivos alterados,
> métrica antes/depois, melhoria, comandos e decisão (ACEITO ou REJEITADO).
> Para adicionar automaticamente: comando `registrar` do verificador.

## Iteração 1 — gerador de README de portfólio

- **Hipótese**: um gerador único (curadoria em YAML + metadados da API do GitHub)
  mantém o README do portfólio sempre atualizado sem trabalho manual, e a data real
  de cada repositório substitui informação que envelhece.
- **Arquivos alterados**: `generate.py`, `config/projects.yaml`,
  `templates/profile.md.j2`, `tests/test_generate.py`,
  `.github/workflows/update-readme.yml`, `requirements.txt`, `.env.example`,
  `README.md`, `README.profile.md`, `NOTES.md`
- **Métrica antes**: 0 de 9 repositórios com data de atualização no README;
  0 testes automatizados; atualização do README manual.
- **Métrica depois**: 9 de 9 repositórios com link confirmado e data real
  (`DD/MM/AAAA`); 15 testes verdes em 0,44 s; atualização diária automatizada.
- **Melhoria**: informação de data saiu de "inexistente" para "9/9 verificada";
  regressão de formatação e vazamento de token agora são pegas por teste.
- **Comandos passaram**: Sim (`python generate.py --offline`, `python generate.py`,
  `python -m pytest -q`).
- **Decisão**: ACEITO
- **Data/hora**: 2026-11-16T08:25:00Z

<!-- Exemplo de entrada (o comando `registrar` gera neste formato):

## Iteração 1
- **Hipótese**: substituir a biblioteca `moment.js` por `date-fns`
- **Arquivos alterados**: `workspace/lib/date.ts`, `workspace/package.json`
- **Métrica antes**: 312 kB
- **Métrica depois**: 298 kB
- **Melhoria**: 4.49%
- **Comandos passaram**: Sim
- **Decisão**: ACEITO
- **Data/hora**: 2026-09-11T21:00:00Z

-->

## Iteração 2 — perfil adaptativo para qualquer usuário

- **Hipótese**: transformar o gerador de um perfil único em ferramenta adaptativa
  (coleta, importação do GitHub, validação, gráficos, visualizador local e dupla
  aprovação) aumenta a cobertura de usuários sem perder a regra de integridade —
  e, com o visualizador, a pessoa vê o resultado antes de publicar.
- **Arquivos alterados**: `perfil.py`, `perfil_adaptativo/` (seguranca, modelo,
  coleta, importacao, analise, graficos, render, preview, aprovacao),
  `templates/perfil_github.md.j2`, `examples/perfil.exemplo.yaml`,
  `tests/test_perfil_adaptativo.py`, `tests/test_generate.py`, `generate.py`,
  `requirements.txt`, `.env.example`, `.github/workflows/` (troca do commit diário
  por CI), `README.md`, `NOTES.md`, `docs/COMO_USAR.md`
- **Métrica antes**: 1 usuário possível (curadoria fixa em `config/projects.yaml`);
  0 caminho de publicação com trava; 0 pré-visualização; 15 testes.
- **Métrica depois**: qualquer usuário (entrevista + importação + YAML); publicação
  só com 2 aprovações ligadas a 3 digitais SHA-256; pré-visualização local com tema
  claro/escuro e gráficos SVG; 49 testes verdes em 2,5 s.
- **Melhoria**: de 15 para 49 testes (+34); de 0 para 2 canais de entrada de dados;
  de 0 para 2 aprovações obrigatórias antes do upload.
- **Comandos passaram**: Sim (`python -m pytest -q`,
  `python perfil.py gerar --offline`, `python perfil.py preview --html`).
- **Decisão**: ACEITO
- **Data/hora**: 2026-11-16T15:05:00Z

## Iteração 3 — três templates visuais com catálogo

- **Hipótese**: separar o visual do conteúdo (catálogo em `config/templates.yaml` e
  três templates originais) permite escolher a aparência sem arriscar o dado, e uma
  única linha de montagem (`gerador.py`) evita que `generate.py` e `perfil.py`
  produzam READMEs diferentes para o mesmo perfil.
- **Arquivos alterados**: `config/templates.yaml`, `templates/minimal|dark-terminal|animated/profile.md.j2`,
  `perfil_adaptativo/templates_visuais.py`, `perfil_adaptativo/gerador.py`,
  `perfil_adaptativo/render.py`, `perfil_adaptativo/graficos.py` (banner),
  `perfil_adaptativo/modelo.py` (nome de exibição com aviso), `generate.py`,
  `perfil.py`, `THIRD_PARTY_NOTICES.md`, `README.md`, `NOTES.md`,
  `docs/COMO_USAR.md`, `tests/test_templates.py`
- **Métrica antes**: 1 visual; 0 validação de catálogo; 49 testes.
- **Métrica depois**: 3 visuais validados por catálogo (menu em terminal, padrão com
  aviso em script); 0 arquivo de terceiro copiado; 64 testes verdes em 3,6 s.
- **Melhoria**: de 49 para 64 testes (+15); de 1 para 3 visuais; banner SVG animado
  gerado pela própria ferramenta.
- **Comandos passaram**: Sim (`python -m pytest -q`,
  `python perfil.py gerar --template dark-terminal --offline`,
  `python generate.py --offline --template animated`).
- **Decisão**: ACEITO
- **Data/hora**: 2026-11-16T15:40:00Z

## Iteração 4 — capturas de tela do visualizador

- **Hipótese**: documentar o visualizador com capturas reais (em vez de descrevê-lo)
  prova que a pré-visualização funciona e, ao capturar em dois temas e em tela estreita,
  revela defeitos que o teste automatizado não vê.
- **Arquivos alterados**: `docs/img/` (9 PNGs), `docs/TELAS.md`, `README.md` (seção de
  telas + limitações), `NOTES.md` (item 4), `perfil_adaptativo/preview.py`
  (tema por URL, `--tema`, tabela rolável), `perfil.py` (flag `--tema`),
  `tests/test_perfil_adaptativo.py`
- **Métrica antes**: 0 capturas; 2 defeitos invisíveis (tema não escolhível por link,
  tabela estourando a largura em tela estreita); 67 testes.
- **Métrica depois**: 9 capturas (piso do projeto é 5, teto sem consultar o dono é 10);
  2 defeitos corrigidos com teste; 67 testes verdes em 4,2 s.
- **Melhoria**: interface agora documentada e comprovada; 0 para 9 imagens; 2 correções
  de layout/tema descobertas pela própria documentação.
- **Comandos passaram**: Sim (`python -m pytest -q`, captura via Chrome headless nos dois
  temas, `perfil.py preview --html --tema claro`).
- **Decisão**: ACEITO
- **Data/hora**: 2026-11-16T15:55:00Z

## Iteração 5 — a coleta lia a conta? Não. Agora lê.

- **Hipótese**: preencher o portfólio com os repositórios públicos da conta (que o
  programa já conhece pelo usuário do GitHub) elimina a digitação manual e evita o
  README sair sem projeto nenhum — e, quando a cota da API acaba, uma segunda rota
  (feed de commits) mantém a coluna de data verdadeira.
- **Problema encontrado**: perfil real gerado com 12 links e **zero projetos**; e a
  data de atualização caía para "não declarado" porque o import descartava `pushed_at`.
- **Estratégias tentadas**: (1) esperar o reset da cota — 40 min, descartada; (2) ler
  repositórios locais — cobriria 3 de 12; (3) **feed Atom de commits** — funcionou,
  devolve ISO do último commit, sem consumir cota.
- **Arquivos alterados**: `perfil_adaptativo/coleta.py` (busca e escolha dos públicos),
  `perfil_adaptativo/importacao.py` (`listar_publicos`, `projetos_a_partir_de`,
  `data_da_ultima_atualizacao`, merge que completa campo vazio), `perfil_adaptativo/analise.py`
  (duas rotas + disjuntor), `perfil_adaptativo/modelo.py` (`atualizado_em`, `template`),
  `perfil.py` (flags `--sem-importar`, `--max`; template lembrado; datas persistidas),
  testes, `README.md`, `docs/COMO_USAR.md`, `NOTES.md`
- **Métrica antes**: perfil real com 0 projeto e 0 data; 12 linhas de link manual.
- **Métrica depois**: 12 projetos e 12 datas reais; geração online de 0,7 s (sem
  repetir consultas); 85 testes verdes em 5,7 s (eram 80).
- **Melhoria**: manuais → automáticos em 12 projetos e 12 datas; +5 testes; 1 defeito
  de vitrine corrigido (destaques sem descrição).
- **Comandos passaram**: Sim (`python -m pytest -q`, `perfil.py gerar`,
  `perfil.py gerar --offline`, `perfil.py validar`).
- **Decisão**: ACEITO
- **Data/hora**: 2026-11-16T18:00:00Z

## Iteração 6 — sem marcador de ausência; estatísticas e conquistas

- **Hipótese**: remover "não declarado" do documento final (o marcador fala da
  extração, não do projeto) e substituir por seções medidas — Estatísticas e
  Conquistas — deixa o README mais honesto e mais informativo ao mesmo tempo.
- **Arquivos alterados**: `perfil_adaptativo/analise.py` (`_sem_marcador`, coluna
  `meta`), `perfil_adaptativo/estatisticas.py` (novo), `perfil_adaptativo/modelo.py`
  (`conquistas`, `estrelas`), `perfil_adaptativo/importacao.py` (estrelas no import e
  no merge), `perfil_adaptativo/coleta.py` (pergunta de conquistas),
  `perfil_adaptativo/render.py` (contexto), `templates/*/profile.md.j2` +
  `templates/parciais/` (estatísticas e conquistas), `perfil.py`, testes, docs
- **Métrica antes**: 17 marcadores "não declarado" no README real; 0 seções de
  estatística e de conquista; 85 testes.
- **Métrica depois**: 0 marcadores; 8 estatísticas medidas e 2 conquistas honestas;
  93 testes verdes em 5,8 s.
- **Melhoria**: 17 → 0 marcadores; +2 seções; +8 testes.
- **Comandos passaram**: Sim (`python -m pytest -q`, `perfil.py gerar --offline`,
  `perfil.py importar`).
- **Decisão**: ACEITO
- **Data/hora**: 2026-11-16T18:35:00Z
