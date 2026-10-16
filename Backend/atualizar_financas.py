"""Atualiza a base trimestral de Finanças (Companhias abertas).

Junta duas fontes:
  1. CVM (dados abertos, ITR): números contábeis do trimestre de todas as companhias abertas com setor
     ligado a uma indústria (config/financas_cvm.json). Atualiza sozinho.
  2. Releases das empresas (config/financas_releases.json): números ajustados e KPIs operacionais das empresas
     acompanhadas. Atualizados uma vez por trimestre, na sessão descrita no documento do protótipo.
Para cada empresa vale o trimestre mais recente; no mesmo trimestre, vale o número ajustado do release.

Também monta Backend/releases_trimestre.json: os releases de resultado (press-releases entregues à CVM)
do trimestre seguinte ao da base ajustada, para a sessão trimestral.
"""
import csv
import io
import re
import unicodedata
import urllib.parse
import zipfile
from pathlib import Path

from comum import CONFIG, DADOS, agora, baixar, baixar_json, gravar_json, ler_json, log, registrar_atualizacao

ITR = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{ano}.zip"
IFDATA = "https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata/"
CADASTRO = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
IPE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"
MINIMO_EMPRESAS = 100     # um trimestre só vira o período da base quando já há empresas suficientes
FIM_TRIMESTRE = {"03-31": 1, "06-30": 2, "09-30": 3, "12-31": 4}
INICIO_TRIMESTRE = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}


