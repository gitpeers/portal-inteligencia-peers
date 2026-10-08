"""Envia os arquivos de Frontend/dados para o Supabase, de onde a página os lê depois do login.

Roda depois que os scripts do Backend ou a rotina de IA trabalharam nos arquivos (baixados antes por
baixar_dados.py). Também serve para carregar uma seção editada à mão.

    python enviar_dados.py --todos              # envia todas as seções
    python enviar_dados.py companhias_abertas   # envia só uma seção

Precisa das variáveis SUPABASE_URL e SUPABASE_SERVICE_KEY (ver supabase_api.py).
"""
import sys

from comum import DADOS, agora, ler_json, log
from supabase_api import exigir_configuracao, gravar_secao


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    exigir_configuracao()
    nomes = sorted(p.stem for p in DADOS.glob("*.json")) if args == ["--todos"] else args
    if not nomes:
        sys.exit(f"Nenhum arquivo em {DADOS}: rode baixar_dados.py antes.")
    for nome in nomes:
        caminho = DADOS / f"{nome}.json"
        if not caminho.exists():
            sys.exit(f"Arquivo não encontrado: {caminho}")
        gravar_secao(nome, ler_json(caminho), agora().isoformat())
        log(f"enviado: {nome}")


if __name__ == "__main__":
    main()
