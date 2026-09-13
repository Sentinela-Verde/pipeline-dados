# modelo_impacto — mensuração do impacto de data centers

Etapa final da modelagem: mede o quanto a chegada de um data center muda vegetação,
construção, temperatura de superfície e indicadores socioeconômicos de uma região, além do
que já era esperado pela tendência regional. A leitura de referência pra entender a
estrutura de dados usada aqui é o
[guia de estrutura de dados](guia_estrutura_dados_modelo_impacto.md) — leia-o antes dos
scripts, ele define os conceitos (`tratado`, `horizonte`, ano de referência/baseline,
grupo de controle, `par_id`) que os dois steps abaixo pressupõem.

## Entrada: o painel consolidado

Ambos os steps partem de `data/silver/consolidado_impacto_modelo.csv` — uma linha por
**área x horizonte** (uma área tratada ou de controle, num ano relativo à abertura do data
center ao qual está pareada). Colunas principais:

| Grupo | Colunas |
|---|---|
| Identificação | `site_id`, `tipo` (`tratamento`/`controle`), `pareado_com`, `municipio`, `uf` |
| Horizonte | `ano`, `ano_inicio_obra`, `ano_relativo_ao_inicio_obra`, `fase` (`pre`/`durante`/`pos`) |
| Pareamento | `qualidade_par`, `dist_tratamento_controle_km` |
| Porte do data center | `mw_construido_total`, `tier`, `tier_projetado_max`, `n_predios_no_campus`, `whitespace_construido_sqm_total` |
| Contexto | `bioma`, `regiao` |
| Satélite | `prop_vegetacao_densa`, `prop_vegetacao_rala`, `prop_solo_exposto_obras`, `prop_construida_urbana`, `prop_agua` |
| Clima | `lst_media_celsius` |
| Socioeconômico | `populacao`, `emprego_formal_total`, `pib_mil_reais`, `numero_empresas` |

### ⚠️ Lacuna conhecida: não existe (ainda) um step que gere esse CSV

Diferente do resto do pipeline, **nenhum script deste repositório produz o
`consolidado_impacto_modelo.csv`** — ele hoje é um insumo pronto (um painel já montado
fora daqui, unindo a saída de
[`modeling/modelo_classifica_imagem`](../modelo_classifica_imagem/README.md) com dados de
LST, o pareamento de
[`modeling/modelo_grupo_controle`](../modelo_grupo_controle/README.md) e o socioeconômico
de [`extract/bigquery_ibge`](../../extract/bigquery_ibge/README.md)). Reconstruir esse join
como um `step0_monta_painel.py` é o próximo passo natural pra fechar o pipeline
ponta-a-ponta — hoje ele é o único elo que ainda depende de um processo manual.

## Pipeline

| Step | Arquivo | O que faz |
|---|---|---|
| 1 | `step1_analise_exploratoria.py` | Visão geral, event study, teste de placebo, DiD simples, rankings, correlações e a curva de efeito líquido por par/horizonte |
| 2 | `step2_estagio2_modelo_efeito.py` | Treina o modelo que aprende o efeito líquido a partir do porte do data center + tendência pré-obra, valida com Leave-One-DC-Out |

`comum.py` guarda a lógica compartilhada pelos dois (cálculo de ano-base e `delta_*` —
ver item 4 do guia; e a inclinação da tendência pré-obra — item 5).

```bash
cd data-extraction/modeling/modelo_impacto
pip install -r requirements.txt
python step1_analise_exploratoria.py
python step2_estagio2_modelo_efeito.py
```

## step1 — análise exploratória

Recalcula `delta_<var>` (variação de cada variável-alvo em relação ao ano-base pré-obra da
área) e roda, nessa ordem: visão geral e % de nulos, médias tratamento x controle, **event
study** (evolução do delta por horizonte, tratamento x controle), **teste de placebo**
(deltas nos horizontes negativos — devem ficar perto de 0), **DiD simples** (fase pós vs.
pré), rankings de municípios por maior perda de vegetação/aumento de LST, matriz de
correlação, e a **curva de efeito líquido** (`delta_tratamento - delta_controle`) agregada
entre os pares — esta última é o mesmo alvo que o step2 aprende a prever, só que aqui
descritivo (média/mediana entre pares), não modelado.

Saídas em `data/gold/modelo_impacto/`:
- `efeito_liquido_por_par.csv` — um registro por (par, horizonte, variável).
- `curva_efeito_liquido.csv` — agregado (média, mediana, desvio padrão, nº de pares) por
  (variável, horizonte).
- `figuras/event_study_tratamento_x_controle.png`, `figuras/curva_efeito_liquido.png`.

## step2 — Estágio 2 (aprender o efeito)

Monta, por área: **features fixas** (nível e tendência pré-obra de cada variável-alvo,
porte do data center, bioma/região) e o **alvo** (efeito líquido nos horizontes
`config.HORIZONTES_ALVO = [0, 1, 2]`). Treina um Random Forest raso
(`max_depth=config.RF_MAX_DEPTH`, hoje 3) por variável de `config.VARS_MODELO`
(`prop_vegetacao_densa`, `prop_construida_urbana`, `lst_media_celsius`), valida com
**Leave-One-DC-Out** (remove a área inteira, nunca uma linha isolada — item 9 do guia) e
compara com uma baseline ingênua que só prevê a média do treino.

Saídas em `data/gold/modelo_impacto/`:
- `validacao_leave_one_dc_out.csv` — MAE do modelo vs. baseline, por variável.
  `melhora_vs_baseline_%` perto de 0 (ou negativa) = o modelo não aprendeu nada além da
  média; valores bem positivos (>30-40%) indicariam sinal real capturado pelas features.
- `modelos/modelo_efeito_<variavel>.joblib` — modelo final (treinado com todos os dados)
  por variável, reutilizável via `joblib.load(...)` + `prever_impacto()`.
- `figuras/importancia_features_estagio2.png`.

## Limitações (herdadas de `proposta_projeto.md`)

- **Amostra pequena** (poucos pares tratamento/controle) — o Leave-One-DC-Out é a
  validação honesta possível hoje; qualquer ganho vistoso sobre a baseline de média deve
  ser tratado com ceticismo até a amostra crescer.
- **Qualidade de pareamento** — uma fração relevante das linhas do painel tem
  `qualidade_par == "ruim"`; isso não é filtrado automaticamente por nenhum dos steps
  (decisão pendente — ver `qualidade_par` no painel), mas é a primeira alavanca a puxar se
  os resultados não melhorarem.
- **Dados de porte incompletos** — `mw_construido_total`, `tier`, `tier_projetado_max` têm
  bastante nulo; o `SimpleImputer` cobre tecnicamente o buraco, mas o modelo não aprende
  muito de uma coluna que é, na prática, "desconhecido" na maioria das linhas.
- **Modelo raso de propósito** — mantém a interpretabilidade que a proposta pede, mas
  também limita a capacidade de capturar interações mais complexas entre porte e contexto
  regional.
- **Lacuna do painel consolidado** — ver seção acima.
