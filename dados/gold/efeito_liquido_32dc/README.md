# dados/gold/efeito_liquido_32dc/

> ⚠️ **Análise exploratória, à parte do estudo oficial.** Não substitui nem altera o estudo de
> 15 pares em `dados/gold/efeito_liquido/` — é uma checagem de robustez sobre a mesma pergunta,
> com uma amostra maior.

Gerado por `projetos/09_analise_estatistica_impacto/step_analise_32dc_br_eua.py`, a partir de
`dados/gold/base_final_32_dc_br_eua.csv` (31 pares tratamento/controle: os 15 do Brasil + uma
fonte suplementar de data centers nos EUA).

**Pergunta:** ampliar a amostra melhora a significância estatística do efeito líquido?

## Arquivos

- `resumo_significancia_32dc.csv` — mesmo formato de
  `efeito_liquido/consequencias_terreno_resumo.csv` (p-valor, p-FDR, IC95%, Cohen's d por
  variável), calculado sobre os 31 pares.
- `comparacao_15_vs_31_pares.csv` — p-valor e p-valor FDR lado a lado, 15 vs. 31 pares, para ver
  diretamente o efeito de aumentar a amostra.

## Resultado

Os p-valores melhoram com a amostra maior (ex.: área construída, p_fdr 0,94 → 0,19), mas
**nenhuma variável cruza o limiar de significância (α=0,05) após a correção por múltiplas
comparações** — mesma conclusão qualitativa do estudo de 15 pares. Isso é evidência de que o
problema é tamanho de amostra (poder estatístico), não ausência de sinal — não é, por si só,
uma confirmação de efeito.

## Por que é separado do estudo oficial

A base de 31 pares usa uma fonte suplementar (EUA) que ainda não passou pelo mesmo processo de
curadoria/validação da amostra brasileira, e mistura dois países com contextos regulatórios e
socioeconômicos diferentes — misturar isso ao resultado principal sem essa ressalva seria
enganoso. Por isso vive em pasta e script próprios, sem tocar em `comum.py`,
`step1b_analise_consequencias.py` nem nos dados do estudo original.
