# Metodologia — Temperatura de superfície (LST)

Apoio ao modelo de impacto do Guilherme (ver `modelo-impacto/README.md`). Frente separada
do classificador principal (`src/sentinela/`), não usa nem afeta o pipeline dele.

## Fonte

- **Coleção GEE:** [`MODIS/061/MOD11A2`](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD11A2)
  (Terra MODIS, produto LST/Emissividade, versão 061).
- **Banda:** `LST_Day_1km` — temperatura de superfície terrestre diurna.
- **Resolução espacial:** 1 km/pixel (nativa do produto).
- **Resolução temporal:** composto de 8 dias (~46 cenas/ano por pixel, quando não há falha de
  sensor). Cada pixel do composto já é o melhor valor observado na janela de 8 dias — o produto
  MOD11A2 já aplica sua própria triagem de qualidade/nuvem internamente, então **não foi aplicada
  máscara de nuvem manual adicional** (cenas 100% nubladas dentro do buffer simplesmente não
  produzem valor e são descartadas, não interpoladas).
- **Conversão de unidade:** valor bruto do pixel × `0.02` (fator de escala do produto) − `273.15`
  (Kelvin → Celsius).

### Por que MODIS e não Landsat/Sentinel-2 termal
MOD11A2 foi escolhido em vez de bandas termais do Landsat porque cobre 2016-2025 de forma
homogênea (mesmo sensor, mesma resolução, mesmo produto o período todo), sem precisar harmonizar
Landsat 8/9 termal (100 m, reamostrado para 30 m) com Sentinel-2 (que não tem banda termal — só
teria Landsat termal disponível 2019-2025, deixando 2016-2018 sem fonte). Para o proposito deste
apoio (série anual de LST por site, não classificação pixel a pixel), a resolução de 1 km do MODIS
é suficiente — o buffer de 5 km em raio já cobre uma área de ~78 km², bem maior que 1 pixel MODIS.

## Sites e período

- **16 sites** de `config/sites.geojson` (`site_id`, `municipio`, `uf`, `lat`, `lon`,
  `buffer_km` — todos com `buffer_km = 5`). Essa é a lista validada disponível neste repositório
  no momento da extração (2026-09-03). O Guilherme está levantando separadamente uma lista mais
  ampla de ~20 facilities via datacentermap.com; **quando essa lista chegar e for incorporada a
  `config/sites.geojson` (ou outro arquivo equivalente), basta rodar o script de novo** — ele lê a
  lista de sites dinamicamente e não tem nenhum site hardcoded. Não expandimos a lista aqui além
  dos 16 já validados, para não inventar coordenadas fora do processo de validação já usado pelo
  time (v1-v5 nas properties do GeoJSON).
- **Período:** 2016–2025 (10 anos), conforme pedido. A coleção MOD11A2 cobre esse período
  integralmente sem lacunas — não foi preciso ajustar o intervalo para nenhum site.

## Buffer

Círculo geodésico de raio `buffer_km` (5 km) ao redor do ponto `(lat, lon)` de cada site
(`ee.Geometry.Point([lon, lat]).buffer(buffer_km * 1000)`), mesmo buffer usado no
`config/sites.geojson` do classificador principal — mantém os dois recortes espacialmente
consistentes.

## Agregação anual

Para cada par (site, ano):

1. Filtra a coleção `MOD11A2` para o ano e para o buffer do site (`filterDate` + `filterBounds`).
2. Para **cada cena** de 8 dias (até ~46 por ano), converte para Celsius e reduz a **1 valor**:
   a média espacial dos pixels válidos dentro do buffer (`ee.Reducer.mean()`, escala 1000 m).
   Cenas sem nenhum pixel válido no buffer (100% nublado) não geram valor.
3. A **média anual reportada** é a média aritmética simples desses valores por cena (não
   ponderada por dia — como um ano tem ~46 cenas de 8 dias razoavelmente bem distribuídas ao
   longo do calendário, isso já é próximo de uma média uniforme ao longo do ano, sem precisar do
   passo intermediário de agregar por mês primeiro).
