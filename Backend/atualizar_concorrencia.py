"""Atualiza a seção Concorrência: movimentos estratégicos das consultorias concorrentes, a partir do Google Notícias.

Sem IA: o robô busca as notícias, filtra as que mostram um movimento do concorrente (aquisição, parceria, nova
oferta, liderança, risco...) e grava com os campos de análise vazios. A rotina de IA (Backend/ia/ROTINA.md)
escreve o fato, o sinal e o impacto para a Peers por cima.

A lista de concorrentes NÃO fica no repositório (que é público): vem da seção "concorrentes" do Supabase, baixada
por baixar_dados.py para Frontend/dados/concorrentes.json. As regras genéricas (tipos de movimento, filtros) ficam em
config/concorrencia_regras.json. Pelo mesmo motivo, o log só mostra contagens, nunca nomes nem manchetes.

    python Backend/atualizar_concorrencia.py
"""
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from comum import (CONFIG, DADOS, agora, baixar, gravar_json, identificador, ler_json, log, normalizar,
                   registrar_atualizacao)
from atualizar_noticias import _padrao, data_do_item, texto_limpo

JANELA_DIAS = 7           # coleta diária: o Google Notícias às vezes indexa com alguns dias de atraso
CARGA_INICIAL_DIAS = 180  # concorrente novo na lista: busca os últimos 6 meses de uma vez
VALIDADE_DIAS = 365       # histórico de 12 meses (mapa de parcerias e ficha do concorrente)
TETO_POR_CONCORRENTE = 40  # por rodada, para a rotina de IA dar conta
DIAS_MESMO_FATO = 7       # mesma parceria do mesmo concorrente em poucos dias = o mesmo fato em outro veículo
TIPOS_DE_FATO_UNICO = {"Resultados", "Risco e reputação", "Aquisição", "Fusão e combinação"}

