# Protocolo de comunicação

Este arquivo é o contrato entre front-end e back-end.

Marcas usadas nas tabelas: `OPC` indica item opcional e `REC` indica item que
depende da reconexão.

## 7.1 API REST (HTTPS)

| Método | Rota | Auth | Corpo / resposta |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | — | `{username, password}` → `201 {id, username}`. Erros: `409` username já existe, `422` dados inválidos. |
| POST | `/api/auth/login` | — | `{username, password}` → `200 {access_token, token_type: "bearer", expires_in, user: {id, username}}`. Erro: `401` com mensagem genérica; `429` excesso de tentativas. |
| GET | `/api/me` | Bearer | `200 {id, username, stats: {wins, losses, draws, points}}` — dados do usuário logado e suas estatísticas. |
| GET | `/api/ranking?limit=20` | Bearer | Lista ordenada `[{position, username, points, wins, draws, losses}]`. |
| GET | `/api/health` | — | `{status, db}` — usado pelo Docker e nos testes. |
| GET | `/api/admin/stats` | Bearer (admin) | OPC Online, partidas ativas, erros recentes (painel). |

Regras de validação: username com 3–20 caracteres `[a-zA-Z0-9_]`, comparado em
minúsculas; senha com 8–72 caracteres.

Erros REST: corpo no formato `{"detail": "..."}`, com a mensagem em português.
Erro inesperado no servidor responde `500` com `{"detail": "Erro interno."}`.
Quando o corpo da requisição vem malformado (campo ausente ou de tipo errado), o
`422` é gerado pelo FastAPI e `detail` é uma lista de erros de validação, não um
texto.

## 7.2 Conexão WebSocket

- URL: `wss://<host>/ws`. O navegador não permite cabeçalhos personalizados no
  WebSocket, por isso o token **não** vai na URL (ficaria em logs): a primeira
  mensagem obrigatória é `AUTH`.
- Se `AUTH` não chegar em 5 s, ou o token for inválido, o servidor fecha com
  código `4401`.
- Keep-alive: ping/pong de protocolo do próprio Uvicorn (intervalo ~20 s)
  detecta conexões mortas. Não é preciso PING de aplicação.
- Uma sessão por usuário: se o mesmo usuário conectar de novo, a conexão antiga
  é fechada com `4001`.
- Tamanho máximo de mensagem: 4 KB. Frames maiores fecham a conexão com `1009`.

## 7.3 Envelope comum

Toda mensagem, nos dois sentidos, é um objeto JSON (texto UTF-8, um objeto por
frame) com o formato:

```jsonc
{
  "type": "MOVE",                       // tipo da mensagem (tabelas 7.4)
  "id":   "5b1e...c2",                  // UUID gerado por quem envia
  "ref":  null,                         // em respostas/erros: id da mensagem que as originou
  "ts":   "2026-10-14T19:03:22.114Z",   // ISO-8601 UTC
  "payload": { "match_id": "6710...", "cell": 4, "seq": 3 }
}
```

## 7.4 Catálogo de mensagens

### Cliente → Servidor

| type | payload | Efeito |
| --- | --- | --- |
| `AUTH` | `{token}` | Autentica a conexão. Resposta: `AUTH_OK` ou fechamento 4401. |
| `INVITE_SEND` | `{to_username}` | Cria partida `PENDING` e convida. |
| `INVITE_CANCEL` | `{match_id}` | Convidante cancela convite pendente. |
| `INVITE_RESPOND` | `{match_id, accept: bool}` | Convidado aceita ou rejeita. |
| `MOVE` | `{match_id, cell: 0..8, seq}` | Tenta jogar na casa indicada. |
| `FORFEIT` | `{match_id}` | Desiste; adversário vence. |
| `MATCH_SYNC` | `{match_id}` | Pede o estado completo (usado após reconexão ou `STALE_STATE`). |

### Servidor → Cliente

