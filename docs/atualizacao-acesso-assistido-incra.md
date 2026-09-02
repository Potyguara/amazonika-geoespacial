# Atualização — acesso assistido às bases do INCRA

Esta atualização preserva o banco PostGIS e todas as versões já importadas.

## Instalação

Interrompa o servidor web com `Control + C` e execute:

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/atualizacao-acesso-assistido-incra.zip -d .
docker compose up -d --build api
docker compose exec api python -m app.configure_incra_access
curl http://localhost:8000/health
npm run dev -- --host 0.0.0.0
```

O comando `configure_incra_access` apenas altera a forma de obtenção das fontes do INCRA. Ele não exclui feições, versões ou cargas SIGEF existentes.

## Utilização

1. Abra **Fontes de dados**.
2. No cartão de uma fonte do INCRA, clique em **Acessar INCRA**.
3. Faça a autenticação diretamente no portal oficial usando o gov.br.
4. Baixe o arquivo vetorial correspondente à base e ao estado desejado.
5. Volte ao sistema, clique na engrenagem da mesma fonte e selecione o arquivo.
6. Confira a data de referência e clique em **Importar e ativar versão**.

A versão anterior permanece ativa se o novo arquivo não passar pela validação.

## Segurança

O sistema não captura CPF, senha, cookie, token, sessão gov.br ou certificado digital. A autenticação acontece apenas na página oficial aberta em outra aba. O banco armazena somente os dados vetoriais importados e a proveniência técnica da carga.

## WMS do Acervo Fundiário

Links no formato abaixo são destinados à visualização WMS:

```text
https://acervofundiario.incra.gov.br/i3geo/ogc.php?tema=assentamentos_ap
```

Eles não são WFS e não podem ser usados diretamente para análises vetoriais. Se um endereço desse tipo estiver salvo como WFS, o instalador o converte para acesso assistido.
