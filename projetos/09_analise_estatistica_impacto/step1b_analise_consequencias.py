"""Step 1b — análise de consequências: o que a chegada de um data center causa no terreno.

Ver o README.md desta pasta (seções "Possíveis gaps" e "Técnicas pensadas para causalidade")
pro raciocínio completo por trás deste script. Resumindo o que ele faz que o `step1` (análise
exploratória) não fazia:

1. **Testa significância**, não só descreve. `step1_analise_exploratoria.py` calcula média,
   mediana e desvio-padrão do efeito líquido por (variável, horizonte) — mas nunca pergunta
   "isso é diferente de zero, ou pode ser ruído dessa amostra pequena?". Este script responde
   essa pergunta.
2. **Nunca pseudo-replica linhas do mesmo par.** O painel tem várias linhas (horizontes) por
   área. Testar significância direto nessas linhas trataria o horizonte 0 e o horizonte +1 do
   MESMO par como duas observações independentes — não são (mesmo princípio do item 9 do
   `guia_estrutura_dados_modelo_impacto.md`, que exige Leave-One-DC-Out por área, não por
   linha). Aqui, cada par vira exatamente 1 número por variável antes de qualquer teste.
3. **Corrige por comparações múltiplas** (Benjamini-Hochberg). Testar ~10 variáveis a 5% de
   significância sem correção dá quase 40% de chance de pelo menos 1 falso positivo só por
   acaso — e é fácil ler esse falso positivo como "o data center causou X".
4. **Usa permutação e bootstrap, não teste-t.** Com n_pares por volta de 15, a suposição de
   normalidade de um teste-t paramétrico é frágil. Permutação (sign-flip) e bootstrap não
   exigem distribuição nenhuma — só reamostragem —, e não dependem de `scipy` (que não está
   no `requirements.txt` deste projeto).
5. **Tenta reconstruir uma cadeia, não só listar sintomas soltos.** Além do "o que muda"
   (seção 1), a seção 2 pergunta "o que explica o quê": o quanto a queda de vegetação e o
   aumento de solo exposto/área construída (mudança física de 1ª ordem) andam junto com o
   aumento de LST (efeito de 2ª ordem) — uma primeira mediação, deliberadamente descrita como
   correlacional/observacional, não como prova causal.

Saídas em `config.OUTPUT_DIR` (mesma pasta do step1, `dados/gold/efeito_liquido/`):
- `consequencias_terreno_resumo.csv` — 1 linha por variável-alvo: efeito médio, IC95%
  (bootstrap), Cohen's d, p-valor (permutação) e p-valor corrigido (FDR).
- `consequencias_terreno_mediacao_lst.csv` — coeficientes padronizados da regressão de
  delta_LST sobre as variáveis de cobertura do solo, com p-valor por permutação.
- `figuras/forest_plot_consequencias.png` (se `matplotlib` estiver instalado).
- `relatorio_consequencias_terreno.html` — narrativa em texto gerada a partir da tabela de
  resumo, pronta pra ler sem precisar interpretar CSV.

Uso:
    python step1b_analise_consequencias.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from comum import calcula_deltas, calcula_efeito_liquido_por_par
from relatorio_html import RelatorioHTML

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ModuleNotFoundError:
    HAS_MPL = False

pd.set_option("display.float_format", "{:.4f}".format)
RNG = np.random.default_rng(config.RANDOM_STATE)


# ============================================================================
# Inferência sem scipy: permutação, bootstrap e FDR na mão.
# Deliberado — o requirements.txt deste projeto não lista scipy, e a amostra é pequena o
# bastante (n_pares ~15) pra não precisar de nada mais sofisticado que reamostragem direta.
# ============================================================================

def _todas_combinacoes_sinal(n: int) -> np.ndarray:
    """Todas as 2**n combinações de sinal (+1/-1) possíveis para n observações, como matriz
    (2**n, n). Usa os bits da própria contagem 0..2**n-1 em vez de `itertools.product`/
    `np.meshgrid` — mais leve de memória e sem loop em Python."""
    bits = (np.arange(2 ** n)[:, None] >> np.arange(n)) & 1
    return 1 - 2 * bits  # bit 0 -> sinal +1, bit 1 -> sinal -1


def teste_permutacao_sinal(valores: np.ndarray) -> float:
    """P-valor bicaudal de H0: "a distribuição do efeito líquido é simétrica em torno de 0".

    Sign-flip test: sob H0, qual dos dois lados de cada par vira "tratamento" é arbitrário,
    então o sinal de cada efeito líquido observado também é. Enumera todas as combinações de
    sinal quando `n <= config.LIMITE_PERMUTACAO_EXATA` (teste exato); acima disso, amostra
    Monte Carlo. Estatística: a média (mais sensível a deslocamento consistente que a
    mediana, que é robusta demais pra amostra já pequena).
    """
    valores = np.asarray(valores, dtype=float)
    n = len(valores)
    media_obs = valores.mean()

    if n <= config.LIMITE_PERMUTACAO_EXATA:
        sinais = _todas_combinacoes_sinal(n)
    else:
        sinais = RNG.choice([1, -1], size=(config.N_PERMUTACOES_MONTE_CARLO, n))

    medias_nulas = (sinais * valores).mean(axis=1)
    return float(np.mean(np.abs(medias_nulas) >= np.abs(media_obs) - 1e-12))


def bootstrap_ic95(valores: np.ndarray) -> tuple[float, float]:
    """IC95% da média por bootstrap percentil (reamostra pares com reposição)."""
    valores = np.asarray(valores, dtype=float)
    n = len(valores)
    idx = RNG.integers(0, n, size=(config.N_BOOTSTRAP, n))
    medias_boot = valores[idx].mean(axis=1)
    return float(np.percentile(medias_boot, 2.5)), float(np.percentile(medias_boot, 97.5))


def cohen_d_uma_amostra(valores: np.ndarray) -> float:
    """Tamanho de efeito padronizado (média / desvio-padrão) — permite comparar o quão forte
    é o efeito entre variáveis com escalas bem diferentes (proporção 0-1 vs. °C vs. R$ mil)."""
    valores = np.asarray(valores, dtype=float)
    desvio = valores.std(ddof=1)
    return float(valores.mean() / desvio) if desvio > 0 else np.nan


def magnitude_cohen_d(d: float) -> str:
    if np.isnan(d):
        return "n/d"
    ad = abs(d)
    if ad < 0.2:
        return "desprezível"
    if ad < 0.5:
        return "pequena"
    if ad < 0.8:
        return "média"
    return "grande"


def corrige_fdr_benjamini_hochberg(p_valores: pd.Series) -> pd.Series:
    """Benjamini-Hochberg — controla a taxa de falsos positivos entre TODOS os testes
    rodados juntos (aqui, uma variável-alvo por teste), em vez de avaliar cada p-valor
    isoladamente a 5%."""
    validos = p_valores.dropna().sort_values()
    m = len(validos)
    if m == 0:
        return p_valores.copy()
    ranks = np.arange(1, m + 1)
    ajustado = validos.to_numpy() * m / ranks
    ajustado = np.minimum.accumulate(ajustado[::-1])[::-1]  # torna monótono (passo padrão do BH)
    ajustado = np.clip(ajustado, 0, 1)
    return pd.Series(ajustado, index=validos.index).reindex(p_valores.index)


# ============================================================================
# 1) Efeito líquido por par, colapsado num único nº por (par, variável) pós-obra
# ============================================================================

def monta_efeito_por_par_pos_obra(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (par, variável): média do efeito líquido nos horizontes pós-obra
    (`config.HORIZONTES_ALVO`) disponíveis pra aquele par — ver item 2 do docstring do
    módulo sobre por que isso não pode ser feito linha a linha."""
    efeito_df = calcula_efeito_liquido_por_par(df, config.VARS_ALVO)
    pos = efeito_df[efeito_df["horizonte"].isin(config.HORIZONTES_ALVO)]
    return pos.groupby(["par", "variavel"])["efeito_liquido"].mean().reset_index()


