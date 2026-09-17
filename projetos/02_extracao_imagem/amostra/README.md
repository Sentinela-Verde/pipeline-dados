# amostra/ — 1 GeoTIFF real, versionado, pra conferência

Esta pasta **não** segue a regra geral de `dados/bronze/imagens_satelite/` (gitignorada — os
GeoTIFF de verdade são pesados demais pro git, ver `.gitignore` e decisão 4 do README da raiz).
Ela existe só pra ter **1 exemplo real de saída da etapa 2, versionado junto do código**, pra
quem abrir o repositório conseguir ver o resultado sem precisar rodar Earth Engine.

## O que tem aqui

`ascenty-hortolandia-htl5/` — cópia exata do que a etapa gerou em
`dados/bronze/imagens_satelite/sentinel2/ascenty-hortolandia-htl5/2022.tif` (gitignorado lá):

- `2022.tif` — composto Sentinel-2 harmonizado, 6 bandas (blue/green/red/nir/swir1/swir2),
  10 m, EPSG:31983, 96 imagens compostas, 100% pixels válidos, 8,18 MB.
- `s2_ascenty-hortolandia-htl5_2022.json` — manifest de proveniência (sha256, grade, parâmetros
  de máscara de nuvem, harmonização) — o mesmo que fica em `dados/manifests/`.

## Por que esse site

`ascenty-hortolandia-htl5` foi o primeiro facility processado a partir da nova fonte de dados
desta etapa: `dados/silver/datacenter_filtrado.csv` (saída de
`projetos/01_coleta_datacenter/filtro_elegibilidade/`), em vez da lista curada antiga em
`parametros/sites.geojson`. Serve de prova de que o encadeamento
coleta → correção de endereço → filtro de elegibilidade → extração de imagem funciona ponta a
ponta pra um facility real.

## Como foi gerado

```bash
cd projetos/02_extracao_imagem
python sentinel2.py --site ascenty-hortolandia-htl5 --ano 2022
```

(o `site_id` `ascenty-hortolandia-htl5` foi adicionado a `parametros/sites.geojson` com
lat/lon vindos direto do `datacenter_filtrado.csv` — é uma feature nova ali, distinta de
`ascenty-hortolandia`, que é o campus agregado já usado nos outros 16 sites)
