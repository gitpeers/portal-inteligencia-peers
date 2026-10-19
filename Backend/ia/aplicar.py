"""Rotina de IA, passo 3: confere as respostas escritas pela IA e grava só os campos de texto nos dados do portal.

Não usa IA. Lê Backend/ia/trabalho/pendencias.json e respostas*.json (a IA pode escrever em partes).
Se alguma resposta não passar na conferência, nada é gravado e o script lista o que corrigir (saída 1).
Números, datas, links e classificações nunca são alterados aqui: só resumo, textos de análise e a marca de IA.

    python Backend/ia/aplicar.py
"""
import html
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comum import DADOS, RAIZ, agora, baixar, gravar_json, hoje_iso, ler_json, log  # noqa: E402

IA = Path(__file__).resolve().parent
TRABALHO = IA / "trabalho"
ESTADO = IA / "estado.json"
RELATORIO = RAIZ / "Backend" / "relatorio_ia.json"
ANALISES = DADOS / "analises.json"

# campo: (limite de caracteres, pode ficar vazio)
CAMPOS = {
    "radar": {"resumo": (350, False), "porQueImporta": (220, False), "anguloPeers": (240, True)},
    "movimentos": {"tese": (200, False), "leitura": (300, False)},
}
LIMITE_FINANCAS, LIMITE_INDICADORES, LIMITE_APROFUNDAMENTO = 480, 380, 420
# Concorrência: os campos de texto e duas escolhas fechadas (selo e offering afetada)
CAMPOS_CONCORRENCIA = {"fato": (300, False), "sinal": (240, False), "impacto": (300, False)}
SELOS = ("Ameaça", "Oportunidade", "Monitorar")
LEITURA_SEMANA = (3, 5, 300)   # mínimo e máximo de pontos, caracteres por ponto
# So what dos indicadores: quatro textos, as notícias citadas no "por que" e a frase fixa quando não há causa na fonte
CAMPOS_SOWHAT = {"oQue": 260, "porQue": 280, "impacto": 320, "oportunidade": 260}
SEM_CAUSA = "Causa não identificada nas fontes do portal."
MAX_FONTES_SOWHAT = 2
LIMITE_TITULO_FONTE, TRECHO = 160, (20, 400)   # fonte oficial: título da página e trecho copiado dela (mín., máx.)
NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
_PAGINAS = {}


def site_permitido(url, sites):
    """O endereço é de um dos sites oficiais (sem https e sem www; vale subdomínio e página abaixo do caminho)?"""
    u = urllib.parse.urlsplit(url)
    host = u.hostname or ""
    for s in sites:
        s_host, _, s_caminho = s.partition("/")
        # gov.br/<órgão> é só o portal federal: subdomínios de gov.br são estados e prefeituras, não a fonte
        dominio_ok = host in (s_host, "www." + s_host) if s_host == "gov.br" else (host == s_host or host.endswith("." + s_host))
        if dominio_ok and u.path.lstrip("/").startswith(s_caminho):
            return u.scheme == "https"
    return False


def so_letras(texto):
    """Minúsculas, sem acentos e só letras e números: compara o trecho com a página sem tropeçar em espaços,
    pontuação ou marcação."""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def trecho_na_pagina(url, trecho):
    """Abre a página e confere se o trecho está nela. Em PDF, confere só se o arquivo existe. Devolve o problema
    encontrado ou None."""
    if url not in _PAGINAS:
        try:
            _PAGINAS[url] = baixar(url, tentativas=2, timeout=40)
        except Exception as e:
            _PAGINAS[url] = e
    pagina = _PAGINAS[url]
    if isinstance(pagina, Exception):
        return f"não abriu ({str(pagina)[:60]})"
    if pagina[:5] == b"%PDF-":
        return None
    texto = pagina.decode("utf-8", "replace")
    texto = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", texto)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    return None if so_letras(trecho) in so_letras(texto) else "o trecho não está na página"