# ============================================================================
# 2) Resumo estatístico por variável-alvo
# ============================================================================

def secao_resumo_significancia(efeito_par_var: pd.DataFrame, relatorio: RelatorioHTML) -> pd.DataFrame:
    print("=" * 70)
    print("1. SIGNIFICÂNCIA DO EFEITO LÍQUIDO PÓS-OBRA, POR VARIÁVEL")
    print("=" * 70)

    linhas = []
    for var in config.VARS_ALVO:
        valores = efeito_par_var.loc[efeito_par_var["variavel"] == var, "efeito_liquido"].dropna().to_numpy()
        n = len(valores)
        if n < config.MIN_PARES_TESTE:
            linhas.append({
                "variavel": var, "n_pares": n, "media": np.nan, "mediana": np.nan,
                "ic95_baixo": np.nan, "ic95_alto": np.nan, "cohen_d": np.nan,
                "magnitude": "amostra insuficiente", "p_valor": np.nan,
            })
            continue

        media = float(valores.mean())
        ic_baixo, ic_alto = bootstrap_ic95(valores)
        d = cohen_d_uma_amostra(valores)
        p = teste_permutacao_sinal(valores)
        linhas.append({
            "variavel": var, "n_pares": n, "media": media, "mediana": float(np.median(valores)),
            "ic95_baixo": ic_baixo, "ic95_alto": ic_alto, "cohen_d": d,
            "magnitude": magnitude_cohen_d(d), "p_valor": p,
        })

    resumo = pd.DataFrame(linhas)
    resumo["p_valor_fdr"] = corrige_fdr_benjamini_hochberg(resumo.set_index("variavel")["p_valor"]).to_numpy()
    resumo["significativo_fdr"] = resumo["p_valor_fdr"] < config.ALPHA
    resumo["direcao"] = np.select(
        [resumo["media"] > 0, resumo["media"] < 0], ["aumenta", "diminui"], default="n/d"
    )
    resumo = resumo.sort_values("p_valor_fdr", na_position="last")

    print(resumo.round(4).to_string(index=False))
    n_significativas = int(resumo["significativo_fdr"].sum())
    print(f"\n-> {n_significativas} de {len(resumo)} variáveis com efeito líquido "
          f"estatisticamente diferente de 0 após correção FDR (alfa={config.ALPHA}).")

    relatorio.secao("1. Significância do efeito líquido pós-obra, por variável")
    relatorio.texto(
        "Cada linha testa se o efeito líquido médio (delta_tratamento - delta_controle, "
        "média dos horizontes pós-obra) é consistentemente diferente de zero ENTRE OS PARES "
        "— não linha a linha, pra não pseudo-replicar o mesmo evento.\n"
        "Teste: permutação de sinal (sign-flip), bicaudal. IC95%: bootstrap percentil "
        f"({config.N_BOOTSTRAP:,} reamostragens). p_valor_fdr: correção Benjamini-Hochberg "
        "pra comparações múltiplas."
    )
    relatorio.tabela(resumo.round(4))
    return resumo


