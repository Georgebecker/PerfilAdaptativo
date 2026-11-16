"""
perfil_adaptativo — ferramenta que transforma a curadoria de um perfil em README.

O nome do pacote diz o que ele faz: em vez de um README escrito à mão para uma
pessoa só, cada peça aqui é adaptativa — recebe os dados do dono do perfil,
confere, mede, gera o texto e deixa a pessoa ver o resultado antes de qualquer
publicação.

Como as peças se encaixam (da esquerda para a direita, como uma linha de montagem):

    seguranca -> modelo -> coleta -> analise -> render -> preview -> aprovacao

- `seguranca`: barreira que recusa senha, token e chave em qualquer campo.
- `modelo`: formato do perfil, normalização e validação.
- `coleta`: entrevista que preenche o perfil com o que o usuário sabe.
- `analise`: programa que trata os dados novos e mede o que chegou.
- `render`: monta o Markdown do README a partir dos dados já mastigados.
- `preview`: mostra o README renderizado localmente, como o GitHub mostraria.
- `aprovacao`: exige dois aceites antes de liberar o upload.

Nada aqui grava valor de chave: a chave do GitHub, quando existir, vive na
variável de ambiente do usuário e só é lida no momento do upload.
"""

__version__ = "1.0.0"
