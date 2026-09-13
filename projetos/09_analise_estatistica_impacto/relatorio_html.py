"""Gerador de relatório HTML autocontido (sem dependência externa além de pandas/matplotlib,
que os steps já usam) — tabelas viram `<table>` e figuras do matplotlib são embutidas como PNG
em base64, então o `.html` final abre em qualquer navegador sem precisar dos CSVs/PNGs ao lado.

Uso típico dentro de um step:

    from relatorio_html import RelatorioHTML

    relatorio = RelatorioHTML("Análise exploratória — modelo de impacto")
    relatorio.secao("1. Visão geral")
    relatorio.texto("Linhas: 204 | Colunas: 51")
    relatorio.tabela(df.head())
    relatorio.figura(fig)  # ANTES de plt.close(fig)
    relatorio.salvar(config.OUTPUT_DIR / "relatorio.html")
"""
import base64
import html
from io import BytesIO
from pathlib import Path

import pandas as pd

_CSS = """
body { font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; max-width: 1000px;
       margin: 40px auto; padding: 0 20px; color: #1a1a1a; background: #fafafa; }
h1 { border-bottom: 3px solid #2ecc71; padding-bottom: 12px; }
h2 { margin-top: 48px; border-bottom: 1px solid #ddd; padding-bottom: 6px; color: #1a1a1a; }
p.subtitulo { color: #666; margin-top: -8px; }
table { border-collapse: collapse; margin: 12px 0 24px; font-size: 13px; }
table, th, td { border: 1px solid #ddd; }
th, td { padding: 6px 10px; text-align: right; }
th { background: #f0f0f0; text-align: center; }
td:first-child, th:first-child { text-align: left; }
pre { background: #f0f0f0; padding: 12px 16px; border-radius: 6px; overflow-x: auto;
      font-size: 13px; white-space: pre-wrap; }
img { max-width: 100%; margin: 12px 0 24px; display: block; }
.nota { color: #666; font-size: 13px; font-style: italic; }
"""


class RelatorioHTML:
    def __init__(self, titulo: str, subtitulo: str = ""):
        self.titulo = titulo
        self.subtitulo = subtitulo
        self._blocos = []

    def secao(self, titulo: str):
        self._blocos.append(f"<h2>{html.escape(titulo)}</h2>")

    def texto(self, texto: str):
        self._blocos.append(f"<pre>{html.escape(str(texto))}</pre>")

    def nota(self, texto: str):
        self._blocos.append(f"<p class='nota'>{html.escape(texto)}</p>")

    def tabela(self, df_ou_series, max_linhas: int = 200, **kwargs):
        """Adiciona um DataFrame ou Series como tabela HTML (trunca em `max_linhas`)."""
        obj = df_ou_series.to_frame() if isinstance(df_ou_series, pd.Series) else df_ou_series
        if len(obj) > max_linhas:
            obj = obj.head(max_linhas)
            truncado = True
        else:
            truncado = False
        self._blocos.append(obj.to_html(**kwargs))
        if truncado:
            self.nota(f"mostrando as primeiras {max_linhas} de {len(df_ou_series)} linhas")

    def figura(self, fig, legenda: str = ""):
        """Embute uma figura do matplotlib como PNG em base64. Chamar ANTES de `plt.close(fig)`."""
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        self._blocos.append(f'<img src="data:image/png;base64,{b64}" alt="{html.escape(legenda)}">')
        if legenda:
            self.nota(legenda)

    def render(self) -> str:
        corpo = "\n".join(self._blocos)
        subtitulo_html = f"<p class='subtitulo'>{html.escape(self.subtitulo)}</p>" if self.subtitulo else ""
        return (
            f"<!doctype html><html lang='pt-br'><head><meta charset='utf-8'>"
            f"<title>{html.escape(self.titulo)}</title><style>{_CSS}</style></head><body>"
            f"<h1>{html.escape(self.titulo)}</h1>{subtitulo_html}{corpo}"
            f"</body></html>"
        )

    def salvar(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")
        return path
