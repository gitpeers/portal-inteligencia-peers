"""Publica a base de clientes da Peers na visão comercial do portal (Time comercial e aba Conexões por empresa).

Lê "base clientes.xlsx" (a carteira de projetos, uma linha por projeto) e grava um resumo por cliente na tabela
"conexoes" do Supabase, linha "clientes". A tabela só entrega dados a quem está na lista de acesso comercial (ver
Supabase/comercial.sql). Nunca vai para o repositório, que é público.

Vai para o portal, por cliente: nome, status (ativo ou há quanto tempo terminou o último projeto), número de projetos,
o último projeto (nome, offering e mês de fim), as offerings já feitas e os responsáveis (líder de conta, N1 e MD do
último projeto). Ficam de fora o código e as datas exatas dos projetos. Propostas recusadas ou canceladas não contam.

    python publicar_clientes.py "<pasta Base de clientes>"

Precisa de openpyxl e de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import hashlib
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from comum import agora, log
from supabase_api import chamar, exigir_configuracao

ARQUIVO = "base clientes.xlsx"
# do mais recente ao mais antigo: o status do cliente é o do projeto mais recente
STATUS = ["Cliente ativo", "Finalizado até 6 meses", "Finalizado de 6 a 12 meses", "Finalizado há mais de 12 meses"]


def montar(arquivo):
    import openpyxl
    ws = openpyxl.load_workbook(arquivo, read_only=True, data_only=True).worksheets[0]
    linhas = ws.iter_rows(values_only=True)
    ix = {str(c).strip(): i for i, c in enumerate(next(linhas)) if c}
    g = lambda r, c: (str(r[ix[c]]).strip() if c in ix and r[ix[c]] is not None else "")
    projetos = {}
    for r in linhas:
        if not r or not g(r, "Cliente") or g(r, "IndFaseCRM") == "Recusada/Cancelada":
            continue
        inicio = r[ix["DataInicio"]] if isinstance(r[ix["DataInicio"]], datetime) else datetime.min
        projetos.setdefault(g(r, "Cliente"), []).append({
            "inicio": inicio, "projeto": g(r, "Projeto"), "offering": g(r, "OfferingMajoritaria"),
            "fim": g(r, "Mês/Ano Fim"), "status": g(r, "Status Cliente"), "lider": g(r, "LiderConta"),
            "n1": g(r, "N1Responsavel"), "md": g(r, "MDConta")})
    clientes = []
    for nome, ps in sorted(projetos.items(), key=lambda x: x[0].lower()):
        ps.sort(key=lambda p: p["inicio"], reverse=True)
        ultimo = ps[0]
        status = min((p["status"] for p in ps if p["status"] in STATUS), key=STATUS.index, default="")
        # responsáveis: os do último projeto; se faltar, o mais frequente nos outros projetos
        resp = lambda c: ultimo[c] or next((v for v, _ in Counter(p[c] for p in ps if p[c]).most_common(1)), "")
        offerings = [o for o, _ in Counter(p["offering"] for p in ps if p["offering"]).most_common()]
        clientes.append([nome, status, len(ps), ultimo["projeto"], ultimo["offering"], ultimo["fim"],
                         offerings, resp("lider"), resp("n1"), resp("md")])
    return clientes


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    arquivo = Path(sys.argv[1]) / ARQUIVO
    if not arquivo.exists():
        sys.exit(f"Não achei {arquivo}.")
    exigir_configuracao()
    clientes = montar(arquivo)
    gerado = datetime.fromtimestamp(arquivo.stat().st_mtime).strftime("%d/%m/%Y")
    conteudo = {"geradoEm": gerado, "sha": hashlib.sha256(arquivo.read_bytes()).hexdigest(),
                # [nome, status, projetos, último projeto, offering do último, fim do último (mm/aaaa),
                #  offerings já feitas, líder de conta, N1, MD]
                "clientes": clientes}
    chamar("POST", "conexoes?on_conflict=nome", [{"nome": "clientes", "conteudo": conteudo, "atualizado_em": agora().isoformat()}],
           {"Prefer": "resolution=merge-duplicates,return=minimal"})
    ativos = sum(1 for c in clientes if c[1] == STATUS[0])
    log(f"Publicada a base de clientes ({gerado}): {len(clientes)} clientes, {ativos} ativos.")


if __name__ == "__main__":
    main()
