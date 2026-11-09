"""Cotações do dia das companhias abertas do portal (faixa de ações da Edição do dia, de Finanças e da Roda gigante).

Roda pelo GitHub Actions a cada 15 minutos no horário do pregão (cotacoes.yml) e grava a seção "cotacoes" do
Supabase. A página relê essa seção a cada 5 minutos, então ninguém consulta a bolsa direto do navegador.

1. Mapa empresa -> ação: o CNPJ de cada empresa de companhias_abertas é procurado na lista de empresas listadas da
   B3; das ações da empresa (ON 3, PN 4, units 11, PNA 5, PNB 6), fica a mais negociada. O mapa é refeito a cada
   30 dias ou quando entra empresa nova.
2. Cotação: Yahoo Finance (atraso de cerca de 15 minutos; cotação em tempo real da B3 é paga), em lotes de 20.

    python atualizar_cotacoes.py           # atualiza e grava no Supabase
    python atualizar_cotacoes.py --refazer # refaz o mapa empresa -> ação antes

Precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import base64
import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

from comum import agora, baixar_json, log
from supabase_api import chamar, exigir_configuracao, gravar_secao

B3 = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetInitialCompanies/"
SPARK = "https://query1.finance.yahoo.com/v7/finance/spark?range=1d&interval=1d&symbols="
CLASSES = ["3", "4", "11", "5", "6"]
MERCADO = {"ibov": "^BVSP", "dolar": "BRL=X"}
DIAS_MAPA = 30


def listadas_b3():
    """{cnpj (14 dígitos): códigos de negociação da empresa, ex.: [PETR]}."""
    mapa, pagina, total = {}, 1, 1
    while pagina <= total:
        p = base64.b64encode(json.dumps({"language": "pt-br", "pageNumber": pagina, "pageSize": 120}).encode()).decode()
        j = baixar_json(B3 + p)
        total = j["page"]["totalPages"]
        for e in j["results"]:
            # a B3 tira os zeros à esquerda do CNPJ; a mesma empresa pode ter mais de um código
            if e.get("cnpj") and re.fullmatch(r"[A-Z0-9]{4}", e.get("issuingCompany") or ""):
                mapa.setdefault(e["cnpj"].zfill(14), []).append(e["issuingCompany"])
        pagina += 1
    return mapa


def spark(simbolos):
    """{símbolo: meta do Yahoo} para os que existem; lotes de 20 (um código ruim derruba o lote: aí ele é repartido)."""
    saida = {}

    def lote(lista):
        try:
            res = baixar_json(SPARK + urllib.parse.quote(",".join(lista), safe=",^=."), tentativas=1)["spark"]["result"] or []
        except Exception as e:
            if len(lista) > 1:
                meio = len(lista) // 2
                lote(lista[:meio]), lote(lista[meio:])
            elif not str(lista[0]).endswith(".SA") or "404" not in str(e):
                log(f"cotação: {lista[0]} falhou ({e})")
            return
        for r in res:
            meta = ((r.get("response") or [{}])[0]).get("meta") or {}
            if meta.get("regularMarketPrice") is not None:
                saida[r["symbol"]] = meta

    for i in range(0, len(simbolos), 20):
        lote(simbolos[i:i + 20])
    return saida


def montar_mapa(empresas):
    """{id da empresa no portal: ticker} e a lista das que não têm ação negociada."""
    b3 = listadas_b3()
    codigo = {e["id"]: b3.get(re.sub(r"\D", "", e.get("cnpj") or "").zfill(14), []) for e in empresas}
    cand = sorted({c + s + ".SA" for cs in codigo.values() for c in cs for s in CLASSES})
    metas = spark(cand)
    mapa = {}
    for id_, c in codigo.items():
        opcoes = [((m.get("regularMarketVolume") or 0) * m["regularMarketPrice"], s[:-3])
                  for s in (x + k + ".SA" for x in c for k in CLASSES) if (m := metas.get(s))]
        if opcoes:
            mapa[id_] = max(opcoes)[1]
    return mapa, sorted(set(codigo) - set(mapa))


def item(meta):
    quando = datetime.fromtimestamp(meta.get("regularMarketTime") or 0, timezone.utc).astimezone(agora().tzinfo)
    return {"p": round(meta["regularMarketPrice"], 4), "v": round(meta.get("regularMarketChangePercent") or 0, 2),
            "h": quando.isoformat(timespec="minutes")}


def main():
    exigir_configuracao()
    linhas = {l["nome"]: l["conteudo"] for l in
              chamar("GET", "secoes?select=nome,conteudo&nome=in.(companhias_abertas,cotacoes)")}
    empresas = linhas["companhias_abertas"]["empresas"]
    ant = linhas.get("cotacoes") or {}
    mapa, sem = ant.get("mapa") or {}, ant.get("semAcao") or []
    velho = not ant.get("mapaEm") or datetime.fromisoformat(ant["mapaEm"]) < agora() - timedelta(days=DIAS_MAPA)
    novas = {e["id"] for e in empresas} - set(mapa) - set(sem)
    if "--refazer" in sys.argv or velho or novas:
        mapa, sem = montar_mapa(empresas)
        mapaEm = agora().isoformat(timespec="minutes")
        log(f"cotação: mapa refeito, {len(mapa)} empresas com ação, {len(sem)} sem ação negociada")
    else:
        mapaEm = ant["mapaEm"]
    metas = spark([t + ".SA" for t in sorted(set(mapa.values()))] + list(MERCADO.values()))
    acoes = {id_: {"t": t, **item(metas[t + ".SA"])} for id_, t in mapa.items() if t + ".SA" in metas}
    mercado = {k: item(metas[s]) for k, s in MERCADO.items() if s in metas}
    if not acoes:
        sys.exit("Nenhuma cotação veio do Yahoo; a seção anterior fica como está.")
    gravar_secao("cotacoes", {"atualizadoEm": agora().isoformat(timespec="minutes"), "fonte": "Yahoo Finance (atraso de ~15 min)",
                              "mercado": mercado, "acoes": acoes, "mapa": mapa, "semAcao": sem, "mapaEm": mapaEm},
                 agora().isoformat())
    log(f"cotação: {len(acoes)} ações e {len(mercado)} indicadores de mercado gravados.")


if __name__ == "__main__":
    main()
