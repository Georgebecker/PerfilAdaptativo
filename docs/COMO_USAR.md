# Como usar o PerfilAdaptativo

Guia do fluxo completo: coletar, importar, gerar, visualizar, aprovar e publicar.
Todo comando roda da raiz do projeto e precisa das dependências instaladas
(`pip install -r requirements.txt`).

## O caminho em sete passos

```bash
python perfil.py iniciar                          # 1. pergunta os seus dados
python perfil.py importar --github seu-usuario    # 2. traz o que o GitHub já sabe
python perfil.py validar                          # 3. confere e mostra o que falta
python perfil.py gerar                            # 4. escreve README + gráficos
python perfil.py preview --abrir                  # 5. vê no navegador, como no GitHub
python perfil.py aprovar --etapa 1                # 6. dados revisados
python perfil.py aprovar --etapa 2                #    texto final aprovado
python perfil.py publicar --confirmar             # 7. envia ao GitHub
```

Nenhum passo é obrigatório na ordem além de 1→4 (precisa de perfil para gerar) e
5/6→7 (publicar exige as duas aprovações válidas para **exatamente** o conteúdo
atual).

## O que cada comando faz

| Comando | Faz | Nunca faz |
|---|---|---|
| `iniciar` | Entrevista guiada; **lê a conta pública do GitHub** e oferece os repositórios para confirmar; grava em `data/processed/perfil.yaml` e já gera o README | Não pergunta senha, token nem chave, e recusa resposta com essa cara; não inclui repositório sem sua confirmação |
| `importar` | Baixa perfil e repositórios públicos do GitHub; mescla sem apagar o que você escreveu | Não apaga projeto existente nem inventa estágio |
| `validar` | Mostra resumo, completude e laudo (erros e avisos) | Não grava nada |
| `gerar` | Valida, mede, desenha gráficos, grava `saidas/README.md` e `saidas/relatorio.json` | Não consulta a rede com `--offline` |
| `preview` | Serve a página local em `http://127.0.0.1:8765` (ou grava `.html` com `--html`) | Não expõe a máquina: escuta só 127.0.0.1 |
| `aprovar --etapa 1` | Registra o aceite dos dados | Não publica nada |
| `aprovar --etapa 2` | Registra o aceite do texto final | Não publica nada |
| `status` | Resume perfil, completude e estado das aprovações | — |
| `publicar --confirmar` | Envia README + gráficos ao repositório de perfil | Não envia sem duas aprovações válidas nem sem token |

## De onde vêm os projetos e as datas

Você informa o usuário do GitHub; o resto o programa busca:

1. **Ao coletar (`iniciar`)** — lê a conta pública, lista os repositórios com nome,
   linguagem e descrição e pergunta se quer incluir todos ou escolher por número.
   Fork e repositório arquivado ficam fora.
2. **Ao gerar (`gerar`)** — para repositório da própria conta, consulta a API para
   atualizar a data. Quando a cota de 60 consultas/hora acaba (HTTP 403), usa o
   **feed de commits** (`/commits/HEAD.atom`), público e fora dessa cota.
3. **Sempre** — a data descoberta é gravada no perfil: `gerar --offline` continua
   mostrando a data real, e a segunda geração não repete as consultas.

O que a API **não** sabe continua em branco: `status` (publicado, MVP, rascunho) e
"o que o projeto prova" quando o repositório não tem descrição. Esses dois você
completa rodando `iniciar` de novo (Enter mantém o que já está lá).

Flags úteis do `iniciar`:

- `--sem-importar` — não lê a conta; cadastro manual, como antes.
- `--max N` — quantos repositórios oferecer (padrão: 12).
- `--offline` — nada de rede, nem na coleta nem na geração.

## Templates visuais

O visual do README é escolhido por `--template`, com o catálogo em
`config/templates.yaml`:

| id | visual |
|---|---|
| `minimal` (padrão) | tabelas, listas e badges discretos |
| `dark-terminal` | banner de terminal, badges fortes e bloco `console` |
| `animated` | cabeçalho centralizado, banner animado e cartões em citação |

```bash
python perfil.py gerar --template dark-terminal
python generate.py --offline --template animated
python perfil.py iniciar          # num terminal, mostra o menu numerado
```

Sem `--template`: em terminal interativo aparece o menu; em script ou pipe, o
padrão `minimal` é usado com aviso no log. Template inexistente gera erro com a
lista dos válidos — nunca arquivo vazio.

Os três recebem o mesmo contexto (nome, bio, projetos, gráficos): mudar de
visual muda a arrumação, nunca o dado. Banner e gráficos são SVG gerados pela
ferramenta; nenhum arquivo de terceiro é copiado. As referências de estilo e o
status de licença de cada uma estão em `THIRD_PARTY_NOTICES.md`.

## Estatísticas e Conquistas

Duas seções que nascem dos dados, nunca de texto solto:

**Estatísticas** — tabela com o que o perfil permite medir: projetos, destaques,
tecnologias distintas, projetos com descrição, links verificados, estrelas informadas
pelo GitHub, atualizados nos últimos 90 dias e completude do cadastro. Métrica sem
base não entra, e perfil sem projeto não gera a seção.

**Conquistas** — duas origens:

1. **Declaradas por você** (certificação, prêmio, formação) — campo `conquistas` do
   perfil ou a pergunta da entrevista, separando por `;`. O programa nunca inventa.
2. **Marcos medidos** — só quando atingidos, e sempre com o número ao lado: "Dez
   projetos no portfólio — 12 no total". Aparece apenas o maior marco alcançado;
   listar 1, 3, 5 e 10 ao mesmo tempo repetiria o mesmo número quatro vezes.

