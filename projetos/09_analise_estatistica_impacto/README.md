# modelo_impacto — mensuração do impacto de data centers

Etapa final da modelagem: mede o quanto a chegada de um data center muda vegetação,
construção, temperatura de superfície e indicadores socioeconômicos de uma região, além do
que já era esperado pela tendência regional. A leitura de referência pra entender a
estrutura de dados usada aqui é o
[guia de estrutura de dados](guia_estrutura_dados_modelo_impacto.md) — leia-o antes dos
scripts, ele define os conceitos (`tratado`, `horizonte`, ano de referência/baseline,
grupo de controle, `par_id`) que os dois steps abaixo pressupõem.

## Entrada: o painel consolidado

Os steps partem de `dados/gold/consolidado_impacto_modelo.csv` — uma linha por
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
`consolidado_impacto_modelo.csv`** — ele hoje é montado manualmente, unindo a saída do
[Modelo 1](../../modelos/modelo_1_classificacao_imagem/) (classificação de cobertura do solo)
com dados de LST, o pareamento do
[Modelo 2](../../modelos/modelo_2_grupo_controle/selecao_candidatos/README.md) e o
socioeconômico de [`06_extracao_socioeconomico/ibge`](../06_extracao_socioeconomico/ibge/README.md).
Reconstruir esse join como um `step0_monta_painel.py` é o próximo passo natural pra fechar o
pipeline ponta-a-ponta — hoje ele é o único elo que ainda depende de um processo manual.

## Pipeline

| Step | Arquivo | O que faz |
|---|---|---|
| 1 | `step1_analise_exploratoria.py` | Visão geral, event study, teste de placebo, DiD simples, rankings, correlações e a curva de efeito líquido por par/horizonte |
| 1b | `step1b_analise_consequencias.py` | Testa significância do efeito líquido (permutação + FDR) numa janela FIXA de horizontes pós-obra (`config.HORIZONTES_ALVO`), gera a narrativa "o que a chegada de um data center pode causar" e uma primeira mediação física (o que explica a variação de LST) |
| 1c | `step1c_analise_por_fase.py` | Mesma pergunta do 1b, mas separada pela fase REAL da obra (`pre`/`durante`/`pos`, calculada por site a partir de `ano_operacional` — não uma janela fixa igual pra todo mundo) |
| 2 | `step2_estagio2_modelo_efeito.py` (**ainda não existe** — ver gap abaixo) | Treinaria um modelo que aprende o efeito líquido a partir do porte do data center + tendência pré-obra, validado com Leave-One-DC-Out |

`comum.py` guarda a lógica compartilhada entre os steps (cálculo de ano-base e `delta_*` —
ver item 4 do guia; a inclinação da tendência pré-obra — item 5; e o cálculo de efeito
líquido por par, usado tanto pelo step1 quanto pelo step1b).

