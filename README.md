# Jogo da Velha Multiplayer

Jogo da velha para 2 jogadores em rede, em arquitetura cliente-servidor com
comunicação em tempo real por WebSocket. Projeto da disciplina Redes de
Computadores 2.

## Stack

- Back-end: Python 3.14 + FastAPI
- Front-end: React + TypeScript + Vite
- Banco de dados: MongoDB
- Ambiente: Docker Compose

## Estrutura

- `backend/`: servidor (API REST e WebSocket)
- `frontend/`: cliente web
- `infra/`: arquivos de infraestrutura
- `docs/`: documentação do projeto

## Pré-requisitos

- Git
- Docker: Docker Desktop no Windows e no macOS; Docker Engine com o plugin
  compose no Linux
- Python 3.14, só para rodar testes e lint fora do Docker. No Linux, uma forma
  simples de instalar é `uv python install 3.14` ou o pyenv
- Node.js LTS

## Como rodar

1. Crie o arquivo `.env` a partir do exemplo, na raiz do repositório.

   Windows (cmd):

   ```
   copy .env.example .env
   ```

   Linux/macOS:

   ```
   cp .env.example .env
   ```

   Os valores do exemplo funcionam em desenvolvimento. Fora dele, troque as
   senhas e o `JWT_SECRET`.

2. Suba o MongoDB e o back-end.

   ```
   docker compose up -d --build
   ```

3. Em outro terminal, rode o front-end.

   ```
   cd frontend
   npm install
   npm run dev
   ```

Endereços:

- Front-end: http://localhost:5173
- Health check do back-end: http://localhost:8000/api/health

## Como testar

### Back-end

Os testes de integração usam o MongoDB do Docker, então deixe o
`docker compose` no ar antes de rodar o `pytest`.

Windows (cmd):

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest
```

Linux/macOS:

```
cd backend
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest
```

O ambiente virtual só precisa ser criado e ter as dependências instaladas uma
vez. Nas próximas, basta ativá-lo.

### Front-end

```
cd frontend
npm run lint
npm run format:check
npm run build
```

## Comandos do Docker

| Comando | Quando usar |
| --- | --- |
| `docker compose up -d --build` | Subir o ambiente, ou reconstruir depois de mudar o `Dockerfile` ou os `requirements`. |
| `docker compose logs -f backend` | Acompanhar os logs do servidor em tempo real. |
| `docker compose down` | Parar tudo mantendo os dados do banco. |
| `docker compose down -v` | Parar tudo e apagar o volume do banco, para recomeçar do zero. |

Mudanças em `backend/app/` não exigem reconstruir: o servidor recarrega sozinho.

## Problemas comuns

### Porta 27017 ocupada

O `docker compose up` falha ao publicar a porta do `mongo` quando já existe um
MongoDB instalado e rodando no sistema. Pare o serviço e desative o início
automático.

Windows (cmd como administrador):

```
net stop MongoDB
sc config MongoDB start= demand
```

Linux:

```
sudo systemctl stop mongod
sudo systemctl disable mongod
```

### Linux pedindo sudo para o docker

Adicione seu usuário ao grupo `docker` e entre de novo na sessão.

```
sudo usermod -aG docker $USER
```

### Mudou usuário ou senha do banco no .env

O usuário da aplicação só é criado quando o volume do banco está vazio. Depois
de alterar o `.env`, apague o volume e suba de novo.

```
docker compose down -v
docker compose up -d --build
```

## Documentação

- [Protocolo de comunicação](docs/protocolo.md)
- [Como contribuir](CONTRIBUTING.md)

## Como contribuir

As regras de branches, commits e merge requests estão em
[CONTRIBUTING.md](CONTRIBUTING.md).
