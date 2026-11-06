"""Guarda, para as empresas da Roda gigante, as notícias do Radar e os movimentos além da janela do portal.

O Radar guarda 30 dias e os movimentos cerca de 45; o quadro "No mercado" da Roda mostra 90. Este script roda todo dia
depois de enviar_dados.py: lê a linha protegida "roda" da tabela conexoes, separa os itens de hoje que citam alguma
empresa da lista e acrescenta ao arquivo da própria linha (conteudo.arquivo), apagando o que passou de 90 dias.

Os nomes das empresas são confidenciais e o log do GitHub Actions é público: o script só imprime contagens. A seleção
aqui é larga (a grafia aparece em qualquer lugar do item); o portal aplica a mesma regra das notícias ao mostrar.

    python arquivar_roda.py

Precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import json
import re
import unicodedata
from datetime import timedelta

from comum import DADOS, agora, ler_json, log
from supabase_api import chamar, exigir_configuracao

DIAS = 90
CAMPOS = {   # só o que o quadro usa
    "r": ["id", "data", "url", "fonte", "manchete", "resumo", "porQueImporta", "anguloPeers", "relevancia", "offering"],
    "m": ["id", "data", "url", "fonte", "player", "tese", "tipo", "valor", "leitura", "offering"],
}


def norm(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", t).strip() + " "


def itens(nome):
    caminho = DADOS / f"{nome}.json"
    dados = ler_json(caminho) if caminho.exists() else []
    if isinstance(dados, dict):
        dados = dados.get("itens", [])
    return dados or []


def main():
    exigir_configuracao()
    linha = chamar("GET", "conexoes?select=conteudo&nome=eq.roda")
    if not linha or not (linha[0].get("conteudo") or {}).get("players"):
        log("Roda gigante: sem lista publicada, nada a arquivar.")
        return
    conteudo = linha[0]["conteudo"]
    corte = (agora() - timedelta(days=DIAS)).strftime("%Y-%m-%d")
    fontes = {"r": itens("radar"), "m": itens("movimentos")}
    arquivo = conteudo.get("arquivo") or {}
    novos = 0
    for pl in conteudo["players"]:
        grafias = [g for g in {norm(x) for x in pl.get("nomes", []) + [pl.get("nome")]} if g.strip()]
        guardados = [x for x in arquivo.get(pl["nome"], []) if x.get("data", "") >= corte]
        vistos = {(x["k"], x.get("url") or x.get("id"), x.get("data")) for x in guardados}
        for k, lista in fontes.items():
            for it in lista:
                if it.get("data", "") < corte:
                    continue
                texto = norm(" ".join(str(it.get(c) or "") for c in CAMPOS[k]))
                if not any(g in texto for g in grafias):
                    continue
                chave = (k, it.get("url") or it.get("id"), it.get("data"))
                if chave in vistos:
                    continue
                vistos.add(chave)
                guardados.append({"k": k, **{c: it[c] for c in CAMPOS[k] if it.get(c) not in (None, "")}})
                novos += 1
        arquivo[pl["nome"]] = sorted(guardados, key=lambda x: x.get("data", ""), reverse=True)
    # empresas que saíram da lista não ficam no arquivo
    arquivo = {p["nome"]: arquivo.get(p["nome"], []) for p in conteudo["players"]}
    conteudo["arquivo"] = arquivo
    conteudo["arquivoEm"] = agora().strftime("%Y-%m-%d")
    chamar("PATCH", "conexoes?nome=eq.roda", {"conteudo": conteudo}, {"Prefer": "return=minimal"})
    log(f"Roda gigante: {novos} itens novos no arquivo, {sum(len(v) for v in arquivo.values())} no total ({DIAS} dias).")


if __name__ == "__main__":
    main()
