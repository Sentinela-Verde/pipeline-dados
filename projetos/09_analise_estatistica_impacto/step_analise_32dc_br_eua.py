"""Novo estudo — testa se ampliar a amostra pra 31 pares (15 Brasil + 16 EUA, base
`dados/gold/base_final_32_dc_br_eua.csv`) melhora a significância estatística do efeito líquido,
em relação ao estudo original (15 pares, só Brasil, `dados/gold/consolidado_impacto_modelo.csv`).

**Não mexe em nada do estudo original** — nem no CSV de entrada, nem em `config.py`,
`step1b_analise_consequencias.py`, `step1c_analise_por_fase.py`, nem nas saídas deles em
`dados/gold/efeito_liquido/`. Esse arquivo é novo, lê uma fonte nova, escreve numa pasta nova
(`dados/gold/efeito_liquido_32dc/`), e reaproveita (importa, não copia) a mesma matemática de
`comum.py`/`step1b_analise_consequencias.py` — permutação de sinal, bootstrap IC95%, Cohen's d,
FDR — pra que a comparação "15 pares vs. 31 pares" isole SÓ o efeito do tamanho da amostra, não
mude de método no caminho.

## Diferenças reais da base nova (verificadas antes de rodar, não assumidas)

- **31 sites de tratamento** (15 BR, obra 2014-2023; 16 EUA, obra 2019-2022) + seus controles
  pareados = 428 linhas (214 tratamento + 214 controle).
- **Instrumento por PAÍS, nunca misturado dentro do mesmo par**: Brasil usa `rf_v1.0-tuned`
  (MapBiomas), EUA usa `dynamic_world` — confirmado 0 pares com mais de 1 instrumento. Isso é
  exatamente a "saída (a)" que o ADR-006 (`modelo-imagens-satelite`) cogitava (usar Dynamic World
  direto nos EUA em vez de retreinar um classificador global) — o retreino tinha sido reprovado
  no próprio ADR por não se pagar (funil de datação < 30 campi pareáveis).
- **Sem `emprego_formal_total`/`numero_empresas`** (não existem nesta base — provavelmente não há
  fonte equivalente pros EUA). `VARS_ALVO` aqui tem 8 variáveis, não 10: as 5 de satélite + LST +
  população + PIB.
- **qualidade_par majoritariamente "ruim"** (328 de 428 linhas, ~77%) — pior proporção que o
  estudo original (66/204 ≈ 32%, conferir se mudou). Não filtrado aqui, pelo mesmo motivo do
  original: mudar o filtro junto com o tamanho da amostra impediria isolar qual dos dois mudou o
  resultado.

Saída em `dados/gold/efeito_liquido_32dc/`:
- `resumo_significancia_32dc.csv` — mesmo formato do `consequencias_terreno_resumo.csv` original.
- `comparacao_15_vs_31_pares.csv` — as duas tabelas lado a lado, pra responder a pergunta direta
  "a amostra maior melhorou a significância?".

Uso:
    python step_analise_32dc_br_eua.py
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

pd.set_option("display.float_format", "{:.4f}".format)

# --- Fonte nova, isolada do estudo original --------------------------------
CONSOLIDADO_32DC_CSV = config.RAIZ_PROJETO / "dados" / "gold" / "base_final_32_dc_br_eua.csv"
OUTPUT_DIR_32DC = config.RAIZ_PROJETO / "dados" / "gold" / "efeito_liquido_32dc"
OUTPUT_DIR_32DC.mkdir(parents=True, exist_ok=True)

# 8 variáveis (a base nova não tem emprego_formal_total/numero_empresas)
VARS_ALVO_32DC = config.VARS_SATELITE + config.VARS_CLIMA + ["populacao", "pib_mil_reais"]


def corrige_pareado_com_eua(df: pd.DataFrame) -> pd.DataFrame:
    """BUG DE DADOS encontrado nesta base (2026-09-15): nas linhas dos 16 sites dos EUA, o lado
    'tratamento' vem com `pareado_com` vazio (só o 'controle' aponta pro par) — diferente do
    padrão brasileiro, onde o tratamento também referencia a si mesmo. Sem essa correção,
    `comum.calcula_efeito_liquido_por_par` nunca encontra o lado tratamento desses 16 pares (o
    filtro por `pareado_com` não pega a linha), e os EUA saem SILENCIOSAMENTE zerados do cálculo
    — foi exatamente isso que aconteceu na primeira rodada deste script (31 pares no `print`,
    mas 15 pares em todo resultado real). Corrigido aqui, não em `comum.py` (compartilhado com o
    estudo original, que não deve mudar)."""
    df = df.copy()
    mascara = (df["tipo"] == "tratamento") & df["pareado_com"].isna()
    n_corrigidas = int(mascara.sum())
    df.loc[mascara, "pareado_com"] = df.loc[mascara, "site_id"]
    if n_corrigidas:
        print(f"AVISO: corrigidas {n_corrigidas} linha(s) de tratamento com `pareado_com` vazio "
              f"(bug de dados dos sites EUA) — preenchidas com o próprio site_id.")
    return df


def monta_efeito_por_par_pos_obra(df: pd.DataFrame, vars_alvo: list[str]) -> pd.DataFrame:
    """Mesma lógica de `step1b.monta_efeito_por_par_pos_obra`, parametrizada por `vars_alvo`
    (o original é fixo em `config.VARS_ALVO`, que não bate com esta base)."""
    efeito_df = calcula_efeito_liquido_por_par(df, vars_alvo)
    pos = efeito_df[efeito_df["horizonte"].isin(config.HORIZONTES_ALVO)]
    return pos.groupby(["par", "variavel"])["efeito_liquido"].mean().reset_index()


def testa_significancia(efeito_par_var: pd.DataFrame, vars_alvo: list[str]) -> pd.DataFrame:
    """Mesma lógica de `step1b.secao_resumo_significancia`, sem o lado de impressão/relatório
    HTML (não precisamos duplicar isso, só a tabela)."""
    linhas = []
    for var in vars_alvo:
        valores = efeito_par_var.loc[efeito_par_var["variavel"] == var, "efeito_liquido"].dropna().to_numpy()
        n = len(valores)
        if n < config.MIN_PARES_TESTE:
            linhas.append({"variavel": var, "n_pares": n, "media": np.nan, "mediana": np.nan,
                            "ic95_baixo": np.nan, "ic95_alto": np.nan, "cohen_d": np.nan,
                            "magnitude": "amostra insuficiente", "p_valor": np.nan})
            continue
        media = float(valores.mean())
        ic_baixo, ic_alto = bootstrap_ic95(valores)
        d = cohen_d_uma_amostra(valores)
        p = teste_permutacao_sinal(valores)
        linhas.append({"variavel": var, "n_pares": n, "media": media, "mediana": float(np.median(valores)),
                        "ic95_baixo": ic_baixo, "ic95_alto": ic_alto, "cohen_d": d,
                        "magnitude": magnitude_cohen_d(d), "p_valor": p})

    resumo = pd.DataFrame(linhas)
    resumo["p_valor_fdr"] = corrige_fdr_benjamini_hochberg(resumo.set_index("variavel")["p_valor"]).to_numpy()
    resumo["significativo_fdr"] = resumo["p_valor_fdr"] < config.ALPHA
    resumo["direcao"] = np.select([resumo["media"] > 0, resumo["media"] < 0], ["aumenta", "diminui"], default="n/d")
    return resumo.sort_values("p_valor_fdr", na_position="last")


def main() -> None:
    if not CONSOLIDADO_32DC_CSV.exists():
        raise SystemExit(f"{CONSOLIDADO_32DC_CSV} não existe.")

    print(f"Lendo {CONSOLIDADO_32DC_CSV.name}...")
    df = pd.read_csv(CONSOLIDADO_32DC_CSV)
    n_trat = df[df["tipo"] == "tratamento"]["site_id"].nunique()
    print(f"{len(df)} linhas, {n_trat} sites de tratamento "
          f"({df[df['tipo']=='tratamento'].groupby('pais')['site_id'].nunique().to_dict()})")

    df = corrige_pareado_com_eua(df)
    df, _ = calcula_deltas(df, VARS_ALVO_32DC)
    efeito_par_var = monta_efeito_por_par_pos_obra(df, VARS_ALVO_32DC)
    resumo_novo = testa_significancia(efeito_par_var, VARS_ALVO_32DC)

    print("\n" + "=" * 78)
    print(f"NOVO ESTUDO — {n_trat} pares (BR+EUA) — significância do efeito líquido pós-obra")
    print("=" * 78)
    print(resumo_novo.round(4).to_string(index=False))
    n_sig_novo = int(resumo_novo["significativo_fdr"].sum())
    print(f"\n-> {n_sig_novo} de {len(resumo_novo)} variáveis significativas após FDR (alfa={config.ALPHA}).")

    saida_resumo = OUTPUT_DIR_32DC / "resumo_significancia_32dc.csv"
    resumo_novo.to_csv(saida_resumo, index=False, encoding="utf-8")
    print(f"\nSalvo em {saida_resumo}")

    # --- Comparação direta com o estudo original (15 pares, só Brasil) -----
    if not config.CONSOLIDADO_CSV.exists():
        print(f"\nAVISO: {config.CONSOLIDADO_CSV} não encontrado — pulando comparação com o estudo original.")
        return

    df_original = pd.read_csv(config.CONSOLIDADO_CSV)
    df_original, _ = calcula_deltas(df_original, config.VARS_ALVO)
    efeito_original = monta_efeito_por_par_pos_obra(df_original, config.VARS_ALVO)
    resumo_original = testa_significancia(efeito_original, config.VARS_ALVO)

    vars_comuns = [v for v in VARS_ALVO_32DC if v in config.VARS_ALVO]
    comp = resumo_original.set_index("variavel").loc[vars_comuns, ["n_pares", "media", "p_valor_fdr", "significativo_fdr"]]
    comp.columns = [f"{c}_original_15par" for c in comp.columns]
    comp2 = resumo_novo.set_index("variavel").loc[vars_comuns, ["n_pares", "media", "p_valor_fdr", "significativo_fdr"]]
    comp2.columns = [f"{c}_novo_31par" for c in comp2.columns]
    comparacao = comp.join(comp2).reset_index()

    print("\n" + "=" * 78)
    print("COMPARAÇÃO DIRETA — o mesmo teste, 15 pares (só BR) vs. 31 pares (BR+EUA)")
    print("=" * 78)
    print(comparacao.round(4).to_string(index=False))

    melhorou = int((comparacao["significativo_fdr_novo_31par"] & ~comparacao["significativo_fdr_original_15par"]).sum())
    piorou = int((~comparacao["significativo_fdr_novo_31par"] & comparacao["significativo_fdr_original_15par"]).sum())
    print(f"\n-> variáveis que PASSARAM a ser significativas com a amostra maior: {melhorou}")
    print(f"-> variáveis que DEIXARAM de ser significativas com a amostra maior: {piorou}")

    saida_comp = OUTPUT_DIR_32DC / "comparacao_15_vs_31_pares.csv"
    comparacao.to_csv(saida_comp, index=False, encoding="utf-8")
    print(f"\nSalvo em {saida_comp}")


if __name__ == "__main__":
    main()