def narrativa_consequencias(resumo: pd.DataFrame) -> list[str]:
    """Gera frases legíveis a partir da tabela de resumo — a resposta direta pra "o que a
    chegada de um data center pode causar num terreno", em vez de deixar só a tabela falar."""
    significativas = resumo[resumo["significativo_fdr"]].reindex(
        resumo[resumo["significativo_fdr"]]["cohen_d"].abs().sort_values(ascending=False).index
    )
    if significativas.empty:
        return [
            "Nenhuma variável passou no teste de significância após a correção por "
            "comparações múltiplas — com a amostra atual (poucos pares, muita linha com "
            "qualidade_par == 'ruim'), não dá pra afirmar efeito causal robusto pra nenhuma "
            "variável ainda. Ver seção de limitações."
        ]

    frases = []
    for _, row in significativas.iterrows():
        sinal = "reduz" if row["direcao"] == "diminui" else "aumenta"
        frases.append(
            f"{row['variavel']}: a chegada do data center {sinal}, em média, "
            f"{row['media']:+.4f} (IC95% [{row['ic95_baixo']:+.4f}, {row['ic95_alto']:+.4f}]) "
            "em relação ao que se esperaria pela tendência da região (grupo de controle) — "
            f"efeito de magnitude {row['magnitude']} (Cohen's d={row['cohen_d']:.2f}), "
            f"com {int(row['n_pares'])} pares avaliados (p_fdr={row['p_valor_fdr']:.3f})."
        )
    return frases


# ============================================================================
# 3) Mediação física: o que explica o aumento de LST
# ============================================================================

