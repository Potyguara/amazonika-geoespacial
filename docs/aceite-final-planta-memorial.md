# Aceite final da planta e memorial — Amazonika Geoespacial

Branch: `feat/fechamento-memorial-formatos-20261109`

## Escopo
- Cinco formatos físicos: A0/A1/A2/A3/A4, retrato/paisagem.
- Três estilos profissionais de planta, sem alterar as coordenadas originais.
- A3/A4: geometria na primeira folha e quadros técnicos/tabelas nas folhas
  seguintes para evitar microtipografia e preservar dados.
- Memorial A/B/C: confronto identificado em faixa com nome integral,
  trecho e distância; prosa justificada; marcos em destaque.
- Assinaturas: nomes e qualificações em parágrafos centralizados e
  independentes, preservando documento, CREA, visto e ART se cadastrados.
- Geração de planta/memorial somente pelo comando explícito na interface.

## Verificação automatizada
Executar `bash scripts/qa-refino-cartografico.sh` no worktree isolado:
- [ ] `test_final_paper_formats.py` — 30 combinações básicas de papel,
  orientação e modelo e 12 cenários densos com 61 vértices em A3/A4.
- [ ] `test_memorial_manual_highlights.py` — destaque e rodapé legado.
- [ ] testes anteriores do motor e do WMM2025.
- [ ] TypeScript e build frontend com URL de homologação.
- [ ] builds Docker de API e frontend.

## Homologação / evidência visual
- [ ] Confirmar A4/A3 com 4 e 8 vértices, A2/A1/A0 com 61.
- [ ] Conferir nomes integrais dos confrontantes, trechos e extensões.
- [ ] Conferir o quadro de assinaturas sem transbordamento.
- [ ] Conferir início/fim do memorial, destaque por confrontante e
      integridade dos nomes de vértices.
- [ ] Conferir assinatura final centralizada e sem duplicação legada.
- [ ] Conferir escala numérica vs. medida impressa e norte verdadeiro;
      declinação WMM com data válida.
- [ ] Verificar que mudar orientação e modelo não gera PDF automaticamente.
- [ ] Confirmar tamanho físico via MediaBox do PDF.
- [ ] Não apagar backups da homologação até aprovação dos três modelos.

## Produção
Proibida promoção automática a partir desta branch.
Exigir aprovação dos PDFs reais, identificação exata do commit testado
e dos digests Docker; criar backup do banco/volumes, registrar caminho
de reversão e aplicar apenas em janela autorizada.
