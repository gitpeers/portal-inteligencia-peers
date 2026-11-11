"""Relatório do uso do portal (tabela uso_portal, ver Supabase/uso.sql): só contagens, sem pessoas.

    python relatorio_uso.py          # últimos 28 dias, por semana
    python relatorio_uso.py 7        # últimos 7 dias

Mostra, por semana: sessões, aberturas de cada aba (a Roda gigante e as outras visões de Oportunidades à parte),
briefings gerados de cada tipo, perfis e a parcela de sessões que passam por mais de 3 abas sem gerar nada (sinal de
quem procura e não acha). Precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from comum import agora
from supabase_api import chamar, exigir_configuracao

GERA = {"briefing", "briefing_conta", "briefing_concorrentes", "planilha_relacionamentos"}


def main():
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else 28
    exigir_configuracao()
    desde = (agora() - timedelta(days=dias)).isoformat()
    linhas, pagina = [], 0
    while True:
        lote = chamar("GET", f"uso_portal?select=em,evento,aba,detalhe,perfil,sessao&em=gte.{desde}&order=em"
                             f"&limit=1000&offset={pagina * 1000}")
        linhas += lote
        if len(lote) < 1000:
            break
        pagina += 1
    if not linhas:
        print(f"Nenhum registro nos últimos {dias} dias.")
        return
    semanas = defaultdict(list)
    for l in linhas:
        d = datetime.fromisoformat(l["em"].replace("Z", "+00:00")).astimezone(agora().tzinfo).date()
        semanas[d - timedelta(days=d.weekday())].append(l)
    for ini in sorted(semanas):
        ls = semanas[ini]
        sess = defaultdict(list)
        for l in ls:
            sess[l["sessao"]].append(l)
        abas = Counter((l["aba"] + (f" ({l['detalhe']})" if l["detalhe"] else "")) for l in ls if l["evento"] == "aba")
        gera = Counter(l["evento"] for l in ls if l["evento"] in GERA)
        perdidas = sum(1 for s in sess.values()
                       if len({l["aba"] for l in s if l["evento"] == "aba"}) > 3 and not any(l["evento"] in GERA for l in s))
        print(f"\n== Semana de {ini.strftime('%d/%m')} · {len(sess)} sessões")
        print("  perfis:", dict(Counter(s[0]["perfil"] for s in sess.values())))
        print("  abas:", ", ".join(f"{a} {n}" for a, n in abas.most_common()))
        print("  geraram:", dict(gera) or "nada")
        print(f"  sessões com mais de 3 abas e nada gerado: {perdidas} ({perdidas / len(sess):.0%})")


if __name__ == "__main__":
    main()
