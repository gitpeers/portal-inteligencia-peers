"""Atualiza a coluna "Hoje" e o Focus da aba Cenário 2027.

Os cenários (pessimista, base, otimista) e os textos são escritos pela equipe e publicados com
publicar_cenario.py; ficam só no Supabase (seção "cenario"). Este script só troca os números que têm fonte
pública com API, conforme o campo "auto" de cada linha:
  hoje.auto.sgs     série do SGS do Banco Central ("sinal": -1 inverte, para o primário em % do PIB)
  hoje.auto.sidra   consulta do SIDRA/IBGE, com {p} no lugar do período
  hoje.auto.ibov    fechamento do Ibovespa (e a variação desde a véspera da eleição)
  base.auto.focus   mediana do Focus para o ano do cenário (quando o cenário base é o próprio Focus)
  focus             mediana do Focus agora e na data "focusPre" (anterior à eleição), para mostrar a mudança

    python atualizar_cenario.py                 # usa Frontend/dados/cenario.json (rotina diária)
    python atualizar_cenario.py arquivo.json    # atualiza outro arquivo (exemplo local, publicação)
"""
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from comum import DADOS, agora, baixar_json, gravar_json, ler_json, log, registrar_atualizacao

ANO = "2027"
OLINDA = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"


def sgs(codigo):
    dados = baixar_json(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/1?formato=json")
    d = dados[-1]
    dia, mes, ano = d["data"].split("/")
    # a meta da Selic vem com datas futuras (vale até a próxima reunião): limita a hoje
    return float(d["valor"]), min(f"{ano}-{mes}-{dia}", agora().date().isoformat())


def sgs_historico(codigo, diaria, sinal=1):
    """Últimos 5 anos e meio (série diária, um ponto por semana, ou mensal): [[data, valor]], para o gráfico."""
    hoje = agora().date().isoformat()
    ini = f"01/01/{int(hoje[:4]) - 6}"      # a API limita 'ultimos/N' a poucos pontos; por período não há esse limite
    dados = baixar_json(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={ini}")
    pts = []
    for d in dados:
        dia, mes, ano = d["data"].split("/")
        if f"{ano}-{mes}-{dia}" <= hoje and d["valor"] not in (None, ""):
            pts.append([f"{ano}-{mes}-{dia}", float(d["valor"]) * sinal])
    if diaria:      # um ponto por semana, mantendo sempre o último
        pts = pts[::-5][::-1]
    pts = [p for p in pts if p[0] >= f"{int(hoje[:4]) - 6}{hoje[4:]}"]
    return pts


def sidra_historico(consulta):
    """Últimos 5 anos e meio de uma série do SIDRA (trimestral ou mensal): [[data, valor]]."""
    linhas = baixar_json("https://apisidra.ibge.gov.br/values" + consulta.replace("{p}", "last%2080"))[1:]
    hoje = agora().date().isoformat()
    corte = f"{int(hoje[:4]) - 6}{hoje[4:]}"
    pts = []
    for x in linhas:
        p = x["D3C"]                       # AAAAMM; 01 a 04 = trimestre, acima disso = mês
        m = int(p[4:6])
        data = f"{p[:4]}-{(m * 3 if m <= 4 else m):02d}-15"
        if data >= corte and x["V"] not in (None, "", "-", "..."):
            pts.append([data, float(x["V"])])
    return pts


def sidra(consulta):
    linhas = baixar_json("https://apisidra.ibge.gov.br/values" + consulta.replace("{p}", "last%201"))[1:]
    p = linhas[-1]["D3C"]          # período, ex. 202602 = 2º trimestre de 2026
    return float(linhas[-1]["V"]), f"{p[5]}T{p[2:4]}"


def ibov():
    """Fechamentos diários do Ibovespa nos últimos 5 anos: [(data, valor)]."""
    r = baixar_json("https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP?range=5y&interval=1d")["chart"]["result"][0]
    br = timezone(timedelta(hours=-3))
    return [(datetime.fromtimestamp(t, br).date().isoformat(), c)
            for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]


def focus(indicadores, desde):
    """Mediana do Focus para 2027, por indicador e data de referência, a partir de 'desde'."""
    filtro = f"DataReferencia eq '{ANO}' and baseCalculo eq 0 and Data ge '{desde}'"
    url = OLINDA + "?" + urllib.parse.urlencode({"$filter": filtro, "$format": "json", "$top": "5000",
                                                  "$select": "Indicador,IndicadorDetalhe,Data,Mediana"}, quote_via=urllib.parse.quote)
    serie = {}
    for r in baixar_json(url, timeout=90)["value"]:
        if r["Indicador"] in indicadores and not r.get("IndicadorDetalhe"):
            serie.setdefault(r["Indicador"], {})[r["Data"]] = r["Mediana"]
    return serie


def na_data(serie, data):
    """Valor na data pedida ou no último dia antes dela."""
    antes = [d for d in serie if d <= data]
    return serie[max(antes)] if antes else None


def atualizar(c):
    linhas = [l for e in c["etapas"] for l in e["linhas"]]
    erros = 0
    for l in linhas:
        a = (l.get("hoje") or {}).get("auto")
        if not a:
            continue
        try:
            if "sgs" in a:
                v, d = sgs(a["sgs"])
                l["hoje"]["valor"], l["hoje"]["data"] = v * a.get("sinal", 1), d if a.get("freq") == "diaria" else d[:7]
                try:
                    l["historico"] = sgs_historico(a["sgs"], a.get("freq") == "diaria", a.get("sinal", 1))
                except Exception as e:      # sem o histórico, o gráfico some mas o número de hoje fica
                    log(f"cenario: {l['id']} sem histórico ({e})")
            elif "sidra" in a:
                l["hoje"]["valor"], l["hoje"]["data"] = sidra(a["sidra"])
                try:
                    l["historico"] = sidra_historico(a["sidra"])
                except Exception as e:
                    log(f"cenario: {l['id']} sem histórico ({e})")
            elif a.get("ibov"):
                s = ibov()
                l["hoje"]["valor"], l["hoje"]["data"] = round(s[-1][1]), s[-1][0]
                passo = max(1, len(s) // 260)       # ~260 pontos no gráfico de 5 anos
                l["historico"] = [[d, round(v)] for d, v in s[::-passo][::-1]]
                pre = [x for x in s if x[0] < c["eleicao"]]
                if pre:
                    l["hoje"]["desdeEleicao"] = round((s[-1][1] / pre[-1][1] - 1) * 100, 2)
                    l["hoje"]["preEleicao"] = {"data": pre[-1][0], "valor": round(pre[-1][1])}
        except Exception as e:      # uma fonte fora do ar mantém o último valor
            erros += 1
            log(f"cenario: {l['id']} sem atualização ({e})")
    nomes = {l["focus"] for l in linhas if l.get("focus")} | {l["base"]["auto"]["focus"] for l in linhas
                                                               if (l.get("base") or {}).get("auto")}
    if nomes:
        try:
            serie = focus(nomes, (datetime.fromisoformat(c["focusPre"]) - timedelta(days=10)).date().isoformat())
            for l in linhas:
                s = serie.get(l.get("focus"))
                if s:
                    ult = max(s)
                    l["focusAgora"] = {"data": ult, "valor": s[ult], "pre": na_data(s, c["focusPre"])}
                b = (l.get("base") or {}).get("auto")
                if b and serie.get(b["focus"]):
                    sb = serie[b["focus"]]
                    l["base"]["valor"], l["base"]["data"] = sb[max(sb)], max(sb)
        except Exception as e:
            erros += 1
            log(f"cenario: Focus sem atualização ({e})")
    c["atualizadoEm"] = agora().isoformat(timespec="minutes")
    return erros


def main():
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else DADOS / "cenario.json"
    if not caminho.exists():
        log("cenario: seção ainda não publicada, nada a fazer")
        return
    c = ler_json(caminho)
    erros = atualizar(c)
    gravar_json(caminho, c)
    if len(sys.argv) == 1:
        registrar_atualizacao("cenario")
    log(f"cenario: atualizado ({erros} fonte(s) com erro)")


if __name__ == "__main__":
    main()
