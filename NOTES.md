# NOTES — decisões do PerfilAdaptativo

Registro das decisões que não são óbvias pelo código. Cada uma diz o motivo,
para que ninguém "conserte" depois o que foi escolhido de propósito.

## 1. O README do projeto não é mais o README do perfil

**Decisão:** `README.md` documenta o **projeto**. O README de perfil é gerado em
`saidas/README.md` (e os gráficos em `saidas/graficos/`), pasta ignorada pelo git.

**Por que:** enquanto os dois eram o mesmo arquivo, qualquer varredura automática
apagava a documentação do projeto, e a documentação ficava presa a uma pessoa. Agora
o gerador escreve fora da raiz e o README do repositório só muda quando alguém muda.

**Consequência aceita:** `generate.py` (fluxo antigo, preso a `config/projects.yaml`)
passou a gravar em `saidas/` por padrão; os testes foram ajustados junto.

## 2. `include_unverified_links: false`

**Decisão:** em `--offline`, a coluna de link mostra "não verificado" em vez de montar
`https://github.com/<user>/<repo>`.

**Por que:** a regra de integridade do projeto vale também para o link. Sem consulta à
API não há evidência de que o repositório exista, e link inventado em portfólio é pior
que link ausente.

**Exceção:** endereço **declarado no perfil** é usado como está — é palavra do dono,
não invenção do programa.

## 3. Versões fixadas no `requirements.txt` vs. ambiente local

**Decisão:** `requirements.txt` fixa `requests==2.32.3`, `Jinja2==3.1.4`,
`PyYAML==6.0.2`, `Markdown==3.7` e `pytest==8.3.3` (alvo: Python 3.11, o da Action).

**Por que:** a máquina local roda Python 3.14, onde essas versões não têm build
pronta — instalar ali exigiria compilar `PyYAML` do zero. Os testes locais rodam com
as versões já instaladas e passam; a Action usa os pins em Python 3.11.

**Consequência aceita:** duas combinações de versão em uso. Se um dia divergirem em
comportamento, a referência é a da Action.

## 4. Capturas de tela: feitas, e o que elas revelaram

**Decisão:** `docs/img/` guarda nove capturas do visualizador local, com legenda em
`docs/TELAS.md`; o README mostra as cinco que contam a história principal.

**Por que nove:** o piso do projeto é cinco (estado inicial, fluxo principal, resultado
com número, erro amigável, diferencial). As outras quatro cobrem estado vazio, Markdown
cru, o segundo template e a tela estreita. Acima de dez, a regra manda consultar o dono
— nove fica abaixo disso e cada uma tem função própria.

**Como foram feitas:** Chrome headless com `--window-size` fixo, sobre o perfil fictício
`examples/perfil.exemplo.yaml`. Nada foi montado à mão; a única edição foi o recorte do
gráfico, para não gastar espaço com área vazia.

**Duas correções que as capturas forçaram** (motivo de valerem o trabalho):

1. **Tema escolhido pela URL.** O navegador headless segue o tema do sistema, então
   documentar os dois temas exigiria forjar imagem. Em vez disso, o servidor passou a
   aceitar `?tema=claro|escuro` e o `--tema` fixa o tema no `.html` exportado. O script
   respeita o valor já presente no `<html>` e cai no `localStorage`/sistema só quando
   nada foi fixado.
2. **Tabela com rolagem própria.** Na captura de tela estreita, a tabela de seis colunas
   esticava o documento e cortava o texto ao lado. Agora cada `<table>` é envolvida por
   `.tabela-rolavel` (`overflow-x: auto`): a rolagem fica dentro da caixa da tabela, sem
   arrastar o cabeçalho junto.

**Limite declarado:** as imagens são de um ambiente (Windows + Chrome headless). Outro
navegador pode espaçar tabela e badge de forma levemente diferente; o HTML é o mesmo.

## 5. Um leitor, dois formatos: o perfil antigo continua válido

**Decisão:** `modelo.de_dicionario` aceita o formato novo em português (`nome`,
`projetos`, `prova`, `destaque`) e o antigo em inglês (`github_user`, `projects`,
`proof`, `featured`), por meio de apelidos de campo.

**Por que:** migrar dado de pessoa é o jeito mais fácil de perdê-lo. Com apelidos, o
`config/projects.yaml` atual continua gerando README sem edição manual, e quem começa
hoje usa o formato em português.

## 6. Zero projeto é aviso, não erro

**Decisão:** um perfil sem projetos é válido; o README sai com a apresentação e uma
seção explicando que ainda não há projeto.