def numero(texto):
    """'1.234,5' → 1234.5; '2,6' → 2.6; '361.7' → 361.7."""
    t = texto.replace(".", "") if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", texto) else texto
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def numeros_permitidos(obj, saida=None):
    """Todos os números de uma pendência (valores e números dentro de textos), mais as conversões de milhões
    para bilhões, que são o arredondamento usual na escrita."""
    saida = set() if saida is None else saida
    if isinstance(obj, bool):
        return saida
    if isinstance(obj, (int, float)):
        saida.update({float(obj), abs(float(obj))})
        if abs(obj) >= 1000:
            saida.add(abs(float(obj)) / 1000)
    elif isinstance(obj, str):
        saida.update(n for n in (numero(m) for m in NUMERO.findall(obj)) if n is not None)
    elif isinstance(obj, dict):
        for v in obj.values():
            numeros_permitidos(v, saida)
    elif isinstance(obj, list):
        for v in obj:
            numeros_permitidos(v, saida)
    return saida


def numeros_estranhos(texto, permitidos):
    """Números do texto que não estão na pendência. Valem também os inteiros pequenos (contagens, meses) e os anos."""
    fora = []
    for m in NUMERO.findall(re.sub(r"\b[1-4]T\d{2}\b", "", texto)):
        x = numero(m)
        if x is None or (x.is_integer() and (x <= 12 or 1990 <= x <= 2035)):
            continue
        if not any(abs(x - a) <= max(0.051, abs(a) * 0.005) for a in permitidos):
            fora.append(m)
    return fora


def conferir_sowhat(erros, pend, resp):
    offerings = pend["referencia"]["offerings"]
    for chave, c in resp.get("sowhat", {}).items():
        item = pend.get("sowhat", {}).get(chave)
        onde = f"sowhat/{chave}"
        if not item:
            erros.append(f"{onde}: fora das pendências"); continue
        if not isinstance(c, dict) or set(c) != set(CAMPOS_SOWHAT) | {"fontes"}:
            erros.append(f"{onde}: os campos são exatamente {sorted(set(CAMPOS_SOWHAT) | {'fontes'})}"); continue
        for campo, limite in CAMPOS_SOWHAT.items():
            conferir_texto(erros, f"{onde}.{campo}", c[campo], limite, False)
        ids = {n["id"] for n in item["noticias"]}
        sites = (item.get("fonteOficial") or {}).get("sites", [])
        fontes, trechos = c["fontes"], []
        if not isinstance(fontes, list) or len(fontes) > MAX_FONTES_SOWHAT:
            erros.append(f"{onde}.fontes: lista de até {MAX_FONTES_SOWHAT} fontes"); fontes = []
        for k, f in enumerate(fontes):
            if isinstance(f, str):
                if f not in ids:
                    erros.append(f"{onde}.fontes[{k}]: {f} não está nas noticias deste indicador")
            elif isinstance(f, dict) and set(f) == {"url", "titulo", "trecho"} and all(isinstance(v, str) for v in f.values()):
                if not site_permitido(f["url"], sites):
                    erros.append(f"{onde}.fontes[{k}].url: precisa ser https e de um site de fonteOficial.sites {sites}")
                    continue
                conferir_texto(erros, f"{onde}.fontes[{k}].titulo", f["titulo"], LIMITE_TITULO_FONTE, False)
                if not TRECHO[0] <= len(f["trecho"].strip()) <= TRECHO[1]:
                    erros.append(f"{onde}.fontes[{k}].trecho: de {TRECHO[0]} a {TRECHO[1]} caracteres copiados da página")
                    continue
                problema = trecho_na_pagina(f["url"], f["trecho"])
                if problema:
                    erros.append(f"{onde}.fontes[{k}]: {problema}; corrija o trecho ou use \"{SEM_CAUSA}\"")
                else:
                    trechos.append(f["trecho"])
            else:
                erros.append(f'{onde}.fontes[{k}]: id de notícia ou {{"url", "titulo", "trecho"}} da fonte oficial')
        if not fontes and isinstance(c["porQue"], str) and c["porQue"].strip() != SEM_CAUSA:
            erros.append(f'{onde}.porQue: sem fonte, escreva exatamente "{SEM_CAUSA}"')
        elif fontes and isinstance(c["porQue"], str) and c["porQue"].strip() == SEM_CAUSA:
            erros.append(f"{onde}.porQue: com fonte, explique a causa que ela mostra")
        if isinstance(c["oportunidade"], str) and not any(c["oportunidade"].strip().startswith(o + ":") for o in offerings):
            erros.append(f"{onde}.oportunidade: comece pelo nome exato de uma offering seguido de dois-pontos")
        permitidos = numeros_permitidos(item)
        for campo in CAMPOS_SOWHAT:
            if isinstance(c[campo], str):
                # os números do "por que" também podem vir do trecho conferido na fonte oficial
                fora = numeros_estranhos(c[campo], permitidos | numeros_permitidos(trechos) if campo == "porQue" else permitidos)
                if fora:
                    erros.append(f"{onde}.{campo}: números que não estão nos dados deste indicador: {', '.join(fora)}")