def chave(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\b(s a|sa|s/a|ltda|em recuperacao judicial|cia|companhia)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def rotulo(fim):
    """'2026-06-30' -> '2T26'."""
    return f"{FIM_TRIMESTRE[fim[5:]]}T{fim[2:4]}"


def rotulo_longo(codigo):
    """'2T26' -> '2T26 · abr–jun/2026'."""
    meses = {1: "jan–mar", 2: "abr–jun", 3: "jul–set", 4: "out–dez"}
    return f"{codigo} · {meses[int(codigo[0])]}/20{codigo[2:]}"


def ler_csv(arquivo, nome):
    return csv.DictReader(io.StringIO(arquivo.read(nome).decode("latin-1")), delimiter=";")


def valor_mi(linha):
    v = float(linha["VL_CONTA"])
    return v / 1000 if linha["ESCALA_MOEDA"].upper() == "MIL" else v / 1_000_000


def numeros_cvm(ano, individual=frozenset()):
    """Números trimestrais (3 meses) de todos os trimestres do ano, por CNPJ, com o mesmo trimestre do ano anterior.
    Devolve o trimestre mais recente com cobertura suficiente e as contas; cada empresa usa o seu último trimestre.
    `individual`: CNPJs que podem entrar pelo individual quando não publicam consolidado (só as acompanhadas: as
    subsidiárias sem controladas, como as distribuidoras de energia, contariam em dobro com o grupo)."""
    arq = zipfile.ZipFile(io.BytesIO(baixar(ITR.format(ano=ano), timeout=180)))

    def tres_meses(l):
        q = FIM_TRIMESTRE.get(l["DT_FIM_EXERC"][5:])
        return q is not None and l["DT_INI_EXERC"] == f'{l["DT_FIM_EXERC"][:4]}-{INICIO_TRIMESTRE[q]}'
    # consolidado; acompanhada sem controladas, que só publica o individual (ex.: Assaí), entra pelo individual
    contas, acum = {}, {}
    for tipo in ("con", "ind"):
        aceita = (lambda cnpj: True) if tipo == "con" else (lambda cnpj, ja=set(contas): cnpj in individual and cnpj not in ja)
        for l in ler_csv(arq, f"itr_cia_aberta_DRE_{tipo}_{ano}.csv"):
            if aceita(l["CNPJ_CIA"]) and tres_meses(l):
                contas.setdefault(l["CNPJ_CIA"], {}).setdefault(l["DT_FIM_EXERC"], {})[l["CD_CONTA"]] = (valor_mi(l), l["DS_CONTA"])
        # depreciação e amortização: a DFC é acumulada no ano, então o trimestre é a diferença entre dois ITRs seguidos
        for l in ler_csv(arq, f"itr_cia_aberta_DFC_MI_{tipo}_{ano}.csv"):
            if aceita(l["CNPJ_CIA"]) and l["CD_CONTA"].startswith("6.01.01.") \
                    and re.search(r"deprecia|amortiza|exaust", l["DS_CONTA"], re.I) and l["DT_INI_EXERC"] == f"{ano}-01-01":
                d = acum.setdefault(l["CNPJ_CIA"], {})
                d[l["DT_FIM_EXERC"]] = d.get(l["DT_FIM_EXERC"], 0) + valor_mi(l)
    cobertura = {}
    for cnpj, c in contas.items():
        for fim in c:
            if fim[:4] == str(ano):
                cobertura.setdefault(fim, set()).add(cnpj)
    validos = sorted(f for f, c in cobertura.items() if len(c) >= MINIMO_EMPRESAS)
    if not validos:
        return None, {}
    fins = {n: f"{ano}-{k}" for k, n in FIM_TRIMESTRE.items()}
    for cnpj, d in acum.items():
        for q in range(1, 5):
            fim, antes = fins[q], fins.get(q - 1)
            if fim in d and fim in contas.get(cnpj, {}) and (q == 1 or antes in d):
                contas[cnpj][fim]["da"] = d[fim] - (d[antes] if q > 1 else 0)
    return validos[-1], contas


def ultimo_trimestre(c, ano):
    """Trimestre mais recente do ano que a empresa já entregou."""
    proprios = [f for f in c if f[:4] == str(ano)]
    return max(proprios) if proprios else None


def pct(a, b):
    return round(a / b * 100, 1) if a is not None and b else None


def cresc(atual, antes):
    return round((atual / antes - 1) * 100, 1) if atual is not None and antes and antes > 0 else None


def fmt(v, pctual=False):
    """Formato do portal: R$ milhões sem casas (1.234) ou percentual com uma casa (10,6%)."""
    if v is None:
        return "n.d."
    if pctual:
        return f"{v:+.1f}%".replace(".", ",")
    return f"{v:,.0f}".replace(",", ".") if abs(v) >= 10 else f"{v:.1f}".replace(".", ",")


def fp(v):
    return "n.d." if v is None else f"{v:.1f}%".replace(".", ",")


def subcontas(d, raiz, padrao):
    """Soma das contas logo abaixo de `raiz` cuja descrição casa com `padrao`."""
    nivel = raiz.count(".") + 1
    return sum(d[k][0] for k in d if k.startswith(raiz + ".") and k.count(".") == nivel
               and re.search(padrao, d[k][1], re.I))


def receita_venda(d):
    """Receita de venda. Tira da conta 3.01 o que a CVM põe nela sem ser venda: a despesa de seguros das operadoras
    de saúde no IFRS 17 (ex.: Hapvida; volta para o custo, e o lucro bruto não muda) e a variação do valor justo
    dos ativos biológicos (ex.: SLC). Assim a receita fica como nos releases."""
    if "3.01" not in d:
        return None
    return d["3.01"][0] - subcontas(d, "3.01", r"despesas? de seguros?") - subcontas(d, "3.01", r"valor justo")


def lucro_controladores(d):
    """Lucro atribuído aos controladores, o que os releases reportam. A conta do lucro do período é achada pelo nome:
    3.11 nas empresas, 3.09 nos bancos. Sem a abertura, vale o consolidado. Se a empresa preencheu a parte dos
    controladores com zero e o consolidado não é zero (erro de preenchimento visto na CVM em Grupo Mateus,
    Hapvida, Panvel e outras), usa o consolidado menos os não controladores."""
    conta = next((k for k in sorted(d) if k.count(".") == 1 and re.match(r"lucro.*per[íi]odo", d[k][1], re.I)), "3.11")
    filhas = {k: d[k] for k in d if k.startswith(conta + ".") and k.count(".") == 2}
    total = d.get(conta, (None, ""))[0]
    contr = next((v for v, ds in filhas.values() if re.search(r"controlador", ds, re.I) and not re.search(r"n[ãa]o", ds, re.I)), None)
    minor = next((v for v, ds in filhas.values() if re.search(r"n[ãa]o controlador", ds, re.I)), None)
    if contr is None or (contr == 0 and total):
        return total - (minor or 0) if total is not None else None
    return contr


def empresa_cvm(cnpj, nome, ind, div, valor_id, fim, c):
    atual, antes = c[fim], c.get(f"{int(fim[:4]) - 1}{fim[4:]}", {})
    g = lambda d, k: d.get(k, (None, ""))[0]
    banco = "intermedia" in c[fim].get("3.01", (0, ""))[1].lower()
    lucro, lucro_ant = lucro_controladores(atual), lucro_controladores(antes)
    base = {"id": "cvm-" + re.sub(r"\D", "", cnpj), "nome": nome, "ind": ind, "div": div, "valorId": valor_id,
            "cnpj": cnpj, "fonte": "cvm", "periodo": rotulo(fim), "op": []}
    if banco or div == "Banking":
        mf, mf_ant = g(atual, "3.03"), g(antes, "3.03")
        base["div"] = "Banking" if ind == "Financial Services" else div
        base["metr"] = {"margemFinanceira": mf, "crescMFB": cresc(mf, mf_ant), "lucroLiquido": lucro,
                        "crescLL": cresc(lucro, lucro_ant), "carteira": None, "crescCarteira": None,
                        "inadimplencia": None, "roe": None, "cet1": None}
        base["fin"] = [["Resultado bruto de intermediação financeira", fmt(mf)], ["Crescimento (a/a)", fmt(cresc(mf, mf_ant), True)],
                       ["Lucro líquido (controladores)", fmt(lucro)], ["Crescimento do lucro (a/a)", fmt(cresc(lucro, lucro_ant), True)]]
        return base
    receita, receita_ant = receita_venda(atual), receita_venda(antes)
    if not receita:
        return None
    bruto, ebit, da = g(atual, "3.03"), g(atual, "3.05"), atual.get("da")
    ebitda = ebit + da if ebit is not None and da is not None else None
    base["metr"] = {"receita": round(receita), "receitaTipo": "líquida", "cresc": cresc(receita, receita_ant),
                    "ebitda": round(ebitda) if ebitda is not None else None, "margemEbitda": pct(ebitda, receita),
                    "lucroLiquido": round(lucro) if lucro is not None else None, "margemLiquida": pct(lucro, receita)}
    base["fin"] = [["Receita líquida", fmt(receita)], ["Crescimento (a/a)", fmt(cresc(receita, receita_ant), True)],
                   ["Lucro bruto", fmt(bruto)], ["Margem bruta", fp(pct(bruto, receita))],
                   ["Resultado operacional (EBIT)", fmt(ebit)], ["Depreciação e amortização", fmt(da)],
                   ["EBITDA (EBIT + D&A)", fmt(ebitda)], ["Margem EBITDA", fp(pct(ebitda, receita))],
                   ["Lucro líquido (controladores)", fmt(lucro)], ["Margem líquida", fp(pct(lucro, receita))]]
    return base


def ifdata(anomes, relatorio, codigos):
    """Um relatório do IF.data (conglomerados prudenciais) das instituições pedidas: {código: {coluna: valor}}."""
    filtro = urllib.parse.quote(" or ".join(f"CodInst eq '{c}'" for c in codigos))
    url = (IFDATA + "IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)"
           f"?@AnoMes={anomes}&@TipoInstituicao=1&@Relatorio='{relatorio}'&$format=json&$filter={filtro}")
    d = {}
    for x in baixar_json(url, timeout=240)["value"]:
        d.setdefault(x["CodInst"], {})[x["NomeColuna"].split("\n")[0].strip()] = x["Saldo"]
    return d


def bancos_ifdata(empresas):
    """Carteira, ROE e capital principal (CET1) dos bancos que vêm da CVM, pelo IF.data do Banco Central
    (conglomerado prudencial), na mesma data-base do ITR. O IF.data sai cerca de 3 meses depois do trimestre:
    até lá os campos ficam n.d., para não misturar períodos. A inadimplência não está nos relatórios usados."""
    por_periodo = {}
    for e in empresas:
        if e["fonte"] == "cvm" and e["div"] == "Banking":
            por_periodo.setdefault(e["periodo"], []).append(e)
    for per, lista in por_periodo.items():
        tri, ano = int(per[0]), 2000 + int(per[2:])
        am = ano * 100 + tri * 3
        am_ant = am - 3 if tri > 1 else (ano - 1) * 100 + 12
        cad = baixar_json(IFDATA + f"IfDataCadastro(AnoMes=@AnoMes)?@AnoMes={am}&$format=json&$top=100000", timeout=240)["value"]
        lider = {c["CnpjInstituicaoLider"]: c["CodInst"] for c in cad
                 if c.get("CnpjInstituicaoLider") and c["CodInst"] == c.get("CodConglomeradoPrudencial")}
        cod = {e["id"]: lider.get(re.sub(r"\D", "", e["cnpj"])[:8]) for e in lista}
        cods = sorted({c for c in cod.values() if c})
        if not cods:
            continue
        r1, r1_tri, r1_ano, r5 = ifdata(am, "1", cods), ifdata(am_ant, "1", cods), ifdata(am - 100, "1", cods), ifdata(am, "5", cods)
        for e in lista:
            c = cod[e["id"]]
            v, t, a = r1.get(c, {}), r1_tri.get(c, {}), r1_ano.get(c, {})
            if not v.get("Carteira de Crédito"):
                continue
            # o lucro do IF.data é acumulado no semestre: jun e dez trazem 6 meses, mar e set trazem 3
            lucro = v.get("Lucro Líquido")
            if tri in (2, 4):
                lucro = lucro - t["Lucro Líquido"] if lucro is not None and t.get("Lucro Líquido") is not None else None
            pl = [x for x in (v.get("Patrimônio Líquido"), t.get("Patrimônio Líquido")) if x]
            roe = round(lucro * 4 / (sum(pl) / len(pl)) * 100, 1) if lucro is not None and pl else None
            carteira = round(v["Carteira de Crédito"] / 1e9, 1)
            cc = cresc(v["Carteira de Crédito"], a.get("Carteira de Crédito"))
            cet1 = r5.get(c, {}).get("Índice de Capital Principal")
            cet1 = round(cet1 * 100, 1) if cet1 is not None else None
            e["metr"].update({"carteira": carteira, "crescCarteira": cc, "roe": roe, "cet1": cet1})
            e["fin"] += [["Carteira de crédito (R$ bi)", f"{carteira:.1f}".replace(".", ",")],
                         ["Crescimento da carteira (a/a)", fmt(cc, True)], ["ROE anualizado", fp(roe)],
                         ["Capital principal (CET1)", fp(cet1)],
                         ["Fonte de carteira, ROE e CET1", f"IF.data (Banco Central), conglomerado prudencial, {per}"]]
    return sum(1 for e in empresas if e["fonte"] == "cvm" and e["div"] == "Banking" and e["metr"].get("carteira"))


def releases(cnpjs, depois_de):
    """Press-releases entregues à CVM depois do fim do trimestre, das empresas acompanhadas."""
    achados = {}
    for ano in sorted({depois_de[:4], agora().strftime("%Y")}):
        arq = zipfile.ZipFile(io.BytesIO(baixar(IPE.format(ano=ano), timeout=120)))
        for l in ler_csv(arq, arq.namelist()[0]):
            so_ingles = re.search(r"ingl|english|\dQ\d", l["Assunto"], re.I) and not re.search(r"portugu", l["Assunto"], re.I)
            if l["CNPJ_Companhia"] in cnpjs and l["Tipo"] == "Press-release" and l["Data_Entrega"] > depois_de and not so_ingles:
                atual = achados.get(l["CNPJ_Companhia"])
                if not atual or l["Data_Entrega"] > atual["data"]:
                    achados[l["CNPJ_Companhia"]] = {"data": l["Data_Entrega"], "assunto": l["Assunto"], "link": l["Link_Download"]}
    return achados


def main():
    cfg = ler_json(CONFIG / "financas_cvm.json")
    base = ler_json(CONFIG / "financas_releases.json")
    ano = int(agora().strftime("%Y"))
    base_cnpj = {e["cnpj"] for e in base["empresas"]}
    fim, contas = numeros_cvm(ano, base_cnpj)
    if fim is None:                       # início do ano, antes do 1º ITR: usa o ano anterior
        fim, contas = numeros_cvm(ano - 1, base_cnpj)
    log(f"CVM: trimestre {rotulo(fim)}, {len(contas)} empresas com DRE")

    cadastro = {c["CNPJ_CIA"]: c for c in csv.DictReader(io.StringIO(baixar(CADASTRO, timeout=120).decode("latin-1")), delimiter=";")
                if c["SIT"] == "ATIVO"}
    v = ler_json(DADOS / "valor1000.json")
    i_id, i_raz, i_ind, i_div = (v["campos"].index(k) for k in ("id", "razao", "ind", "div"))
    i_nome = v["campos"].index("nome")
    valor = {chave(l[i_raz]): (l[i_id], l[i_ind], l[i_div]) for l in v["linhas"]}
    nome_valor = {l[i_id]: l[i_nome] for l in v["linhas"]}

    empresas = []
    for cnpj, c in contas.items():
        fim_emp = ultimo_trimestre(c, fim[:4])
        if cnpj in base_cnpj or not fim_emp or cnpj not in cadastro:
            continue
        cad = cadastro[cnpj]
        setor = re.sub(r"^Emp\. Adm\. Part\. - ", "", cad["SETOR_ATIV"])
        vid, ind, div = valor.get(chave(cad["DENOM_SOCIAL"]), (None, None, None))
        if not ind:
            if setor not in cfg["setores"]:
                continue
            ind, div = cfg["setores"][setor]
        ind, div = cfg.get("excecoes", {}).get(cnpj, {}).get("classe", (ind, div))   # correções da revisão por empresa
        nome = nome_valor.get(vid) or re.sub(r"\s+(S\.?\s?A\.?|S/A)$", "", (cad["DENOM_COMERC"] or cad["DENOM_SOCIAL"]).strip(), flags=re.I).title()
        e = empresa_cvm(cnpj, nome, ind, div, vid, fim_emp, c)
        if e:
            empresas.append(e)

    # empresas acompanhadas: vale o trimestre mais recente; no mesmo trimestre, o número ajustado do release
    ordem = lambda r: (int(r[2:]), int(r[0]))
    for e in base["empresas"]:
        c = contas.get(e["cnpj"])
        fim_emp = ultimo_trimestre(c, fim[:4]) if c else None
        if fim_emp and ordem(rotulo(fim_emp)) > ordem(base["periodo"]):
            novo = empresa_cvm(e["cnpj"], e["nome"], e["ind"], e["div"], e["valorId"], fim_emp, c)
            if novo:
                novo.update({"id": e["id"], "op": e["op"], "opPeriodo": base["periodo"], "release": e.get("release")})
                empresas.append(novo)
                continue
        empresas.append({**e, "fonte": "release", "periodo": base["periodo"]})

    try:
        log(f"IF.data: carteira, ROE e CET1 de {bancos_ifdata(empresas)} bancos que vêm da CVM")
    except Exception as e:   # o IF.data fora do ar não impede o resto de Finanças
        log(f"  falha no IF.data: {str(e)[:80]}")

    periodo = max((e["periodo"] for e in empresas), key=ordem)
    gravar_json(DADOS / "companhias_abertas.json", {"periodo": rotulo_longo(periodo), "empresas": empresas})
    log(f"Finanças: {len(empresas)} companhias abertas ({sum(e['fonte'] == 'release' for e in empresas)} com números ajustados dos releases)")

    # fila de releases para a sessão trimestral
    q, aa = int(base["periodo"][0]), int(base["periodo"][2:])
    q, aa = (1, aa + 1) if q == 4 else (q + 1, aa)
    proximo = f"20{aa:02d}-{[k for k, n in FIM_TRIMESTRE.items() if n == q][0]}"
    try:
        achados = releases(base_cnpj, proximo)
        fila = [{"id": e["id"], "nome": e["nome"], "cnpj": e["cnpj"], **achados.get(e["cnpj"], {"data": None, "link": None})}
                for e in base["empresas"]]
        gravar_json(Path(__file__).resolve().parent / "releases_trimestre.json",
                    {"trimestre": rotulo(proximo), "atualizadoEm": agora().strftime("%Y-%m-%d"), "releases": fila})
        log(f"Releases do {rotulo(proximo)}: {len(achados)} de {len(fila)} empresas acompanhadas já divulgaram")
    except Exception as e:
        log(f"  falha ao montar a fila de releases: {str(e)[:80]}")
    registrar_atualizacao("financas")


if __name__ == "__main__":
    main()