GNEWS = "https://news.google.com/rss/search?"
EDICOES = {   # idioma da busca -> parâmetros do Google Notícias e escopo exibido no portal
    "pt": ({"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}, "Brasil"),
    "en": ({"hl": "en-US", "gl": "US", "ceid": "US:en"}, "Global"),
}
# palavras de movimento na própria busca: sem elas, os estudos e entrevistas ocupam os 100 resultados do Google
BUSCA_MOVIMENTO = {
    "pt": "(adquire OR compra OR aquisição OR parceria OR acordo OR aliança OR lança OR inaugura OR investe OR "
          "contrata OR nomeia OR sócio OR CEO OR demissões OR multa OR investigação OR receita)",
    "en": "(acquires OR acquisition OR partnership OR alliance OR launches OR opens OR invests OR appoints OR "
          "hires OR CEO OR layoffs OR fined OR probe OR lawsuit OR revenue)",
}


def buscar(termo, idioma, dias):
    params, _ = EDICOES[idioma]
    url = GNEWS + urllib.parse.urlencode({"q": f"({termo}) {BUSCA_MOVIMENTO[idioma]} when:{dias}d", **params})
    raiz = ET.fromstring(baixar(url, timeout=30))
    for it in raiz.iter("item"):
        fonte = (it.findtext("source") or "").strip()
        titulo = texto_limpo(it.findtext("title") or "")
        if fonte and titulo.endswith(" - " + fonte):          # o Google acrescenta " - Veículo" à manchete
            titulo = titulo[: -len(fonte) - 3].strip()
        yield {"titulo": titulo, "fonte": fonte or "Google Notícias", "link": it.findtext("link"),
               "quando": data_do_item(it.findtext("pubDate"))}


def tem(lista, texto_norm):
    return next((p for p in lista if _padrao(p).search(texto_norm)), None)


def posicao(palavras, texto_norm):
    """Posição da primeira palavra da lista no texto (ou None)."""
    achadas = [m.start() for p in palavras for m in [_padrao(p).search(texto_norm)] if m]
    return min(achadas) if achadas else None


def mencao(conc, titulo):
    """Grafia do concorrente citada na manchete (maiúsculas importam: uma sigla em maiúsculas não casa com a palavra comum)."""
    for nome in sorted(conc["nomes"], key=len, reverse=True):
        if re.search(r"(?<![\w&-])" + re.escape(nome) + r"(?![\w&-])", titulo):
            return nome
    return None


def tipo_do_movimento(t, p_nome, regras):
    """Risco vale com o nome em qualquer lugar; 'Cliente e projeto' quando a palavra vem antes do nome (a empresa
    contrata o concorrente); os demais quando a palavra vem depois do nome (o concorrente é o sujeito)."""
    for tipo, palavras in regras["tipos"].items():
        p = posicao(palavras, t)
        if p is None:
            continue
        if tipo == "Risco e reputação":
            return tipo
        if tipo == "Cliente e projeto":
            if p < p_nome and not re.search(r"(?:from|da|do|de) (?:the )?$", t[:p_nome]):
                return tipo   # "Empresa contrata X"; não "Empresa contrata executivo da X" (troca de emprego)
            continue
        depois = [m.start() for w in palavras for m in _padrao(w).finditer(t) if m.start() > p_nome]
        if depois:
            return tipo
    return None


def classificar(n, conc, regras, escopo):
    """Devolve (tipo, parceiros) se a manchete mostra um movimento do concorrente; senão None."""
    titulo = n["titulo"]
    nome = mencao(conc, titulo)
    if not nome:
        return None   # o nome só aparece no corpo da matéria: o concorrente não é o assunto
    t = normalizar(titulo)
    if tem(regras["excluir"], t) or any(x in titulo for x in conc.get("excluir", [])):
        return None
    if re.search(r"(?:\bex-|\bex |\bformer |\bfmr\.? )" + re.escape(nome), titulo, re.I):
        return None   # ex-funcionário do concorrente, não o concorrente
    p_nome = posicao([normalizar(nome).strip()], t)
    if p_nome is None:
        return None
    tipo = tipo_do_movimento(t, p_nome, regras)
    if not tipo:
        return None
    forte = tipo in regras["tipos_fortes"]
    if not forte and (tem(regras["estudo_ou_opiniao"], t) or re.match(re.escape(nome) + r"\s*:", titulo)):
        return None   # estudo, pesquisa ou opinião assinada pelo concorrente ("X: o mercado vai..."), não um movimento
    if escopo == "Global":
        if tipo not in regras["global_so_tipos"]:
            return None
        exige = regras["global_exige"].get(tipo)
        if exige and not tem(exige, t):
            return None   # nomeação regional ou escritório em outro país: pouco diz ao mercado brasileiro
    parceiros = sorted({p for p in regras["parceiros_tecnologia"]
                        if re.search(r"(?<![\w-])" + re.escape(p) + r"(?![\w-])", titulo)})
    parceiros = sorted({"AWS" if p == "Amazon Web Services" else ("NVIDIA" if p == "Nvidia" else p) for p in parceiros})
    return tipo, parceiros


def mesmo_fato(a, b):
    if a["concorrente"] != b["concorrente"] or a["tipo"] != b["tipo"]:
        return False
    if normalizar(a["manchete"])[:70] == normalizar(b["manchete"])[:70]:
        return True
    dias = abs((date.fromisoformat(a["data"]) - date.fromisoformat(b["data"])).days)
    if a["tipo"] in TIPOS_DE_FATO_UNICO and dias <= 3:
        return True   # resultado, multa ou aquisição noticiados por vários veículos nos mesmos dias
    return bool(a["parceiros"]) and a["parceiros"] == b["parceiros"] and dias <= DIAS_MESMO_FATO


def coletar(conc, regras, dias):
    limite = agora() - timedelta(days=dias)
    achados, vistos = [], set()
    falhas = 0
    for idioma, (_, escopo) in EDICOES.items():
        for termo in conc["buscar"]:
            try:
                noticias = list(buscar(termo, idioma, dias))
            except Exception:
                falhas += 1
                continue
            for n in noticias:
                if not n["link"] or not n["quando"] or n["quando"] < limite or n["link"] in vistos:
                    continue
                vistos.add(n["link"])
                c = classificar(n, conc, regras, escopo)
                if not c:
                    continue
                tipo, parceiros = c
                achados.append({
                    "id": identificador("c", n["link"]), "concorrente": conc["id"], "nome": conc["nome"],
                    "grupo": conc["grupo"], "tipo": tipo, "manchete": n["titulo"], "fonte": n["fonte"],
                    "url": n["link"], "data": n["quando"].strftime("%Y-%m-%d"), "escopo": escopo,
                    "parceiros": parceiros, "offering": regras["offering_por_tipo"].get(tipo, ""),
                    "fato": "", "sinal": "", "impacto": "", "selo": "", "ia": False,
                })
    achados.sort(key=lambda i: (i["data"], i["escopo"] == "Brasil"), reverse=True)   # no mesmo dia, a versão em português primeiro
    return achados[:TETO_POR_CONCORRENTE], falhas


def main():
    lista = DADOS / "concorrentes.json"
    if not lista.exists():
        log("Concorrência: lista de concorrentes não cadastrada no Supabase (seção 'concorrentes'); nada a fazer")
        return
    concorrentes = ler_json(lista)["concorrentes"]
    regras = ler_json(CONFIG / "concorrencia_regras.json")
    caminho = DADOS / "concorrencia.json"
    dados = ler_json(caminho) if caminho.exists() else {"itens": [], "carga": {}}

    antigos = dados["itens"]
    novos, falhas, cargas = [], 0, 0
    for conc in concorrentes:
        inicial = conc["id"] not in dados["carga"]
        achados, f = coletar(conc, regras, CARGA_INICIAL_DIAS if inicial else JANELA_DIAS)
        falhas += f
        for item in achados:
            if any(item["url"] == x["url"] or mesmo_fato(item, x) for x in antigos + novos):
                continue
            novos.append(item)
        if inicial and f < 2 * len(conc["buscar"]):   # só marca a carga feita se alguma busca respondeu
            dados["carga"][conc["id"]] = agora().strftime("%Y-%m-%d")
            cargas += 1

    corte = (agora() - timedelta(days=VALIDADE_DIAS)).strftime("%Y-%m-%d")
    ativos = {c["id"] for c in concorrentes}
    itens = [i for i in antigos + novos if i["data"] >= corte and i["concorrente"] in ativos]
    itens.sort(key=lambda i: i["data"], reverse=True)
    dados["itens"] = itens
    dados["carga"] = {k: v for k, v in dados["carga"].items() if k in ativos}
    gravar_json(caminho, dados)
    registrar_atualizacao("concorrencia")
    log(f"Concorrência: {len(concorrentes)} concorrentes ({cargas} com carga inicial), {len(novos)} movimentos novos, "
        f"{len(itens)} no histórico" + (f", {falhas} buscas sem resposta" if falhas else ""))


if __name__ == "__main__":
    main()
