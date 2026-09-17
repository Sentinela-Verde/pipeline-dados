# Pipeline de dados: coletas, armazenamento, modelos e análises

Pipeline de dados do Sentinela Verde: da coleta de data centers e imagens de satélite até a
análise estatística do impacto ambiental e territorial no entorno deles.

## Racional geral

Data centers vêm crescendo rápido no Brasil, em geral perto de áreas urbanas ou periurbanas: cada
um ocupa terreno, consome dezenas de MW e altera o uso do solo ao seu redor. Não existe hoje uma
medição sistemática desse impacto — a pergunta de pesquisa deste projeto é: **a chegada de um data
center muda, de forma mensurável, a cobertura do solo (vegetação, construção, solo exposto) e a
temperatura de superfície ao seu redor — além do que já mudaria de qualquer forma pela tendência
regional?**

Responder isso exige separar o que teria acontecido de qualquer jeito (crescimento urbano natural,
tendência regional) do que é atribuível especificamente ao data center. A estratégia adotada é
comparar cada área tratada (onde um data center foi construído) com uma área de controle (uma
região parecida socioeconomicamente que não recebeu data center), medindo as duas antes e depois
da obra — um desenho de inferência causal observacional (event study / diferença-em-diferenças),
o cabível quando não é possível randomizar quem recebe o "tratamento".

O pipeline existe para produzir, de ponta a ponta, os dados que alimentam essa comparação:

1. localizar data centers reais e um grupo de controle comparável (coleta + filtro de
   elegibilidade + pareamento por similaridade socioeconômica);
2. baixar e classificar imagem de satélite (vegetação densa/rala, solo exposto, área construída,
   água) de cada área, ano a ano, tanto para o data center quanto para seu controle;
3. extrair temperatura de superfície e indicadores socioeconômicos da mesma área;
4. consolidar tudo num painel único (área × ano); e
5. testar estatisticamente se o efeito líquido (tratamento − controle) é diferente de zero, com o
   cuidado de corrigir por múltiplas comparações e validar sem misturar linhas do mesmo evento
   entre treino e teste.

Hoje a amostra é pequena (15 pares tratamento/controle no Brasil) e o resultado honesto, depois da
correção por múltiplas comparações, é que nenhuma variável mostra efeito estatisticamente
significativo ainda — embora a direção de algumas (ex.: área construída) aponte para uma possível
interferência que a amostra atual não tem poder estatístico para confirmar. Esse resultado, suas
limitações e os próximos passos metodológicos estão documentados em
[`projetos/09_analise_estatistica_impacto/`](projetos/09_analise_estatistica_impacto/README.md).

> Os pontos marcados como "⚠ decisão em aberto" na seção de decisões, mais abaixo, ainda não têm
> dono — o resto deste documento já reflete a estrutura em uso.

## Diagrama do pipeline

