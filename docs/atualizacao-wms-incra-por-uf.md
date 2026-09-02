# Atualização — WMS INCRA por UF e alerta quinzenal

## Instalação

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/atualizacao-wms-incra-por-uf.zip -d .
docker compose up -d --build api
docker compose exec api python -m app.configure_incra_wms
curl http://localhost:8000/health
npm run dev -- --host 0.0.0.0
```

O comando de configuração preserva todas as versões e feições já importadas.

## Operação

- No mapa, escolha uma UF no seletor **UF das camadas INCRA**.
- Ative somente os temas necessários em **Gerenciar todas as fontes**.
- Cada linha possui um switch próprio para ligar ou desligar a camada.
- O WMS público mostra a publicação oficial corrente.
- Na engrenagem de uma fonte INCRA, use **Testar conexão WMS do Amapá** antes de cadastrar as demais UFs.
- Use a engrenagem da fonte para importar o vetor utilizado nas identificações, análises e relatórios.
- O indicador fica vermelho quando não existe vetor ou quando a data de referência ultrapassa 15 dias.

Temas disponíveis: SIGEF particular, SIGEF público, imóveis certificados privados, imóveis certificados públicos, parcelas georreferenciadas, assentamentos, reconhecimento territorial e territórios quilombolas.
