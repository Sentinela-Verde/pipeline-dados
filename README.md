# Sugestão de estrutura de pastas — dados, modelos e projetos

Proposta v1 para o time de arquitetura, derivada direto do
[diagrama de pipeline](diagrama.html) já revisado. Hoje o pipeline
está espalhado em **3 repositórios** (`data-extraction`, `modelo-imagens-satelite` e o protótipo
abandonado `datacenter-extracao-modelos`), cada um com sua própria convenção de pastas — esta
proposta organiza tudo sob uma estrutura única, agrupando por **dados / modelos / projetos**, do
jeito que o time pediu.

> Isto é ponto de partida pra discussão, não decisão fechada — em particular, os 5 pontos
> marcados como "⚠ decisão em aberto" abaixo precisam de um dono antes de qualquer migração.

## Status da migração

Migração incremental: o código e o dado de cada fonte estão sendo trazidos pra cá aos poucos,
antes de reconectar o pipeline como um todo — ver `## De-para` para o destino de cada peça.

- [x] **01 · Coleta datacenter** — código de `data-extraction/extract/scraping_datacentermap/`
      copiado para `projetos/01_coleta_datacenter/`; dado bruto (cache JSON + CSV final) copiado
      de `data-extraction/data/raw/datacentermap/` e `outputs_extraction/datacentermap_datacenters.csv`
      para `dados/bronze/datacentermap/`. **Ainda não integrado ao resto do pipeline nesta pasta.**
- [ ] 02 · Extração de imagem
- [ ] 03 · Extração de labels
- [ ] 04 · Índices espectrais
- [ ] 05 · Extração LST
- [x] **06 · Extração socioeconômico** — só a parte IBGE: código de `extract/bigquery_ibge/`
      copiado para `projetos/06_extracao_socioeconomico/ibge/`; dado (`ibge_municipios.csv`)
      copiado para `dados/bronze/ibge/`. **US ainda pendente** (`socioeconomico_us/` continua vazio).
- [ ] Modelo 1 — treino/inferência
- [x] **Modelo 2 — grupo de controle (só seleção de candidatos)** — código de
      `modeling/modelo_grupo_controle/` copiado para
      `modelos/modelo_2_grupo_controle/selecao_candidatos/`; dados (cidades similares, 6 pontos,
      mapa) copiados para `dados/silver/grupo_controle/`. **`comparacao_estatistica/` continua
      vazio** — esse código ainda não existe em nenhum repositório hoje (ver decisão 4).
      ⚠️ depende de `datacenter_filtrado.csv` (gerado por `transform/filtra_datacenter/`, não
      migrado ainda) pra rodar de ponta a ponta.
- [ ] 07 · Reiteração / expansão da amostra
- [ ] 08 · Consolidação — **código continua inexistente** (ver decisão 3); só o dado final
      (`consolidado_impacto_modelo.csv`, hoje montado manualmente) foi copiado pra
      `dados/gold/`, junto com a migração da análise estatística abaixo
- [x] **09 · Análise estatística de impacto** — código de `modeling/modelo_impacto/` copiado
      para `projetos/09_analise_estatistica_impacto/`, **excluindo deliberadamente
      `step2_estagio2_modelo_efeito.py`** (o modelo de Estágio 2/Random Forest não faz parte
      deste escopo); dados (`consolidado_impacto_modelo.csv`, curva de efeito líquido, event
      study, relatório HTML) copiados para `dados/gold/`

## Árvore proposta