Fluxo completo — coleta → extração de imagem → rótulos → índices espectrais → Modelo 1
(treino/inferência) → Modelo 2 (grupo de controle) → consolidação → análise estatística →
reiteração/expansão da amostra. [Versão interativa, com zoom](https://claude.ai/code/artifact/0f4cf670-5e55-4495-bb8b-f0ea743d679f);
abaixo, a mesma fonte, renderizada direto pelo GitHub:

```mermaid
flowchart TD
    subgraph S1["1 · Coleta"]
        A1["Scraping<br/>datacentermap.com"]:::fonte
        A2[["lat/lon, ano construção,<br/>specs de porte (MW/tier)"]]:::dado
        A3["Google Geocoding API<br/>(reverse geocoding por lat/lon)"]:::fonte
        A4[["Endereço/município/estado/país/CEP (silver)<br/>município e estado sempre atualizados;<br/>demais só complementados onde faltava"]]:::dado
        A1 --> A2
        A2 --> A3 --> A4
    end

    subgraph S2["2 · Extração de imagem"]
        B1["Google Earth Engine"]:::fonte
        B2[["GeoTIFF bandas<br/>Landsat 30m / Sentinel-2 10m"]]:::dado
        A2 --> B1 --> B2
    end

    subgraph S3["3 · Rótulos (em paralelo)"]
        C1["MapBiomas Coleção 9"]:::fonte
        C2[["Label automático anual"]]:::dado
        C3["WorldCover"]:::fonte
        C4[["Crosscheck<br/>(só ano 2021)"]]:::dado
        C5["Rotulagem manual<br/>211 polígonos<br/>(solo exposto/obras)"]:::manual
        C1 --> C2
        C3 --> C4
        C5 -. precedência .-> C2
    end

    subgraph S4["4 · Índices espectrais"]
        D1["Cálculo de 7 índices<br/>NDVI·EVI·NDWI·MNDWI·NDBI·BSI·NDMI"]:::processo
        D2[["Bandas + 7 índices"]]:::dado
        B2 --> D1 --> D2
    end

    subgraph S5T["5a · Modelo 1 — Treino (uma vez só)"]
        E0[["Dataset amostrado<br/>bandas+índices+labels<br/>split por bloco, sem vazamento"]]:::dado
        ET["Treino Random Forest<br/>(GroupKFold, validação)"]:::modelo
        EJ[["models/rf_{tag}.joblib<br/>+ sha256 de conferência"]]:::dado
        D2 --> E0
        C2 --> E0
        C4 -. peso do label .-> E0
        E0 --> ET --> EJ
    end

    subgraph S5["5b · Modelo 1 — Inferência (tratamento)"]
        E1["Predição em lote<br/>(reaplica o .joblib, não retreina)"]:::modelo
        E2[["Mapa de classes + % confiança<br/>15 data centers (Brasil)"]]:::dado
        EJ --> E1
        D2 --> E1
        E1 --> E2
    end

    subgraph S6["Temperatura (paralelo)"]
        F0["MODIS MOD11A2<br/>(Terra, LST diurna, 8 dias, 1 km)"]:::fonte
        F1["Extração LST<br/>(buffer 5 km por site)"]:::processo
        F2[["LST média por área/ano<br/>2016-2025"]]:::dado
        A2 --> F1
        F0 --> F1 --> F2
    end

    subgraph S7["Socioeconômico"]
        G1["BigQuery · IBGE"]:::fonte
        G2[["População, PIB, empresas<br/>por município (Brasil)"]]:::dado
        G3["Socioeconômico US<br/>(ACS 5-year, Census Bureau)"]:::fonte
        G4[["Equivalente por condado/cidade<br/>(EUA)"]]:::dado
        G1 --> G2
        G3 --> G4
    end

    subgraph S8["6 · Modelo 2 — Grupo de controle"]
        H1["KNN cidades similares"]:::modelo
        H2[["Município/cidade similar"]]:::dado
        H3["6 pontos candidatos<br/>(distância/direção do DC)"]:::processo
        H3a["Inferência (mesmo .joblib)<br/>classifica os 6 candidatos<br/>(uso comparativo)"]:::modelo
        H3b["Comparação estatística<br/>nível/tendência pré-obra<br/>candidato vs. data center"]:::processo
        H4["Escolha final do ponto<br/>(mapa + comparação estatística)"]:::manual
        H5[["Grupo controle definido"]]:::dado
        G2 --> H1
        G4 -. "(sites EUA)" .-> H1
        A4 -. "município/estado padronizado" .-> H1
        H1 --> H2 --> H3 --> H3a --> H3b --> H4 --> H5
        EJ -. "mesmo modelo, não retreina" .-> H3a
        E2 -. "nível/tendência do data center" .-> H3b
    end

    subgraph S9["Modelo 1 — Inferência (controle, completa)"]
        I1["Predição em lote<br/>(mesmo .joblib, AOI completo<br/>do ponto já escolhido)"]:::modelo
        I2[["Mapa de classes<br/>área de controle"]]:::dado
        EJ -. "mesmo modelo, não retreina" .-> I1
        H5 --> I1 --> I2
    end

    subgraph S10["7 · Consolidação"]
        J1["Junção manual<br/>(sem script hoje)"]:::manual
        J2[["consolidado_impacto_modelo.csv<br/>1 linha por área x ano"]]:::dado
        E2 --> J1
        I2 --> J1
        F2 --> J1
        G2 --> J1
        A2 --> J1
        J1 --> J2
    end

    subgraph S11["8 · Análise estatística"]
        K1["Event study · placebo · DiD<br/>curva de efeito líquido"]:::processo
        K2[["Efeito líquido por variável/horizonte<br/>± erro padrão"]]:::dado
        J2 --> K1 --> K2
    end

    subgraph S12["9 · Reiteração — expansão automática da amostra"]
        L0["Mais pontos do scraping<br/>datacentermap (candidatos novos)"]:::dado
        L1["Inferência (mesmo .joblib)<br/>classifica um raio menor<br/>ao redor do ponto"]:::modelo
        L2[["Série anual de % por classe<br/>no raio menor, por site"]]:::dado
        L3["Calibrador de obra<br/>(regras: pico de solo exposto ·<br/>recuo do solo · salto de área construída)"]:::processo
        L4[["ano_inicio_obra / ano_fim_obra<br/>estimados automaticamente"]]:::dado
        A2 --> L0 --> L1
        EJ -. "mesmo modelo, não retreina" .-> L1
        L1 --> L2 --> L3 --> L4
    end
    L4 -. "alimenta de volta o dataset de datacenters<br/>(define fase pré/durante/pós sem pesquisa manual do ano)<br/>→ amostra expandida: 15 → N sites (N a confirmar)" .-> A2

    subgraph S13["Próximos passos — fora do escopo atual"]
        N1["Consumo de energia<br/>(ANEEL/MME)"]:::futuro
        N2["Uso de água<br/>(SNIS)"]:::futuro
        N3["Ruído"]:::futuro
        N1 ~~~ N2 ~~~ N3
    end
    N1 -. "entraria na análise final<br/>— ainda não integrado" .-> J2
    N2 -. "idem" .-> J2
    N3 -. "idem" .-> J2

    classDef fonte fill:#37474F,color:#ffffff,stroke:#263238;
    classDef processo fill:#546E7A,color:#ffffff,stroke:#37474F;
    classDef modelo fill:#1B5E20,color:#ffffff,stroke:#0d3311,stroke-width:2px;
    classDef dado fill:#ECEFF1,color:#222222,stroke:#90A4AE;
    classDef manual fill:#F5A623,color:#2a1d00,stroke:#8a5a00,stroke-width:2px,stroke-dasharray: 4 3;
    classDef futuro fill:#C62828,color:#ffffff,stroke:#7f1d1d,stroke-width:2px,stroke-dasharray: 3 3;
```

> Se editar o diagrama, mude nos dois lugares: aqui (pra renderizar no GitHub) e em
> `diagrama.html` (pra manter zoom/legenda/tabela de etapas funcionando).

## Árvore do repositório

```
sentinela_verde/
│
├── dados/                                  # data lake — bronze/silver/gold
│   ├── bronze/                             # bruto, exatamente como veio da fonte
│   │   ├── datacentermap/                  # scraping (JSON cru, cache incremental) + correção de endereço
│   │   ├── imagens_satelite/               # (AWS S3) — GeoTIFF pesado não fica no git, só o manifest
│   │   │   ├── landsat/
│   │   │   └── sentinel2/
│   │   ├── labels/                         # tifs leves (13 MB), versionados aqui
│   │   │   ├── dynamic_world/              # fonte principal
│   │   │   └── mapbiomas/                  # mantido como alternativa
│   │   ├── temperatura/                    # LST por site x ano + cenas brutas (220 KB, leve)
│   │   ├── footprints_osm/                 # polígonos de prédio do OpenStreetMap (EUA)
│   │   ├── ibge/
│   │   └── socioeconomico_us/              # equivalente ao IBGE pra grupo controle nos EUA
│   │
│   ├── silver/                             # tratado / intermediário
│   │   ├── datacentermap_enderecos_corrigidos.csv  # endereço/município/estado/país/CEP (242/242 OK)
│   │   ├── features/                       # (AWS S3) — 13 bandas, dado derivado pesado
│   │   ├── datacao_obra/                   # série de NDBI, validação e datas derivadas por campus
│   │   ├── expansao_amostra/               # série no raio menor (etapa 7) — ❌ depende do Modelo 1
│   │   └── grupo_controle/                 # 6 candidatos + comparação estatística (etapa 6/6a) + escolha final
│   │
│   ├── gold/                               # pronto pra modelar / analisar
│   │   ├── area_por_classe.csv             # série por site × ano × sensor × classe (rf_v2.0-dw) — ver decisão 5
│   │   ├── dataset_classificacao.parquet   # (AWS S3) — dataset amostrado que alimenta o treino (5a)
│   │   ├── consolidado_impacto_modelo.csv  # ⚠ hoje montado manualmente — etapa 7 do diagrama
│   │   ├── efeito_liquido/                 # saídas do step1/1b/1c: curvas, event study, testes de significância
│   │   ├── efeito_liquido_32dc/            # análise exploratória à parte — ver nota abaixo
│   │   └── powerbi_export/                 # tabelas gold pro dashboard Power BI — ver nota abaixo
│   │
│   ├── labels_manual/                      # 211 polígonos humanos — é INSUMO versionado, não saída
│   └── manifests/                          # 1.066 manifests — proveniência (sha256), sempre commitado
│
├── modelos/
│   ├── modelo_1_classificacao_imagem/
│   │   ├── treino/                         # roda 1x, gera o artefato (etapa 5a)
│   │   ├── inferencia/                     # classifica.py — reaplica o .joblib já treinado (etapas 5b e 6b)
│   │   ├── config/                         # classes.yml, params.yml, sites.geojson
│   │   ├── exemplos/                       # 1 par input/output real, pra conferir a inferência sem rodar o pipeline inteiro
│   │   └── artefatos/                      # (AWS S3) — *.joblib + *.sha256
│   │
│   └── modelo_2_grupo_controle/
│       ├── selecao_candidatos/             # KNN cidade similar (BR ou US) + 6 pontos candidatos
│       ├── comparacao_estatistica/         # chama a inferência do modelo 1 (dependência
│       │                                   # cruzada, ver decisão 2) + compara nível/tendência pré-obra
│       └── artefatos/                      # (AWS S3)
│
├── projetos/                               # 1 pasta por etapa do diagrama, numeradas na mesma ordem
│   ├── 01_coleta_datacenter/               # inclui correcao_endereco/ e filtro_elegibilidade/
│   ├── 02_extracao_imagem/
│   ├── 03_extracao_labels/
│   ├── 04_indices_espectrais/
│   ├── 05_extracao_lst/
│   ├── 06_extracao_socioeconomico/         # ibge/ + socioeconomico_us/
│   ├── 07_reiteracao_expansao_amostra/     # candidatos do scraping, joblib em raio menor, calibrador de obra
│   ├── 08_consolidacao/                    # ver decisão 1
│   └── 09_analise_estatistica_impacto/     # sem o Estágio 2/RF — event study, placebo, DiD, curva efeito líquido
│
├── docs/
│   ├── decisoes/                           # ADRs do time
│   └── tarefas/                            # 1 tarefa por arquivo
│
└── proximos_passos/                        # backlog isolado, fora do pipeline ativo
    ├── energia_aneel_mme/                  # aneel_energia_municipio + bigquery_mme_energia_uf — não conectado ao pipeline ativo
    ├── agua_snis/                          # bigquery_snis_agua — sem dado, nunca foi gerado na fonte
    └── ruido/                              # sem fonte de dado ainda
```

## Análises exploratórias (fora do estudo principal)

Duas coisas neste repositório são investigações à parte do estudo de 15 pares descrito no
racional acima — não substituem o resultado principal, apenas o complementam:

- **`dados/gold/efeito_liquido_32dc/`** (gerado por
  `projetos/09_analise_estatistica_impacto/step_analise_32dc_br_eua.py`) — testa se ampliar a
  amostra para 31 pares (Brasil + EUA, fonte suplementar) melhora a significância estatística.
  Os p-valores melhoram, mas nenhuma variável cruza o limiar de significância após a correção por
  múltiplas comparações — ver seção própria no
  [README da análise estatística](projetos/09_analise_estatistica_impacto/README.md).
- **`dados/gold/powerbi_export/`** (gerado por `export_gold_powerbi.py`, na mesma pasta) — exporta
  o painel dos 15 pares (mais imagens em miniatura) em formato de tabela gold, para alimentar um
  dashboard Power BI — ver [README da pasta](dados/gold/powerbi_export/README.md).

## Decisões em aberto (o time de arquitetura precisa bater o martelo)

### 1 · Quem escreve o `08_consolidacao/`?

Esta é a maior lacuna do pipeline hoje (marcada em âmbar, como etapa manual, no diagrama): não existe
nenhum script que junte classificação (tratamento + controle) + LST + IBGE num painel único — é
feito manualmente. Virar código aqui é o que fecha o pipeline ponta-a-ponta e também é pré-requisito
pra rodar a expansão da amostra (etapa 9) de forma automática, não pontual.

### 2 · Modelo 2 agora depende do Modelo 1 — isso muda a ordem de deploy/versionamento

Com a comparação estatística dos 6 candidatos (etapa 6a do diagrama) e a expansão automática da
amostra (etapa 9), `modelo_2_grupo_controle/` e `projetos/07_reiteracao_expansao_amostra/` passam a
**chamar o `.joblib` do Modelo 1** diretamente — não são mais dois modelos independentes que só se
encontram no painel consolidado. Isso tem duas implicações pra arquitetura: (1) uma mudança no
Modelo 1 (novo treino, novo `tag`) pode invalidar resultados do Modelo 2 já gerados, então vale
registrar no manifest do Modelo 2 **qual `sha256` do `.joblib`** foi usado; (2) o pacote/serviço que
expõe a inferência do Modelo 1 precisa ser importável tanto por quem roda a classificação direta
(etapas 5b/6b) quanto por quem roda a seleção de controle (6a) e a expansão (9) — ou seja, a
inferência não pode ficar "presa" dentro do projeto do Modelo 1 sem uma forma de reuso.

### 3 · Fonte de dado socioeconômico dos EUA ainda não existe

`socioeconomico_us/` está na árvore como placeholder — nenhuma extração equivalente ao IBGE para
municípios/condados americanos foi encontrada no código hoje. Antes de implementar
`modelos/modelo_2_grupo_controle/` para sites nos EUA, alguém precisa decidir a fonte (Census
Bureau ACS? BLS? outra?) — isso também é pré-requisito de qualquer expansão internacional do
estudo (proposta, ainda não aprovada).

### 4 · Onde mora o dado pesado

Resolvido: os binários pesados (`.joblib`, `.tif`, `.parquet`) ficam na **AWS** (S3), não no git —
marcado com "(AWS S3)" na árvore, em cada pasta onde isso se aplica. Pra imagem já está em
produção: **`.tif` vive só no S3**, no bucket bronze
`plataforma-lakehouse-bronze-149465616406-us-east-1-an`, sob
`raw/imagens_satelite/{sensor}/site_id=<id>/ano=<ano>/<ano>.tif` (particionamento Hive, pra Glue/
Athena enxergarem as partições). O **manifest é leve e fica versionado** em `dados/manifests/`,
além de espelhado no S3 — é ele que liga o commit ao arquivo remoto, via `sha256`.

Regra geral que saiu daqui, e que vale pras próximas etapas: *output leve vai pro git **e** pro
S3; output pesado vai só pro S3.*

### 5 · O CSV publicado sai de um classificador que o projeto reprovou ⚠

Correção de um registro anterior: esta decisão dizia que "qual classificação é a de produção"
estava em aberto. **Não está** — o critério existe, está escrito desde antes de haver número, e
foi medido. O `manifest.json` que acompanha os artefatos no S3 e o **ADR-006 §8** registram:

> produção é o **`rf_v1.0-tuned`**, e o critério de adoção deste projeto **não é acurácia, é
> estabilidade temporal**: um retreino só substitui o modelo atual se ficar abaixo da
> instabilidade do próprio rótulo que o treinou.

O `rf_v2.0-dw` ganha em acurácia com folga — macro-F1 0,828 contra 0,776, e a classe 3
(`solo_exposto_obras`) salta de F1 0,580 para 0,804, o maior ganho isolado do projeto, porque o
Dynamic World tem `bare` nativa onde o MapBiomas não tinha canteiro de obras. E ainda assim
reprova, nos mesmos pixels e nos mesmos 58 pares de anos:

| instrumento | instabilidade temporal |
|---|---:|
| `dynamic_world` (a barra) | **7,21%** |
| `rf_v2.0-dw` | 13,09% |
| `rf_v1.0-tuned` | 17,54% |

O retreino melhora 25% nesse eixo e continua 1,8× acima da barra. A hipótese registrada lá é que
estabilidade vem de **contexto espacial** — o Dynamic World é uma rede convolucional, e o nosso é
um Random Forest por pixel, sem vizinhança nenhuma. Se estiver certa, nenhum retreino com a mesma
arquitetura passa.

**O problema que isso cria aqui.** O `dados/gold/area_por_classe.csv` publicado neste repositório
é do **`rf_v2.0-dw`** — o modelo reprovado. A escolha foi coerente com o Dynamic World ser a fonte
de rótulo ativa desde 2026-09-11, mas cria uma divergência real com o resto do projeto: toda a
análise de impacto publicada (o achado de 18/20 pares, p=0,0002, o placebo, os testes de robustez)
foi calculada com o `rf_v1.0-tuned`. E é sob o v2.0-dw que o achado **não replica** — 9/14,
p=0,21, contra 14/14, p=0,0001.

Três saídas, e a escolha é do time:

1. **Republicar o CSV a partir do `rf_v1.0-tuned`**, alinhando com o que a análise usou. O
   exportador já aceita `--token`, então é uma execução — mas o fator de correção de sensor teria
   de ser o do v1.0 (ele existe, é o arquivo histórico), e a classe 3 volta a não ser corrigível.
2. **Manter o v2.0-dw e assumir a divergência**, documentando que o CSV de indicadores e a análise
   de impacto falam de classificações diferentes.
3. **Publicar os dois** e deixar a comparação explícita — é a mais cara e a que mais informa, já
   que a diferença entre eles é um resultado do projeto.

Enquanto não se decide, vale a regra que o código já impõe: o fator de correção de sensor é
calibrado sobre uma classificação e o exportador falha se aplicá-lo a outra (ver
`modelos/modelo_1_classificacao_imagem/indicadores/relatorios/`).

No CSV, `tipo` é `tratamento` em toda linha e `pareado_com` está vazio: o grupo de controle ainda
não existe. É a etapa 6a que preenche essas duas colunas.
