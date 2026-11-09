"""Publica a aba Cenário 2027 (menu Mercado) no portal.

Os cenários (pessimista, base, otimista), as fontes e os textos de efeito na empresa são escritos pela equipe num
arquivo fora deste repositório (que é público). Este script atualiza na hora os números com API (atualizar_cenario.py)
e grava tudo na seção "cenario" do Supabase. Depois, a rotina diária só troca a coluna Hoje e o Focus.

    python publicar_cenario.py "<arquivo cenario.json>"

Formato: {"titulo", "origem", "corte", "notaCenarios", "focusPre", "eleicao", "etapas": [{"n", "nome", "sub",
"linhas": [{"id", "indicador", "medida", "unidade", "casas", "hoje": {"valor", "nota", "data", "auto"},
"pess"|"base"|"otim": {"valor", "fonte"}, "focus", "efeito"}]}]}. Ver atualizar_cenario.py para o campo "auto".

Precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import sys
from pathlib import Path

import atualizar_cenario
from comum import agora, ler_json, log
from supabase_api import exigir_configuracao, gravar_secao


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    exigir_configuracao()
    c = ler_json(Path(sys.argv[1]))
    if not c.get("etapas") or not all(l.get("id") and l.get("hoje") for e in c["etapas"] for l in e["linhas"]):
        sys.exit("Arquivo sem etapas ou com linha sem id/hoje.")
    erros = atualizar_cenario.atualizar(c)
    gravar_secao("cenario", c, agora().isoformat())
    log(f"Cenário publicado: {sum(len(e['linhas']) for e in c['etapas'])} indicadores ({erros} fonte(s) sem atualização).")


if __name__ == "__main__":
    main()
