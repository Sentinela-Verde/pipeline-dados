# Guia de Estrutura de Dados — Modelo de Impacto de Data Centers

Este guia reúne as definições principais sobre como estruturar a tabela de dados que vai alimentar o modelo de mensuração de impacto da chegada de um data center em uma região. Serve como referência rápida e como material de apoio para explicar o desenho do problema.

## 1. Unidade de observação

Cada linha da tabela representa **uma área, em um horizonte de tempo específico** — não uma área por ano bruto, nem uma área única resumindo tudo. Uma mesma área (seja um data center real ou uma área de controle) gera várias linhas, uma para cada horizonte medido.

## 2. Coluna `tratado`

Sinaliza se a linha pertence a uma área que **recebeu de fato um data center** (`tratado = 1`) ou a uma área de controle, parecida, que não recebeu (`tratado = 0`). É o que separa, dentro da mesma tabela, os casos reais dos casos de comparação.

## 3. Coluna `horizonte`

É a distância, em anos, entre o ano da linha e o **ano de referência** daquela área (ver item 4). Pode ser:

- **Positivo (lag)** — anos depois da abertura do data center. Ex.: `horizonte = 0` é o próprio ano de abertura, `horizonte = +1` é um ano depois, e assim por diante.
- **Negativo (lead)** — anos antes da abertura. Servem como **teste de placebo**: se a área já estivesse mudando sozinha antes do data center existir, isso apareceria como um salto nos leads, o que seria um alerta de que a comparação não é confiável.

## 4. Ano de referência (baseline)

Cada área tem um único ano de referência: **o ano de abertura do data center menos 1** (ou, no caso de um controle, o ano de abertura do data center ao qual ele está pareado, menos 1). Todo `delta` é calculado contra esse mesmo ano, não importa se o horizonte é positivo ou negativo. A linha correspondente a `horizonte = -1` não existe na tabela, porque seria a comparação do ano de referência com ele mesmo (sempre daria zero).

## 5. Features de nível e tendência pré-implantação

Calculadas a partir dos anos anteriores ao ano de referência, para cada variável extraída da imagem de satélite (vegetação, água, construção, estrada):

- **Nível** — o valor da variável no ano de referência.
- **Tendência** — a inclinação de uma reta ajustada sobre os anos pré-disponíveis, indicando se a região já estava mudando por conta própria (crescimento urbano natural) antes do data center chegar.

Essas colunas são fixas para a área — não mudam entre as linhas de horizonte diferentes da mesma área.

## 6. Colunas de alvo (`delta_*`)

Uma coluna por variável de interesse (vegetação, água, construção, estrada, temperatura, indicadores socioeconômicos), sempre calculada como a diferença entre o valor no ano da linha e o valor no ano de referência. É o que o modelo aprende a prever no Estágio 2.

## 7. Expansão do horizonte (usando toda a série de satélite)

Como a série de satélite cobre 2016–2026 (11 anos), é possível usar a janela inteira disponível em vez de se limitar a `horizonte = 0, +1, +2`. Isso pode gerar até **10 linhas por área** (11 anos menos o ano de referência excluído). A proporção entre leads e lags varia conforme o ano de abertura: um data center que abriu no meio da série fica equilibrado; um que abriu perto do fim tem muitos leads e poucos lags disponíveis (e o inverso para quem abriu no início da série).

Importante: isso aumenta a densidade de observação por evento, mas **não aumenta o número de eventos reais** — continuam sendo os mesmos data centers. A validação (item 9) precisa continuar agrupando por área, não por linha.

## 8. Grupo de controle

Uma área de controle é uma região parecida (nível e tendência pré-implantação semelhantes, porte de município e distância de centros urbanos compatíveis) que **não recebeu data center**. Ela serve para estimar o contrafactual: o que teria acontecido com a área do data center se ele não tivesse sido construído.

Diferença importante em relação aos leads (item 3): os leads testam a própria área do data center contra o passado dela; o controle estima o que aconteceria com uma área parecida no mesmo período pós-abertura, isolando choques regionais que afetariam as duas áreas igualmente (seca, crise econômica, nova infraestrutura).

**Estrutura:** cada controle é uma linha própria na tabela (mesmo formato de todas as outras), com `tratado = 0` e uma coluna `par_id` apontando para qual data center ele está pareado. **É possível ter vários controles por data center** — isso não exige nenhuma mudança na estrutura, só mais linhas com o mesmo `par_id`. Formato de coluna (um `delta_controle` ao lado do `delta_tratado`) não escala bem quando o número de controles varia entre data centers, por isso o formato em linha é o recomendado.

Com múltiplos controles, a média (ou mediana) deles em cada horizonte pode ser comparada com a área tratada — isso é calculado como etapa de análise, não precisa ser uma coluna fixa da tabela principal.

## 9. Validação (Leave-One-DC-Out)

Como cada área gera várias linhas correlacionadas, a validação não pode remover linhas isoladas — precisa remover **a área inteira** de uma vez. E quando a área removida é um data center, os controles pareados a ele (via `par_id`) saem junto do treino nessa rodada. Isso evita que o modelo veja informação sobre a vizinhança da área de teste através dos seus próprios controles.

## 10. Casos especiais (fora do treino/validação padrão)

- **Sem ano de abertura preenchido** — não é possível calcular ano de referência nem deltas; ficam bloqueados até o dado ser completado.
- **Abriu antes do início da série de satélite (2016)** — não há como calcular nível/tendência pré-implantação; fica fora do treino.
- **Ainda não abriu** — não tem `delta` observado ainda; vira caso de teste real (previsão) depois que o modelo estiver pronto, não entra no treino nem na validação.

## Exemplo consolidado

| area_id | tratado | par_id | horizonte | veg_nivel_pre | veg_tendencia_pre | delta_vegetacao |
|---|---|---|---|---|---|---|
| ascenty_vinhedo | 1 | — | -3 | 0.62 | -0.01 | +0.00 |
| ascenty_vinhedo | 1 | — | 0 | 0.62 | -0.01 | -0.08 |
| ascenty_vinhedo | 1 | — | +1 | 0.62 | -0.01 | -0.15 |
| controle_vinhedo_a | 0 | ascenty_vinhedo | -3 | 0.60 | -0.01 | -0.01 |
| controle_vinhedo_a | 0 | ascenty_vinhedo | 0 | 0.60 | -0.01 | -0.01 |
| controle_vinhedo_b | 0 | ascenty_vinhedo | 0 | 0.58 | -0.02 | +0.00 |

Essa é a tabela única que reúne áreas tratadas e de controle, todos os horizontes disponíveis, pronta para alimentar o Estágio 2 do modelo.
