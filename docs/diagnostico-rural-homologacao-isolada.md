# Homologação rural isolada — portas 18002/13002

A API de produção 18000, web 13000, banco de produção e homologação
cartográfica 18001/13001 **não são alterados**. Nunca anexar o banco de
homologação à rede/volume da produção. Compose novo
`docker-compose.rural-homolog.yml`, projeto obrigatório
`amazonika-rural-homolog`; volumes separados.

## 1. Preparar variáveis locais e conferir configuração (sem iniciar nada)

```bash
cd /tmp/amazonika-rural-homolog
git fetch origin
git checkout --detach origin/feat/diagnostico-rural-coordenada-20261104
umask 077
python3 - <<'PY'
from pathlib import Path
from secrets import token_urlsafe
path=Path(".env.rural-homolog")
if path.exists():
    print("Arquivo já existe; preservado:", path)
else:
    path.write_text("RURAL_HOMOLOG_DB_PASSWORD="+token_urlsafe(32)+"\n")
    path.chmod(0o600)
    print("Variáveis isoladas criadas (senha ocultada).")
PY
docker compose --project-name amazonika-rural-homolog \
  --env-file .env.rural-homolog -f docker-compose.rural-homolog.yml config --quiet
echo "COMPOSE_RURAL_HOMOLOG_VALIDO"
```

Importante: o arquivo `.env.rural-homolog` deve ser mantido fora do Git;
nunca copiar para a produção ou publicar seu conteúdo.

## 2. Iniciar somente PostgreSQL e API (Earth Engine desligado)

```bash
docker compose --project-name amazonika-rural-homolog \
  --env-file .env.rural-homolog -f docker-compose.rural-homolog.yml \
  up -d --build db api

curl -fsS http://127.0.0.1:18002/ready
curl -fsS http://127.0.0.1:18000/ready
```

A API cria schema **somente no seu banco novo**. Confirme as duas
respostas ready/db=ok antes de avançar.

## 3. Criar administrador somente no banco de homologação

```bash
read -r -s -p "Senha descartável de homologação (min. 14 caracteres): " RURAL_PASSWORD
echo
printf '%s\n' "$RURAL_PASSWORD" | docker compose \
  --project-name amazonika-rural-homolog --env-file .env.rural-homolog \
  -f docker-compose.rural-homolog.yml exec -T \
  -e RURAL_HOMOLOG_SEED=yes \
  -e RURAL_HOMOLOG_ADMIN_EMAIL=admin-rural@example.invalid \
  api python /app/scripts/seed_rural_homolog_admin.py
unset RURAL_PASSWORD
```

Não usar e-mail ou credenciais de produção. Script bloqueia qualquer
database diverso de `db/amazonika_rural_homolog`, exige opt-in e não
redefine senha de usuário existente.

## 4. Login por API local com cookie real

Usar cookie-jar privado e POST via stdin, sem expor senha na linha de
comando nem no histórico. O prompt `getpass` exige terminal interativo.

```bash
umask 077
python3 - <<'PY' | curl -fsS -c /tmp/amazonika-rural-homolog.cookies \
    -H 'Content-Type: application/json' --data-binary @- \
    http://127.0.0.1:18002/api/v1/auth/login
import getpass, json
print(json.dumps({
    "email": "admin-rural@example.invalid",
    "password": getpass.getpass("Senha de homologação: "),
}))
PY

echo
curl -fsS -b /tmp/amazonika-rural-homolog.cookies \
  http://127.0.0.1:18002/api/v1/auth/me
```

Se o terminal não permitir `getpass`, fazer login diretamente no
navegador pelo túnel SSH descrito abaixo. Nunca inserir senha em
argumento de processo, comando, log, print ou commit.

## 5. Frontend isolado

Somente após confirmar autenticação e API:
```bash
docker compose --project-name amazonika-rural-homolog \
  --env-file .env.rural-homolog -f docker-compose.rural-homolog.yml \
  up -d --build web
curl -I http://127.0.0.1:13002/
```

No Windows, criar túnel SSH (substitua servidor pelo host real):
```powershell
ssh -L 13002:127.0.0.1:13002 -L 18002:127.0.0.1:18002 root@SEU_SERVIDOR
```
Abrir `http://127.0.0.1:13002`. É essencial manter o mesmo hostname
`127.0.0.1` para os cookies `Secure` e `SameSite=Lax`.
A configuração da interface aponta para
`http://127.0.0.1:18002/api/v1`, acessível via segundo túnel.

## Segurança/limpeza

Não abrir portas 13002/18002 no firewall público: bind é em loopback.
Manter flags GEE desligadas. `docker compose --project-name
amazonika-rural-homolog ... down` remove contêineres e rede, preservando
volumes. **Nunca** usar `down -v` sem backup e autorização explícita.
Para interromper serviços, não usar comandos sem `--project-name` e
`-f` adequados. Excluir o cookie-jar temporário após o teste:
`rm -f /tmp/amazonika-rural-homolog.cookies`.

Não ativar consulta paga nesta fase.