```
sentinela_verde/
│
├── dados/                                  # data lake — 1 convenção única (ver decisão 1)
│   ├── bronze/                             # bruto, exatamente como veio da fonte
│   │   ├── datacentermap/                  # ✅ scraping (JSON cru, cache incremental) — já puxado
│   │   ├── imagens_satelite/
│   │   │   ├── landsat/
│   │   │   └── sentinel2/
│   │   ├── labels/
│   │   │   ├── mapbiomas/
│   │   │   └── worldcover/
│   │   ├── ibge/                           # ✅ já puxado
│   │   └── socioeconomico_us/              # equivalente ao IBGE, para grupo controle nos EUA (⚠ fonte a definir)
│   │
│   ├── silver/                             # tratado / intermediário
│   │   ├── features/                       # bandas + 7 índices, por sensor x site x ano
│   │   ├── expansao_amostra/               # série no raio menor + calibrador de obra (etapa 9)
│   │   └── grupo_controle/                 # 6 candidatos + comparação estatística (etapa 6/6a) + escolha final
│   │
│   ├── gold/                               # pronto pra modelar / analisar
│   │   ├── dataset_classificacao.parquet   # dataset amostrado que alimenta o treino (5a)
│   │   ├── consolidado_impacto_modelo.csv  # ⚠ hoje montado manualmente — etapa 7 do diagrama
│   │   └── efeito_liquido/                 # saídas do step1: curvas, event study, CSVs
│   │
│   ├── labels_manual/                      # 211 polígonos humanos — é INSUMO versionado, não saída
│   └── manifests/                          # proveniência (sha256, parâmetros) — sempre commitado
│
├── modelos/
│   ├── modelo_1_classificacao_imagem/
│   │   ├── treino/                         # sentinela.train — roda 1x, gera o artefato (etapa 5a)
│   │   ├── inferencia/                     # sentinela.predict — reaplica (etapas 5b e 6b)
│   │   ├── config/                         # classes.yml, params.yml, sites.geojson
│   │   └── artefatos/                      # *.joblib + *.sha256 (binário — ver decisão 2)
│   │
│   └── modelo_2_grupo_controle/
│       ├── selecao_candidatos/             # ✅ já puxado — KNN cidade similar (BR ou US) + 6 pontos candidatos
│       ├── comparacao_estatistica/         # chama a inferência do modelo 1 (dependência cruzada,
│       │                                   # ver nota abaixo) + compara nível/tendência pré-obra
│       └── artefatos/
│
├── projetos/                               # 1 pasta por etapa do diagrama, numeradas na mesma ordem
│   ├── 01_coleta_datacenter/               # ✅ código já puxado
│   ├── 02_extracao_imagem/
│   ├── 03_extracao_labels/
│   ├── 04_indices_espectrais/
│   ├── 05_extracao_lst/
│   ├── 06_extracao_socioeconomico/         # ibge/ (Brasil) + socioeconomico_us/ (⚠ fonte a definir)
│   ├── 07_reiteracao_expansao_amostra/     # + candidatos do scraping, joblib em raio menor, calibrador de obra
│   ├── 08_consolidacao/                    # ⚠ não existe hoje — ver decisão 3
│   └── 09_analise_estatistica_impacto/     # ✅ já puxado (sem o Estágio 2/RF) — event study, placebo, DiD, curva efeito líquido
│
├── docs/
│   ├── decisoes/                           # ADRs (ex.: status de propostas como Dynamic World)
│   ├── tarefas/                            # 1 tarefa por arquivo
│   └── guia_estrutura_dados.md
│
├── apresentacao/                           # material pra banca/stakeholders (já existe hoje)
│
└── proximos_passos/                        # backlog isolado, fora do pipeline ativo
    ├── energia_aneel_mme/                  # já tem coleta pronta, não conectada
    ├── agua_snis/                          # já tem coleta pronta, não conectada
    └── ruido/                              # sem fonte de dado ainda
```

## De-para com o que existe hoje

| Repositório atual | Pasta/arquivo atual | Vai para |
|---|---|---|
| `data-extraction` | `extract/scraping_datacentermap/` | ✅ `projetos/01_coleta_datacenter/` |
| `data-extraction` | `data/raw/datacentermap/` + `data/raw/outputs_extraction/datacentermap_datacenters.csv` | ✅ `dados/bronze/datacentermap/` |
| `data-extraction` | `extract/imagens_satelite/{landsat,sentinel2}/` | `projetos/02_extracao_imagem/` |
| `data-extraction` | `extract/bigquery_ibge/` | ✅ `projetos/06_extracao_socioeconomico/ibge/` |
| — | *(não existe ainda)* | `projetos/06_extracao_socioeconomico/socioeconomico_us/` — precisa de fonte equivalente ao IBGE pros EUA |
| `data-extraction` | `modeling/modelo_grupo_controle/` | ✅ `modelos/modelo_2_grupo_controle/selecao_candidatos/` |
| — | *(não existe ainda)* | `modelos/modelo_2_grupo_controle/comparacao_estatistica/` — reaplica o `.joblib` do modelo 1 nos 6 candidatos e compara nível/tendência com o data center |
| `data-extraction` | `modeling/modelo_impacto/step1_*.py` (sem step2) | ✅ `projetos/09_analise_estatistica_impacto/` |
| `data-extraction` | `data/silver/consolidado_impacto_modelo.csv` + `data/gold/modelo_impacto/{curva_efeito_liquido,efeito_liquido_por_par}.csv` etc. | ✅ `dados/gold/` |
| `data-extraction` | `data/{bronze,silver,gold}/` | `dados/{bronze,silver,gold}/` (já usa a convenção proposta) |
| `modelo-imagens-satelite` | `src/sentinela/dataset.py`, `train.py` | `modelos/modelo_1_classificacao_imagem/treino/` |
| `modelo-imagens-satelite` | `src/sentinela/predict.py` | `modelos/modelo_1_classificacao_imagem/inferencia/` |
| `modelo-imagens-satelite` | `config/`, `models/*.joblib` | `modelos/modelo_1_classificacao_imagem/{config,artefatos}/` |
| `modelo-imagens-satelite` | `data/{raw,interim,processed}/` | `dados/{bronze,silver,gold}/` (precisa migrar convenção) |
| `modelo-imagens-satelite` | `data/labels_manual/`, `data/manifests/` | `dados/{labels_manual,manifests}/` (sem mudança) |
| `modelo-imagens-satelite` | `scripts/nucleo_datacenter_por_ano.py`, `datar_obra_por_serie.py` | `projetos/07_reiteracao_expansao_amostra/` — ⚠ hoje esses scripts só reaproveitam classificação já feita (raio 500m sobre os 15 sites); o fluxo alvo (rodar o `.joblib` direto num raio menor para pontos *novos* do scraping) precisa de um caminho de inferência que ainda não existe |
| `modelo-imagens-satelite` | `docs/decisoes/`, `docs/tarefas/` | `docs/{decisoes,tarefas}/` (sem mudança) |
| `data-extraction` | `extract/aneel_energia_municipio/`, `bigquery_mme_energia_uf/`, `bigquery_snis_agua/` | `proximos_passos/{energia_aneel_mme,agua_snis}/` |
| `datacenter-extracao-modelos` | (protótipo abandonado, working tree já apagado) | não migra — decidir se arquiva o repo ou apaga de vez |

