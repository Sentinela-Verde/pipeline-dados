# Etapa 5 — Extração de LST (temperatura de superfície)

Série anual de temperatura de superfície por site, para a frente "Temperatura (paralelo)" do
diagrama. É de onde vêm as colunas `lst_*` do painel consolidado que a análise de impacto usa —
a hipótese de ilha de calor só é testável com isto aqui.

```
python lst.py                      # todos os sites, 2016-2025
python lst.py --site ascenty-vinhedo
python lst.py --ano-inicio 2020 --ano-fim 2025
```

Precisa de credencial do Earth Engine (`EE_PROJECT` no `.env` da raiz; `EE_SERVICE_ACCOUNT_KEY`
opcional, para rodar sem browser).

## Fonte: MODIS, não Landsat

**O diagrama dizia "Extração LST (Landsat)" e estava errado** — foi corrigido junto com esta
migração. A implementação sempre usou `MODIS/061/MOD11A2` (Terra, LST diurna, composto de 8 dias,
1 km), e a justificativa está em `METODOLOGIA.md`:

- o MOD11A2 cobre a janela inteira com **o mesmo sensor, mesma resolução e mesmo produto**;
- o termal do Landsat exigiria harmonizar Landsat 8/9 (100 m reamostrado para 30 m) e deixaria
  **2016-2018 sem fonte**, porque o Sentinel-2 não tem banda termal — só haveria Landsat termal
  de 2019 em diante;
- para série anual por site dentro de um buffer de 5 km (~78 km²), 1 km de pixel é suficiente.

O preço está registrado como limitação: **não dá para medir contraste dentro do site** (o prédio
contra a vegetação a 200 m). Isso exigiria Landsat termal, e é uma frente separada se o time
quiser.

## O que sai

Tudo em `dados/bronze/temperatura/` — bronze porque é dado bruto de fonte externa, como as
imagens e os rótulos; nada aqui é derivado de outra etapa deste repositório.

| arquivo | conteúdo |
|---|---|
| `temperatura_lst.csv` | 1 linha por site × ano: `lst_media_celsius`, `n_observacoes`, fonte e data de extração. É o que a consolidação (etapa 8) junta ao painel |
| `lst_cenas_brutas.csv` | 1 linha por cena de 8 dias — a granularidade fina, para auditar uma média suspeita sem reextrair |
| `log_extracao.json` | avisos de cobertura baixa, site/ano sem dado e valor fora da faixa de sanidade, mais as contagens da execução |

Os três são leves (220 KB no total) e ficam versionados aqui — a regra de dado pesado só no S3
não se aplica.

## Como a média anual é construída

Para cada site/ano, **cada cena** do composto de 8 dias vira uma média regional dos pixels válidos
dentro do buffer (escala nativa, 1 km). A média anual é a média simples dessas médias de cena.

Um ano tem ~46 cenas de 8 dias, o que já dá ponderação praticamente uniforme ao longo do ano —
por isso não existe passo intermediário por mês. `n_observacoes` é o número de cenas com pelo
menos 1 pixel válido: é a coluna para desconfiar de uma média feita sobre poucas cenas (nuvem
persistente). Abaixo de 20 cenas, o site/ano entra como aviso no log.

Cenas 100% nubladas dentro do buffer simplesmente não produzem valor — o `aggregate_array` do
Earth Engine já as omite.

## Verificação da migração

Rodei a versão migrada contra a de origem em `angonap-fortaleza`, 2016 e 2017:

| ano | média (°C) | cenas |
|---|---|---|
| 2016 | 31,84 | 43 |
| 2017 | 31,30 | 46 |

Idêntico ao publicado. As **89 linhas de cena bruta** desses dois anos batem linha a linha com o
arquivo do repositório de origem. Sem deriva de comportamento.

## Diferenças em relação ao original

- **Parâmetros saíram do código** para `parametros/params.yml`: coleção, banda, fator de escala,
  janela, buffer padrão e os dois limiares de qualidade. O original tinha tudo como constante de
  módulo.
- **Ganhou CLI**: `--site`, `--ano-inicio`, `--ano-fim`. O original rodava sempre tudo.
- **Saída pelo `config.py` da etapa**, em `dados/bronze/temperatura/`, em vez de caminhos fixos
  dentro de `modelo-impacto/`.
- **Sem geopandas.** O original importava a geometria pelo caminho do classificador; aqui o
  `sites.geojson` é lido com o `json` da biblioteca padrão, porque nenhuma operação geométrica
  acontece localmente — quem recorta é o Earth Engine.

## O que NÃO veio, e por quê

O repositório de origem tem um segundo script, `impacto_dc_08_lst_pontos.py`, que extrai LST para
os **30 pontos do painel — tratamento e controle**, começando em 2013 em vez de 2016. Ele reusa a
mesma função de extração deste arquivo (mesma coleção, mesmo redutor), mas depende do pareamento
tratamento×controle (`pareamento_controle_rf.csv`) e do painel de features do modelo de impacto,
que ainda não existem neste repositório — é a frente do Modelo 2 / comparação estatística.

Na prática isso quer dizer: **o `temperatura_lst.csv` daqui só cobre o lado tratado.** Quando o
grupo de controle entrar, a extração de LST dos controles precisa passar por este mesmo código, na
mesma execução — se as duas pontas da comparação vierem de caminhos diferentes, a diferença entre
elas deixa de ser interpretável. É a mesma disciplina que a regra de sensor único aplica à
cobertura do solo.