4. `n_observacoes` = número de cenas de 8 dias que contribuíram (ou seja, tinham pelo menos 1
   pixel válido no buffer) naquele ano. Serve como indicador de confiança: valores baixos (bem
   abaixo do teto de ~46) sinalizam nebulosidade persistente naquele site/ano.

## Resultado da extração (2026-09-03)

- **160/160 pares site-ano extraídos com sucesso** (16 sites × 10 anos, 2016-2025), nenhum vazio.
- `n_observacoes` variou de **25 a 46** cenas/ano. Nenhum site/ano ficou abaixo do teto esperado a
  ponto de disparar o alerta de baixa cobertura do script (limiar interno: `n_observacoes < 20`).
- **Ressalva de cobertura:** `clickip-manaus` (Manaus/AM, bioma Amazônia) teve sistematicamente
  menos cenas válidas por ano (25-35, vs. 40-46 na maioria dos outros sites) — nebulosidade
  tropical persistente é conhecida e esperada na região; a média anual ainda é calculada, mas com
  uma amostra de cenas proporcionalmente menor que os demais sites. Tratar com mais cautela em
  comparações entre sites.
- **Faixa de valores por cena (bruto, granularidade fina, não a média anual):** 8.3 °C a 45.1 °C.
  Ambos os extremos são plausíveis como cena isolada (composto de 8 dias, não média anual): o
  mínimo é compatível com uma onda de frio de inverno em `scala-spoapa01` (Porto Alegre/RS, o
  site mais ao sul da amostra) e o máximo com um pico de calor em solo exposto/urbano denso. As
  **médias anuais** (a granularidade que importa para o modelo do Guilherme) ficaram todas dentro
  de ~22-36 °C — nenhuma fora da faixa de sanidade esperada para o Brasil (~15-45 °C).
- Ver `modelo-impacto/raw/temperatura/log_extracao.json` para o log completo (contagens,
  faixa de valores, lista de avisos — vazia nesta extração).

## Limitações conhecidas

1. **LST ≠ temperatura do ar.** Temperatura de superfície (o que este produto mede) pode divergir
   bastante da temperatura do ar (a que aparece em previsão do tempo/estações meteorológicas),
   principalmente em superfícies expostas (solo nu, asfalto, telhado) em dias de sol forte — o
   efeito de ilha de calor de superfície tende a ser mais extremo que o de ilha de calor do ar.
   Isso é esperado e aceitável para o objetivo (detectar mudança de cobertura/uso do solo via
   temperatura), mas não deve ser lido como "temperatura que uma pessoa sentiria".
2. **Só período diurno.** Só a banda `LST_Day_1km` foi usada (há também `LST_Night_1km`,
   disponível na mesma coleção, não extraída aqui — pode ser adicionada depois se fizer sentido
   para o modelo).
3. **Nebulosidade reduz `n_observacoes`**, principalmente em biomas de maior cobertura de nuvem
   (caso notável: Amazônia/`clickip-manaus`, ver acima). Sempre olhar `n_observacoes` junto com
   `lst_media_celsius` antes de usar um valor — uma média baseada em poucas cenas é menos
   confiável que uma baseada em ~45.
4. **Resolução de 1 km.** Para o buffer de 5 km de raio (~78 km²) isso é suficiente para uma média
   regional estável, mas não permite distinguir padrões finos dentro do buffer (ex.: telhado do
   data center vs. vegetação vizinha a 200 m de distância) — para isso seria preciso Landsat
   termal (100 m) ou uma fonte de resolução mais alta, fora do escopo deste apoio.
5. **`aggregate_array` do GEE já descarta cenas nulas automaticamente** (confirmado por teste
   antes da extração completa) — não há necessidade de filtro adicional no lado do cliente, mas
   por segurança o script filtra `None` de qualquer forma.
6. **Sensor único (Terra), sem fusão com Aqua** (`MYD11A2`, coleção irmã do satélite Aqua, horário
   de passagem diferente) — não foi combinado aqui por simplicidade; poderia aumentar
   `n_observacoes` em sites/anos com cobertura mais baixa, se necessário no futuro.
