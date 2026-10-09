"""Rotina de IA, passo 1: confere se o robô do dia terminou e lista o que a IA precisa escrever.

Não usa IA. Grava Backend/ia/trabalho/pendencias.json (fora do repositório) e termina com:
    0  há pendências: seguir para a escrita (ver ROTINA.md)
    3  o robô das 6h ainda não terminou: aguardar e rodar de novo
    4  nada pendente: encerrar sem publicar

    python Backend/ia/preparar.py                    # uso normal
    python Backend/ia/preparar.py --sem-verificar    # testes: não exige a atualização do dia
"""
import json
import statistics
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comum import CONFIG, DADOS, RAIZ, gravar_json, hoje_iso, ler_json, log  # noqa: E402

IA = Path(__file__).resolve().parent
TRABALHO = IA / "trabalho"
ESTADO = IA / "estado.json"
REPO = "gitpeers/portal-inteligencia-peers"
MAX_RADAR = 150          # por execução; o que passar disso fica para o dia seguinte
MAX_MOVIMENTOS = 80
MAX_CONCORRENCIA = 100   # a carga inicial (6 meses) é dividida em alguns dias
DIAS_LEITURA_SEMANA = 7  # a Leitura da semana da Concorrência é reescrita uma vez por semana
DIAS_ESPERA_RELEASES = 50  # depois disso, processa os releases que já saíram mesmo sem a fila completa
FIM_TRIMESTRE = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}


def robo_terminou():
    """O robô grava a data do dia em edicao.json ao terminar; a API do GitHub diz se há execução em andamento."""
    if ler_json(DADOS / "edicao.json").get("hoje") != hoje_iso():
        return False, "o robô das 6h ainda não gravou a edição de hoje"
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=5",
                                     headers={"User-Agent": "portal-peers-ia", "Accept": "application/vnd.github+json"})
        runs = json.load(urllib.request.urlopen(req, timeout=20))["workflow_runs"]
        if any(r["status"] != "completed" and r["event"] != "push" for r in runs):
            return False, "há uma atualização do robô em andamento no GitHub"
    except Exception as e:      # sem acesso à API, vale a data gravada em edicao.json
        log(f"  aviso: não consultei o GitHub ({str(e)[:60]})")
    return True, ""


def mediana(valores):
    v = [x for x in valores if isinstance(x, (int, float))]
    return round(statistics.median(v), 1) if v else None


def financas():
    """Uma entrada por indústria e divisão, com as medianas do trimestre predominante (mesma regra do site)."""
    grupos = {}
    for e in ler_json(DADOS / "companhias_abertas.json")["empresas"]:
        grupos.setdefault(f'{e["ind"]}|{e["div"]}', []).append(e)
    saida = {}
    for chave, lista in grupos.items():
        periodos = [e["periodo"] for e in lista]
        predominante = max(set(periodos), key=lambda p: (periodos.count(p), int(p[2:]) * 10 + int(p[0])))
        dentro = [e for e in lista if e["periodo"] == predominante]
        banco = chave.endswith("|Banking")
        campos = ["margemFinanceira", "crescMFB", "lucroLiquido", "crescLL", "roe", "inadimplencia"] if banco \
            else ["receita", "cresc", "margemEbitda", "margemLiquida", "lucroLiquido"]
        saida[chave] = {
            "periodo": predominante, "empresasNaMediana": len(dentro), "foraDaMediana": len(lista) - len(dentro),
            "unidades": "R$ milhões; cresc = % sobre o mesmo trimestre do ano anterior; margens e ROE em %",
            "mediana": {c: mediana(e["metr"].get(c) for e in dentro) for c in campos},
            "empresas": [{"nome": e["nome"], "periodo": e["periodo"], "fonte": e["fonte"],
                          **{c: e["metr"].get(c) for c in campos}} for e in lista],
        }
    return saida