```bash
cd projetos/09_analise_estatistica_impacto
pip install -r requirements.txt
python step1_analise_exploratoria.py
python step1b_analise_consequencias.py
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

Saídas em `dados/gold/efeito_liquido/`:
- `efeito_liquido_por_par.csv` — um registro por (par, horizonte, variável).
- `curva_efeito_liquido.csv` — agregado (média, mediana, desvio padrão, nº de pares) por
  (variável, horizonte).
- `figuras/event_study_tratamento_x_controle.png`, `figuras/curva_efeito_liquido.png`.
- `relatorio_analise_exploratoria.html` — tudo acima num único HTML autocontido.

## step1b — análise de consequências

Responde a pergunta que o step1 só descreve: **o efeito líquido de cada variável é
estatisticamente diferente de zero, ou pode ser ruído dessa amostra pequena?** Para isso:

1. Colapsa o efeito líquido por par pra **1 valor por (par, variável)** — a média dos
   horizontes pós-obra (`config.HORIZONTES_ALVO`). Isso é deliberado: testar em cima das
   linhas por horizonte trataria observações do mesmo par como independentes (mesma
   pseudo-replicação que o item 9 do guia já proíbe pro Leave-One-DC-Out).
2. Testa cada variável com um **teste de permutação de sinal** (exato até 20 pares, Monte
   Carlo acima disso) e estima o **IC95% por bootstrap** — sem depender de `scipy` (não está
   no requirements) nem da suposição de normalidade de um teste-t com n~15.
3. Corrige os p-valores por **Benjamini-Hochberg** (FDR) — testar ~10 variáveis a 5% sem
   correção infla o risco de falso positivo pra quase 40%.
4. Gera uma **narrativa em texto** a partir da tabela (as variáveis que sobrevivem à
   correção, ordenadas por tamanho de efeito) — a resposta direta pra "o que a chegada de um
   data center pode causar num terreno".
5. Roda uma **mediação física exploratória**: regride `delta_lst_media_celsius` sobre as
   variações de vegetação/solo exposto/área construída (por área, 1 linha por site) pra ver
   qual mudança de cobertura do solo mais anda junto com o aquecimento — regressão
   observacional (OLS manual via numpy + p-valor por permutação), não uma prova causal.

Saídas em `dados/gold/efeito_liquido/`:
- `consequencias_terreno_resumo.csv` — 1 linha por variável: média, IC95%, Cohen's d,
  p-valor e p-valor FDR.
- `consequencias_terreno_mediacao_lst.csv` — coeficientes padronizados da mediação de LST.
- `figuras/forest_plot_consequencias.png` (só se `matplotlib` estiver instalado — o script
  roda e produz os CSVs/HTML mesmo sem ele).
- `relatorio_consequencias_terreno.html`.

## step1c — significância por fase real da obra (pré/durante/pós)

`step1b` colapsa o efeito líquido numa janela fixa de horizontes (`HORIZONTES_ALVO = [0,1,2]`)
igual pra todo data center. Mas a obra não dura o mesmo tempo em todo mundo — o painel real
mostra o horizonte `+1` de um site que construiu em 1 ano já como fase `"pos"` (operando), e o
`+1` de um que levou 3 anos ainda como `"durante"`. `step1c` usa a coluna `fase` do painel
diretamente (por site, não uma janela fixa), rodando os mesmos testes do 1b (permutação, IC95%
bootstrap, Cohen's d) em 3x mais combinações (10 variáveis × 3 fases = 30), com FDR aplicado
em cima de todas as 30 juntas.

**Ressalva:** o horizonte -1 (ano-base) é rotulado `"pre"` no painel, mas seu efeito líquido é
sempre 0 por construção (é a própria referência) — excluído da agregação de `"pre"` aqui, senão
puxaria essa fase artificialmente pra zero.

**Resultado real (rodado em 2026-09-14):** ainda **0 de 30** combinações variável×fase
significativas após FDR (alfa=0.05) — mesmo veredito honesto do step1b, agora com mais detalhe.
Os dois sinais mais próximos de significância (mas que não sobrevivem à correção): `populacao`
na fase `pos` (Cohen's d "média" 0.61, p bruto=0.006, p_fdr=0.176) e `lst_media_celsius` caindo
mais na fase `pos` (-0.34°C) do que na `durante` (-0.15°C) — nenhum dos dois cruza o limiar após
corrigir por 30 comparações.

Saída: `consequencias_por_fase.csv`, `figuras/comparacao_fases.png`.

## step2 — Estágio 2 (aprender o efeito)

Monta, por área: **features fixas** (nível e tendência pré-obra de cada variável-alvo,
porte do data center, bioma/região) e o **alvo** (efeito líquido nos horizontes
`config.HORIZONTES_ALVO = [0, 1, 2]`). Treina um Random Forest raso
(`max_depth=config.RF_MAX_DEPTH`, hoje 3) por variável de `config.VARS_MODELO`
(`prop_vegetacao_densa`, `prop_construida_urbana`, `lst_media_celsius`), valida com
**Leave-One-DC-Out** (remove a área inteira, nunca uma linha isolada — item 9 do guia) e
compara com uma baseline ingênua que só prevê a média do treino.

Saídas em `dados/gold/efeito_liquido/`:
- `validacao_leave_one_dc_out.csv` — MAE do modelo vs. baseline, por variável.
  `melhora_vs_baseline_%` perto de 0 (ou negativa) = o modelo não aprendeu nada além da
  média; valores bem positivos (>30-40%) indicariam sinal real capturado pelas features.
- `modelos/modelo_efeito_<variavel>.joblib` — modelo final (treinado com todos os dados)
  por variável, reutilizável via `joblib.load(...)` + `prever_impacto()`.
- `figuras/importancia_features_estagio2.png`.

## Técnicas pensadas para causalidade (além do que já está implementado)

O DiD/event study do step1 e o teste de permutação do step1b já são inferência causal
"de base" (contrafactual via grupo de controle + placebo pré-tendência). O que seria o
próximo degrau, em ordem de prioridade dado o tamanho de amostra atual:

- **Regressão DiD com covariáveis** (em vez de só a diferença de médias) — controla
  explicitamente por `bioma`, `regiao`, porte do data center e tendência pré-obra na mesma
  equação, em vez de só comparar médias brutas tratamento x controle. É o passo mais barato
  a partir do painel que já existe.
- **Efeitos fixos de par/tempo (two-way fixed effects)** — absorve qualquer choque que afete
  igualmente tratamento e controle de um mesmo par (seca regional, crise, nova rodovia) sem
  precisar listar essas variáveis uma a uma.
- **Synthetic control** — em vez de 1 controle por par (ou a média de poucos), constrói um
  "controle sintético" como combinação ponderada de vários municípios parecidos; ganha
  robustez justamente quando o número de controles reais por data center é pequeno, como é
  o caso aqui (`n_predios_no_campus` e pareamento 1:1 hoje).
- **Double Machine Learning / causal forests** — estimaria efeito heterogêneo (o efeito é
  diferente pra data center grande vs. pequeno? Cerrado vs. Mata Atlântica?) controlando por
  muitas covariáveis ao mesmo tempo sem imposição de forma funcional linear. Só compensa
  quando a amostra crescer — com 15 pares, o risco de overfitting é alto.
- **Inferência por randomização/placebo espacial** — em vez de só testar os horizontes
  negativos (item 3 do guia), testar "datas de tratamento" e "polígonos" falsos sorteados
  aleatoriamente e comparar a distribuição desses efeitos-placebo com o efeito observado;
  robusto a autocorrelação espacial que testes de permutação simples ignoram.
- **Mediação/path analysis formal** (o step1b faz uma versão simples com 1 regressão) —
  encadear vegetação → solo exposto → construção → LST → indicadores socioeconômicos como um
  grafo causal explícito (SEM ou DAG com ajuste por backdoor), em vez de uma regressão
  isolada por efeito.
- **Variável instrumental pro braço socioeconômico** — população/emprego/PIB têm causalidade
  reversa óbvia (a região que já estava crescendo é mais atraente pro data center); sem um
  instrumento (algo que mude a chance de receber um data center sem afetar diretamente a
  economia local, ex.: proximidade de backbone de fibra pré-existente), esse braço deve ficar
  como correlação, não como efeito — é por isso que o step1b não inclui as vars
  socioeconômicas na mediação.

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
- **`step2_estagio2_modelo_efeito.py` ainda não existe** neste repositório (só documentado
  aqui e no guia) — o que existe hoje, além do step1, é o `step1b_analise_consequencias.py`
  e o `step1c_analise_por_fase.py`.

## Análise exploratória à parte: amostra estendida (32 pares BR+EUA)

`step_analise_32dc_br_eua.py` é uma investigação **à parte do estudo oficial de 15 pares**
acima — não o substitui. Testa se ampliar a amostra para 31 pares (Brasil + uma fonte
suplementar de data centers nos EUA) melhora a significância estatística do efeito líquido.
Usa as mesmas funções de `comum.py` (sem alterá-las) e corrige, isoladamente neste script, um
problema de dado encontrado só na base estendida (linhas de tratamento dos EUA sem
`pareado_com` preenchido).

```bash
python step_analise_32dc_br_eua.py
```

Saídas em `dados/gold/efeito_liquido_32dc/`:
- `resumo_significancia_32dc.csv` — mesmo formato de `consequencias_terreno_resumo.csv`, mas
  para os 31 pares.
- `comparacao_15_vs_31_pares.csv` — p-valor e p-valor FDR lado a lado, 15 vs. 31 pares.

**Resultado:** os p-valores melhoram com a amostra maior (ex.: área construída, p_fdr
0,94 → 0,19), mas nenhuma variável cruza o limiar de significância (α=0,05) após a correção —
mesma conclusão qualitativa do estudo de 15 pares, com mais evidência de que o problema é
tamanho de amostra, não ausência de sinal.

## Exportação para o dashboard Power BI

`export_gold_powerbi.py` gera as tabelas gold que alimentam o dashboard (aba "efeito líquido" +
aba "por data center", com imagens raw e classificadas por ano) — ver
[`dados/gold/powerbi_export/README.md`](../../dados/gold/powerbi_export/README.md).
