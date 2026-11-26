# Deploy em produção (VM Ubuntu no Azure)

A produção usa o mesmo `compose.yaml` do desenvolvimento com o override
`compose.prod.yaml`, que:

- tira o `--reload`, o bind mount do código e as portas públicas do backend e do
  MongoDB;
- deixa o Nginx sempre ativo nas portas 80 e 443, com certificado do Let's
  Encrypt;
- acrescenta um container do certbot que renova o certificado sozinho.

O ambiente local continua igual.

## 1. Rede e firewall

No portal do Azure, no grupo de segurança de rede (NSG) da VM, deixe entrar só:

| Porta | Uso | Origem |
| --- | --- | --- |
| 22 | SSH | de preferência só o seu IP |
| 80 | HTTP (validação do Let's Encrypt e redirecionamento) | qualquer |
| 443 | HTTPS e WSS | qualquer |

Na VM, o mesmo com o `ufw`:

```
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Aponte o DNS do domínio (registro `A`) para o IP público da VM antes de emitir
o certificado.

## 2. Docker

Instale o Docker Engine com o plugin compose pelo repositório oficial:

```
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
```

Saia e entre de novo na sessão para usar o `docker` sem `sudo`.

## 3. Código

Clone o repositório na VM com uma credencial somente leitura (um deploy key SSH
ou um token de acesso com permissão apenas de leitura):

```
git clone <url-do-repositorio> tic-tac-toe-network
cd tic-tac-toe-network
```

Se usar um token na URL, ele fica gravado em `.git/config` da VM. Por isso use
uma credencial só de leitura e revogue-a se a VM for descartada.

## 4. `.env` de produção

```
cp .env.example .env
chmod 600 .env
```

Edite o `.env`:

| Variável | Valor |
| --- | --- |
| `DOMAIN` | o domínio, ex.: `jogo.exemplo.com.br` |
| `LETSENCRYPT_EMAIL` | e-mail para avisos do Let's Encrypt |
| `ALLOWED_ORIGINS` | `https://<domínio>` |
| `JWT_SECRET` | saída de `openssl rand -hex 32` |
| `MONGO_ROOT_PASSWORD` e `MONGO_APP_PASSWORD` | senhas novas e fortes |
| `MONGO_URI` | a mesma senha nova de `MONGO_APP_PASSWORD` dentro da URI |
| `COMPOSE_FILE` | `compose.yaml:compose.prod.yaml` (assim `docker compose` já usa o override) |

O usuário da aplicação no MongoDB só é criado quando o volume está vazio. Defina
as senhas antes da primeira subida.

## 5. Primeiro certificado e subida

O Nginx de produção não sobe sem certificado. O script emite o primeiro em modo
standalone (o certbot ocupa a porta 80 por alguns segundos), sobe a stack e
passa a renovação para webroot, pelo Nginx.

Teste antes contra o ambiente de testes do Let's Encrypt, que não consome o
limite de emissões:

```
./infra/deploy/primeiro-certificado.sh --staging
```

Se der certo, apague o certificado de teste e emita o real:

```
docker compose down
docker volume rm tic-tac-toe-network_letsencrypt
./infra/deploy/primeiro-certificado.sh
```

Confira:

```
docker compose ps
curl https://<domínio>/api/health
```

A renovação é automática. O container `certbot` tenta renovar a cada 12 h e,
quando um certificado é renovado, o Nginx recarrega em até 5 minutos.

## 6. Atualizar

```
git pull
docker compose up -d --build
```

## 7. Backup do MongoDB

Backup com o banco no ar:

```
docker compose exec -T mongo sh -c 'mongodump --archive --gzip -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin' > mongo-$(date +%F).archive.gz
```

Restauração:

```
docker compose exec -T mongo sh -c 'mongorestore --archive --gzip --drop -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin' < mongo-AAAA-MM-DD.archive.gz
```

Alternativa: cópia do volume inteiro, com o MongoDB parado.

```
docker compose stop mongo
docker run --rm -v tic-tac-toe-network_mongo-data:/data -v "$PWD":/backup alpine tar czf /backup/mongo-data-$(date +%F).tgz -C /data .
docker compose start mongo
```

Guarde os backups fora da VM.

## Comandos úteis

| Comando | Quando usar |
| --- | --- |
| `docker compose logs -f backend` | Acompanhar os eventos do servidor |
| `docker compose logs certbot` | Conferir as tentativas de renovação |
| `docker compose restart nginx` | Forçar o Nginx a reler o certificado |
| `docker compose down` | Parar tudo mantendo os dados |