def indicadores():
    saida = {}
    for s in ler_json(DADOS / "indicadores.json"):
        reais = [x for x in s["indicadores"] if x.get("status") == "real"]
        if reais:
            saida[s["id"]] = {
                "industria": s["industria"], "divisao": s["divisao"], "segmento": s["segmento"],
                "indicadores": [{k: x.get(k) for k in ("nome", "valor", "unidade", "var", "varPP", "varUnidade",
                                                       "comparacao", "periodo", "fonte")} for x in reais],
            }
    return saida


def releases():
    """Sessão trimestral: entra quando a fila do novo trimestre está completa ou passou o prazo de espera."""
    fila = ler_json(RAIZ / "Backend" / "releases_trimestre.json")
    base = ler_json(CONFIG / "financas_releases.json")
    if fila["trimestre"] == base["periodo"]:
        return None
    prontos = [r for r in fila["releases"] if r.get("link")]
    t = fila["trimestre"]
    fim = f'20{t[2:]}-{FIM_TRIMESTRE[t[0]]}'
    dias = (date.fromisoformat(hoje_iso()) - date.fromisoformat(fim)).days
    if not prontos or (len(prontos) < len(fila["releases"]) and dias < DIAS_ESPERA_RELEASES):
        return None
    return {"trimestre": t, "trimestreAtual": base["periodo"], "prontos": prontos,
            "faltam": [r["nome"] for r in fila["releases"] if not r.get("link")]}


def aprofundamento():
    """Visão por player de cada indicador ligado: o setor, as empresas e a diferença de cada uma (do robô)."""
    caminho = DADOS / "aprofundamento.json"
    if not caminho.exists():
        return {}
    saida = {}
    for p in ler_json(caminho)["pontes"]:
        saida[f'{p["segmento"]}|{p["indicador"]}'] = {
            "indicador": p["indicador"], "nivel": p["nivel"], "nota": p["nota"], "metrica": p["rotuloMetrica"],
            "unidade": p["unidadeMetrica"], "setor": p.get("setor"),
            "players": [{k: x.get(k) for k in ("nome", "valor", "diferenca", "posicao", "periodo")} for x in p["players"]],
        }
    return saida


def concorrencia():
    """Movimentos dos concorrentes sem análise e, uma vez por semana, o material da Leitura da semana."""
    caminho_lista, caminho_itens = DADOS / "concorrentes.json", DADOS / "concorrencia.json"
    if not (caminho_lista.exists() and caminho_itens.exists()):
        return None, None, 0
    perfil = {c["id"]: {k: c.get(k) for k in ("nome", "grupo", "concorreEm")}
              for c in ler_json(caminho_lista)["concorrentes"]}
    itens = ler_json(caminho_itens)["itens"]
    sem_ia = sorted((i for i in itens if not i.get("ia")), key=lambda i: i["data"], reverse=True)
    pend = [{k: i.get(k) for k in ("id", "concorrente", "nome", "grupo", "tipo", "manchete", "fonte", "data",
                                    "escopo", "parceiros", "offering")} for i in sem_ia[:MAX_CONCORRENCIA]]
    semana = None
    analises = ler_json(DADOS / "analises.json") if (DADOS / "analises.json").exists() else {}
    ultima = (analises.get("concorrencia") or {}).get("geradoEm", "")
    hoje = date.fromisoformat(hoje_iso())
    if not ultima or (hoje - date.fromisoformat(ultima)).days >= DIAS_LEITURA_SEMANA:
        inicio = (hoje - timedelta(days=DIAS_LEITURA_SEMANA)).isoformat()
        da_semana = [i for i in itens if i["data"] >= inicio and not i.get("oculto")]
        # os itens da semana que ainda não têm análise vêm nas pendências: a leitura usa as análises escritas hoje
        semana = {"inicio": inicio, "fim": hoje_iso(),
                  "itens": [{k: i.get(k) for k in ("id", "nome", "grupo", "tipo", "manchete", "data", "escopo",
                                                    "parceiros", "fato", "sinal", "impacto", "selo")} for i in da_semana]}
    return {"perfis": perfil, "itens": pend}, semana, max(0, len(sem_ia) - MAX_CONCORRENCIA)