**Por que:** o documento **começa zerado e cresce**. Transformar "ainda não cadastrei"
em erro impediria a primeira geração justamente de quem acabou de criar o perfil.

## 7. Dupla aprovação amarra três digitais, não uma

**Decisão:** o registro de aprovação guarda SHA-256 do README, do perfil normalizado e
do conjunto de gráficos. Qualquer mudança em qualquer um dos três zera as etapas.

**Por que:** aprovar texto e publicar imagem diferente seria furar o próprio lacre.
A digital do conjunto leva o **nome** do arquivo junto do conteúdo, então renomear um
gráfico também invalida.

**Limite declarado:** é detecção de mudança, não assinatura criptográfica. Quem tem
acesso à máquina pode editar o registro; a proteção é contra erro e esquecimento.

## 8. Gráficos em SVG gerados pelo próprio Python

**Decisão:** `graficos.py` desenha SVG de barras com a biblioteca padrão.

**Alternativas descartadas:** Mermaid (não renderiza na pré-visualização local sem
JavaScript externo), print de tela (envelhece e não escala), serviço de imagem
(terceiro no caminho, quebra quando o serviço cai).

**Por que SVG:** é texto, é pequeno, escala sem perder nitidez, o GitHub exibe como
imagem e o mesmo arquivo pode ser servido localmente em `/graficos/*.svg`. O bloco de
estilo interno usa `prefers-color-scheme`, então o gráfico acompanha o tema do GitHub.

## 9. Tema claro/escuro em um clique, sem servidor

**Decisão:** o botão de tema e o script que lembra a escolha viajam **dentro** da
página gerada, com `localStorage` e `prefers-color-scheme` como padrão.

**Por que:** o `.html` exportado precisa funcionar aberto com dois cliques (`file://`),
onde não há servidor para guardar estado. Cores ficam em variáveis CSS; trocar de tema
é redefinir variáveis, não reescrever a folha de estilo.

## 10. A pré-visualização imita o GitHub — de propósito, e sem copiar desenho alheio

**Decisão:** o cabeçalho tem marca, `usuario/repositorio`, selo "Público", botões
Estrela/Fork e as abas do repositório, tudo ilustrativo e com `title` explicando cada
peça. Os ícones são SVG próprios, desenhados para este projeto.

**Por que:** quem nunca publicou um README não sabe onde o texto aparece nem o que é
"fork". A simulação ensina a anatomia da página. Nada é clicável (exceto o tema e o
Markdown cru) para não prometer navegação que não existe.

## 11. Fim do commit automático do README

**Decisão:** o workflow diário que regerava e commitava `README.md` foi substituído por
uma esteira de testes + geração do exemplo offline, com os arquivos como artefato.

**Por que:** publicação automática contradiz a regra central do projeto — local
primeiro, dois aceites e só então upload. Além disso, o commit diário apagaria a
documentação do projeto.

## 12. Segredo é recusado em três portas

**Decisão:** `seguranca.verificar_campos` roda na coleta (a cada resposta), na
validação e imediatamente antes de gravar qualquer arquivo.

**Por que:** uma porta só é convite a esquecer a segunda. A mensagem sempre diz o
**tipo** de segredo e o **campo**, nunca o valor — vazar na mensagem de erro seria a
mesma coisa que gravar no arquivo.

## 13. Três visuais, um contexto só

**Decisão:** o catálogo `config/templates.yaml` é a fonte de verdade dos visuais
(`minimal`, `dark-terminal`, `animated`). Ele é lido e validado antes de renderizar;
o id inexistente gera erro com a lista dos válidos. Todos os templates recebem o
mesmo contexto — trocar de visual muda a arrumação, nunca o dado.

**Por que:** com três visuais e dois comandos, a montagem precisava existir uma vez
só. `perfil_adaptativo/gerador.py` é essa linha de montagem; `generate.py` e
`perfil.py` chamam a mesma função, então regra corrigida num lugar vale nos dois.

**Escolha do visual:** `--template` manda; sem ele, terminal interativo mostra o
menu numerado e script/pipe usa o padrão com aviso no log. Aviso importa: gerar com
visual diferente do esperado, calado, parece defeito.

**Sobre os templates de referência:** os três são desenhos originais deste projeto
(MIT). Nenhum arquivo de terceiro foi copiado. O repositório
`Jenesyx/pretty-github` **não** declara licença reconhecível (a API devolve
`NOASSERTION`), então dele só se aproveitou a ideia geral de layout — e o
`THIRD_PARTY_NOTICES.md` registra isso em vez de inventar permissão MIT que a origem
não declarou.

