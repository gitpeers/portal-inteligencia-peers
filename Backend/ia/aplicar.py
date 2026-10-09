"""Rotina de IA, passo 3: confere as respostas escritas pela IA e grava só os campos de texto nos dados do portal.

Não usa IA. Lê Backend/ia/trabalho/pendencias.json e respostas*.json (a IA pode escrever em partes).
Se alguma resposta não passar na conferência, nada é gravado e o script lista o que corrigir (saída 1).
Números, datas, links e classificações nunca são alterados aqui: só resumo, textos de análise e a marca de IA.

    python Backend/ia/aplicar.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comum import DADOS, RAIZ, agora, gravar_json, hoje_iso, ler_json, log  # noqa: E402

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
    gravar_json(ANALISES, analises)
    contagem["concorrencia"] = gravar_concorrencia(resp)
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
            **{k: len(v) for k, v in faltando.items()},
        },
        "descartados": resp.get("descartar", {}),
        "revisar": resp.get("revisar", {}),
    })
    log(f"Gravado: {contagem}" + (f"; ficaram sem resposta: {faltando}" if faltando else ""))


if __name__ == "__main__":
    main()
