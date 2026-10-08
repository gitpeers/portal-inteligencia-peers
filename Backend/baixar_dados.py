"""Baixa os dados do portal do Supabase para Frontend/dados, antes de os scripts trabalharem neles.

Os dados do portal ficam só no Supabase. Os scripts do Backend e a rotina de IA trabalham com arquivos: este
script cria esses arquivos a partir do Supabase e, no fim, enviar_dados.py devolve o resultado. Os arquivos de
Frontend/dados são temporários e não vão para o repositório (estão no .gitignore).

    python baixar_dados.py

Precisa das variáveis SUPABASE_URL e SUPABASE_SERVICE_KEY (ver supabase_api.py).
"""
from comum import DADOS, gravar_json, log
from supabase_api import exigir_configuracao, ler_secoes


def main():
    exigir_configuracao()
    secoes = ler_secoes()
    if not secoes:
        raise SystemExit("O Supabase não devolveu nenhuma seção: confira a URL, a chave e a tabela secoes.")
    DADOS.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in sorted(secoes.items()):
        gravar_json(DADOS / f"{nome}.json", conteudo)
    log(f"baixadas {len(secoes)} seções: {', '.join(sorted(secoes))}")


if __name__ == "__main__":
    main()
