"""Importa HTMLs já baixados manualmente (fora do fluxo normal do
run_pipeline.py) pro data/raw/datacentermap/, sem precisar rodar o Selenium
de novo. Útil quando você já tem uma extração completa salva em disco de
outra vez.

Espera o layout de nomes:
  <pasta-regioes>/regiao_<slug>.html
  <pasta-datacenters>/datacenter_<slug>.html          (aba overview)
  <pasta-datacenters>/datacenter_<slug>_specs.html    (aba specs)

Cada HTML é lido, o __NEXT_DATA__ extraído e só os dados relevantes salvos —
igual aos steps 2/4 fariam com uma resposta vinda do Selenium. Página de
rate limit ("Page View Limit Reached") é detectada e marcada como
`bloqueado` em vez de `ok` (ver comum/next_data.esta_bloqueado).

Uso:
    python importar_html.py --regioes "../../html_regiao" --datacenters "../../html_datacenter"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from comum.cache_store import STATUS_BLOQUEADO, STATUS_ERRO, STATUS_OK, salvar
from comum.next_data import esta_bloqueado, extrair_features_com_coords, extrair_page_props


def status_e_props(caminho: Path):
    html = caminho.read_text(encoding="utf-8")
    props = extrair_page_props(html)
    if props is None:
        return STATUS_ERRO, None
    if esta_bloqueado(props):
        return STATUS_BLOQUEADO, None
    return STATUS_OK, props


def importar_regioes(pasta: Path) -> dict:
    contagem = {STATUS_OK: 0, STATUS_BLOQUEADO: 0, STATUS_ERRO: 0}
    arquivos = sorted(pasta.glob("regiao_*.html"))
    for arquivo in arquivos:
        slug = arquivo.stem.removeprefix("regiao_")
        status, props = status_e_props(arquivo)

        dados = None
        if status == STATUS_OK:
            mapdata = props.get("mapdata") or {}
            dados = {
                "geodata": props.get("geodata"),
                "dcs": extrair_features_com_coords(mapdata.get("dcs")),
            }

        salvar(config.RAW_DATA_REGIOES, slug, status, dados)
        contagem[status] += 1

    print(f"Regiões importadas de '{pasta}': {len(arquivos)} arquivo(s) -> {contagem}")
    return contagem


def importar_datacenters(pasta: Path) -> dict:
    contagem = {STATUS_OK: 0, STATUS_BLOQUEADO: 0, STATUS_ERRO: 0}
    arquivos = sorted(pasta.glob("datacenter_*.html"))
    for arquivo in arquivos:
        nome = arquivo.stem.removeprefix("datacenter_")
        if nome.endswith("_specs"):
            slug, aba = nome.removesuffix("_specs"), "specs"
        else:
            slug, aba = nome, "overview"

        status, props = status_e_props(arquivo)
        dados = None
        if status == STATUS_OK:
            dados = {"dc": props.get("dc"), "tab": props.get("tab"), "serviceplan": props.get("serviceplan")}

        salvar(config.RAW_DATA_DATACENTERS, f"{slug}__{aba}", status, dados)
        contagem[status] += 1

    print(f"Datacenters importados de '{pasta}': {len(arquivos)} arquivo(s) -> {contagem}")
    return contagem


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regioes", type=Path, help="pasta com os regiao_<slug>.html")
    parser.add_argument("--datacenters", type=Path, help="pasta com os datacenter_<slug>[_specs].html")
    args = parser.parse_args()

    if not args.regioes and not args.datacenters:
        parser.error("passe pelo menos --regioes ou --datacenters")

    if args.regioes:
        importar_regioes(args.regioes)
    if args.datacenters:
        importar_datacenters(args.datacenters)


if __name__ == "__main__":
    main()
