"""Valida as fontes de notícias: confere se cada uma tem feed RSS legível e com notícias recentes.

Lê config/fontes_candidatas.json, testa cada fonte do mesmo jeito que a atualização do portal faz e grava
o resultado em relatorio_fontes.md e relatorio_fontes.json (na pasta Backend). Para cada fonte:
  1. tenta o feed informado, se houver;
  2. procura o endereço do feed na página inicial do site (<link rel="alternate" type="application/rss+xml">);
  3. tenta os endereços mais comuns (/feed/, /rss, /feed.xml...).

    python validar_fontes.py
"""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urljoin

from atualizar_noticias import data_do_item, ler_feed
from comum import CONFIG, agora, baixar, gravar_json, ler_json, log
from pathlib import Path

CAMINHOS_COMUNS = ["/feed/", "/feed", "/rss", "/rss/", "/rss.xml", "/feed.xml", "/index.xml", "/?feed=rss2"]
RECENTE_DIAS = 14


def descobrir_feed(site):
    """Endereços de feed anunciados na página inicial."""
    try:
        html = baixar(site, tentativas=1, timeout=15).decode("utf-8", "ignore")
    except Exception:
        return []
    achados = []
    for tag in re.findall(r"<link[^>]+>", html, flags=re.I):
        if re.search(r"application/(rss|atom)\+xml", tag, flags=re.I):
            m = re.search(r'href=["\']([^"\']+)', tag, flags=re.I)
            if m:
                achados.append(urljoin(site, m.group(1)))
    return achados


def testar_feed(url):
    """Devolve (n_itens, data_mais_recente) ou levanta erro se não for um feed legível."""
    itens = ler_feed({"url": url}, tentativas=1, timeout=15)
    datas = [d for d in (data_do_item(i["data"]) for i in itens) if d]
    if not itens:
        raise ValueError("feed sem itens")
    return len(itens), max(datas) if datas else None


def validar(fonte):
    tentativas = []
    if fonte.get("feed"):
        tentativas.append(fonte["feed"])
    if fonte.get("site"):
        tentativas += descobrir_feed(fonte["site"])
        base = fonte["site"].rstrip("/")
        tentativas += [base + c for c in CAMINHOS_COMUNS]
    vistos, ultimo_erro = set(), "sem endereço para testar"
    for url in tentativas:
        if url in vistos:
            continue
        vistos.add(url)
        try:
            n, recente = testar_feed(url)
        except Exception as e:
            ultimo_erro = str(e)[:80]
            continue
        if recente and recente >= agora() - timedelta(days=RECENTE_DIAS):
            situacao = "ok"
        elif recente:
            situacao = "parado"
        else:
            situacao = "sem data"
        return {"situacao": situacao, "feed": url, "itens": n,
                "mais_recente": recente.strftime("%Y-%m-%d") if recente else None}
    return {"situacao": "sem feed", "feed": None, "erro": ultimo_erro}


ROTULO = {"ok": "Feed ativo", "parado": f"Feed sem notícias nos últimos {RECENTE_DIAS} dias",
          "sem data": "Feed sem datas", "sem feed": "Sem feed legível"}


def main():
    cand = ler_json(CONFIG / "fontes_candidatas.json")["fontes"]

    def uma(f):
        r = validar(f)
        r.update({k: f[k] for k in ("nome", "site", "industria", "papel") if k in f})
        log(f"{ROTULO[r['situacao']]:<40} {f['nome']}")
        return r

    # testa várias fontes ao mesmo tempo; a ordem do relatório segue a do arquivo de candidatas
    with ThreadPoolExecutor(max_workers=12) as ex:
        resultados = list(ex.map(uma, cand))
    pasta = Path(__file__).resolve().parent
    gravar_json(pasta / "relatorio_fontes.json", {"validadoEm": agora().strftime("%Y-%m-%d %H:%M"), "fontes": resultados})
    linhas = [f"# Validação das fontes de notícias ({agora():%d/%m/%Y})", "",
              "| Fonte | Indústria | Situação | Feed | Notícia mais recente |", "|---|---|---|---|---|"]
    for r in resultados:
        linhas.append(f"| {r['nome']} | {r.get('industria', '')} | {ROTULO[r['situacao']]} | {r.get('feed') or '—'} | {r.get('mais_recente') or '—'} |")
    (pasta / "relatorio_fontes.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    ok = sum(r["situacao"] == "ok" for r in resultados)
    log(f"{ok} de {len(resultados)} fontes com feed ativo")


if __name__ == "__main__":
    main()
