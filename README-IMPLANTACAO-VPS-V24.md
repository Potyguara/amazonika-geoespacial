# Amazonika Geoespacial v24 — implantação na VPS do SIS Amazonika

Esta versão adiciona uma pilha de produção isolada para a VPS Hostinger KVM 2.
O SIS Amazonika continua executando por PM2 na porta 3333 e não é modificado.

## Arquitetura

- frontend: `127.0.0.1:13000`;
- API: `127.0.0.1:18000`;
- PostGIS: somente na rede privada Docker, sem porta pública;
- Nginx: `geo.amazonikaengenharia.com.br`;
- HTTPS: Certbot já instalado na VPS;
- limites: PostGIS 3 GB, API 1,5 GB e frontend 1,5 GB;
- logs Docker rotacionados;
- backup PostGIS com retenção local de 14 dias.

## Migração

Execute `bash deploy/exportar-dados-mac.sh` no Mac para preservar fontes,
versões vetoriais, análises e camadas regionais. Transfira a pasta
`migracao-vps` juntamente com o projeto para `/opt/amazonika-geoespacial`.

## VPS

1. Instale o Docker: `bash deploy/install-docker-ubuntu.sh`.
2. Inicialize: `bash deploy/inicializar-vps.sh`.
3. Crie o registro DNS A `geo` apontando para a VPS.
4. Após a propagação: `certbot --nginx -d geo.amazonikaengenharia.com.br --redirect`.

As portas dos containers são vinculadas exclusivamente a `127.0.0.1`, pois
portas Docker publicadas em todas as interfaces podem contornar regras UFW.
