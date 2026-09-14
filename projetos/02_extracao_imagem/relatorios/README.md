# Relatórios da etapa 2

CSVs de conferência da ingestão. Versionados aqui (são leves) para poderem ser lidos direto no
GitHub, sem passar pelo S3.

## `qualidade_ingestao.csv` — 256 linhas

Uma linha por raster ingerido (site × sensor × ano), com o contexto do site e o resultado da
ingestão:

| coluna | o que é |
|---|---|
| `site_id`, `tier`, `regiao`, `bioma` | contexto do site, de `parametros/sites.geojson` |
| `sensor`, `ano` | qual raster |
| `n_imagens_usadas` | quantas cenas entraram no composto mediano anual |
| `pct_pixels_validos` | % de pixels não-nodata depois da máscara de nuvem |
| `tamanho_mb` | tamanho do `.tif` gerado |
| `status` | `ok` ou o motivo da ressalva |

É por aqui que se vê se algum site/ano tem composto fraco (poucas cenas, muita nuvem) antes de
tratar o número dele como confiável.

## `harmonizacao_residuo.csv` — 9 linhas

Resíduo medido da harmonização espectral Landsat ↔ Sentinel-2, uma linha por banda mais os
índices: `vies`, `desvio`, `rmse`, `r2` sobre 1.500 pontos pareados. É a evidência por trás da
decisão de harmonização (ADR-003 no repositório de origem) — o que justifica tratar as duas eras
como uma série só.

## ⚠ Sem gerador neste repositório

Estes dois CSVs foram **copiados como artefatos**, não regerados aqui:

- `qualidade_ingestao.csv` sai de `sentinela.gee.executar_lote --relatorio`, o orquestrador de
  lote, que não foi migrado — ele coordena as etapas 2, 3 e 4 juntas e não cabe dentro de uma
  etapa só.
- `harmonizacao_residuo.csv` sai de `sentinela.gee.medir_residuo_harmonizacao`, também não
  migrado.

Ou seja: se a ingestão for reexecutada, estes arquivos **não se atualizam sozinhos**. Ambos os
geradores continuam em `modelo-imagens-satelite`. Migrar os dois é decisão em aberto.