```yaml
conquistas:
  - "Certificação em Análise de Dados — SENAI"
  - "Prêmio de inovação interna 2025"
```

## O arquivo do perfil

Fica em `data/processed/perfil.yaml` (pasta ignorada pelo git). Formato mínimo:

```yaml
versao: 1
nome: Ana Exemplo
github: ana-exemplo
bio: "Python, dados e automação"
local: Florianópolis/SC
site: https://ana.example.com

links:
  - rotulo: LinkedIn
    url: https://www.linkedin.com/in/ana-exemplo

projetos:
  - repo: exemplo-etl
    destaque: true
    prova: "Pipeline que baixa indicadores públicos e grava em SQLite"
    stack: ["Python", "ETL", "SQLite"]
    status: publicado
```

Regras do arquivo:

- `nome` e `github` são obrigatórios; o resto é opcional e vira "não declarado".
- `projetos` pode ficar vazia: o README sai só com a apresentação e cresce depois.
- `repo` aceita `meu-projeto`, `fulano/meu-projeto` ou a URL completa.
- `stack` aceita lista ou texto com vírgulas; a comparação ignora maiúsculas.
- `status` é texto livre (`publicado`, `MVP`, `rascunho`); vazio vira "não declarado".
- Duplicata de repositório é removida com aviso — nunca duplicada em silêncio.

O perfil antigo (`config/projects.yaml`, chaves em inglês) continua legível: pode
apontar `--perfil config/projects.yaml` e o leitor traduz os campos.

## O visualizador local

```bash
python perfil.py preview                 # serve saidas/README.md
python perfil.py preview --gerar         # regera antes de servir
python perfil.py preview --porta 8899    # outra porta
python perfil.py preview --tema escuro   # já abre no tema escuro
python perfil.py preview --html saidas/preview.html --tema claro   # arquivo para dois cliques
```

O que a página mostra:

- **Cabeçalho que imita o GitHub** — marca, `usuario/repositorio`, selo "Público",
  botões Estrela e Fork e as abas (Código, Issues, Pull requests, Ações, Projetos,
  Wiki, Segurança, Insights). Tudo isso é ilustrativo: nada é clicável, exceto o
  botão de tema e o link do Markdown cru.
- **Tema claro/escuro em um clique** — o botão na faixa troca as cores na hora e
  lembra a escolha; sem escolha, segue a preferência do sistema operacional. Também
  dá para fixar por link: `http://127.0.0.1:8765/?tema=claro`.
- **`/raw`** — o Markdown exatamente como está no arquivo.
- **`/graficos/*.svg`** — os gráficos gerados, servidos da pasta de saída.
- **Tela estreita** — a tabela de projetos ganha rolagem própria em vez de empurrar a
  página inteira para o lado.

A página é regenerada a cada F5 (lê o arquivo do disco), então dá para editar o
README no editor e só recarregar. As telas capturadas estão em
[`TELAS.md`](TELAS.md).

## Dupla aprovação, sem atalho

O registro fica em `data/processed/aprovacoes.json` e guarda três digitais
(SHA-256): README, perfil e gráficos.

- A **etapa 1** é a revisão dos dados ("o que vai aparecer").
- A **etapa 2** é a revisão do texto final ("como vai aparecer").
- Conteúdo diferente do aprovado zera as duas: regeerar o README, mudar um campo do
  perfil ou alterar um gráfico invalida a aprovação anterior.
- Repetir a mesma etapa não conta duas vezes.
- `publicar` sem `--confirmar` só mostra o estado e sai com código 1.

Se `status` disser "o README ou o perfil mudou depois da aprovação", basta aprovar
de novo as duas etapas depois de revisar a mudança.

## Publicação

```bash
# token na variável de ambiente do usuário (nunca em arquivo)
segredos.ps1 -Definir GITHUB_TOKEN

python perfil.py publicar --confirmar
python perfil.py publicar --confirmar --repo usuario/usuario --caminho README.md
```

- O destino padrão é `usuario/usuario` — o repositório especial de perfil do GitHub.
  Ele precisa existir (crie no GitHub com o mesmo nome do seu usuário).
- Vão junto o `README.md` e cada `graficos/*.svg`, porque o texto referencia as
  imagens por caminho relativo. Sem eles, a imagem apareceria quebrada.
- Erros têm explicação em português: token sem permissão (401/403), repositório
  ausente (404) e conflito de gravação (409/422).
- Se o README subir e um gráfico falhar, a mensagem diz exatamente isso e manda
  repetir a publicação para completar.

## Privacidade e segredos

- O perfil vive em `data/processed/` e as saídas em `saidas/` — as duas pastas estão
  no `.gitignore`.
- Nenhum arquivo guarda valor de chave. O token do GitHub é lido da variável de
  ambiente no momento do upload.
- O programa recusa senha, token e chave em qualquer campo, na coleta, na validação
  e na hora de gravar. A mensagem de recusa diz o tipo de segredo e o campo, nunca o
  valor.
- O servidor de pré-visualização escuta só `127.0.0.1` e não lista diretórios.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `perfil não encontrado` | Rode `python perfil.py iniciar` ou aponte `--perfil` |
| `falta o usuário do GitHub` | Edite o YAML ou rode `iniciar` de novo (Enter mantém o resto) |
| `publicação bloqueada` | Leia o motivo em `status`; normalmente faltam aprovações válidas |
| `falta o token do GitHub` | `segredos.ps1 -Definir GITHUB_TOKEN` e abra um terminal novo |
| `não consegui abrir a porta` | Use `--porta 8899` |
| Imagem de gráfico quebrada no GitHub | Publique de novo: os SVGs viajam junto com o README |
| Acentos estranhos no terminal | Saída é UTF-8; em console antigo use Windows Terminal |
