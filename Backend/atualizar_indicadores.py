"""Atualiza os Indicadores setoriais ligados a séries públicas (config/indicadores_fontes.json).

Conectores:
  sgs    Banco Central, séries do SGS (mensais)
  sidra  IBGE, consultas na API SIDRA (mensais, trimestrais ou anuais: campo "freq")
  mpv    Banco Central, estatísticas de meios de pagamento (Pix, cartões, estabelecimentos)
  spi    Banco Central, índice de disponibilidade do SPI (Pix)
  ifdata Banco Central, balanços dos conglomerados no IF.data (sistema e bancos públicos)
  comex  MDIC, Comex Stat (exportações e importações por capítulo, posição ou setor ISIC)
  rtn    Tesouro Nacional, planilha do Resultado do Tesouro Nacional (governo central)
  fpm    Tesouro Nacional, planilha consolidada de transferências (aba FPM)
  finame BNDES, desembolsos mensais das linhas Finame (máquinas e equipamentos)
  capag  Tesouro Nacional, capacidade de pagamento de estados e municípios
  siconfi Tesouro Nacional, RREO e RGF dos 27 estados (ICMS, pessoal e dívida sobre a RCL)
  anp    ANP, dados abertos mensais (produção, vendas) e preços médios de revenda
  ons    ONS, carga de energia mensal do SIN ('metrica' eolica_solar: geração eólica + solar centralizada, balanço horário)
  siga   ANEEL, SIGA: capacidade instalada de geração (total, renovável e participação)
  caged  MTE, Novo Caged: estoque de empregos formais por setor (Tabela 6.1, série com ajustes)
  anatel Anatel, dados abertos de acessos: arquivo de totais mensais de dentro do zip (telefonia móvel,
         banda larga fixa, TV por assinatura), lido por partes, sem baixar o zip inteiro
  anatel_col Anatel, arquivos por município (*_Colunas.csv): participação da fibra, municípios com 5G e
         prestadoras de pequeno porte, no mês mais recente contra o mesmo mês do ano anterior
  sih    Ministério da Saúde, SIH/SUS pelo TabNet: internações em 12 meses e permanência média (dias ÷ internações)
  cnes   Ministério da Saúde, CNES: leitos, leitos de UTI e estabelecimentos com leitos (CSV anual de leitos)
O valor mais recente vira o número do card, e a variação é contra o mesmo período do ano anterior.
Indicadores sem série configurada continuam com valor de exemplo; os sem fonte pública ficam marcados
como sem atualização automática.
"""
import csv
import io
import json
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

from comum import CONFIG, DADOS, agora, baixar, baixar_json, gravar_json, ler_json, log, normalizar, registrar_atualizacao

ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DEFASAGEM = {"mensal": 12, "trimestral": 4, "anual": 1}
OLINDA = "https://olinda.bcb.gov.br/olinda/servico/"


def meses_atras(n):
    d = agora().date().replace(day=1)
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
    return d


# ---------- conectores: cada um devolve [(data, valor)] em ordem cronológica ----------

def serie_sgs(codigo, n):
    """Últimos n valores mensais de uma série do SGS. A API limita "ultimos" a 20, então usa janela de datas."""
    inicio = meses_atras(n + 2)
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
           f"&dataInicial={inicio:%d/%m/%Y}&dataFinal={agora():%d/%m/%Y}")
    pontos = []
    for p in baixar_json(url):
        d, m, a = p["data"].split("/")
        pontos.append((date(int(a), int(m), int(d)), float(p["valor"])))
    return sorted(pontos)[-n:]


def serie_sidra(consulta, n, freq="mensal"):
    """Últimos n valores de uma consulta SIDRA. Períodos: AAAAMM (mês), AAAATT (trimestre) ou AAAA (ano)."""
    dados = baixar_json(f"https://apisidra.ibge.gov.br/values/{consulta}/p/last%20{n}")
    cabecalho, linhas = dados[0], dados[1:]
    chave = next(k for k, v in cabecalho.items() if k.endswith("C") and v.startswith(("Mês", "Trimestre", "Ano")))
    pontos = []
    for l in linhas:
        cod = l[chave]
        try:
            valor = float(l["V"])
        except ValueError:              # "..." ou "-": sem dado no período
            continue
        if freq == "anual":
            d = date(int(cod[:4]), 12, 1)
        elif freq == "trimestral":
            d = date(int(cod[:4]), int(cod[4:6]) * 3, 1)
        else:
            d = date(int(cod[:4]), int(cod[4:6]), 1)
        pontos.append((d, valor))
    soma = {}                           # várias categorias na mesma consulta (ex.: CNAE 13 + 14): soma por período
    for d, v in pontos:
        soma[d] = soma.get(d, 0) + v
    return sorted(soma.items())


def serie_mpv(cfg, n):
    """Estatísticas de meios de pagamento (Olinda/MPV). O parâmetro do recurso é o período inicial:
    uma chamada traz a série inteira a partir dele."""
    if cfg["freq"] == "mensal":
        url = (OLINDA + "MPV_DadosAbertos/versao/v1/odata/MeiosdePagamentosMensalDA(AnoMes=@AnoMes)"
               f"?@AnoMes='{meses_atras(n + 2):%Y%m}'&$format=json&$top=10000")
        campo_data = "AnoMes"
    else:
        ini = meses_atras(3 * (n + 2))
        url = (OLINDA + f"MPV_DadosAbertos/versao/v1/odata/{cfg['recurso']}(trimestre=@trimestre)"
               f"?@trimestre='{ini.year}{(ini.month - 1) // 3 + 1}'&$format=json&$top=100000")
        campo_data = "datatrimestre" if cfg["recurso"] == "MeiosdePagamentosTrimestralDA" else "trimestre"
    soma = {}
    for l in baixar_json(url, timeout=120)["value"]:
        b = str(l[campo_data]).replace("-", "")
        if cfg["freq"] == "mensal":
            d = date(int(b[:4]), int(b[4:6]), 1)
        elif len(b) == 5:                  # 20262 = 2º trimestre de 2026
            d = date(int(b[:4]), int(b[4]) * 3, 1)
        else:                              # 20260630
            d = date(int(b[:4]), int(b[4:6]), 1)
        soma[d] = soma.get(d, 0) + sum(float(l[c] or 0) for c in cfg["campos"])
    return sorted(soma.items())[-n:]


