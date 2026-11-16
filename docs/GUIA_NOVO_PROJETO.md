# Guia — criar um projeto a partir desta base

Esta base (`projeto_loop`) é o modelo dos projetos novos. Copie os arquivos de
estrutura, mas nunca copie `.env`, `.venv`, dados locais ou arquivos do Git.

## Atenção ao gerador da base

O gerador `scripts\criar_projeto_base.ps1`, no repositório de origem, copia o `.env`
local da base. Não o execute até que esse comportamento seja corrigido. Depois de
criar a pasta de destino, gere os arquivos de ambiente usando o modelo seguro:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.copilot\templates\env\novo-env.ps1" -Destino "D:\Projetos\projeto_x"
```

O destino precisa existir. O modelo cria `.env` e `.env.example`, define
`PROJETO_NOME` pelo nome da pasta e garante que `.env` seja ignorado pelo Git.

## Estrutura que acompanha a base

| Item | Vai para o Git? |
|---|---|
| `README.md`, `LICENSE`, `.gitignore`, `.gitattributes`, `requirements.txt` | Sim |
| `.env.example` | Sim, sem valores de segredo |
| `.env` | Não |
| `.githooks/`, `.github/`, `meu-loop-agente/` | Sim |
| `docs/REGRAS_DE_OURO.md` e este guia | Sim |
| `data/` e `notebooks/` | Só os arquivos `.gitkeep` |
| `.venv/`, dados locais, logs e caches | Não |

## Conferência

Na pasta do projeto, confirme a proteção antes de qualquer commit:

```powershell
git check-ignore -v .env
git config core.hooksPath
git status --short
```

O primeiro comando deve confirmar que `.env` está ignorado; o segundo deve mostrar
`.githooks`. Confira também que `.env` não aparece no stage. Nunca use `git add -f`
em arquivo de ambiente.