def regressao_ols_manual(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """OLS com intercepto via mínimos quadrados (numpy puro — sem scikit-learn, que não está
    instalado neste ambiente e não está listado no requirements.txt deste projeto)."""
    X_com_intercepto = np.column_stack([np.ones(len(X)), X])
    coef, *_ = np.linalg.lstsq(X_com_intercepto, y, rcond=None)
    return coef  # [intercepto, beta_1, beta_2, ...]


def permutacao_coeficientes(X: np.ndarray, y: np.ndarray, n_permutacoes: int) -> np.ndarray:
    """P-valor por permutação pra cada coeficiente: embaralha y, reajusta o modelo, e compara
    a magnitude do coeficiente sob o embaralhamento com a observada. Evita depender de scipy
    pra distribuição t/F, ao custo de n_permutacoes ajustes de OLS (barato: n é pequeno)."""
    coef_obs = regressao_ols_manual(X, y)
    contagem = np.zeros(len(coef_obs))
    for _ in range(n_permutacoes):
        y_perm = RNG.permutation(y)
        coef_perm = regressao_ols_manual(X, y_perm)
        contagem += np.abs(coef_perm) >= (np.abs(coef_obs) - 1e-12)
    return contagem / n_permutacoes


def secao_mediacao_lst(df: pd.DataFrame, relatorio: RelatorioHTML):
    print("\n" + "=" * 70)
    print("2. MEDIAÇÃO FÍSICA: O QUE EXPLICA A VARIAÇÃO DE LST NAS ÁREAS TRATADAS")
    print("=" * 70)

    tratadas_pos = df[
        (df["tipo"] == "tratamento") & (df["ano_relativo_ao_inicio_obra"].isin(config.HORIZONTES_ALVO))
    ]
    colunas_preditoras = [f"delta_{v}" for v in config.VARS_MEDIACAO_LST]
    por_site = (
        tratadas_pos.groupby("site_id")[colunas_preditoras + ["delta_lst_media_celsius"]]
        .mean()
        .dropna()
    )

    n = len(por_site)
    n_min = config.MIN_PARES_TESTE + len(config.VARS_MEDIACAO_LST)
    print(f"n_sites (1 valor por site, média dos horizontes pós-obra): {n}")
    if n < n_min:
        aviso = (
            f"Amostra insuficiente pra regressão de mediação com confiança (n={n}, "
            f"{len(config.VARS_MEDIACAO_LST)} preditores, mínimo recomendado n>={n_min}) "
            "— seção pulada."
        )
        print(aviso)
        relatorio.secao("2. Mediação física: o que explica a variação de LST")
        relatorio.nota(aviso)
        return None

    y = por_site["delta_lst_media_celsius"].to_numpy()
    X_bruto = por_site[colunas_preditoras].to_numpy()
    # padroniza os preditores (z-score) só pra poder comparar magnitude de coeficiente entre
    # variáveis com escalas diferentes (proporção 0-1 de área vs. proporção 0-1 de área)
    desvios = X_bruto.std(axis=0, ddof=1)
    desvios[desvios == 0] = 1.0  # evita divisão por zero se algum preditor for constante
    X = (X_bruto - X_bruto.mean(axis=0)) / desvios

    coef = regressao_ols_manual(X, y)
    p_valores = permutacao_coeficientes(X, y, config.N_PERMUTACOES_MONTE_CARLO)

    resultado = pd.DataFrame({
        "preditor": ["intercepto"] + colunas_preditoras,
        "coeficiente_padronizado": coef,
        "p_valor_permutacao": p_valores,
    })
    print(resultado.round(4).to_string(index=False))
    print(
        "\n-> coeficiente_padronizado: quanto delta_lst muda (em °C) por 1 desvio-padrão de "
        "variação no preditor, mantendo os outros preditores fixos. Regressão observacional "
        f"em cima de só {n} áreas — ajuda a apontar qual mudança de cobertura do solo caminha "
        "junto com o aquecimento, não prova que causa por si só."
    )

    relatorio.secao("2. Mediação física: o que explica a variação de LST")
    relatorio.texto(
        f"Regressão OLS (n={n} áreas tratadas, 1 valor por área = média dos horizontes "
        "pós-obra) de delta_lst_media_celsius sobre as variações de cobertura do solo. "
        "Preditores padronizados (z-score) pra comparar magnitude entre eles. P-valor por "
        f"permutação ({config.N_PERMUTACOES_MONTE_CARLO:,} embaralhamentos de y)."
    )
    relatorio.tabela(resultado.round(4))
    relatorio.nota(
        "Regressão observacional, não um experimento controlado — trate como hipótese pra "
        "investigar com mais dado (mais data centers reais), não como efeito causal "
        "estabelecido. Ver 'Técnicas pensadas para causalidade' no README."
    )
    return resultado


# ============================================================================
# 4) Figura (opcional — só roda se matplotlib estiver instalado)
# ============================================================================

def figura_forest_plot(resumo: pd.DataFrame, relatorio: RelatorioHTML):
    if not HAS_MPL:
        relatorio.nota("matplotlib não instalado neste ambiente — forest plot pulado (dados completos no CSV).")
        print("\n(matplotlib não instalado — pulando forest plot; dados completos no CSV)")
        return

    plotavel = resumo.dropna(subset=["media"]).sort_values("media")
    fig, ax = plt.subplots(figsize=(8, max(3, 0.5 * len(plotavel))))
    cores = ["tab:red" if sig else "tab:gray" for sig in plotavel["significativo_fdr"]]
    erro_baixo = plotavel["media"] - plotavel["ic95_baixo"]
    erro_alto = plotavel["ic95_alto"] - plotavel["media"]
    for i, (_, row) in enumerate(plotavel.iterrows()):
        ax.errorbar(row["media"], i, xerr=[[erro_baixo.iloc[i]], [erro_alto.iloc[i]]],
                    fmt="o", color=cores[i], ecolor=cores[i], capsize=3)
    ax.set_yticks(range(len(plotavel)))
    ax.set_yticklabels(plotavel["variavel"])
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Efeito líquido médio pós-obra (IC95% bootstrap)")
    ax.set_title("Efeito líquido por variável — vermelho = significativo após FDR")
    fig.tight_layout()

    relatorio.figura(fig, "Efeito líquido por variável (forest plot) — vermelho = significativo após FDR")
    fig.savefig(config.FIGURAS_DIR / "forest_plot_consequencias.png", dpi=150)
    plt.close(fig)


# ============================================================================

def main():
    df = pd.read_csv(config.CONSOLIDADO_CSV)
    df, _ = calcula_deltas(df, config.VARS_ALVO)

    relatorio = RelatorioHTML(
        "O que a chegada de um data center pode causar num terreno",
        f"Painel: {config.CONSOLIDADO_CSV.name} | {df['site_id'].nunique()} áreas | "
        f"{df['pareado_com'].nunique()} pares tratamento-controle",
    )

    efeito_par_var = monta_efeito_por_par_pos_obra(df)
    resumo = secao_resumo_significancia(efeito_par_var, relatorio)

    print("\n" + "=" * 70)
    print("NARRATIVA")
    print("=" * 70)
    relatorio.secao("Narrativa")
    for frase in narrativa_consequencias(resumo):
        print("- " + frase)
        relatorio.texto(frase)

    figura_forest_plot(resumo, relatorio)
    mediacao = secao_mediacao_lst(df, relatorio)

    relatorio.secao("Limitações (leia antes de citar qualquer número acima)")
    relatorio.texto(
        "- Amostra pequena: 15 pares tratamento-controle únicos hoje; qualquer p-valor aqui "
        "é sobre essa amostra, não uma verdade populacional.\n"
        "- qualidade_par: boa parte das linhas do painel tem qualidade_par == 'ruim' e entra "
        "nos testes sem filtro — refazer só com qualidade 'bom'/'aceitável' é a primeira "
        "checagem de robustez a rodar se os resultados mudarem o quadro.\n"
        "- A mediação de LST é regressão observacional em poucas áreas — sinal pra investigar "
        "com mais dado, não efeito causal estabelecido.\n"
        "- Efeitos socioeconômicos (população, emprego, PIB) não entraram na mediação: têm "
        "causalidade reversa plausível (a região cresce e por isso atrai o data center, não "
        "só o contrário) e exigem uma técnica que trate esse viés — ver 'Técnicas pensadas "
        "para causalidade' no README."
    )

    caminho_resumo = config.OUTPUT_DIR / config.CONSEQUENCIAS_RESUMO_CSV_NAME
    resumo.to_csv(caminho_resumo, index=False)
    print(f"\nResumo salvo em {caminho_resumo}")

    if mediacao is not None:
        caminho_mediacao = config.OUTPUT_DIR / config.CONSEQUENCIAS_MEDIACAO_CSV_NAME
        mediacao.to_csv(caminho_mediacao, index=False)
        print(f"Mediação salva em {caminho_mediacao}")

    caminho_html = relatorio.salvar(config.OUTPUT_DIR / config.CONSEQUENCIAS_RELATORIO_HTML_NAME)
    print(f"Relatório HTML: {caminho_html}")


if __name__ == "__main__":
    main()
