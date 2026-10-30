"""Publica o Mapa de Conexões na visão comercial do portal (aba Relacionamentos).

Lê a versão mais recente de base_conexoes_peers_v<N>.xlsx na pasta Extração de Leads e grava na tabela "conexoes"
do Supabase (ver Supabase/comercial.sql), que só entrega os dados a quem está na lista de acesso comercial. Nunca vai
para o repositório, que é público.

Vai para o portal só o necessário para saber quem da Peers chega a cada empresa: executivo (nome, nível, vertical),
lead (nome, cargo, senioridade, link do LinkedIn), empresa, grupo e indústria. Ficam de fora e-mail, headline,
localização, a rede interna da Peers, as classificações comerciais (Verde e Azul, CRM, ABM) e o funil comercial.

    python publicar_conexoes.py "<pasta Extração de Leads>"               # publica agora
    python publicar_conexoes.py "<pasta Extração de Leads>" --automatico  # só se mudou (tarefa agendada)

O modo --automatico publica só quando a base mudou, não está aberta no Excel e foi salva há mais de 2 minutos.
Precisa de openpyxl e de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import hashlib
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from comum import agora, log
from supabase_api import chamar, exigir_configuracao

MINUTOS_SEM_EDICAO = 2
# a indústria da base mistura os nomes da Peers com as categorias do LinkedIn: tudo vira uma das indústrias do portal
INDUSTRIA = {
    "Varejo": ["varejo", "retail", "consumer goods", "bens de consumo", "wholesale", "personal care"],
    "Educação": ["educa", "education"],
    "Financial Services": ["financial", "meios de pagamento", "banking", "bancário", "bancario", "seguro", "insurance",
                           "investment", "venture capital"],
    "Health": ["health", "saúde", "saude", "hospital", "medical", "pharma", "biotech", "wellness"],
    "A&B + Agro": ["alimentos", "food", "agro", "farming"],
    "Manufacturing & Natural Resources": ["manufactur", "indústria", "industria", "aviation", "mineração", "mining", "metais"],
    "Power & Utilities": ["energia", "energy", "power", "utilities", "petróleo", "petroleo", "petroleum", "environmental"],
    "Transportes & Logística": ["transport", "logística", "logistica", "warehous", "travel"],
    "TI & Telecom": ["it services", "telecom", "data infrastructure", "technology", "software", "computer"],
}
ORDEM_SENIORIDADE = ["C-Level", "VP - Vice Presidente", "Superintendente", "Diretor/Head", "Gerente", "Coordenador",
                     "Especialista", "Analista", "Nao identificado"]


def industria_portal(valor):
    v = (valor or "").lower()
    return next((ind for ind, chaves in INDUSTRIA.items() if any(c in v for c in chaves)), "Outros")


def base_mais_recente(pasta):
    """base_conexoes_peers_v19.xlsx, v20...: a de maior número."""
    versoes = [(int(m.group(1)), p) for p in pasta.glob("base_conexoes_peers_v*.xlsx")
               if (m := re.fullmatch(r"base_conexoes_peers_v(\d+)\.xlsx", p.name, re.I))]
    return max(versoes)[1] if versoes else None


def montar(arquivo):
    import openpyxl
    ws = openpyxl.load_workbook(arquivo, read_only=True, data_only=True)["base_conexoes"]
    linhas = ws.iter_rows(values_only=True)
    ix = {c: i for i, c in enumerate(next(linhas)) if c}
    g = lambda r, c: (str(r[ix[c]]).strip() if c in ix and r[ix[c]] is not None else "")
    execs, empresas, leads = {}, {}, {}
    ind_empresa = {}
    relevante = {}    # empresa -> 1 (alvo ou porte relevante: aparece na lista) ou 0 (só aparece quando alguém busca)
    for r in linhas:
        if not r or not g(r, "executivo_peers") or r[ix["eh_rede_interna"]] is True:
            continue      # a rede interna (colegas e ex-colegas da Peers) fica fora, como no Mapa
        ex = g(r, "executivo_peers")
        execs.setdefault(ex, [ex.title(), g(r, "nivel"), g(r, "vertical")])
        emp = g(r, "empresa_padronizada") or g(r, "lead_empresa")
        if not emp:
            continue
        empresas.setdefault(emp, [emp, g(r, "grupo_holding")])
        ind_empresa.setdefault(emp, Counter())[industria_portal(g(r, "industria_alvo"))] += 1
        # até a v22 não há porte_relevante: tudo aparece; depois, só alvo e porte relevante (R$ 300 mi ou 500 funcionários)
        rel = 1 if g(r, "empresa_alvo") != "Não" or g(r, "porte_relevante") in ("", "Sim") else 0
        relevante[emp] = max(relevante.get(emp, 0), rel)
        chave = g(r, "lead_linkedin_url") or f'{g(r, "lead_nome")}|{emp}'
        lead = leads.setdefault(chave, {"nome": g(r, "lead_nome"), "cargo": g(r, "lead_cargo"),
                                        "senioridade": g(r, "senioridade"), "url": g(r, "lead_linkedin_url"),
                                        "empresa": emp, "execs": set()})
        lead["execs"].add(ex)
    lista_execs = sorted(execs)
    lista_emp = sorted(empresas)
    pos_ex = {e: i for i, e in enumerate(lista_execs)}
    pos_emp = {e: i for i, e in enumerate(lista_emp)}
    ordem = {s: i for i, s in enumerate(ORDEM_SENIORIDADE)}
    saida_leads = sorted(
        ([l["nome"], l["cargo"], l["senioridade"], l["url"], pos_emp[l["empresa"]], sorted(pos_ex[e] for e in l["execs"])]
         for l in leads.values()),
        key=lambda l: (l[4], -len(l[5]), ordem.get(l[2], 99), l[0]))
    return {
        "execs": [execs[e] for e in lista_execs],                      # [nome, nível, vertical]
        "empresas": [empresas[e] + [ind_empresa[e].most_common(1)[0][0], relevante[e]] for e in lista_emp],  # [nome, grupo, indústria, relevante]
        "leads": saida_leads,                                           # [nome, cargo, senioridade, url, empresa, [execs]]
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    automatico = "--automatico" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    arquivo = base_mais_recente(Path(args[0]))
    if not arquivo:
        sys.exit(f"Nenhuma base_conexoes_peers_v<N>.xlsx em {args[0]}.")
    if automatico:
        if (arquivo.parent / f"~${arquivo.name}").exists():
            return            # aberta no Excel: espera fechar
        if time.time() - arquivo.stat().st_mtime < MINUTOS_SEM_EDICAO * 60:
            return
    sha = hashlib.sha256(arquivo.read_bytes()).hexdigest()
    exigir_configuracao()
    if automatico:
        atual = chamar("GET", "conexoes?select=sha:conteudo->>sha&nome=eq.mapa")
        if atual and atual[0].get("sha") == sha:
            return            # nada novo
    dados = montar(arquivo)
    gerado = datetime.fromtimestamp(arquivo.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
    conteudo = {"versao": arquivo.stem.rsplit("_", 1)[-1], "geradoEm": gerado, "sha": sha, **dados}
    chamar("POST", "conexoes?on_conflict=nome", [{"nome": "mapa", "conteudo": conteudo, "atualizado_em": agora().isoformat()}],
           {"Prefer": "resolution=merge-duplicates,return=minimal"})
    log(f"Publicado o Mapa de Conexões {conteudo['versao']} ({gerado}): {len(dados['leads'])} leads, "
        f"{len(dados['empresas'])} empresas, {len(dados['execs'])} executivos.")


if __name__ == "__main__":
    main()
