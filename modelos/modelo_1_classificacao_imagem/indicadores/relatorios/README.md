# Validação cruzada de sensores — evidência do fator de correção

Estes seis CSVs são a razão de existir de duas colunas do `dados/gold/area_por_classe.csv`:
**`fator_correcao_sensor`** e **`faixa_serie`**. Quem for usar aquele CSV para comparar níveis ou
tendências ao longo do tempo precisa saber o que está aqui.

Todos são medidos sobre a classificação **`rf_v2.0-dw`** — a mesma que gera o CSV publicado.

## O problema que eles medem

A série muda de sensor no meio: Landsat (30 m) até 2018, Sentinel-2 (10 m) de 2019 em diante. Uma
mudança de área entre 2018 e 2019 pode ser obra de verdade — ou só o sensor trocando. Nos anos de
sobreposição (2019-2021) os dois sensores cobrem o mesmo terreno, e é isso que permite separar as
duas coisas.

| arquivo | o que responde |
|---|---|
| `diferenca_area_por_classe.csv` | por site × ano × classe, quanto da diferença é **resolução** (`diff_resolucao`) e quanto é **sensor** (`diff_sensor_isolado`), comparando Landsat, S2 nativo e S2 agregado a 30 m |
| `degrau_2018_vs_overlap.csv` | o degrau publicado na virada 2018→2019 contra o controle real, com uma coluna `veredito` por site × classe |
| `estabilidade_fator_por_site_classe.csv` | o fator é estável entre anos? (`media`, `desvio`, `cv` por site × classe) |
| `heterogeneidade_fator_entre_sites.csv` | o fator é estável entre sites? É o `cv_entre_sites` daqui que decide se dá para corrigir |
| `concordancia_espacial_por_par.csv` | % de concordância pixel a pixel entre os dois sensores, separando borda e interior |
| `matriz_confusao_agregada.csv` | matriz de confusão Landsat × S2-agregado-30m, nas 5 classes |

## Como isso vira o fator

O método está gravado em `../parametros/fator_correcao_sensor_sv20_rf_v2.0-dw.json` — um arquivo
de fator por classificação, porque o fator é calibrado **sobre** uma delas:

> `fator_mult = area_s2_agregado_30m_ha / area_landsat_ha` (mesma resolução, 30 m nos dois lados —
> isola sensor de resolução), média dos 3 anos de sobreposição, **por site**. Só aplicado se
> estável dentro do site (CV < 0,30 entre anos) **e** parecido entre sites (CV < 0,35 entre a
> média dos 16 sites). Base: 48 pares de sobreposição.

Só duas classes foram avaliadas, e sob o `rf_v2.0-dw` **as duas passam no critério**:

| classe | estável dentro do site | CV entre sites | tratamento | efeito no CSV |
|---|---|---|---|---|
| 4 · `construida_urbana` | 16/16 sites | 0,211 | **corrige** | `fator_correcao_sensor` por site, de 1,0867 a 2,2947 |
| 3 · `solo_exposto_obras` | 15/16 sites | 0,307 | **corrige** | `fator_correcao_sensor` por site, de 0,2440 a 0,8393 |

As classes 1, 2 e 5 não estão no JSON — saem com fator 1,0. Para referência, o
`heterogeneidade_fator_entre_sites.csv` mede as cinco: a 1 (`vegetacao_densa`) tem o menor CV
entre sites, 0,087, e a 5 (`agua`) o maior, 0,520.

**A classe 3 mudou de desfecho com a recalibragem.** Sob o `rf_v1.0-tuned` ela tinha CV entre
sites de 0,440 e ficava sem correção ("calibrar em 3 anos e aplicar aos outros 6 da era Landsat
seria chute, não correção"). Sob o `rf_v2.0-dw` o CV cai para 0,307 e ela passa a ser corrigida —
o Dynamic World tem classe `bare` nativa, e a classificação resultante se comporta de forma mais
consistente entre os dois sensores. A classe 4 continua corrigida, mas com fatores diferentes: os
do v1.0 iam de 0,4359 a 1,0977 (encolhiam a área Landsat), os do v2.0-dw vão de 1,0867 a 2,2947
(aumentam). É a medida de quanto o fator antigo estava errado para esta classificação.

**Consequência prática:** a coluna `faixa_serie` continua sendo a forma de saber o que é
comparável com o quê:

| `faixa_serie` | linhas no CSV |
|---|---|
| `sentinel2_oficial_2019_2025` | 560 |
| `landsat_pre2019_nao_corrigido` | 378 |
| `landsat_pre2019_corrigido_sv20` | 252 |
| `landsat_overlap_referencia` | 240 |

## Proveniência

Todos os seis CSVs e o JSON saem de uma execução só, sobre os rasters do `rf_v2.0-dw`:

```
python -m sentinela.validacao_sensores --modelo models/rf_v2.0-dw.joblib \n                                       --token classificado-rf_v2.0-dw
```

48 pares de sobreposição (16 sites × 3 anos), nenhuma reclassificação — o módulo só lê os rasters
que a inferência já escreveu.

**⚠ Sem gerador neste repositório.** Estes CSVs e o JSON foram copiados como artefatos: o
`validacao_sensores.py` continua em `modelo-imagens-satelite` e não foi migrado. Se a
classificação for reexecutada, nada aqui se atualiza sozinho — é preciso rodar o comando acima lá
e copiar os arquivos de volta.

O que o `export_indicadores.py` daqui garante é que o fator não seja aplicado à classificação
errada: ele lê `fator_correcao_sensor_sv20_<modelo_versao>.json` e **falha** se o `modelo_versao`
gravado no JSON não for o que está sendo exportado. Foi exatamente esse cruzamento silencioso que
produziu a primeira versão deste CSV.
