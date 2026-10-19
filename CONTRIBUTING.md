# Como contribuir

## Branches

- `main` só recebe merge da `develop` ao fim de cada marco.
- Ninguém faz push direto em `main` nem em `develop`.
- Cada tarefa fica em uma branch criada a partir da `develop`, com um dos
  prefixos: `feat/...`, `fix/...`, `docs/...`, `test/...`, `chore/...`.

## Commits

Conventional Commits, com o tipo em inglês e a descrição em português.

```
feat: adiciona cadastro de usuário
```

## Antes do merge request

No back-end:

```
ruff check
ruff format --check
pytest
```

No front-end:

```
npm run lint
npm run format:check
npm run build
```

## Merge request

- Sempre para a `develop`.
- Precisa da aprovação de um colega antes do merge.

## Protocolo

Mudança em [docs/protocolo.md](docs/protocolo.md) só com acordo dos três, em
merge request próprio, antes de qualquer código que dependa dela.

## Segredos

Segredos nunca entram no Git. O `.env` fica fora do repositório e toda variável
nova entra no `.env.example` com valor de exemplo.
