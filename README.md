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

## Documentação

- [Protocolo de comunicação](docs/protocolo.md)
- [Como contribuir](CONTRIBUTING.md)