def ler_respostas():
    total = {}
    for arq in sorted(TRABALHO.glob("respostas*.json")):
        for secao, itens in ler_json(arq).items():
            if isinstance(itens, list):        # concorrenciaSemana: lista de pontos, escrita de uma vez
                total[secao] = itens
            else:
                total.setdefault(secao, {}).update(itens)
    return total


def conferir_texto(erros, onde, valor, limite, vazio_ok):
    if not isinstance(valor, str):
        erros.append(f"{onde}: precisa ser texto"); return
    v = valor.strip()
    if not v and not vazio_ok:
        erros.append(f"{onde}: vazio")
    if len(v) > limite:
        erros.append(f"{onde}: {len(v)} caracteres (limite {limite})")
    if re.search(r"https?://|\n", v):
        erros.append(f"{onde}: sem links nem quebras de linha")


def gravar_concorrencia(resp):
    """Grava as análises dos movimentos dos concorrentes; os descartados somem do site, mas ficam guardados."""
    caminho = DADOS / "concorrencia.json"
    novos, descartes = resp.get("concorrencia", {}), resp.get("descartarConcorrencia", {})
    if not (novos or descartes):
        return 0
    dados = ler_json(caminho)
    for i in dados["itens"]:
        if i["id"] in novos:
            i.update({k: v.strip() for k, v in novos[i["id"]].items()})
            i["ia"] = True
        if i["id"] in descartes:
            i.update({"oculto": True, "motivoOculto": descartes[i["id"]].strip(), "ia": True})
    gravar_json(caminho, dados)
    return len(novos) + len(descartes)


