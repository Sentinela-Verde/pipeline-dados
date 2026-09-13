"""Step 1 — análise exploratória do painel consolidado de impacto.

Carrega `data/silver/consolidado_impacto_modelo.csv`, calcula deltas em relação ao ano-base
pré-obra de cada área, e roda uma bateria de checagens: visão geral/qualidade dos dados,
event study (tratamento x controle), teste de placebo (pré-tendências), diferença-em-
diferenças simples, ranking de data centers por impacto, correlação entre variáveis, e a
curva de efeito líquido por par (`delta_tratamento - delta_controle`) e horizonte — o
insumo mais direto pro Estágio 2 (`step2_estagio2_modelo_efeito.py`).

Tudo é impresso no terminal (pra quem roda interativo) e também escrito num único relatório
HTML autocontido — ver `config.RELATORIO_EXPLORATORIA_HTML` — que já traz as tabelas e os
gráficos embutidos, pra abrir no navegador ou mandar pra alguém sem precisar dos CSVs/PNGs
ao lado.

Uso:
    python step1_analise_exploratoria.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from comum import calcula_deltas
from relatorio_html import RelatorioHTML

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

pd.set_option("display.float_format", "{:.4f}".format)
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3


def secao_visao_geral(df: pd.DataFrame, relatorio: RelatorioHTML):
    print("=" * 70)
    print("1. VISÃO GERAL")
    print("=" * 70)
    print(f"Linhas: {df.shape[0]} | Colunas: {df.shape[1]}")
    print(f"Data centers/áreas únicas (site_id): {df['site_id'].nunique()}")
    print(f"Pares (pareado_com): {df['pareado_com'].nunique()}")
    print("\nDistribuição tipo (tratamento x controle):")
    print(df["tipo"].value_counts())
    print("\nDistribuição fase da obra:")
    print(df["fase"].value_counts())
    print("\nQualidade do pareamento:")
    print(df["qualidade_par"].value_counts())
    nulos = (df.isna().mean() * 100).sort_values(ascending=False).head(15).round(1)
    print("\n% de valores nulos por coluna (top 15):")
    print(nulos)

    relatorio.secao("1. Visão geral")
    relatorio.texto(
        f"Linhas: {df.shape[0]} | Colunas: {df.shape[1]}\n"
        f"Data centers/áreas únicas (site_id): {df['site_id'].nunique()}\n"
        f"Pares (pareado_com): {df['pareado_com'].nunique()}"
    )
    relatorio.tabela(df["tipo"].value_counts().rename("tipo"))
    relatorio.tabela(df["fase"].value_counts().rename("fase"))
    relatorio.tabela(df["qualidade_par"].value_counts().rename("qualidade_par"))
    relatorio.nota("% de valores nulos por coluna (top 15)")
    relatorio.tabela(nulos.rename("% nulos"))


def secao_medias_por_tipo(df: pd.DataFrame, relatorio: RelatorioHTML):
    print("\n" + "=" * 70)
    print("2. MÉDIAS POR TIPO (TRATAMENTO x CONTROLE)")
    print("=" * 70)
    resumo_tipo = df.groupby("tipo")[config.VARS_ALVO].mean(numeric_only=True).round(3).T
    print(resumo_tipo)

    relatorio.secao("2. Médias por tipo (tratamento x controle)")
    relatorio.tabela(resumo_tipo)


def secao_event_study(df: pd.DataFrame, delta_cols: list[str], relatorio: RelatorioHTML) -> pd.DataFrame:
    print("\n" + "=" * 70)
    print("4. EVENT STUDY (variação média por horizonte)")
    print("=" * 70)
    event_study = (
        df.groupby(["ano_relativo_ao_inicio_obra", "tipo"])[delta_cols]
        .mean()
        .reset_index()
    )

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    plot_vars = ["delta_prop_vegetacao_densa", "delta_prop_solo_exposto_obras",
                 "delta_prop_construida_urbana", "delta_lst_media_celsius"]
    for ax, var in zip(axes.flat, plot_vars):
        for tipo, cor in [("tratamento", "tab:red"), ("controle", "tab:blue")]:
            sub = event_study[event_study["tipo"] == tipo]
            ax.plot(sub["ano_relativo_ao_inicio_obra"], sub[var], marker="o", label=tipo, color=cor)
        ax.axvline(0, color="gray", linestyle="--", linewidth=1)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_title(var.replace("delta_", ""))
        ax.set_xlabel("Horizonte (anos relativo ao início da obra)")
        ax.legend()
    fig.suptitle("Event Study: Tratamento x Controle")
    fig.tight_layout()

    relatorio.secao("4. Event study (variação média por horizonte)")
    relatorio.figura(fig, "Event Study: Tratamento x Controle")

    fig.savefig(config.FIGURAS_DIR / "event_study_tratamento_x_controle.png", dpi=150)
    plt.close(fig)

    return event_study


def secao_placebo(df: pd.DataFrame, delta_cols: list[str], relatorio: RelatorioHTML):
    print("\n" + "=" * 70)
    print("5. TESTE DE PLACEBO (horizontes negativos)")
    print("=" * 70)
    pre_periodo = df[df["ano_relativo_ao_inicio_obra"] < 0]
    placebo = pre_periodo.groupby("tipo")[delta_cols].mean().round(4).T
    print(placebo)
    print("\n-> valores próximos de 0 nos horizontes negativos = boa notícia")
    print("   (área não estava mudando sozinha antes da obra)")

    relatorio.secao("5. Teste de placebo (horizontes negativos)")
    relatorio.tabela(placebo)
    relatorio.nota(
        "valores próximos de 0 = boa notícia (a área não estava mudando sozinha antes da obra)"
    )


def secao_did(df: pd.DataFrame, relatorio: RelatorioHTML) -> pd.Series:
    print("\n" + "=" * 70)
    print("6. DIFERENÇA-EM-DIFERENÇAS (DiD) — fase 'pos' vs 'pre'")
    print("=" * 70)

    def did(var):
        m = df.groupby(["tipo", "fase"])[var].mean()
        try:
            trat_pre, trat_pos = m["tratamento", "pre"], m["tratamento", "pos"]
            ctrl_pre, ctrl_pos = m["controle", "pre"], m["controle", "pos"]
            return (trat_pos - trat_pre) - (ctrl_pos - ctrl_pre)
        except KeyError:
            return np.nan

    did_df = pd.Series({var: did(var) for var in config.VARS_ALVO}, name="efeito_DiD").sort_values()
    print(did_df.round(4))

    relatorio.secao("6. Diferença-em-diferenças (DiD) — fase 'pos' vs 'pre'")
    relatorio.tabela(did_df.round(4))
    return did_df


def secao_ranking(df: pd.DataFrame, relatorio: RelatorioHTML):
    print("\n" + "=" * 70)
    print("8/9. RANKINGS (tratamento, fase pós)")
    print("=" * 70)
    pos_trat = df[(df["tipo"] == "tratamento") & (df["fase"] == "pos")]

    ranking_veg = pos_trat.groupby("municipio")["delta_prop_vegetacao_densa"].mean().sort_values().round(3).head(10)
    print("Maior perda de vegetação densa:")
    print(ranking_veg)

    ranking_lst = (
        pos_trat.groupby("municipio")["delta_lst_media_celsius"].mean()
        .sort_values(ascending=False).round(3).head(10)
    )
    print("\nMaior aumento de LST:")
    print(ranking_lst)

    relatorio.secao("8/9. Rankings (tratamento, fase pós)")
    relatorio.nota("Maior perda de vegetação densa")
    relatorio.tabela(ranking_veg)
    relatorio.nota("Maior aumento de LST")
    relatorio.tabela(ranking_lst)


def secao_correlacao(df: pd.DataFrame, relatorio: RelatorioHTML):
    print("\n" + "=" * 70)
    print("10. Matriz de correlação (satélite, LST, socioeconômico, porte)")
    print("=" * 70)
    colunas = config.VARS_ALVO + ["mw_construido_total", "n_predios_no_campus"]
    corr = df[colunas].corr(numeric_only=True).round(2)
    print(corr)

    relatorio.secao("10. Matriz de correlação (satélite, LST, socioeconômico, porte)")
    relatorio.tabela(corr)


def calcula_efeito_liquido_por_par(df: pd.DataFrame, delta_cols: list[str]) -> pd.DataFrame:
    """efeito_liquido = delta_tratamento - delta_controle, por par e horizonte comum aos dois."""
    registros = []
    for par in df["pareado_com"].dropna().unique():
        grupo = df[df["pareado_com"] == par]
        trat = grupo[grupo["tipo"] == "tratamento"].set_index("ano_relativo_ao_inicio_obra")
        ctrl = grupo[grupo["tipo"] == "controle"].set_index("ano_relativo_ao_inicio_obra")

        for h in trat.index.intersection(ctrl.index):
            for var in config.VARS_ALVO:
                dcol = f"delta_{var}"
                registros.append({
                    "par": par, "horizonte": h, "variavel": var,
                    "efeito_liquido": trat.loc[h, dcol] - ctrl.loc[h, dcol],
                })
    return pd.DataFrame(registros)


def secao_curva_efeito_liquido(efeito_df: pd.DataFrame, relatorio: RelatorioHTML) -> pd.DataFrame:
    print("\n" + "=" * 70)
    print("12/13. CURVA DE EFEITO LÍQUIDO (agregado entre os pares) + placebo")
    print("=" * 70)
    curva = (
        efeito_df.groupby(["variavel", "horizonte"])["efeito_liquido"]
        .agg(media="mean", mediana="median", desvio_padrao="std", n_pares="count")
        .reset_index()
        .sort_values(["variavel", "horizonte"])
    )

    placebo_curva = (
        curva[curva["horizonte"] < 0].groupby("variavel")["media"].mean().sort_values(key=abs)
    )
    print("Teste de placebo (efeito líquido médio pré-obra, perto de 0 = boa notícia):")
    print(placebo_curva.round(4))

    relatorio.secao("12/13. Curva de efeito líquido (agregado entre os pares) + placebo")
    relatorio.nota("Teste de placebo — efeito líquido médio pré-obra (perto de 0 = boa notícia)")
    relatorio.tabela(placebo_curva.round(4))

    vars_para_plotar = ["prop_vegetacao_densa", "prop_solo_exposto_obras",
                        "prop_construida_urbana", "lst_media_celsius"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for ax, var in zip(axes.flat, vars_para_plotar):
        sub = curva[
            (curva["variavel"] == var)
            & curva["horizonte"].between(config.HORIZONTE_GRAFICO_MIN, config.HORIZONTE_GRAFICO_MAX)
        ].sort_values("horizonte")
        erro_padrao = sub["desvio_padrao"] / np.sqrt(sub["n_pares"])

        ax.plot(sub["horizonte"], sub["media"], marker="o", color="tab:red", label="efeito líquido médio")
        ax.fill_between(sub["horizonte"], sub["media"] - erro_padrao, sub["media"] + erro_padrao,
                         color="tab:red", alpha=0.2, label="± erro padrão")
        for _, row in sub.iterrows():
            ax.annotate(f"n={int(row['n_pares'])}", (row["horizonte"], row["media"]),
                        textcoords="offset points", xytext=(0, 8), fontsize=7, ha="center", color="dimgray")
        ax.axvline(0, color="gray", linestyle="--", linewidth=1)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_title(var)
        ax.set_xlabel("Horizonte (anos relativo ao início da obra)")
        ax.legend(fontsize=8)
    fig.suptitle("Efeito líquido médio entre os pares, por horizonte (DiD par-a-par)")
    fig.tight_layout()

    relatorio.figura(fig, "Efeito líquido médio entre os pares, por horizonte (DiD par-a-par)")

    fig.savefig(config.FIGURAS_DIR / "curva_efeito_liquido.png", dpi=150)
    plt.close(fig)

    return curva


def main():
    df = pd.read_csv(config.CONSOLIDADO_CSV)
    relatorio = RelatorioHTML(
        "Análise exploratória — modelo de impacto",
        f"Painel: {config.CONSOLIDADO_CSV.name} ({df.shape[0]} linhas x {df.shape[1]} colunas)",
    )

    secao_visao_geral(df, relatorio)
    secao_medias_por_tipo(df, relatorio)

    df, _baseline_map = calcula_deltas(df, config.VARS_ALVO)
    delta_cols = [f"delta_{c}" for c in config.VARS_ALVO]

    secao_event_study(df, delta_cols, relatorio)
    secao_placebo(df, delta_cols, relatorio)
    secao_did(df, relatorio)

    print("\n" + "=" * 70)
    print("7. Nº de observações por qualidade de pareamento x tipo")
    print("=" * 70)
    crosstab_qualidade = pd.crosstab(df["qualidade_par"], df["tipo"])
    print(crosstab_qualidade)
    relatorio.secao("7. Nº de observações por qualidade de pareamento x tipo")
    relatorio.tabela(crosstab_qualidade)

    secao_ranking(df, relatorio)
    secao_correlacao(df, relatorio)

    efeito_df = calcula_efeito_liquido_por_par(df, delta_cols)
    print(f"\n{len(efeito_df)} registros de efeito líquido (pares x horizontes x variáveis)")
    curva = secao_curva_efeito_liquido(efeito_df, relatorio)

    efeito_df.to_csv(config.OUTPUT_DIR / "efeito_liquido_por_par.csv", index=False)
    curva.to_csv(config.OUTPUT_DIR / "curva_efeito_liquido.csv", index=False)

    caminho_html = relatorio.salvar(config.RELATORIO_EXPLORATORIA_HTML)
    print(f"\nCSVs e figuras salvos em {config.OUTPUT_DIR}")
    print(f"Relatório HTML: {caminho_html}")


if __name__ == "__main__":
    main()
