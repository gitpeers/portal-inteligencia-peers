"""Publica a lista de empresas da Roda gigante (sub-aba de Oportunidades) no portal.

A lista fica na tabela protegida "conexoes" (linha "roda"), que só entrega dados a quem está em acesso_comercial.
Não vai para o repositório, que é público: as empresas da roda são confidenciais.

    python publicar_roda.py "<arquivo roda.json>" ["<arquivo pesquisa.json>"]

O arquivo é uma lista de empresas, cada uma com o nome mostrado e as grafias que contam como citação:

    [{"nome": "Itaú", "nomes": ["Itaú Unibanco", "Itaú"]}, {"nome": "Fleury", "nomes": ["Fleury"]}]

O segundo arquivo, opcional, é a pesquisa fora do portal das empresas sem notícia (RI, grupo controlador, Valor 1000 e mídia):
{"geradoEm": "05/11/2026", "empresas": [{"empresa", "capital_aberto", "nota", "itens": [{"origem", "titulo", "data",
"fonte", "url", "resumo"}]}]}. Sem ele, a pesquisa já publicada continua. O arquivo de 90 dias (arquivar_roda.py)
também continua.

Precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import json
import sys
from pathlib import Path

from comum import agora, log
from supabase_api import chamar, exigir_configuracao


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    arquivo = Path(sys.argv[1])
    if not arquivo.exists():
        sys.exit(f"Não achei {arquivo}.")
    players = json.loads(arquivo.read_text(encoding="utf-8"))
    for p in players:
        if not p.get("nome") or not p.get("nomes"):
            sys.exit(f"Cada empresa precisa de 'nome' e 'nomes': {p}")
    pesquisa = None
    if len(sys.argv) == 3:
        pesquisa = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        origens = {"ri", "grupo", "site", "valor1000", "midia"}
        for e in pesquisa.get("empresas", []):
            for it in e.get("itens", []):
                if it.get("origem") not in origens or not it.get("titulo") or not it.get("data"):
                    sys.exit(f"Item da pesquisa sem origem válida, título ou data: {it}")
    exigir_configuracao()
    atual = chamar("GET", "conexoes?select=conteudo&nome=eq.roda")
    antes = (atual[0].get("conteudo") or {}) if atual else {}
    conteudo = {"geradoEm": agora().strftime("%d/%m/%Y"), "players": players}
    for campo in ("arquivo", "arquivoEm", "pesquisa"):   # o que outros scripts gravam na mesma linha não se perde
        if campo in antes:
            conteudo[campo] = antes[campo]
    if pesquisa is not None:
        conteudo["pesquisa"] = pesquisa
    chamar("POST", "conexoes?on_conflict=nome", [{"nome": "roda", "conteudo": conteudo, "atualizado_em": agora().isoformat()}],
           {"Prefer": "resolution=merge-duplicates,return=minimal"})
    log(f"Publicada a lista da Roda gigante: {len(players)} empresas" +
        (f", pesquisa com {sum(len(e.get('itens', [])) for e in pesquisa.get('empresas', []))} itens." if pesquisa else "."))


if __name__ == "__main__":
    main()
