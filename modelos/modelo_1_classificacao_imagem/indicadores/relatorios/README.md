# Validação cruzada de sensores — evidência do fator de correção

Estes seis CSVs são a razão de existir de duas colunas do `dados/gold/area_por_classe.csv`:
**`fator_correcao_sensor`** e **`faixa_serie`**. Quem for usar aquele CSV para comparar níveis ou
tendências ao longo do tempo precisa saber o que está aqui.

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

O método está gravado em `../parametros/fator_correcao_sensor_sv20.json`:

> `fator_mult = area_s2_agregado_30m_ha / area_landsat_ha` (mesma resolução, 30 m nos dois lados —
> isola sensor de resolução), média dos 3 anos de sobreposição, **por site**. Só aplicado se
> estável dentro do site (CV < 0,30 entre anos) **e** parecido entre sites (CV < 0,35 entre a
> média dos 16 sites). Base: 48 pares de sobreposição.

Só duas classes foram avaliadas, e o desfecho foi diferente para cada uma:

| classe | CV entre sites | tratamento | efeito no CSV |
|---|---|---|---|
| 4 · `construida_urbana` | 0,241 | **corrige** | `fator_correcao_sensor` por site, de 0,4359 a 1,0977 |
| 3 · `solo_exposto_obras` | 0,440 | **não corrige** | fator fica 1,0; a série é publicada em faixas separadas |

As classes 1, 2 e 5 não estão no JSON — saem com fator 1,0.

Para a classe 3, a justificativa gravada é explícita: *"calibrar em 3 anos e aplicar aos outros 6
anos da era Landsat seria chute, não correção"*. O fator médio entre sites dela é 13,1 — ordem de
grandeza que mostra por que emendar seria temerário.

**Consequência prática:** para a classe 3, não compare direto um valor da era Landsat com um da era
Sentinel-2. Use a coluna `faixa_serie`, que separa as quatro situações:

| `faixa_serie` | linhas no CSV |
|---|---|
| `sentinel2_oficial_2019_2025` | 560 |
| `landsat_pre2019_nao_corrigido` | 504 |
| `landsat_overlap_referencia` | 240 |
| `landsat_pre2019_corrigido_sv20` | 126 |

## ⚠ Duas ressalvas sérias

**1. O fator foi calibrado sobre outro modelo.** O JSON traz `modelo_versao: rf_v1.0-tuned`, mas o
CSV publicado é do `rf_v2.0-dw`. Ou seja: a correção de sensor aplicada às linhas de
`construida_urbana` foi derivada da classificação antiga. As duas classificações não produzem as
mesmas áreas (a mediana de `solo_exposto_obras` vai de 1,81% para 4,90% entre elas), então **o
fator não é necessariamente válido para o v2.0-dw**. Recalibrar exige rodar
`sentinela.validacao_sensores` sobre os rasters do v2.0-dw — não foi feito.

**2. Sem gerador neste repositório.** Estes CSVs e o JSON foram copiados como artefatos. Saem de
`sentinela.validacao_sensores`, que não foi migrado — se a classificação for reexecutada, nada
aqui se atualiza sozinho. O gerador continua em `modelo-imagens-satelite`.
