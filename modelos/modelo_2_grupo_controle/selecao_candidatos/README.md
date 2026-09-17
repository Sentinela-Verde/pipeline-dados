# modelo_2_grupo_controle/selecao_candidatos — pareamento de grupo de controle

Acha, para cada data center do estudo, um **grupo de controle**: uma área parecida
socioeconomicamente que não recebeu data center, usada depois em
`projetos/09_analise_estatistica_impacto/` como contrafactual (o que teria acontecido com aquela
região se o data center não tivesse sido construído — ver item 8 do
[guia de estrutura de dados](../../../projetos/09_analise_estatistica_impacto/guia_estrutura_dados_modelo_impacto.md)).

A ideia em três etapas:

1. **Cidade similar** — para cada município do Brasil, acha os municípios mais
   parecidos (mesmo perfil de população, PIB per capita e vocação econômica),
   dentro da mesma região do país.
2. **Pontos candidatos** — mede a distância e a direção entre o centro do
   município do data center e o data center em si, e aplica essa mesma
   distância a partir de cada município similar, em 6 direções ao redor dele.
   Cada um desses pontos vira um candidato a área de controle.
3. **Escolha do melhor candidato** — classifica todos os candidatos com o
   mesmo modelo de cobertura do solo (Modelo 1) no período pré-obra e escolhe,
   por AOI, o candidato mais parecido com o próprio data center nesse período
   (menor distância L1 entre as distribuições de classe).

## Pipeline

| Step | Arquivo | Entrada | Saída |
|---|---|---|---|
| 1 | `step1_cidades_similares.py` | `dados/bronze/ibge/ibge_municipios.csv` | `dados/silver/grupo_controle/municipios_com_cidades_similares.csv` |
| 2 | `step2_grupo_controle.py` | `dados/silver/datacenter_filtrado.csv` (de [`filtro_elegibilidade`](../../../projetos/01_coleta_datacenter/filtro_elegibilidade/README.md)) + saída do step1 | `dados/silver/grupo_controle/candidatos_grupo_controle_12pontos.csv` |
| 3 | `step3_seleciona_melhor_controle.py` | saída do step2 (classificada pelo Modelo 1) | `dados/silver/grupo_controle/grupo_controle_escolhido.csv` |
| — | `gerar_mapa_pontos_datacenter.py` | saída do step2 | `dados/silver/grupo_controle/mapa_datacenters.html` (conferência visual, não entra no pipeline) |

`aoi_id` é o identificador usado em todas as saídas abaixo.

Rodar em ordem (cada um lê o CSV que o anterior gerou):

```bash
cd modelos/modelo_2_grupo_controle/selecao_candidatos
python step1_cidades_similares.py
python step2_grupo_controle.py
# entre o step2 e o step3: os candidatos precisam ser extraídos (Earth Engine) e
# classificados pelo Modelo 1 no período pré-obra — ver step3 abaixo
python step3_seleciona_melhor_controle.py
python gerar_mapa_pontos_datacenter.py   # opcional, só pra visualizar no navegador
```

## step1 — cidades similares

Agrupa os municípios por `regiao` (Norte/Nordeste/.../Sul) e roda um KNN
(distância euclidiana, features padronizadas em Z-Score) dentro de cada
grupo, usando o perfil médio 2016-2021 (`config.ANOS_ANALISE`) de:

- `populacao`, `pib_per_capita`
- `pct_va_servicos`, `pct_va_industria`, `pct_va_agropecuaria` (vocação econômica)
- `pct_impostos`

Salva, para cada município, os `config.N_SIMILARES` municípios mais próximos, com um
`percentual_similaridade` (`exp(-distância/2) * 100` — 100% = idêntico, cai
exponencialmente com a distância Z-Score). O step2 usa os `config.N_SIMILARES_PARA_CONTROLE`
primeiros colocados (hoje 2) — os demais ficam disponíveis para quando fizer sentido considerar
mais municípios similares por data center.

## step2 — pontos candidatos

Para cada AOI filtrada:

1. Acha a cidade e os municípios similares dela (do step1, os `N_SIMILARES_PARA_CONTROLE`
   primeiros colocados).
2. Calcula distância (Haversine) e azimute entre a sede do município e o
   data center — isto é, o quão longe e em que direção o data center fica do
   "centro" da sua cidade.
3. Aplica essa mesma distância a partir da sede de cada município similar, em
   `config.N_PONTOS_CONTROLE` (padrão: 6) direções espaçadas a cada 60°,
   começando no Norte (`config.INCLINACAO_INICIAL_GRAUS = 0`).

Com 2 municípios similares × 6 pontos, cada AOI gera 12 candidatos — daí o nome do CSV de saída
(`candidatos_grupo_controle_12pontos.csv`). Um único ponto de controle correria o risco de cair em
cima de outra particularidade local (um rio, uma rodovia, um bairro já denso); gerar vários
candidatos dá margem para escolher o que tiver a cobertura do solo mais parecida com a do data
center no período pré-obra — decisão automatizada no step3, abaixo (o mapa gerado por
`gerar_mapa_pontos_datacenter.py` serve de conferência visual complementar, não é o critério
final).

## step3 — escolha do melhor candidato

Depois que os 12 candidatos por AOI são extraídos (Earth Engine) e classificados pelo Modelo 1 no
período pré-obra (3 anos antes da obra), o step3 escolhe o candidato cuja distribuição de classes
de cobertura do solo (vegetação densa/rala, solo exposto, área construída, água — média dos 3 anos
pré-obra) é a mais parecida com a do próprio data center, medida pela **distância L1** entre as
duas distribuições. Quanto menor a distância, melhor o pareamento:

| Distância L1 | Qualidade |
|---|---|
| ≤ 0,10 | boa |
| ≤ 0,20 | aceitável |
| > 0,20 | ruim |

Os demais candidatos não são descartados — ficam registrados em
`grupo_controle_escolhido.csv` junto do vencedor, para auditoria do critério de escolha.

## `dados/silver/grupo_controle/mapa_datacenters.html`

Mapa de satélite (Esri World Imagery) com, para cada data center: o marcador
do data center, o marcador da sede do município, o marcador do ponto de
controle escolhido e os pontos candidatos ao redor dele, cada um com o
quadrado de amostragem (`config.LADO_QUADRADO_KM`) que é efetivamente extraído do satélite em
`projetos/02_extracao_imagem/`. Serve só pra conferência visual — não é lido por nenhum step
seguinte.