def serie_spi(n):
    linhas = baixar_json(OLINDA + "SPI/versao/v1/odata/PixDisponibilidadeSPI?$format=json&$top=10000")["value"]
    pontos = []
    for l in linhas:
        b = str(l["DataBase"]).replace("-", "")[:6]
        pontos.append((date(int(b[:4]), int(b[4:6]), 1), float(l["Indice"]) * (100 if float(l["Indice"]) <= 1 else 1)))
    return sorted(pontos)[-n:]


_IFDATA = {}


def ifdata_resumo(anomes):
    """Relatório Resumo do IF.data (conglomerados prudenciais), por instituição. Guarda em memória na execução."""
    if anomes not in _IFDATA:
        url = (OLINDA + "IFDATA/versao/v1/odata/IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,"
               f"Relatorio=@Relatorio)?@AnoMes={anomes}&@TipoInstituicao=1&@Relatorio='1'&$format=json&$top=100000")
        d = {}
        for x in baixar_json(url, timeout=240)["value"]:
            d.setdefault(x["CodInst"], {})[x["NomeColuna"].split("\n")[0].strip()] = x["Saldo"]
        _IFDATA[anomes] = d
    return _IFDATA[anomes]


def ifdata_publicos(anomes):
    chave = ("publicos", anomes)
    if chave not in _IFDATA:
        reserva = CONFIG / "ifdata_publicos.json"     # lista salva para quando o cadastro do IF.data estiver fora do ar
        try:
            cad = baixar_json(OLINDA + f"IFDATA/versao/v1/odata/IfDataCadastro(AnoMes=@AnoMes)?@AnoMes={anomes}"
                                       "&$format=json&$top=100000", timeout=120)["value"]
            tc = {}
            for c in cad:
                for k in (c["CodInst"], c["CodConglomeradoPrudencial"]):
                    if k:
                        tc.setdefault(k, c["Tc"])
            _IFDATA[chave] = {k for k, v in tc.items() if v == 1}   # Tc 1 = controle público
            gravar_json(reserva, {"_como_usar": "Códigos dos conglomerados sob controle público no IF.data, salvos "
                                  "automaticamente; usados quando o cadastro do IF.data não responde.",
                                  "anomes": anomes, "codigos": sorted(_IFDATA[chave])})
        except Exception:
            if not reserva.exists():
                raise
            _IFDATA[chave] = set(ler_json(reserva)["codigos"])
    return _IFDATA[chave]


def ifdata_ultimo():
    """Data-base mais recente publicada no IF.data (trimestral, com cerca de 3 meses de defasagem)."""
    d = agora().date()
    q, a = (d.month - 1) // 3 + 1, d.year
    for _ in range(6):
        q, a = (4, a - 1) if q == 1 else (q - 1, a)
        am = a * 100 + q * 3
        if ifdata_resumo(am):
            return am
    raise ValueError("IF.data sem data-base recente")


def ifdata_metrica(metrica, anomes):
    d = ifdata_resumo(anomes)
    publicos = ifdata_publicos(anomes) if metrica.endswith("publicos") else None
    sel = {k: v for k, v in d.items() if publicos is None or k in publicos}
    if metrica.startswith("lucro"):
        # o IF.data acumula o lucro no semestre: jun e dez trazem 6 meses, mar e set trazem 3
        total = sum(v.get("Lucro Líquido") or 0 for v in sel.values())
        if anomes % 100 in (6, 12):
            ant = ifdata_resumo(anomes - 3)
            total -= sum(v.get("Lucro Líquido") or 0 for k, v in ant.items() if k in sel)
        return total
    if metrica.startswith("basileia"):
        pr = [(v.get("Patrimônio de Referência para Comparação com o RWA") or 0, v.get("Índice de Basileia"))
              for v in sel.values() if v.get("Índice de Basileia")]
        rwa = sum(p / b for p, b in pr)
        return sum(p for p, _ in pr) / rwa * 100 if rwa else None
    if metrica == "carteira_publicos":
        return sum(v.get("Carteira de Crédito") or 0 for v in sel.values())
    if metrica == "participacao_publicos":
        total = sum(v.get("Carteira de Crédito") or 0 for v in d.values())
        return sum(v.get("Carteira de Crédito") or 0 for v in sel.values()) / total * 100
    raise ValueError(f"métrica desconhecida: {metrica}")


