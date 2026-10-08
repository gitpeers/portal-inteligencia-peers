"""Atualiza a Agenda setorial a partir do calendário mantido em config/calendario.json
das datas de divulgação do IBGE e das audiências públicas da Câmara (APIs públicas),
configuradas em config/agenda_fontes.json.

Sem IA não dá para extrair datas de eventos de dentro das notícias, então a Agenda vem de um
calendário em arquivo. Eventos com "recorrencia": "anual" passam para o ano seguinte quando a data passa.
Eventos já realizados saem da Agenda automaticamente.
"""
import re
from datetime import date, datetime, timedelta

from comum import CONFIG, DADOS, agora, baixar_json, gravar_json, hoje_iso, ler_json, log, registrar_atualizacao

IBGE_CALENDARIO = "https://servicodados.ibge.gov.br/api/v3/calendario/?de={de}&ate={ate}&qtd=1000"
IBGE_PAGINA = "https://www.ibge.gov.br/calendario-de-divulgacao.html"
CAMARA_EVENTOS = ("https://dadosabertos.camara.leg.br/api/v2/eventos?dataInicio={de}&dataFim={ate}"
                  "&itens=100&pagina={pagina}")
CAMARA_PAGINA = "https://www.camara.leg.br/evento-legislativo/{id}"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def divulgacoes_ibge():
    """Divulgações do IBGE nos próximos dias, já marcadas com as indústrias configuradas."""
    cfg = ler_json(CONFIG / "agenda_fontes.json")
    por_alias = {p["alias"]: p for p in cfg["ibge"]}
    ate = agora() + timedelta(days=cfg["janela_dias"])
    url = IBGE_CALENDARIO.format(de=agora().strftime("%m-%d-%Y"), ate=ate.strftime("%m-%d-%Y"))
    itens = []
    for d in baixar_json(url)["items"]:
        prod = por_alias.get(d.get("alias_produto"))
        if not prod:
            continue
        data = datetime.strptime(d["data_divulgacao"][:10], "%d/%m/%Y").date().isoformat()
        mes, ano = d.get("mes_referencia_inicio"), d.get("ano_referencia_inicio")
        ref = f"Referência: {MESES[mes - 1]}/{ano}." if mes and ano else ""
        (ind, div), *_ = prod["industrias"]
        itens.append({
            "tipo": "Publicação de referência", "titulo": f"IBGE · {prod['nome']}", "data": data,
            "local": "Online (IBGE)", "industria": ind, "divisao": div,
            "industrias": sorted({i for i, _ in prod["industrias"]}), "offering": prod["offering"],
            "detalhe": f"{d['titulo']}. {ref}".strip(), "url": d.get("link") or IBGE_PAGINA, "id": f"ibge{d['id']}",
        })
    return itens


def proxima_data(iso, hoje):
    d = date.fromisoformat(iso)
    while d.isoformat() < hoje:
        try:
            d = d.replace(year=d.year + 1)
        except ValueError:          # 29 de fevereiro
            d = d.replace(year=d.year + 1, day=28)
    return d.isoformat()


def audiencias_camara():
    """Audiências públicas e seminários das comissões da Câmara ligadas às indústrias."""
    cfg = ler_json(CONFIG / "agenda_fontes.json")["camara"]
    de, ate = agora(), agora() + timedelta(days=cfg["janela_dias"])
    eventos, pagina = [], 1
    while True:
        lote = baixar_json(CAMARA_EVENTOS.format(de=de.strftime("%Y-%m-%d"), ate=ate.strftime("%Y-%m-%d"), pagina=pagina))["dados"]
        eventos += lote
        if len(lote) < 100 or pagina >= 20:
            break
        pagina += 1
    itens = []
    for e in eventos:
        if e["descricaoTipo"] not in cfg["tipos"] or e.get("situacao") == "Cancelada":
            continue
        com = next((o for o in e["orgaos"] if o["sigla"] in cfg["comissoes"]), None)
        if not com:
            continue
        ind, div, off = cfg["comissoes"][com["sigla"]]
        tema = " ".join((e.get("descricao") or "").split())   # a descrição vem quebrada em várias linhas
        tema = re.split(r"\s(?:\(?REQ|Req\.|Requerimento|Em atendimento|1\)|Convidad|Expositor)", tema, flags=re.I)[0].strip(" .:-")
        tema = tema if len(tema) <= 140 else tema[:137].rsplit(" ", 1)[0] + "…"
        local = (e.get("localCamara") or {}).get("nome") or e.get("localExterno") or "Câmara dos Deputados"
        itens.append({
            "tipo": "Data regulatória", "titulo": f"Câmara · {e['descricaoTipo']}: {tema}", "data": e["dataHoraInicio"][:10],
            "local": f"{local}, Brasília", "industria": ind, "divisao": div, "offering": off,
            "detalhe": com["nome"] + ".", "url": CAMARA_PAGINA.format(id=e["id"]), "id": f"cam{e['id']}",
        })
    return itens


def main():
    hoje = hoje_iso()
    caminho = CONFIG / "calendario.json"
    cal = ler_json(caminho)
    mudou = False
    for e in cal["eventos"]:
        if e.get("recorrencia") == "anual" and e["data"] < hoje:
            e["data"] = proxima_data(e["data"], hoje)
            mudou = True
    if mudou:
        gravar_json(caminho, cal)
    agenda = [e for e in cal["eventos"] if e["data"] >= hoje]
    try:
        ibge = divulgacoes_ibge()
        log(f"IBGE: {len(ibge)} divulgações na janela")
        agenda += ibge
    except Exception as e:   # o IBGE fora do ar não impede a Agenda manual
        log(f"  falha no calendário do IBGE: {str(e)[:80]}")
    try:
        camara = audiencias_camara()
        log(f"Câmara: {len(camara)} audiências na janela")
        agenda += camara
    except Exception as e:   # a Câmara fora do ar não impede o resto da Agenda
        log(f"  falha na agenda da Câmara: {str(e)[:80]}")
    agenda.sort(key=lambda e: e["data"])
    gravar_json(DADOS / "agenda.json", agenda)
    log(f"Agenda: {len(agenda)} entradas futuras de {len(cal['eventos'])} no calendário")
    registrar_atualizacao("agenda")


if __name__ == "__main__":
    main()
