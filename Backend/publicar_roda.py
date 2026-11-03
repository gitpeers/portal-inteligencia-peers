"""Publica a lista de empresas da Roda gigante (sub-aba de Oportunidades) no portal.

A lista fica na tabela protegida "conexoes" (linha "roda"), que só entrega dados a quem está em acesso_comercial.
Não vai para o repositório, que é público: as empresas da roda são confidenciais.

    python publicar_roda.py "<arquivo roda.json>"

O arquivo é uma lista de empresas, cada uma com o nome mostrado e as grafias que contam como citação:

    [{"nome": "Itaú", "nomes": ["Itaú Unibanco", "Itaú"]}, {"nome": "Fleury", "nomes": ["Fleury"]}]

Precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import json
import sys
from pathlib import Path

from comum import agora, log
from supabase_api import chamar, exigir_configuracao


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    arquivo = Path(sys.argv[1])
    if not arquivo.exists():
        sys.exit(f"Não achei {arquivo}.")
    players = json.loads(arquivo.read_text(encoding="utf-8"))
    for p in players:
        if not p.get("nome") or not p.get("nomes"):
            sys.exit(f"Cada empresa precisa de 'nome' e 'nomes': {p}")
    exigir_configuracao()
    conteudo = {"geradoEm": agora().strftime("%d/%m/%Y"), "players": players}
    chamar("POST", "conexoes?on_conflict=nome", [{"nome": "roda", "conteudo": conteudo, "atualizado_em": agora().isoformat()}],
           {"Prefer": "resolution=merge-duplicates,return=minimal"})
    log(f"Publicada a lista da Roda gigante: {len(players)} empresas.")


if __name__ == "__main__":
    main()
