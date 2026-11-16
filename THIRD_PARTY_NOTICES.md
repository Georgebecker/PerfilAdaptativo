# Licenças de terceiros — PerfilAdaptativo

Este projeto distribui **três templates de README** em `templates/`. Os três são
**desenhos originais**, escritos para este repositório, sob a licença MIT do
projeto (ver `LICENSE`). Nenhum arquivo de terceiro foi copiado, colado ou
adaptado linha a linha.

Os repositórios abaixo foram **referência de estilo** (ideia de layout, tom,
organização de seção). Ideia de layout não é obra protegida; código e texto são.
Por isso a atribuição aparece aqui mesmo quando nada foi reutilizado: dar crédito
a quem inspirou é parte de trabalhar em público.

## 1. DMS-ranil/Profile-Templetes — referência do template `minimal`

- Repositório: <https://github.com/DMS-ranil/Profile-Templetes>
- Licença declarada: **MIT** (confirmada na API do GitHub em 16/11/2026)
- Uso neste projeto: referência de estilo para `templates/minimal/profile.md.j2`
  (tabela simples, badges básicos, seção de projetos em lista).
- Conteúdo reutilizado: **nenhum arquivo**. Template escrito do zero.

Texto da licença MIT do projeto de referência (aplicável ao material original
dele, não ao nosso):

```text
MIT License

Copyright (c) os autores de DMS-ranil/Profile-Templetes

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

> Se algum dia você adaptar um arquivo do repositório original, copie também o
> aviso de copyright exato que está lá dentro — o texto acima é o modelo padrão,
> e o titular real consta no arquivo `LICENSE` de origem.

## 2. morgan-mordata/morgan-mordata — referência do template `dark-terminal`

- Repositório: <https://github.com/morgan-mordata/morgan-mordata>
- Licença declarada: **MIT** (confirmada na API do GitHub em 16/11/2026)
- Uso neste projeto: referência de estilo para
  `templates/dark-terminal/profile.md.j2` (estética de terminal, bloco de
  console, cores fortes).
- Conteúdo reutilizado: **nenhum arquivo**. Banner e template são gerados por
  `perfil_adaptativo/graficos.py` com os dados do próprio perfil.

Texto da licença MIT do projeto de referência (idem acima quanto ao titular):

```text
MIT License

Copyright (c) os autores de morgan-mordata/morgan-mordata

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 3. Jenesyx/pretty-github — referência do template `animated`

- Repositório: <https://github.com/Jenesyx/pretty-github>
- Licença declarada: **não confirmada**. A API do GitHub devolve
  `NOASSERTION` (não reconheceu licença padrão) em 16/11/2026.
- Uso neste projeto: apenas a **ideia geral** de layout colorido com animação e
  destaque para projetos. Nenhum arquivo, trecho, texto ou SVG foi copiado.
- Conteúdo reutilizado: **nenhum**, justamente por falta de licença clara. O
  banner animado é desenhado por `graficos.gerar_banner(animado=True)`.

### Por que este terceiro item não traz o texto MIT

Colocar um texto de licença que o repositório de origem não declara seria
inventar permissão — e permissão inventada não protege ninguém. Se o autor
publicar a licença (MIT ou outra) e você quiser **reutilizar** material dele,
atualize este arquivo com o texto exato e o aviso de copyright do repositório
antes de copiar qualquer coisa.

## Resumo

| Template | Referência de estilo | Licença da referência | Arquivo copiado? |
|---|---|---|---|
| `minimal` | DMS-ranil/Profile-Templetes | MIT | Não |
| `dark-terminal` | morgan-mordata/morgan-mordata | MIT | Não |
| `animated` | Jenesyx/pretty-github | não declarada | Não |

Dúvida sobre atribuição? Abra uma Issue — prefiro corrigir o crédito a deixar
alguém sem reconhecimento.