def main():
    pend = ler_json(TRABALHO / "pendencias.json")
    resp = ler_respostas()
    if not resp:
        log("Nenhum arquivo de respostas em Backend/ia/trabalho."); sys.exit(1)
    erros = []

    for secao, campos in CAMPOS.items():
        validos = {i["id"] for i in pend.get(secao, [])}
        for id_, c in resp.get(secao, {}).items():
            if id_ not in validos:
                erros.append(f"{secao}/{id_}: id fora das pendências"); continue
            if not isinstance(c, dict) or set(c) - set(campos):
                erros.append(f"{secao}/{id_}: campos permitidos são {sorted(campos)}"); continue
            for campo, (limite, vazio_ok) in campos.items():
                if campo not in c:
                    erros.append(f"{secao}/{id_}: falta {campo}")
                else:
                    conferir_texto(erros, f"{secao}/{id_}.{campo}", c[campo], limite, vazio_ok)
    pendentes = {i["id"] for s in ("radar", "movimentos") for i in pend.get(s, [])}
    for id_, motivo in resp.get("descartar", {}).items():
        if id_ not in pendentes:
            erros.append(f"descartar/{id_}: id fora das pendências")
        else:
            conferir_texto(erros, f"descartar/{id_}", motivo, 160, False)
    for secao, limite in (("financas", LIMITE_FINANCAS), ("indicadores", LIMITE_INDICADORES),
                          ("aprofundamento", LIMITE_APROFUNDAMENTO)):
        validos = set(pend.get(secao, {}))
        for chave, texto in resp.get(secao, {}).items():
            if chave not in validos:
                erros.append(f"{secao}/{chave}: fora das pendências")
            else:
                conferir_texto(erros, f"{secao}/{chave}", texto, limite, False)
    validos_conc = {i["id"] for i in pend.get("concorrencia", [])}
    offerings = set(pend["referencia"]["offerings"])
    for id_, c in resp.get("concorrencia", {}).items():
        if id_ not in validos_conc:
            erros.append(f"concorrencia/{id_}: id fora das pendências"); continue
        permitidos = set(CAMPOS_CONCORRENCIA) | {"selo", "offering"}
        if not isinstance(c, dict) or set(c) != permitidos:
            erros.append(f"concorrencia/{id_}: os campos são exatamente {sorted(permitidos)}"); continue
        for campo, (limite, vazio_ok) in CAMPOS_CONCORRENCIA.items():
            conferir_texto(erros, f"concorrencia/{id_}.{campo}", c[campo], limite, vazio_ok)
        if c["selo"] not in SELOS:
            erros.append(f"concorrencia/{id_}.selo: use um de {SELOS}")
        if c["offering"] not in offerings:
            erros.append(f"concorrencia/{id_}.offering: use o nome exato de uma offering de referencia.offerings")
    for id_, motivo in resp.get("descartarConcorrencia", {}).items():
        if id_ not in validos_conc:
            erros.append(f"descartarConcorrencia/{id_}: id fora das pendências")
        else:
            conferir_texto(erros, f"descartarConcorrencia/{id_}", motivo, 160, False)
        if id_ in resp.get("concorrencia", {}):
            erros.append(f"concorrencia/{id_}: está em concorrencia e em descartarConcorrencia; escolha um")
    if "concorrenciaSemana" in resp:
        pontos = resp["concorrenciaSemana"]
        minimo, maximo, limite = LEITURA_SEMANA
        if "concorrenciaSemana" not in pend:
            erros.append("concorrenciaSemana: a leitura da semana não está nas pendências de hoje")
        elif not isinstance(pontos, list) or not minimo <= len(pontos) <= maximo:
            erros.append(f"concorrenciaSemana: uma lista de {minimo} a {maximo} textos")
        else:
            for k, ponto in enumerate(pontos):
                conferir_texto(erros, f"concorrenciaSemana[{k}]", ponto, limite, False)
    conferir_sowhat(erros, pend, resp)
    if erros:
        log("Respostas com problema (nada foi gravado):")
        for e in erros:
            print("  - " + e)
        sys.exit(1)

    # grava os campos de texto e marca o item como escrito pela IA
    contagem = {}
    for secao, arquivo in (("radar", "radar.json"), ("movimentos", "movimentos.json")):
        itens = ler_json(DADOS / arquivo)
        antes = len(itens)
        novos = resp.get(secao, {})
        descartes = resp.get("descartar", {})
        for i in itens:
            if i["id"] in novos:
                i.update({k: v.strip() for k, v in novos[i["id"]].items()})
                i["ia"] = True
            if i["id"] in descartes:      # sem relação com negócios: some do site, mas fica guardado
                i.update({"oculto": True, "motivoOculto": descartes[i["id"]].strip(), "ia": True})
        assert len(itens) == antes
        gravar_json(DADOS / arquivo, itens)
        contagem[secao] = sum(1 for i in itens if i["id"] in novos or i["id"] in descartes)

    analises = ler_json(ANALISES) if ANALISES.exists() else {"financas": {}, "indicadores": {}}
    for chave, texto in resp.get("financas", {}).items():
        analises["financas"][chave] = {"texto": texto.strip(), "periodo": pend["financas"][chave]["periodo"], "geradoEm": hoje_iso()}
    for chave, texto in resp.get("indicadores", {}).items():
        analises["indicadores"][chave] = {"texto": texto.strip(), "geradoEm": hoje_iso()}
    for chave, texto in resp.get("aprofundamento", {}).items():
        analises.setdefault("aprofundamento", {})[chave] = {"texto": texto.strip(), "geradoEm": hoje_iso()}
    if resp.get("concorrenciaSemana"):
        s_ = pend["concorrenciaSemana"]
        analises["concorrencia"] = {"pontos": [p.strip() for p in resp["concorrenciaSemana"]],
                                    "inicio": s_["inicio"], "fim": s_["fim"], "geradoEm": hoje_iso()}
    for chave, c in resp.get("sowhat", {}).items():
        item = pend["sowhat"][chave]
        noticias = {n["id"]: n for n in item["noticias"]}
        oficial = (item.get("fonteOficial") or {}).get("nome")
        # as fontes citadas vão copiadas: o Radar guarda só 30 dias, e o so what fica até o indicador mudar
        analises.setdefault("sowhat", {})[chave] = {
            **{k: c[k].strip() for k in CAMPOS_SOWHAT},
            "fontes": [{k: noticias[f].get(k) for k in ("manchete", "fonte", "data", "url")} if isinstance(f, str)
                       else {"manchete": f["titulo"].strip(), "fonte": f"{oficial}, fonte oficial", "data": hoje_iso(),
                             "url": f["url"], "oficial": True} for f in c["fontes"]],
            "buscouFonteOficial": bool(oficial), "base": item["base"], "geradoEm": hoje_iso()}
    gravar_json(ANALISES, analises)
    contagem["concorrencia"] = gravar_concorrencia(resp)
    contagem["sowhat"] = len(resp.get("sowhat", {}))
    contagem["concorrenciaSemana"] = 1 if resp.get("concorrenciaSemana") else 0
    contagem["financas"] = len(resp.get("financas", {}))
    contagem["indicadores"] = len(resp.get("indicadores", {}))
    contagem["aprofundamento"] = len(resp.get("aprofundamento", {}))

    # Finanças e Indicadores só contam como feitos quando todas as entradas pendentes foram respondidas
    estado = ler_json(ESTADO) if ESTADO.exists() else {"processadoEm": {}}
    faltando = {}
    for secao in ("financas", "indicadores", "aprofundamento"):
        if secao in pend:
            falta = sorted(set(pend[secao]) - set(resp.get(secao, {})))
            if falta:
                faltando[secao] = falta
            else:
                estado["processadoEm"][secao] = pend["atualizadoEm"][secao]
    gravar_json(ESTADO, estado)

    gravar_json(RELATORIO, {
        "executadoEm": agora().strftime("%Y-%m-%d %H:%M"),
        "escritos": contagem,
        "pendentesNaoRespondidos": {
            "radar": len(pend.get("radar", [])) - contagem["radar"],
            "movimentos": len(pend.get("movimentos", [])) - contagem["movimentos"],
            "concorrencia": len(pend.get("concorrencia", [])) - contagem["concorrencia"],
            "sowhat": len(pend.get("sowhat", {})) - contagem["sowhat"],
            **{k: len(v) for k, v in faltando.items()},
        },
        "descartados": resp.get("descartar", {}),
        "revisar": resp.get("revisar", {}),
    })
    log(f"Gravado: {contagem}" + (f"; ficaram sem resposta: {faltando}" if faltando else ""))


if __name__ == "__main__":
    main()
