# Pipeline de dados: coletas, armazenamento, modelos e análises

Pipeline de dados do Sentinela Verde: da coleta de data centers e imagens de satélite até a
análise estatística do impacto ambiental e territorial no entorno deles. Organiza, numa estrutura
única (**dados / modelos / projetos**), o que antes estava espalhado em **3 repositórios**
(`data-extraction`, `modelo-imagens-satelite` e o protótipo abandonado
`datacenter-extracao-modelos`), cada um com sua própria convenção de pastas.

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
        F1["Extração LST<br/>(Landsat)"]:::processo
        F2[["LST média por área/ano"]]:::dado
        B2 --> F1 --> F2
    end

    subgraph S7["Socioeconômico"]
        G1["BigQuery · IBGE"]:::fonte
        G2[["População, PIB, empresas<br/>por município (Brasil)"]]:::dado
        G3["Socioeconômico US<br/>(fonte a definir)"]:::fonte
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

❌ = ainda falta migrar (ou não existe código em nenhum repositório hoje):

- ❌ 05 · Extração LST
- ❌ `socioeconomico_us/` (dado + fonte a definir)
- ❌ Modelo 1 — treino/inferência (código ainda não migrado pra cá)
- ❌ `modelo_2_grupo_controle/comparacao_estatistica/` (código não existe em nenhum repositório hoje)
- ❌ 07 · Reiteração / expansão da amostra
- ❌ 08 · Consolidação (código não existe — ver decisões)

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
│   │   ├── ibge/
│   │   └── socioeconomico_us/              # ❌ falta migrar — equivalente ao IBGE pra grupo controle nos EUA, fonte a definir
│   │
│   ├── silver/                             # tratado / intermediário
│   │   ├── datacentermap_enderecos_corrigidos.csv  # endereço/município/estado/país/CEP (242/242 OK)
│   │   ├── features/                       # (AWS S3) — 13 bandas, dado derivado pesado
│   │   ├── expansao_amostra/               # série no raio menor + calibrador de obra (etapa 9)
│   │   └── grupo_controle/                 # 6 candidatos + comparação estatística (etapa 6/6a) + escolha final
│   │
│   ├── gold/                               # pronto pra modelar / analisar
│   │   ├── area_por_classe.csv             # série por site × ano × sensor × classe (rf_v2.0-dw) — ver decisão 5
│   │   ├── dataset_classificacao.parquet   # (AWS S3) — dataset amostrado que alimenta o treino (5a)
│   │   ├── consolidado_impacto_modelo.csv  # ⚠ hoje montado manualmente — etapa 7 do diagrama
│   │   └── efeito_liquido/                 # saídas do step1: curvas, event study, CSVs
│   │
│   ├── labels_manual/                      # 211 polígonos humanos — é INSUMO versionado, não saída
│   └── manifests/                          # 1.066 manifests — proveniência (sha256), sempre commitado
│
├── modelos/
│   ├── modelo_1_classificacao_imagem/      # ❌ treino/inferência ainda não migrados
│   │   ├── indicadores/                    # classificado → dados/gold/area_por_classe.csv;
│   │   │                                   # relatorios/ = validação cruzada de sensores (CSV no git)
│   │   ├── treino/                         # sentinela.train — roda 1x, gera o artefato (etapa 5a)
│   │   ├── inferencia/                     # sentinela.predict — reaplica (etapas 5b e 6b)
│   │   ├── config/                         # classes.yml, params.yml, sites.geojson
│   │   └── artefatos/                      # (AWS S3) — *.joblib + *.sha256
│   │
│   └── modelo_2_grupo_controle/
│       ├── selecao_candidatos/             # KNN cidade similar (BR ou US) + 6 pontos candidatos
│       ├── comparacao_estatistica/         # ❌ falta migrar — chama a inferência do modelo 1 (dependência
│       │                                   # cruzada, ver decisão 2) + compara nível/tendência pré-obra
│       └── artefatos/                      # (AWS S3)
│
├── projetos/                               # 1 pasta por etapa do diagrama, numeradas na mesma ordem
│   ├── 01_coleta_datacenter/               # inclui correcao_endereco/
│   ├── 02_extracao_imagem/                 # inclui relatorios/ (qualidade da ingestão, resíduo da harmonização)
│   ├── 03_extracao_labels/
│   ├── 04_indices_espectrais/
│   ├── 05_extracao_lst/                    # ❌ falta migrar
│   ├── 06_extracao_socioeconomico/         # ibge/ ok | socioeconomico_us/ ❌ falta migrar (fonte a definir)
│   ├── 07_reiteracao_expansao_amostra/     # ❌ falta migrar — candidatos do scraping, joblib em raio menor, calibrador de obra
│   ├── 08_consolidacao/                    # ❌ falta migrar — ver decisão 1
│   └── 09_analise_estatistica_impacto/     # sem o Estágio 2/RF — event study, placebo, DiD, curva efeito líquido
│
├── docs/
│   ├── decisoes/                           # ADRs (ex.: status de propostas como Dynamic World)
│   ├── tarefas/                            # 1 tarefa por arquivo
│   └── guia_estrutura_dados.md
│
└── proximos_passos/                        # backlog isolado, fora do pipeline ativo
    ├── energia_aneel_mme/                  # aneel_energia_municipio + bigquery_mme_energia_uf — não conectado ao pipeline ativo
    ├── agua_snis/                          # bigquery_snis_agua — sem dado, nunca foi gerado na fonte
    └── ruido/                              # sem fonte de dado ainda
