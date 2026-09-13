"""Orquestra o pipeline inteiro. Cada etapa também roda sozinha
(`python regioes/step3_scrape_regioes.py`) — esse script só chama todas na
ordem certa (uma vez cada) e repassa as flags de linha de comando.

Uso:
    python run_pipeline.py               # roda tudo, pulando o que já está em cache
    python run_pipeline.py --so step5    # roda só uma etapa
    python run_pipeline.py --forcar      # ignora o cache e busca tudo de novo (steps 1, 3 e 5)

Teste rápido (pipeline inteiro, mas só 1 região e até 3 datacenters dela —
valores em config.TESTE_LIMITE_REGIOES / TESTE_LIMITE_DATACENTERS):
    python run_pipeline.py --teste
    # equivale a:
    python run_pipeline.py --limite-regioes 1 --limite-datacenters 3

`--limite-regioes`/`--limite-datacenters` passados explicitamente sempre
prevalecem sobre `--teste`.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from pais import step1_scrape_pais, step2_montar_regioes
from regioes import step3_scrape_regioes, step4_montar_links_datacenters
from datacenters import step5_scrape_datacenters, step6_build_csv

ETAPAS = {
    "step1": step1_scrape_pais.main,
    "step2": step2_montar_regioes.main,
    "step3": step3_scrape_regioes.main,
    "step4": step4_montar_links_datacenters.main,
    "step5": step5_scrape_datacenters.main,
    "step6": step6_build_csv.main,
}
ETAPAS_COM_FORCAR = {"step1", "step3", "step5"}


def montar_kwargs(nome: str, args: argparse.Namespace) -> dict:
    kwargs = {}
    if nome in ETAPAS_COM_FORCAR:
        kwargs["forcar"] = args.forcar
    if nome == "step3":
        kwargs["limite"] = args.limite_regioes
    if nome == "step5":
        kwargs["limite"] = args.limite_datacenters
    return kwargs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--so", choices=ETAPAS.keys(), help="roda só essa etapa")
    parser.add_argument("--forcar", action="store_true", help="ignora o cache (steps 1, 3 e 5)")
    parser.add_argument("--limite-regioes", type=int, default=None, help="step 3: só busca as N primeiras regiões pendentes")
    parser.add_argument("--limite-datacenters", type=int, default=None, help="step 5: só busca N datacenters pendentes")
    parser.add_argument(
        "--teste", action="store_true",
        help=f"atalho: --limite-regioes {config.TESTE_LIMITE_REGIOES} --limite-datacenters "
             f"{config.TESTE_LIMITE_DATACENTERS} (não sobrescreve limites passados explicitamente)",
    )
    args = parser.parse_args()

    if args.teste:
        if args.limite_regioes is None:
            args.limite_regioes = config.TESTE_LIMITE_REGIOES
        if args.limite_datacenters is None:
            args.limite_datacenters = config.TESTE_LIMITE_DATACENTERS

    etapas_a_rodar = {args.so: ETAPAS[args.so]} if args.so else ETAPAS

    for nome, funcao in etapas_a_rodar.items():
        print(f"\n=== {nome} ===")
        funcao(**montar_kwargs(nome, args))


if __name__ == "__main__":
    main()