def main():
    if "--sem-verificar" not in sys.argv:
        ok, motivo = robo_terminou()
        if not ok:
            log(f"Aguardar: {motivo}.")
            sys.exit(3)
    edicao = ler_json(DADOS / "edicao.json")
    estado = ler_json(ESTADO) if ESTADO.exists() else {"processadoEm": {}}
    feito = estado.get("processadoEm", {})
    ultima = edicao.get("atualizadoEm", {})
    taxo = ler_json(DADOS / "taxonomia.json")

    radar = sorted((i for i in ler_json(DADOS / "radar.json") if not i.get("ia")), key=lambda i: i["data"], reverse=True)
    movs = sorted((m for m in ler_json(DADOS / "movimentos.json") if not m.get("ia")), key=lambda m: m["data"], reverse=True)
    pend = {
        "geradoEm": hoje_iso(),
        "referencia": {"offerings": taxo["offerings"], "temas": taxo["temas"]},
        "radar": [{k: i.get(k) for k in ("id", "manchete", "resumo", "fonte", "industria", "divisao", "offering", "temas", "data")}
                  for i in radar[:MAX_RADAR]],
        "movimentos": [{k: m.get(k) for k in ("id", "player", "tipo", "tese", "valor", "fonte", "industria", "divisao", "data")}
                       for m in movs[:MAX_MOVIMENTOS]],
        "atualizadoEm": {},
    }
    if ultima.get("financas", "") > feito.get("financas", ""):
        pend["financas"] = financas(); pend["atualizadoEm"]["financas"] = ultima["financas"]
    if ultima.get("indicadores", "") > feito.get("indicadores", ""):
        pend["indicadores"] = indicadores(); pend["atualizadoEm"]["indicadores"] = ultima["indicadores"]
    rel = releases()
    if rel:
        pend["releases"] = rel
    # visão por player: reescrita quando Indicadores ou Finanças mudam (não todo dia, embora o robô recalcule)
    base_aprof = max(ultima.get("indicadores", ""), ultima.get("financas", ""))
    if base_aprof and base_aprof > feito.get("aprofundamento", ""):
        aprof = aprofundamento()
        if aprof:
            pend["aprofundamento"] = aprof
            pend["atualizadoEm"]["aprofundamento"] = base_aprof
    conc, semana, conc_fora = concorrencia()
    if conc:
        pend["referencia"]["concorrentes"] = conc["perfis"]
        pend["concorrencia"] = conc["itens"]
    if semana:
        pend["concorrenciaSemana"] = semana

    TRABALHO.mkdir(exist_ok=True)
    for velho in TRABALHO.glob("respostas*.json"):      # respostas de uma execução anterior não valem mais
        velho.unlink()
    gravar_json(TRABALHO / "pendencias.json", pend)
    resumo = {"radar": len(pend["radar"]), "movimentos": len(pend["movimentos"]),
              "financas": len(pend.get("financas", {})), "indicadores": len(pend.get("indicadores", {})),
              "releases": len(rel["prontos"]) if rel else 0,
              "aprofundamento": len(pend.get("aprofundamento", {})),
              "concorrencia": len(pend.get("concorrencia", [])), "concorrenciaSemana": 1 if semana else 0}
    log(f"Pendências: {resumo} (ficaram para outro dia: {max(0, len(radar) - MAX_RADAR)} do Radar, "
        f"{max(0, len(movs) - MAX_MOVIMENTOS)} de Movimentos, {conc_fora} da Concorrência)")
    sys.exit(0 if any(resumo.values()) else 4)


if __name__ == "__main__":
    main()
