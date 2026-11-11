"""Publica a aba Cenário 2027 (menu Mercado) no portal.

Os cenários (pessimista, base, otimista), as fontes e os textos de efeito na empresa são escritos pela equipe num
arquivo fora deste repositório (que é público). Este script atualiza na hora os números com API (atualizar_cenario.py)
e grava tudo na seção "cenario" do Supabase. Depois, a rotina diária só troca a coluna Hoje e o Focus.

    python publicar_cenario.py "<arquivo cenario.json>" ["<cenario_textos.json>"]

O segundo arquivo (opcional) traz os textos "o que é", "implicação para as empresas" e "motivo" de cada cenário,
casados com os indicadores pelo nome (ver mesclar_textos).

Formato: {"titulo", "origem", "corte", "notaCenarios", "focusPre", "eleicao", "etapas": [{"n", "nome", "sub",
"linhas": [{"id", "indicador", "medida", "unidade", "casas", "hoje": {"valor", "nota", "data", "auto"},
"pess"|"base"|"otim": {"valor", "fonte"}, "focus", "efeito"}]}]}. Ver atualizar_cenario.py para o campo "auto".

Precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import re
import sys
from pathlib import Path

import atualizar_cenario
from comum import agora, ler_json, log
from supabase_api import exigir_configuracao, gravar_secao


def mesclar_textos(c, textos):
    """Junta os textos explicativos (cenario_textos.json) às linhas do cenário, casando "casa" (regex) com o indicador.

    Campos: oque, impacto (na linha), pess/base/otim.motivo (dentro de cada cenário) e extra_hoje (vira hoje.explicacao).
    Só acrescenta texto: valores, fontes e datas do arquivo da equipe não são alterados.
    """
    usados = set()
    for e in c["etapas"]:
        for l in e["linhas"]:
            for i, t in enumerate(textos):
                if re.search(t["casa"], l["indicador"], re.I):
                    usados.add(i)
                    for k in ("oque", "impacto"):
                        if t.get(k):
                            l[k] = t[k]
                    for k in ("pess", "base", "otim"):
                        if t.get(k) and l.get(k) is not None:
                            l[k]["motivo"] = t[k]["motivo"]
                    if t.get("extra_hoje"):
                        l["hoje"]["explicacao"] = t["extra_hoje"]
                    break
            else:
                log(f"textos: sem texto para o indicador '{l['indicador']}'")
    for i, t in enumerate(textos):
        if i not in usados:
            log(f"textos: '{t['casa']}' não casou com nenhum indicador")


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    exigir_configuracao()
    c = ler_json(Path(sys.argv[1]))
    if len(sys.argv) == 3:
        mesclar_textos(c, ler_json(Path(sys.argv[2])))
    if not c.get("etapas") or not all(l.get("id") and l.get("hoje") for e in c["etapas"] for l in e["linhas"]):
        sys.exit("Arquivo sem etapas ou com linha sem id/hoje.")
    erros = atualizar_cenario.atualizar(c)
    gravar_secao("cenario", c, agora().isoformat())
    log(f"Cenário publicado: {sum(len(e['linhas']) for e in c['etapas'])} indicadores ({erros} fonte(s) sem atualização).")


if __name__ == "__main__":
    main()