**Detalhe técnico:** os cartões do template `animated` usam citação Markdown
(`> ### nome`), e não tabela HTML. Markdown dentro de `<td>` não é renderizado de
forma confiável no GitHub; citação com borda dá o mesmo efeito de cartão e funciona
em qualquer renderizador. O banner animado usa SMIL (`<animate>`): anima onde há
suporte e continua legível onde não há.

## 14. A coleta lê a conta pública — e tem uma segunda rota para a data

**Decisão:** `iniciar` consulta a conta do GitHub logo depois de receber o usuário e
oferece os repositórios públicos para confirmação. A data de atualização vem da API
quando há cota e, quando a cota acaba (HTTP 403), do feed de commits
(`/commits/HEAD.atom`), que é público e não consome a cota.

**Por que:** pedir que a pessoa digite o que o GitHub publica é trabalho manual sem
motivo — o dado já existe. Confirmar antes de incluir também é necessário: há
repositório de teste e de curso que não deve entrar na vitrine.

**Por que a segunda rota:** sem token, a API permite 60 consultas por hora. Doze
projetos por geração esgotam isso em cinco gerações, e então toda consulta passa a
responder 403. O feed Atom devolve a data do último commit com o mesmo significado
prático ("quando o repositório foi mexido"), sem gastar cota. Testado na conta real:
12 datas obtidas, zero cota consumida.

**Três salvaguardas contra desperdício:**

1. disjuntor na API — duas falhas seguidas e a geração para de perguntar (evita doze
   avisos iguais);
2. data descoberta é **gravada no perfil** — a segunda geração caiu de ~12 consultas
   para 0 e levou 0,7 s;
3. a rota alternativa é independente do disjuntor: quando a API está bloqueada, é ela
   que salva a coluna de data.

**Efeito colateral aceito:** a data guardada é a do último commit, que pode ser
alguns dias anterior ao `pushed_at` da API (que conta push de qualquer branch). As
duas são evidência real; quando a API responde, ela manda.

## 15. Destaque prioriza quem tem descrição

**Decisão:** entre os repositórios importados, a vitrine (3 destaques) prefere os que
têm descrição; só depois ordena por estrela e por push recente. O visual escolhido no
`iniciar` fica gravado no perfil (`template:`) e vale nas gerações seguintes.

**Por que:** a primeira importação real colocou na vitrine três repositórios sem
descrição — a parte mais visível do README dizia "não declarado" três vezes. Vitrine
vazia é pior que vitrine menor. E quem escolheu "animated" não deve voltar ao padrão
só porque rodou `gerar` sem `--template`.

## 16. O README não escreve mais "não declarado" (nem "não verificado")

**Decisão:** campo sem dado aparece **vazio ou não aparece**. O marcador continua
existindo no código (`STATUS_SEM_EVIDENCIA_README`) e no laudo de `validar`, mas não
no documento final.

**Por que:** "não declarado" fala sobre a **extração** (o dado não veio), não sobre o
projeto. Numa tabela de portfólio, doze células assim passam impressão de descuido e
roubam atenção do que é real. Quem lê prefere a célula vazia; quem escreve descobre o
que falta no `validar`, que é o lugar certo para o diagnóstico.

**Como:** `analise._sem_marcador` converte o sentinela em texto vazio e a coluna
"Detalhes" (`meta`) junta só o que existe — tecnologia, estágio, data — em vez de
quatro colunas com buracos.

## 17. Estatísticas e conquistas saem do dado, não do texto

**Decisão:** seções novas, calculadas em `perfil_adaptativo/estatisticas.py`.

- **Estatísticas**: projetos, destaques, tecnologias distintas, projetos com
  descrição, links verificados, estrelas (só as informadas pela API), atualizados
  nos últimos 90 dias, completude. Métrica sem base não entra.
- **Conquistas**: as declaradas pela pessoa (campo `conquistas`, pergunta na
  entrevista) vêm primeiro; depois os marcos medidos, **só o maior alcançado** e
  sempre com o número que o comprova.

**Por que assim:** "estatísticas" e "conquistas" são as seções onde portfólio mente.
Aqui número é medido do perfil e conquista automática é um marco que já foi atingido —
não há texto solto do tipo "5+ anos de experiência". Conquista declarada existe porque
certificação e prêmio não são dedutíveis de repositório: só a pessoa sabe, e o
programa não inventa.

**Detalhe:** `estrelas` passou a ser guardado no projeto pela importação (era usado
só para escolher destaque). Assim a estatística sobrevive ao `--offline`.