```

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
Bureau ACS? BLS? outra?) — isso também é pré-requisito da expansão internacional mencionada no
ADR-006 do `modelo-imagens-satelite` (hoje proposta, não aprovada).

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

### 5 · Qual classificação é a de produção — e o fator de sensor calibrado na outra ⚠

`dados/gold/area_por_classe.csv` é o handoff para a comparação estatística (etapa 6a): uma linha
por site × ano × sensor × classe, com `area_m2`, `pct_area_valida`, `fator_correcao_sensor` e a
faixa da série. 1.430 linhas, 16 sites, 2013-2025. Foi gerado do **`rf_v2.0-dw`**, por coerência
com o Dynamic World ser a fonte de rótulo ativa desde 2026-09-11. Daí saem três pontos que
precisam de decisão, não só de registro:

1. **O `rf_v2.0-dw` nunca foi promovido a produção.** A inferência escreve em `classificado/`
   quando é produção e num prefixo versionado (`classificado-rf_v2.0-dw/`) quando é avaliação
   paralela — e esse modelo só existe no prefixo de avaliação. O exportador original tinha o
   prefixo fixo em `classificado_*`, então **não conseguia exportar essa classificação**: ela
   existia no disco e era invisível para ele. A versão migrada ganhou `--token` para escolher o
   prefixo.
2. **É o modelo sob o qual o achado de impacto não replica** (9/14, p=0,21, contra 14/14,
   p=0,0001 do `rf_v1.0-tuned`). A escolha foi deliberada, por coerência com a fonte de rótulo —
   mas a divergência entre os dois é um resultado do projeto, não um detalhe de implementação.
   Para comparação: o `rf_v1.0-tuned` cobre 270 rasters e o `rf_v2.0-dw` cobre 286 (os 16 extras
   são anos Landsat tardios), e a mediana de `solo_exposto_obras` vai de 1,81% para 4,90% — o
   MapBiomas não tem classe de canteiro de obras e o DW tem `bare` nativa.
3. **O fator de correção de sensor foi calibrado sobre o OUTRO modelo.** O
   `fator_correcao_sensor_sv20.json` traz `modelo_versao: rf_v1.0-tuned`, e é ele que preenche a
   coluna `fator_correcao_sensor` das linhas de `construida_urbana` (0,4359 a 1,0977, por site).
   Como as duas classificações não produzem as mesmas áreas, **esse fator não é necessariamente
   válido para o `rf_v2.0-dw`**. Recalibrar exige rodar a validação de sensores sobre os rasters
   do v2.0-dw, o que não foi feito. A evidência do fator está em CSV, legível direto no GitHub:
   `modelos/modelo_1_classificacao_imagem/indicadores/relatorios/`.

No CSV, `tipo` é `tratamento` em toda linha e `pareado_com` está vazio: o grupo de controle ainda
não existe. É a etapa 6a que preenche essas duas colunas.