## Decisões em aberto (o time de arquitetura precisa bater o martelo)

### 1 · Uma convenção única de data lake: `bronze/silver/gold` ou `raw/interim/processed`?

Hoje os dois nomes convivem: `data-extraction` usa bronze/silver/gold (linguagem clássica de
engenharia de dados); `modelo-imagens-satelite` usa raw/interim/processed (convenção comum em
projetos de ML, tipo cookiecutter-data-science). Nenhum dos dois está errado — mas ter os dois no
mesmo pipeline obriga quem lê o código a lembrar qual repo usa qual nome. **Proposta**: padronizar
em `bronze/silver/gold`, porque já é o nome usado na camada final (a que o time de negócio/banca
mais vê, em `modeling/modelo_impacto`) — mas a decisão final é do time.

### 2 · Onde ficam os artefatos binários (`.joblib`, `.tif`, `.parquet`)?

Hoje são gitignored nos dois repos (por bom motivo — são pesados). Numa estrutura única, vale
decidir: ficam fora do controle de versão mesmo (com um manifest de proveniência apontando pra
onde buscar, como já é feito hoje), ou passam a usar algo como Git LFS / bucket S3 versionado? Isso
importa principalmente pro artefato do Modelo 1 (`rf_{tag}.joblib`) — é o "produto" mais crítico de
reproduzir.

### 3 · Quem escreve o `08_consolidacao/`?

Esta é a maior lacuna do pipeline hoje (marcada em âmbar, como etapa manual, no diagrama): não existe
nenhum script que junte classificação (tratamento + controle) + LST + IBGE num painel único — é
feito manualmente. Virar código aqui é o que fecha o pipeline ponta-a-ponta e também é pré-requisito
pra rodar a expansão da amostra (etapa 9) de forma automática, não pontual.

### 4 · Modelo 2 agora depende do Modelo 1 — isso muda a ordem de deploy/versionamento

Com a comparação estatística dos 6 candidatos (etapa 6a do diagrama) e a expansão automática da
amostra (etapa 9), `modelo_2_grupo_controle/` e `projetos/07_reiteracao_expansao_amostra/` passam a
**chamar o `.joblib` do Modelo 1** diretamente — não são mais dois modelos independentes que só se
encontram no painel consolidado. Isso tem duas implicações pra arquitetura: (1) uma mudança no
Modelo 1 (novo treino, novo `tag`) pode invalidar resultados do Modelo 2 já gerados, então vale
registrar no manifest do Modelo 2 **qual `sha256` do `.joblib`** foi usado; (2) o pacote/serviço que
expõe a inferência do Modelo 1 precisa ser importável tanto por quem roda a classificação direta
(etapas 5b/6b) quanto por quem roda a seleção de controle (6a) e a expansão (9) — ou seja, a
inferência não pode ficar "presa" dentro do projeto do Modelo 1 sem uma forma de reuso.

### 5 · Fonte de dado socioeconômico dos EUA ainda não existe

`socioeconomico_us/` está na árvore como placeholder — nenhuma extração equivalente ao IBGE para
municípios/condados americanos foi encontrada no código hoje. Antes de implementar
`modelos/modelo_2_grupo_controle/` para sites nos EUA, alguém precisa decidir a fonte (Census
Bureau ACS? BLS? outra?) — isso também é pré-requisito da expansão internacional mencionada no
ADR-006 do `modelo-imagens-satelite` (hoje proposta, não aprovada).

## Por que separar `treino/` de `inferencia/` dentro do Modelo 1

Reflete a distinção que ajustamos no diagrama: **treino roda uma vez e é caro** (gera o `.joblib`);
**inferência é barata e reaplicada várias vezes** (tratamento, controle, e potencialmente novos
sites conforme a amostra cresce). Separar as pastas deixa claro pra quem chega no repo que rodar
`inferencia/` no dia a dia é normal, mas rodar `treino/` de novo é uma decisão consciente (novo
dataset, novo experimento) — não algo que acontece a cada execução do pipeline.