def serie_ifdata(metrica):
    am = ifdata_ultimo()
    pontos = [(date((am - 100) // 100, am % 100, 1), ifdata_metrica(metrica, am - 100)),
              (date(am // 100, am % 100, 1), ifdata_metrica(metrica, am))]
    return pontos


COMEX = "https://api-comexstat.mdic.gov.br/general"
_COMEX = {}


def comex_consulta(fluxo, nivel, valores, meses):
    """Valor FOB mensal (US$) por código do nível pedido. A API limita o ritmo de pedidos: espaça e repete."""
    chave = (fluxo, nivel, tuple(valores or ()), meses)
    if chave in _COMEX:
        return _COMEX[chave]
    corpo = {"flow": fluxo, "monthDetail": True, "metrics": ["metricFOB"], "details": [nivel],
             # o período vale como faixa de meses repetida em cada ano: pede sempre de janeiro a dezembro
             "period": {"from": f"{meses_atras(meses).year}-01", "to": f"{agora().year}-12"}}
    if valores:
        corpo["filters"] = [{"filter": nivel, "values": valores}]
    req = urllib.request.Request(COMEX, data=json.dumps(corpo).encode(), headers={
        "Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (PortalInteligenciaPeers)"})
    for tentativa in range(6):
        time.sleep(12 if _COMEX else 0)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                linhas = json.loads(r.read())["data"]["list"]
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or tentativa == 5:
                raise
            time.sleep(30)
    campo = next((k for k in linhas[0] if k not in ("year", "monthNumber", "metricFOB") and
                  (k.endswith("Code") or k.lower().startswith("co"))), None) if linhas else None
    dados = {}
    for l in linhas:
        d = date(int(l["year"]), int(l["monthNumber"]), 1)
        dados.setdefault(d, {})[l[campo]] = float(l["metricFOB"])
    _COMEX[chave] = dados
    return dados


def serie_comex(cfg, n):
    """Soma, mês a mês, as partes da fórmula: cada parte tem fluxo, nível, códigos e sinal (+1 ou -1)."""
    total = {}
    for parte in cfg["partes"]:
        nivel = parte.get("nivel", "chapter")
        codigos = parte.get("codigos")
        dados = comex_consulta(parte["fluxo"], nivel, codigos if nivel != "chapter" else None, n + 2)
        for d, por_codigo in dados.items():
            v = sum(x for c, x in por_codigo.items() if not codigos or c in codigos)
            total[d] = total.get(d, 0) + parte.get("sinal", 1) * v
    ultimo = max(total)          # o mês corrente pode vir parcial ou vazio: usa só meses fechados presentes
    return sorted((d, v) for d, v in total.items() if d <= ultimo)[-n:]


TT = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id="
_CACHE = {}


def recurso_tt(pacote, padrao, ultimo=True):
    """URL do recurso mais recente de um pacote do Tesouro Transparente cujo endereço contém o padrão."""
    rec = [r["url"] for r in baixar_json(TT + pacote)["result"]["resources"] if padrao in r["url"].lower()]
    return rec[-1] if ultimo else rec


def serie_rtn(cfg, n):
    """Linha da planilha do Resultado do Tesouro Nacional (R$ milhões, mensal)."""
    if "rtn" not in _CACHE:
        import openpyxl
        url = recurso_tt("resultado-do-tesouro-nacional", "seriehistorica")
        _CACHE["rtn"] = openpyxl.load_workbook(io.BytesIO(baixar(url, timeout=180)), read_only=True, data_only=True)
    linhas = list(_CACHE["rtn"][cfg["tabela"]].iter_rows(values_only=True))
    datas = next(l for l in linhas if l and sum(hasattr(c, "year") for c in l) > 3)
    alvo = next(l for l in linhas if l and l[0] and str(l[0]).strip().startswith(cfg["linha"]))
    pontos = [(d.date().replace(day=1), float(v)) for d, v in zip(datas[1:], alvo[1:])
              if hasattr(d, "year") and isinstance(v, (int, float))]
    return sorted(pontos)[-n:]


def serie_fpm(n):
    """FPM pago aos municípios por mês (R$): aba FPM da planilha consolidada de transferências do Tesouro."""
    import openpyxl
    url = recurso_tt("transferencias-obrigatorias-da-uniao", "consolidados")
    wb = openpyxl.load_workbook(io.BytesIO(baixar(url, timeout=240)), read_only=True, data_only=True)
    linhas = list(wb["FPM"].iter_rows(values_only=True))
    k = next(k for k, l in enumerate(linhas) if l and sum(hasattr(c, "year") for c in l) > 3)
    datas = linhas[k]
    soma = {}
    for l in linhas[k + 1:]:
        if not l or not isinstance(l[1], str) or len(l[1].strip()) != 2:   # só as linhas de UF
            continue
        for d, v in zip(datas, l):
            if hasattr(d, "year") and isinstance(v, (int, float)):
                m = date(d.year, d.month, 1)
                soma[m] = soma.get(m, 0) + float(v)
    return sorted((m, v) for m, v in soma.items() if v)[-n:]


def serie_finame(cfg, n):
    url = "https://dadosabertos.bndes.gov.br/api/3/action/package_show?id=desembolsos-finame"
    url = next(r["url"] for r in baixar_json(url)["result"]["resources"] if "mensal" in r["url"])
    pontos = []
    for l in csv.DictReader(io.StringIO(baixar(url, timeout=120).decode("utf-8-sig")), delimiter=";"):
        v = sum(float(l[c].replace(",", ".")) for c in cfg["campos"])
        pontos.append((date(int(l["ano"]), int(l["mes"]), 1), v))
    return sorted(pontos)[-n:]


def serie_capag(cfg):
    """Capag: estados com nota A ou B (contagem) ou municípios com nota A ou B (% dos classificados)."""
    if cfg["esfera"] == "estados":
        pontos = []
        for url in recurso_tt("capag-estados", "capagdosestados", ultimo=False)[-2:]:
            ano = re.findall(r"(20\d\d)", url)
            linhas = list(csv.reader(io.StringIO(baixar(url).decode("latin-1")), delimiter=";"))
            i = next(k for k, c in enumerate(linhas[0]) if "CAPAG" in c.upper())
            notas = [l[i].strip().upper() for l in linhas[1:] if len(l) > i]
            pontos.append((date(int(ano[-1]) if ano else agora().year, 12, 1), sum(x[:1] in ("A", "B") for x in notas)))
        return sorted(pontos)
    import openpyxl
    urls = recurso_tt("capag-municipios", "capag-municipios", ultimo=False)
    por_ano = {}
    for url in urls:                       # o último arquivo de cada ano
        ano = re.findall(r"(20\d\d)", url.rsplit("/", 1)[1])
        if ano:
            por_ano[int(ano[0])] = url
    pontos = []
    for ano in sorted(por_ano)[-2:]:
        wb = openpyxl.load_workbook(io.BytesIO(baixar(por_ano[ano], timeout=180)), read_only=True, data_only=True)
        linhas = list(wb[wb.sheetnames[0]].iter_rows(values_only=True))
        cab = next(k for k, l in enumerate(linhas) if l and "Nome_Município" in [str(c) for c in l])
        i = [str(c) for c in linhas[cab]].index("CAPAG")
        notas = [str(l[i]).strip().upper() for l in linhas[cab + 1:] if l and len(l) > i and l[i]]
        validas = [x for x in notas if x[:1] in ("A", "B", "C", "D")]
        pontos.append((date(ano, 12, 1), sum(x[:1] in ("A", "B") for x in validas) / len(validas) * 100))
    return sorted(pontos)


SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
UFS = [11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53]


def siconfi(rel, ano, periodo, anexo, uf):
    chave = ("siconfi", rel, ano, periodo, anexo, uf)
    if chave not in _CACHE:
        if rel == "rreo":
            url = (f"{SICONFI}rreo?an_exercicio={ano}&nr_periodo={periodo}&co_tipo_demonstrativo=RREO"
                   f"&no_anexo={anexo}&id_ente={uf}")
        else:
            url = (f"{SICONFI}rgf?an_exercicio={ano}&in_periodicidade=Q&nr_periodo={periodo}&co_tipo_demonstrativo=RGF"
                   f"&no_anexo={anexo}&co_esfera=E&co_poder=E&id_ente={uf}")
        for tentativa in range(5):          # a API limita o ritmo de pedidos: espaça e repete no bloqueio
            time.sleep(0.4)
            try:
                _CACHE[chave] = baixar_json(url, tentativas=1, timeout=90)["items"]
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or tentativa == 4:
                    raise
                time.sleep(20 * (tentativa + 1))
    return _CACHE[chave]


def siconfi_estados(metrica, ano, periodo):
    """Soma (ICMS) ou média ponderada pela RCL (pessoal, dívida) dos 27 estados; None se faltar algum estado."""
    num = den = 0.0
    for uf in UFS:
        if metrica == "investimentos_ano":     # investimentos liquidados no ano, até o bimestre (RREO, Anexo 1)
            it = siconfi("rreo", ano, periodo, "RREO-Anexo%2001", uf)
            v = next((x["valor"] for x in it if x["cod_conta"] == "Investimentos"
                      and x["coluna"].startswith("DESPESAS LIQUIDADAS ATÉ O BIMESTRE")), None)
            if v is None:
                return None
            num += v
            continue
        if metrica == "icms_12m":
            it = siconfi("rreo", ano, periodo, "RREO-Anexo%2003", uf)
            v = next((x["valor"] for x in it if x["conta"].strip().upper() == "ICMS"
                      and x["coluna"] == "TOTAL (ÚLTIMOS 12 MESES)"), None)
            if v is None:
                return None
            num += v
            continue
        anexo = "RGF-Anexo%2001" if metrica == "pessoal_rcl" else "RGF-Anexo%2002"
        it = siconfi("rgf", ano, periodo, anexo, uf)
        if metrica == "pessoal_rcl":
            pct = next((x["valor"] for x in it if x["cod_conta"] == "DespesaComPessoalTotal" and x["coluna"].startswith("%")), None)
            rcl = next((x["valor"] for x in it if x["cod_conta"] == "ReceitaCorrenteLiquidaLimiteLegal"), None)
        else:
            col = [x for x in it if x["coluna"].startswith("Até o")]
            pct = next((x["valor"] for x in col if x["cod_conta"] == "PercentualDaDCSobreARCL"), None)
            rcl = next((x["valor"] for x in col if x["cod_conta"] == "RGF2ReceitaCorrenteLiquida"), None)
        if pct is None or not rcl:
            return None
        num += pct * rcl
        den += rcl
    return num if metrica in ("icms_12m", "investimentos_ano") else num / den


def serie_siconfi(cfg):
    """Último período com os 27 estados publicados e o mesmo período do ano anterior."""
    rreo = cfg["metrica"] in ("icms_12m", "investimentos_ano")
    hoje = agora().date()
    for ano in (hoje.year, hoje.year - 1):
        for p in (range(6, 0, -1) if rreo else range(3, 0, -1)):
            fim = date(ano, p * (2 if rreo else 4), 1)
            if fim > hoje:
                continue
            atual = siconfi_estados(cfg["metrica"], ano, p)
            if atual is None:
                continue
            anterior = siconfi_estados(cfg["metrica"], ano - 1, p)
            return [(date(ano - 1, fim.month, 1), anterior), (fim, atual)] if anterior is not None else [(fim, atual)]
    raise ValueError("Siconfi sem período completo")


MESES_PT = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}
ANP = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/"
ANP_PRECOS = ("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/"
              "precos-revenda-e-de-distribuicao-combustiveis/shlp/mensal/mensal-brasil-desde-jan2013.xlsx")


def dias_no_mes(d):
    prox = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (prox - d).days


def serie_anp(cfg, n):
    """CSV mensal da ANP (ANO;MÊS;...;PRODUTO;valor), somado no Brasil. Meses futuros vêm zerados e são ignorados.
    'por_dia' divide pelo número de dias do mês (para mi bbl/dia ou mi m³/dia); 'fator' multiplica antes."""
    if cfg.get("preco"):
        import openpyxl
        if "anp_precos" not in _CACHE:
            _CACHE["anp_precos"] = list(openpyxl.load_workbook(io.BytesIO(baixar(ANP_PRECOS, timeout=180)),
                                                               read_only=True, data_only=True).active.iter_rows(values_only=True))
        linhas = _CACHE["anp_precos"]
        k = next(k for k, l in enumerate(linhas) if l and l[0] == "MÊS")
        i = list(linhas[k]).index("PREÇO MÉDIO REVENDA")
        pontos = [(l[0].date().replace(day=1), float(l[i])) for l in linhas[k + 1:]
                  if l and hasattr(l[0], "year") and l[1] == cfg["preco"] and isinstance(l[i], (int, float))]
        return sorted(pontos)[-n:]
    if cfg["arquivo"] not in _CACHE:
        _CACHE[cfg["arquivo"]] = baixar(ANP + cfg["arquivo"], timeout=240).decode("utf-8-sig", "ignore")
    soma = {}
    for l in csv.DictReader(io.StringIO(_CACHE[cfg["arquivo"]]), delimiter=";"):
        if cfg.get("produtos") and l["PRODUTO"].strip().upper() not in cfg["produtos"]:
            continue
        col = next(c for c in l if c and c.strip().upper() in ("PRODUÇÃO", "VENDAS"))
        d = date(int(l["ANO"]), MESES_PT[l["MÊS"].strip().upper()[:3]], 1)
        soma[d] = soma.get(d, 0) + float((l[col] or "0").replace(".", "").replace(",", ".") if "," in (l[col] or "") else (l[col] or 0))
    pontos = []
    for d, v in sorted(soma.items()):
        if v <= 0:
            continue
        v *= cfg.get("fator", 1)
        if cfg.get("por_dia"):
            v /= dias_no_mes(d)
        pontos.append((d, v))
    return pontos[-n:]


def serie_ons_carga(n):
    texto = baixar("https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/carga_energia_me/CARGA_MENSAL.csv",
                   timeout=120).decode("utf-8-sig")
    soma = {}
    for l in csv.DictReader(io.StringIO(texto), delimiter=";"):
        d = date(int(l["din_instante"][:4]), int(l["din_instante"][5:7]), 1)
        soma[d] = soma.get(d, 0) + float(l["val_cargaenergiamwmed"] or 0)
    return sorted((d, v) for d, v in soma.items() if v > 0)[-n:]


def serie_ons_eolica_solar(n):
    """Geração eólica + solar centralizada do SIN por mês (MWh), somando o balanço horário de energia do ONS."""
    soma = {}
    for ano in range(agora().year - 2, agora().year + 1):
        try:
            texto = baixar("https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/balanco_energia_subsistema_ho/"
                           f"BALANCO_ENERGIA_SUBSISTEMA_{ano}.csv", timeout=120).decode("utf-8-sig")
        except urllib.error.HTTPError:
            continue
        for l in csv.DictReader(io.StringIO(texto), delimiter=";"):
            if l["id_subsistema"].strip() != "SIN":
                continue
            d = date(int(l["din_instante"][:4]), int(l["din_instante"][5:7]), 1)
            soma[d] = soma.get(d, 0) + float(l["val_gereolica"] or 0) + float(l["val_gersolar"] or 0)
    meses = sorted(soma)
    if meses:                        # o mês corrente ainda está incompleto
        ult = meses[-1]
        if (ult.year, ult.month) == (agora().year, agora().month):
            soma.pop(ult)
    return sorted(soma.items())[-n:]


RENOVAVEIS = ("Solar", "Eólica", "Biomassa")


def serie_siga(cfg):
    """Capacidade instalada (MW) das usinas em operação, hoje e há 12 meses, pela data de entrada em operação."""
    if "siga" not in _CACHE:
        url = "https://dadosabertos.aneel.gov.br/api/3/action/package_show?id=siga-sistema-de-informacoes-de-geracao-da-aneel"
        url = next(r["url"] for r in baixar_json(url)["result"]["resources"] if r["format"].upper() == "CSV")
        _CACHE["siga"] = list(csv.DictReader(io.StringIO(baixar(url, timeout=300).decode("utf-8-sig", "ignore")), delimiter=";"))
    usinas = [u for u in _CACHE["siga"] if u["DscFaseUsina"].startswith("Opera")]
    base = max(u["DatGeracaoConjuntoDados"] for u in usinas)[:10]
    hoje = date(int(base[:4]), int(base[5:7]), 1)
    antes = date(hoje.year - 1, hoje.month, 1)

    def capacidade(ate, filtro):
        total = 0.0
        for u in usinas:
            if (u["DatEntradaOperacao"] or "9999") <= f"{ate:%Y-%m-%d}" and filtro(u):
                total += float((u["MdaPotenciaFiscalizadaKw"] or "0").replace(".", "").replace(",", ".")) / 1000
        return total
    renov = lambda u: any(f in (u["DscOrigemCombustivel"] or "") for f in RENOVAVEIS)
    if cfg["metrica"] == "total":
        f = lambda d: capacidade(d, lambda u: True)
    elif cfg["metrica"] == "renovavel":
        f = lambda d: capacidade(d, renov)
    else:
        f = lambda d: capacidade(d, renov) / capacidade(d, lambda u: True) * 100
    return [(antes, f(antes)), (hoje, f(hoje))]


CAGED_PASTA = "1F89h6odTPGIGMb9eDiJKCute9W89QmqN"   # pasta "Tabelas" do Novo Caged no Google Drive do MTE
MESES_EXTENSO = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def drive_itens(pasta):
    """[(id, nome)] de uma pasta pública do Google Drive, pela visão incorporada (não exige chave)."""
    html = baixar(f"https://drive.google.com/embeddedfolderview?id={pasta}", timeout=60).decode("utf-8", "ignore")
    return re.findall(r'id="entry-([^"]+)".*?flip-entry-title">([^<]*)', html, re.S)


def caged_planilha():
    """Planilha de tabelas do mês mais recente: pasta do ano mais recente > pasta AAAAMM mais recente > xlsx."""
    if "caged" not in _CACHE:
        import openpyxl
        ano = max((n, i) for i, n in drive_itens(CAGED_PASTA) if re.fullmatch(r"\d{4}", n.strip()))[1]
        mes = max((n, i) for i, n in drive_itens(ano) if re.fullmatch(r"\d{6}", n.strip()))[1]
        arq = next(i for i, n in drive_itens(mes) if "tabela" in n.lower() and n.lower().endswith(".xlsx"))
        dados = baixar(f"https://drive.google.com/uc?export=download&id={arq}", timeout=300)
        if dados[:2] != b"PK":   # às vezes o Drive devolve a página de aviso no lugar do arquivo
            dados = baixar(f"https://drive.usercontent.google.com/download?id={arq}&export=download&confirm=t", timeout=300)
        _CACHE["caged"] = openpyxl.load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
    return _CACHE["caged"]


def serie_caged(cfg, n):
    """Estoque mensal de empregos formais de um grupamento ou seção CNAE (linha da Tabela 6.1)."""
    linhas = list(caged_planilha()["Tabela 6.1"].iter_rows(max_row=40, values_only=True))
    k = next(k for k, l in enumerate(linhas) if any(isinstance(c, str) and re.fullmatch(r"\w+/\d{4}", c.strip()) for c in l))
    meses, sub = linhas[k], linhas[k + 1]
    rotulo_linha = lambda l: next((str(c).strip() for c in l if c is not None), "")
    alvo = next(l for l in linhas[k + 2:] if l and rotulo_linha(l).startswith(cfg["linha"]))
    pontos = []
    for j, c in enumerate(meses):
        if isinstance(c, str) and "/" in c and str(sub[j]).strip().lower() == "estoque" and isinstance(alvo[j], (int, float)):
            nome, ano = c.strip().lower().split("/")
            nome = nome.replace("ç", "c")
            if nome in MESES_EXTENSO:
                pontos.append((date(int(ano), MESES_EXTENSO.index(nome) + 1, 1), float(alvo[j])))
    return sorted(pontos)[-n:]


ANATEL = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acessos/"


class ArquivoRemoto(io.RawIOBase):
    """Arquivo na web lido por partes (HTTP Range): o zipfile só busca o índice e o arquivo pedido."""
    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        self.tam = int(urllib.request.urlopen(req, timeout=60).headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, desloc, origem=0):
        self.pos = desloc if origem == 0 else self.pos + desloc if origem == 1 else self.tam + desloc
        return self.pos

    def readinto(self, b):
        if self.pos >= self.tam or not len(b):
            return 0
        fim = min(self.pos + len(b), self.tam) - 1
        req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0", "Range": f"bytes={self.pos}-{fim}"})
        dados = urllib.request.urlopen(req, timeout=120).read()
        b[:len(dados)] = dados
        self.pos += len(dados)
        return len(dados)


def anatel_meses(arquivo):
    """{AAAA-MM: (cabeçalho, linhas)} dos arquivos *_Colunas.csv do zip da Anatel (um ano e o anterior)."""
    chave = "col_" + arquivo
    if chave not in _CACHE:
        import zipfile
        z = zipfile.ZipFile(io.BufferedReader(ArquivoRemoto(ANATEL + arquivo + ".zip"), buffer_size=1 << 20))
        ano = agora().year
        meses = {}
        for i in z.infolist():
            if i.filename.endswith("_Colunas.csv") and any(str(a) in i.filename for a in (ano - 1, ano)):
                bruto = z.read(i.filename)
                try:
                    texto = bruto.decode("utf-8-sig")
                except UnicodeDecodeError:           # alguns arquivos da Anatel vêm em latin-1
                    texto = bruto.decode("latin-1")
                linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
                cab = linhas[0]
                for j, c in enumerate(cab):
                    if re.fullmatch(r"\d{4}-\d{2}", c.strip()):
                        meses[c.strip()] = (cab, linhas[1:], j)
        _CACHE[chave] = meses
    return _CACHE[chave]


def anatel_metrica(metrica, cab, linhas, j):
    col = lambda nome: next(k for k, c in enumerate(cab) if normalizar(c).strip() == nome)
    num = lambda l: float(l[j]) if j < len(l) and l[j].strip() not in ("", "-") else 0.0
    if metrica == "fibra_pct":
        meio = col("meio de acesso")
        total = sum(num(l) for l in linhas)
        return sum(num(l) for l in linhas if l[meio].strip().lower() == "fibra") / total * 100
    if metrica == "municipios_5g":
        ger, mun = col("tecnologia geracao"), col("codigo ibge municipio")
        return float(len({l[mun] for l in linhas if l[ger].strip() == "5G" and num(l) > 0}))
    if metrica == "prestadoras_pp":
        porte, cnpj = col("porte da prestadora"), col("cnpj")
        return float(len({l[cnpj] for l in linhas if l[porte].strip().lower() == "pequeno porte" and num(l) > 0}))
    raise ValueError(f"métrica desconhecida: {metrica}")


def serie_anatel_col(cfg):
    """Mês mais recente e o mesmo mês do ano anterior de uma métrica calculada sobre os arquivos por município."""
    meses = anatel_meses(cfg["arquivo"])
    ult = max(meses)
    ant = f"{int(ult[:4]) - 1}{ult[4:]}"
    pontos = []
    for m in (ant, ult):
        if m in meses:
            cab, linhas, j = meses[m]
            pontos.append((date(int(m[:4]), int(m[5:]), 1), anatel_metrica(cfg["metrica"], cab, linhas, j)))
    return pontos


def serie_anatel(cfg, n):
    """Acessos totais por mês (Ano;Mês;Acessos) do arquivo de totais dentro do zip da Anatel."""
    import zipfile
    z = zipfile.ZipFile(io.BufferedReader(ArquivoRemoto(ANATEL + cfg["arquivo"] + ".zip"), buffer_size=1 << 16))
    texto = z.read(cfg["membro"]).decode("utf-8-sig", "ignore")
    pontos = []
    for l in list(csv.reader(io.StringIO(texto), delimiter=";"))[1:]:
        if len(l) >= 3 and l[0].isdigit() and l[1].isdigit():
            pontos.append((date(int(l[0]), int(l[1]), 1), float(l[-1])))
    return sorted(pontos)[-n:]


CNES_LEITOS = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/Leitos_SUS/Leitos_csv_{ano}.zip"


def cnes_totais(ano):
    """{competência: [leitos, leitos de UTI, estabelecimentos]} de um ano do CSV de leitos do CNES."""
    chave = f"cnes{ano}"
    if chave not in _CACHE:
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(baixar(CNES_LEITOS.format(ano=ano), timeout=180)))
        texto = z.read(z.namelist()[0]).decode("latin-1").lstrip("﻿").lstrip("ï»¿")
        sep = ";" if texto[:500].count(";") > texto[:500].count(",") else ","
        leitor = csv.DictReader(io.StringIO(texto), delimiter=sep)
        leitor.fieldnames = [c.strip().upper() for c in leitor.fieldnames]
        tot = {}
        for l in leitor:
            v = tot.setdefault(l["COMP"], [0, 0, 0])
            v[0] += int(l["LEITOS_EXISTENTES"] or 0)
            v[1] += int(l["UTI_TOTAL_EXIST"] or 0)
            v[2] += 1
        _CACHE[chave] = tot
    return _CACHE[chave]


TABNET_SIH = "http://tabnet.datasus.gov.br/cgi/"


def sih_mensal():
    """{mês: (internações, dias de permanência)} dos últimos 25 meses processados, consultando o TabNet."""
    if "sih" not in _CACHE:
        import urllib.parse
        pagina = baixar(TABNET_SIH + "deftohtm.exe?sih/cnv/nibr.def", timeout=120).decode("latin-1")
        arquivos = re.findall(r'VALUE="(nibr\d{4}\.dbf)"', pagina)[:25]
        campos = [("Linha", "Ano/mês_processamento"), ("Coluna", "--Não-Ativa--"),
                  ("Incremento", "Internações"), ("Incremento", "Dias_permanência")]
        campos += [("Arquivos", a) for a in arquivos] + [("SMunic", "TODAS_AS_CATEGORIAS__"), ("formato", "prn"), ("mostre", "Mostra")]
        req = urllib.request.Request(TABNET_SIH + "tabcgi.exe?sih/cnv/nibr.def",
                                     data=urllib.parse.urlencode(campos, encoding="latin-1").encode(),
                                     headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"})
        texto = urllib.request.urlopen(req, timeout=180).read().decode("latin-1")
        texto = texto.replace("&ccedil;", "c")
        meses = {}
        for nome, ano, inter, dias in re.findall(r'"(\w+)/(\d{4})";(\d+);(\d+)', texto):
            nome = normalizar(nome).strip()
            if nome in MESES_EXTENSO:
                meses[date(int(ano), MESES_EXTENSO.index(nome) + 1, 1)] = (float(inter), float(dias))
        _CACHE["sih"] = meses
    return _CACHE["sih"]


def serie_sih(cfg):
    """Últimos 12 meses e os 12 anteriores: 'internacoes' (soma) ou 'permanencia' (dias ÷ internações)."""
    m = sih_mensal()
    meses = sorted(m)
    pontos = []
    for fim in (len(meses) - 13, len(meses) - 1):
        janela = meses[fim - 11:fim + 1]
        if fim < 11 or len(janela) < 12:
            continue
        inter = sum(m[d][0] for d in janela)
        dias = sum(m[d][1] for d in janela)
        pontos.append((meses[fim], inter if cfg["metrica"] == "internacoes" else dias / inter))
    return pontos


def serie_cnes(cfg, n):
    """Série mensal de uma métrica do CNES: 'leitos', 'uti' ou 'estabelecimentos'."""
    k = ["leitos", "uti", "estabelecimentos"].index(cfg["metrica"])
    ano = agora().year
    pontos = {}
    for a in (ano - 1, ano):
        try:
            for comp, v in cnes_totais(a).items():
                pontos[date(int(comp[:4]), int(comp[4:6]), 1)] = float(v[k])
        except urllib.error.HTTPError:     # o arquivo do ano novo só aparece com a primeira competência
            continue
    return sorted(pontos.items())[-n:]


# ---------- cálculo ----------

def rotulo(d, freq):
    if freq == "anual":
        return str(d.year)
    if freq == "trimestral":
        return f"{(d.month - 1) // 3 + 1}T{d.year % 100:02d}"
    return f"{ABREV[d.month - 1]}/{d.year}"


MESES_HISTORICO = 27   # indicadores com visão por player: 2 anos de série + o trimestre equivalente do ano anterior


def calcular(cfg, historico=False):
    """Valor, variação e período do indicador; com historico=True, também a série mensal ou trimestral recente
    (usada pelo gráfico e pela comparação com os players no mesmo trimestre)."""
    con = cfg["conector"]
    freq = cfg.get("freq", "mensal")
    lag = DEFASAGEM[freq]
    precisa = 26 if (cfg.get("acumular_12m") or cfg.get("somar_12m")) else lag + 1
    if historico:
        precisa = max(precisa, MESES_HISTORICO if freq == "mensal" else 9)
    if con == "sgs":
        codigos = cfg["codigo"] if isinstance(cfg["codigo"], list) else [cfg["codigo"]]
        soma = {}
        for c in codigos:                      # lista de códigos: soma as séries (ex.: PF + PJ)
            for d, v in serie_sgs(c, precisa):
                soma[d] = soma.get(d, 0) + v
        pontos = sorted(soma.items())
        if cfg.get("acumulado_no_ano"):
            mensal = []
            for k, (d, v) in enumerate(pontos):
                antes = pontos[k - 1] if k else None
                if d.month == 1:
                    mensal.append((d, v))
                elif antes and antes[0].year == d.year and antes[0].month == d.month - 1:
                    mensal.append((d, v - antes[1]))
            pontos = mensal
        if cfg.get("dividir_por"):
            base = dict(serie_sgs(cfg["dividir_por"], precisa))
            pontos = [(d, v / base[d] * 100) for d, v in pontos if base.get(d)]
    elif con == "sidra":
        pontos = serie_sidra(cfg["consulta"], precisa, freq)
    elif con == "mpv":
        pontos = serie_mpv(cfg, precisa)
    elif con == "spi":
        pontos = serie_spi(precisa)
    elif con == "rtn":
        pontos = serie_rtn(cfg, precisa)
    elif con == "fpm":
        pontos = serie_fpm(precisa)
    elif con == "finame":
        pontos = serie_finame(cfg, precisa)
    elif con == "capag":
        pontos, lag = serie_capag(cfg), 1
    elif con == "siconfi":
        pontos, lag = serie_siconfi(cfg), 1
    elif con == "anp":
        pontos = serie_anp(cfg, precisa)
    elif con == "ons":
        pontos = serie_ons_eolica_solar(precisa) if cfg.get("metrica") == "eolica_solar" else serie_ons_carga(precisa)
    elif con == "siga":
        pontos, lag = serie_siga(cfg), 1
    elif con == "comex":
        pontos = serie_comex(cfg, precisa)
    elif con == "sih":
        pontos, lag = serie_sih(cfg), 1
    elif con == "cnes":
        pontos = serie_cnes(cfg, precisa)
    elif con == "anatel_col":
        pontos, lag = serie_anatel_col(cfg), 1
    elif con == "anatel":
        pontos = serie_anatel(cfg, precisa)
    elif con == "caged":
        pontos = serie_caged(cfg, precisa)
    elif con == "ifdata":
        pontos, lag = serie_ifdata(cfg["metrica"]), 1
    else:
        raise ValueError(f"conector desconhecido: {con}")
    if not pontos:
        raise ValueError("a fonte não devolveu valores para o período")
    if cfg.get("acumular_12m"):
        def acumulado(fim):
            fator = 1.0
            for _, v in pontos[fim - 11:fim + 1]:
                fator *= 1 + v / 100
            return (fator - 1) * 100
        atual = acumulado(len(pontos) - 1)
        anterior = acumulado(len(pontos) - 13) if len(pontos) >= 24 else None
    elif cfg.get("somar_12m"):
        por_data = dict(pontos)
        fim = pontos[-1][0]
        def janela(ultimo):
            meses = [date(ultimo.year - (ultimo.month - k <= 0), (ultimo.month - k - 1) % 12 + 1, 1) for k in range(12)]
            return sum(por_data[m] for m in meses) if all(m in por_data for m in meses) else None
        atual = janela(fim)
        if atual is None:
            raise ValueError("faltam meses para somar 12 meses")
        anterior = janela(date(fim.year - 1, fim.month, 1))
    else:
        atual = pontos[-1][1]
        anterior = pontos[-1 - lag][1] if len(pontos) > lag else None
    escala = cfg.get("escala", 1)
    if not cfg.get("acumular_12m"):
        atual /= escala
        anterior = anterior / escala if anterior is not None else None
    var = None
    if anterior is not None:
        var = (atual - anterior) if cfg["var"] in ("pp", "abs") else ((atual / anterior - 1) * 100 if anterior else None)
    d = pontos[-1][0]
    if con == "siconfi":
        per = f"{d.month // 2}º bim/{d.year}" if cfg["metrica"] in ("icms_12m", "investimentos_ano") else f"{d.month // 4}º quadr/{d.year}"
        return atual, var, per, None
    serie = None
    if historico and freq in ("mensal", "trimestral") and not cfg.get("acumular_12m") and lag:
        # pontos brutos do período (no somar_12m, o mês, não a soma de 12 meses), na mesma escala do valor exibido
        serie = {"freq": freq, "somado12m": bool(cfg.get("somar_12m")),
                 "pontos": [[p.strftime("%Y-%m"), float(f"{v / escala:.5g}")] for p, v in pontos[-(MESES_HISTORICO if freq == "mensal" else 9):]]}
    return atual, var, rotulo(d, freq), serie


def arredondar(v):
    return round(v, 0 if abs(v) >= 100 else 1 if abs(v) >= 10 else 2)


def main():
    series = ler_json(CONFIG / "indicadores_fontes.json")["series"]
    caminho = DADOS / "indicadores.json"
    segmentos = ler_json(caminho)
    # indicadores com visão por player (config/indicadores_players.json) guardam a série recente
    nome_seg = {s["id"]: s["segmento"] for s in segmentos}
    com_historico = {(nome_seg.get(p["segmento"]), p["indicador"])
                     for p in ler_json(CONFIG / "indicadores_players.json")["pontes"]}
    indice = {(s["segmento"], i["nome"]): i for s in segmentos for i in s["indicadores"]}
    ok = falhas = 0
    relatorio = []
    for cfg in series:
        alvo = indice.get((cfg["segmento"], cfg["indicador"]))
        if not alvo:
            log(f"  não encontrado no portal: {cfg['segmento']} / {cfg['indicador']}")
            falhas += 1
            continue
        try:
            valor, var, periodo, serie = calcular(cfg, (cfg["segmento"], cfg["indicador"]) in com_historico)
        except Exception as e:
            log(f"  falha em {cfg['indicador']}: {str(e)[:100]}")
            relatorio.append({"indicador": cfg["indicador"], "segmento": cfg["segmento"], "conector": cfg["conector"],
                              "situacao": "falha", "erro": str(e)[:150]})
            falhas += 1
            continue
        relatorio.append({"indicador": cfg["indicador"], "segmento": cfg["segmento"], "conector": cfg["conector"],
                          "situacao": "ok"})
        alvo.update({"valor": arredondar(valor), "periodo": periodo, "status": "real",
                     "atualizadoEm": agora().strftime("%Y-%m-%d")})
        if var is not None:
            alvo["var"] = round(var, 1)
        alvo["varPP"] = cfg["var"] == "pp"           # o site mostra "p.p." ou "%" conforme este campo
        if cfg["var"] == "abs":
            alvo["varUnidade"] = cfg["var_unidade"]
        if cfg.get("equivalente"):
            alvo["equivalente"] = cfg["equivalente"]
        if serie:
            alvo["historico"] = serie
        ok += 1
    gravar_json(caminho, segmentos)
    gravar_json(CONFIG.parent / "relatorio_indicadores.json",
                {"executadoEm": agora().strftime("%Y-%m-%d %H:%M"), "ok": ok, "falhas": falhas, "series": relatorio})
    log(f"Indicadores: {ok} atualizados com a fonte, {falhas} com falha")
    registrar_atualizacao("indicadores")


if __name__ == "__main__":
    main()
