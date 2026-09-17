"""Step 1c — a mesma pergunta do step1b (o efeito líquido é diferente de zero?), agora separada
por FASE REAL da obra (pré / durante / pós), em vez de colapsar tudo numa janela fixa de
horizontes.

## Por que isso não é o mesmo que `step1b.monta_efeito_por_par_pos_obra`

`config.HORIZONTES_ALVO = [0, 1, 2]` é uma janela FIXA aplicada igual a todo mundo — mas a
duração da obra varia por data center. Conferido no painel real (`consolidado_impacto_modelo.csv`):
o horizonte `+1` de um site que construiu em 1 ano já é fase `"pos"` (já operando); o horizonte
`+1` de um site que levou 3+ anos ainda é `"durante"`. A coluna `fase` do painel já resolve isso
por linha (calculada a partir de `ano_operacional` de cada site, não de um horizonte fixo) — este
step usa ela diretamente, em vez de reaproveitar `HORIZONTES_ALVO`.

## Ressalva sobre o horizonte -1

`fase == "pre"` inclui o horizonte -1, mas -1 é o **ano-base** — por construção
(`comum.calcula_baseline_map`), seu efeito líquido é SEMPRE 0 (não é um dado real de
pré-tendência, é a definição da régua). Incluí-lo na média de "pre" puxaria essa fase
artificialmente rumo a zero, então é excluído aqui (ver `agrega_por_fase`).

## Metodologia (idêntica ao step1b, reaproveitada de lá — não duplicada)

Permutação de sinal (bicaudal), bootstrap IC95%, Cohen's d, correção FDR (Benjamini-Hochberg).
A diferença é o tamanho da família de testes: 10 variáveis x 3 fases = **30 testes**, todos
corrigidos JUNTOS (mesma regra do step1b: testar muita coisa a 5% sem correção infla falso
positivo).

Saída em `config.OUTPUT_DIR` (`dados/gold/efeito_liquido/`):
- `consequencias_por_fase.csv` — 1 linha por (variável, fase): média, IC95%, Cohen's d, p-valor
  e p-valor FDR.
- `figuras/comparacao_fases.png` (se `matplotlib` estiver instalado).

Uso:
    python step1c_analise_por_fase.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from comum import calcula_deltas, calcula_efeito_liquido_por_par
from step1b_analise_consequencias import (
    bootstrap_ic95,
    cohen_d_uma_amostra,
    corrige_fdr_benjamini_hochberg,
    magnitude_cohen_d,
    teste_permutacao_sinal,
)

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ModuleNotFoundError:
    HAS_MPL = False

pd.set_option("display.float_format", "{:.4f}".format)

FASES = ("pre", "durante", "pos")


def anexa_fase(df: pd.DataFrame, efeito_df: pd.DataFrame) -> pd.DataFrame:
    """Junta a coluna `fase` em cada linha de `efeito_df` — usando a fase do lado TRATAMENTO
    (é a obra dele que define pré/durante/pós; o controle não tem obra nenhuma)."""
    fase_tratamento = (
        df[df["tipo"] == "tratamento"][["pareado_com", "ano_relativo_ao_inicio_obra", "fase"]]
        .drop_duplicates()
        .rename(columns={"pareado_com": "par", "ano_relativo_ao_inicio_obra": "horizonte"})
    )
    out = efeito_df.merge(fase_tratamento, on=["par", "horizonte"], how="left")
    sem_fase = int(out["fase"].isna().sum())
    if sem_fase:
        print(
            f"AVISO: {sem_fase} linha(s) de efeito líquido sem fase correspondente no lado "
            f"tratamento (par/horizonte não encontrado) — descartadas.",
            file=sys.stderr,
        )
        out = out.dropna(subset=["fase"])
    return out


def agrega_por_fase(efeito_com_fase: pd.DataFrame) -> pd.DataFrame:
    """1 linha por (par, variável, fase): média do efeito líquido nos horizontes daquela fase
    disponíveis pra aquele par. Exclui horizonte -1 da fase 'pre' — ver docstring do módulo."""
    mascara_baseline = (efeito_com_fase["fase"] == "pre") & (efeito_com_fase["horizonte"] == -1)
    df = efeito_com_fase[~mascara_baseline]
    return df.groupby(["par", "variavel", "fase"])["efeito_liquido"].mean().reset_index()


def testa_todas_combinacoes(por_par_fase: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for var in config.VARS_ALVO:
        for fase in FASES:
            valores = (
                por_par_fase.loc[
                    (por_par_fase["variavel"] == var) & (por_par_fase["fase"] == fase),
                    "efeito_liquido",
                ]
                .dropna()
                .to_numpy()
            )
            n = len(valores)
            if n < config.MIN_PARES_TESTE:
                linhas.append({
                    "variavel": var, "fase": fase, "n_pares": n, "media": np.nan,
                    "mediana": np.nan, "ic95_baixo": np.nan, "ic95_alto": np.nan,
                    "cohen_d": np.nan, "magnitude": "amostra insuficiente", "p_valor": np.nan,
                })
                continue

            media = float(valores.mean())
            ic_baixo, ic_alto = bootstrap_ic95(valores)
            d = cohen_d_uma_amostra(valores)
            p = teste_permutacao_sinal(valores)
            linhas.append({
                "variavel": var, "fase": fase, "n_pares": n, "media": media,
                "mediana": float(np.median(valores)), "ic95_baixo": ic_baixo,
                "ic95_alto": ic_alto, "cohen_d": d, "magnitude": magnitude_cohen_d(d), "p_valor": p,
            })

    resumo = pd.DataFrame(linhas)
    # chave composta (variavel|fase) pra corrigir os 30 testes na MESMA família — não por fase
    # isolada, senão a correção fica mais fraca do que testar tudo junto de verdade.
    chave = resumo["variavel"] + "|" + resumo["fase"]
    p_fdr = corrige_fdr_benjamini_hochberg(resumo.set_index(chave)["p_valor"])
    resumo["p_valor_fdr"] = p_fdr.to_numpy()
    resumo["significativo_fdr"] = resumo["p_valor_fdr"] < config.ALPHA
    resumo["direcao"] = np.select(
        [resumo["media"] > 0, resumo["media"] < 0], ["aumenta", "diminui"], default="n/d"
    )
    return resumo


def figura_comparacao_fases(resumo: pd.DataFrame, destino: Path) -> None:
    if not HAS_MPL:
        print("matplotlib não instalado — pulando figura (o CSV já tem tudo).")
        return

    vars_fig = config.VARS_SATELITE + config.VARS_CLIMA
    cores = {"pre": "#8A9389", "durante": "#B8791A", "pos": "#1F6F6B"}

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, var in zip(axes.flat, vars_fig):
        sub = resumo[resumo["variavel"] == var].set_index("fase").reindex(FASES)
        x = np.arange(len(FASES))
        medias = sub["media"].to_numpy(dtype=float)
        lo = sub["ic95_baixo"].to_numpy(dtype=float)
        hi = sub["ic95_alto"].to_numpy(dtype=float)
        erros = np.vstack([np.nan_to_num(medias - lo), np.nan_to_num(hi - medias)])

        ax.bar(x, np.nan_to_num(medias), color=[cores[f] for f in FASES], width=0.6)
        ax.errorbar(x, np.nan_to_num(medias), yerr=erros, fmt="none", ecolor="black", capsize=4, linewidth=1)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(FASES)
        ax.set_title(var, fontsize=10)
        for i, fase in enumerate(FASES):
            row = sub.loc[fase]
            if pd.isna(row["media"]):
                continue
            marca = "*" if row["significativo_fdr"] else ""
            ax.annotate(
                f"n={int(row['n_pares'])}{marca}", (i, row["media"]),
                textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8,
            )

    for ax in axes.flat[len(vars_fig):]:
        ax.axis("off")

    fig.suptitle("Efeito líquido médio por fase da obra (± IC95% bootstrap) — * = signif. após FDR")
    fig.tight_layout()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=150)
    plt.close(fig)
    print(f"Figura salva em {destino}")


def main() -> None:
    if not config.CONSOLIDADO_CSV.exists():
        raise SystemExit(f"{config.CONSOLIDADO_CSV} não existe — ver README (lacuna do painel consolidado).")

    df = pd.read_csv(config.CONSOLIDADO_CSV)
    df, _ = calcula_deltas(df, config.VARS_ALVO)
    efeito_df = calcula_efeito_liquido_por_par(df, config.VARS_ALVO)
    efeito_com_fase = anexa_fase(df, efeito_df)
    por_par_fase = agrega_por_fase(efeito_com_fase)

    n_pares_por_fase = por_par_fase.groupby("fase")["par"].nunique().to_dict()
    print(f"Pares disponíveis por fase: {n_pares_por_fase}")

    resumo = testa_todas_combinacoes(por_par_fase).sort_values(["variavel", "fase"])
    print("\n" + "=" * 78)
    print("EFEITO LÍQUIDO POR FASE DA OBRA (pré / durante / pós) — 30 testes, FDR conjunto")
    print("=" * 78)
    print(resumo.round(4).to_string(index=False))

    n_sig = int(resumo["significativo_fdr"].sum())
    print(f"\n-> {n_sig} de {len(resumo)} combinações (variável x fase) com efeito líquido "
          f"estatisticamente diferente de 0 após FDR (alfa={config.ALPHA}).")
    if n_sig:
        print("   Significativas:")
        for _, r in resumo[resumo["significativo_fdr"]].iterrows():
            print(f"   - {r['variavel']} / {r['fase']}: {r['media']:+.4f} "
                  f"(IC95% [{r['ic95_baixo']:+.4f}, {r['ic95_alto']:+.4f}]), p_fdr={r['p_valor_fdr']:.4f}")

    saida_csv = config.OUTPUT_DIR / config.CONSEQUENCIAS_POR_FASE_CSV_NAME
    resumo.to_csv(saida_csv, index=False, encoding="utf-8")
    print(f"\nSalvo em {saida_csv}")

    figura_comparacao_fases(resumo, config.FIGURAS_DIR / "comparacao_fases.png")


if __name__ == "__main__":
    main()