| type | payload | Quando |
| --- | --- | --- |
| `AUTH_OK` | `{user: {id, username}, active_match_id\|null}` | Após AUTH válido. Se houver partida ativa, o cliente pede `MATCH_SYNC`. |
| `PRESENCE_SNAPSHOT` | `{users: [{username, status: FREE\|IN_MATCH}]}` | Logo após AUTH_OK. |
| `PRESENCE_UPDATE` | `{username, status: FREE\|IN_MATCH\|OFFLINE}` | Sempre que alguém entra, sai ou muda de estado. |
| `INVITE_SENT` | `{match_id, to_username, expires_in}` | Confirma ao convidante. |
| `INVITE_RECEIVED` | `{match_id, from_username, expires_in}` | Ao convidado. |
| `INVITE_RESULT` | `{match_id, status: REJECTED\|EXPIRED\|CANCELLED}` | Convite encerrado sem partida. |
| `MATCH_STARTED` | `{match_id, you_are: X\|O, opponent, board, turn, seq}` | Aos dois jogadores quando o convite é aceito. |
| `MATCH_STATE` | `{match_id, board[9], turn, seq, last_move\|null}` | Após cada jogada válida (aos dois) e em resposta a MATCH_SYNC. |
| `MATCH_ENDED` | `{match_id, result: WIN\|LOSS\|DRAW, reason: LINE\|DRAW\|FORFEIT\|DISCONNECT, winning_line\|null, board}` | Fim da partida; `result` é personalizado para cada destinatário. |
| `OPPONENT_DISCONNECTED` | `{match_id, grace_seconds: 30}` | REC Adversário caiu. |
| `OPPONENT_RECONNECTED` | `{match_id}` | REC Adversário voltou. |
| `ERROR` | `{code, message}` (`ref` = id do comando) | Qualquer comando recusado. |

## 7.5 Códigos de erro e de fechamento

| code (ERROR) | Significado |
| --- | --- |
| `INVALID_MESSAGE` | JSON malformado ou fora do schema |
| `UNKNOWN_TYPE` | type inexistente |
| `USER_OFFLINE` | Convidado não está online |
| `USER_BUSY` | Convidado ou convidante já em partida/convite |
| `SELF_INVITE` | Convidou a si mesmo |
| `MATCH_NOT_FOUND` | match_id inexistente |
| `NOT_A_PLAYER` | Usuário não pertence à partida |
| `INVALID_STATE` | Ação incompatível com o status atual |
| `NOT_YOUR_TURN` | Jogada fora do turno |
| `INVALID_CELL` | cell fora de 0–8 |
| `CELL_OCCUPIED` | Casa já marcada |
| `STALE_STATE` | seq desatualizado |
| `RATE_LIMITED` | Mensagens demais por segundo |
| `INTERNAL` | Erro inesperado (detalhe só no log) |

| Close code (WS) | Significado |
| --- | --- |
| `1000` | Fechamento normal (logout) |
| `1009` | Mensagem grande demais |
| `4001` | Sessão substituída por nova conexão |
| `4400` | Violação repetida do protocolo |
| `4401` | Não autenticado / token inválido ou expirado |

> **Regra do cliente:** ao receber 4401, voltar à tela de login; ao receber
> 4001, mostrar “sessão aberta em outra aba” e **não** reconectar; nos demais
> casos inesperados, reconectar com backoff.

## 7.6 Exemplo completo de uma jogada

```text
Cliente A → servidor
{"type":"MOVE","id":"a1","ref":null,"ts":"...","payload":{"match_id":"m42","cell":4,"seq":2}}

Servidor → A e B
{"type":"MATCH_STATE","id":"s9","ref":"a1","ts":"...","payload":{"match_id":"m42",
 "board":["X",null,null,null,"X",null,"O",null,null],"turn":"O","seq":3,
 "last_move":{"symbol":"X","cell":4}}}

Se A tivesse jogado fora do turno (apenas para A):
{"type":"ERROR","id":"s10","ref":"a1","ts":"...","payload":
{"code":"NOT_YOUR_TURN","message":"Aguarde sua vez."}}
```

O tabuleiro é sempre enviado **inteiro** (9 posições, poucos bytes). Isso
simplifica a sincronização: o cliente nunca precisa “aplicar” diferenças, apenas
substituir o estado — e qualquer mensagem perdida é corrigida pela seguinte.
