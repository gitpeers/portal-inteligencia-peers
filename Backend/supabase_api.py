"""Acesso à tabela secoes do Supabase, onde ficam os dados do portal. Só usa a biblioteca padrão do Python.

Precisa das variáveis SUPABASE_URL e SUPABASE_SERVICE_KEY (no GitHub, pelos Secrets; na rotina de IA, nas
variáveis de ambiente da rotina; no computador, definidas no terminal). A chave é a secreta (service_role):
ela ignora as regras de acesso e nunca vai para a página nem para o repositório.
"""
import json
import os
import sys
import urllib.error
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_CHAVE = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
TABELA = "secoes"


def exigir_configuracao():
    if not (SUPABASE_URL and SUPABASE_CHAVE):
        sys.exit("Defina SUPABASE_URL e SUPABASE_SERVICE_KEY antes de rodar (ver README).")


def chamar(metodo, caminho, corpo=None, cabecalhos=None):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{caminho}", method=metodo,
        data=None if corpo is None else json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
        headers={
            "apikey": SUPABASE_CHAVE,
            "Authorization": f"Bearer {SUPABASE_CHAVE}",
            "Content-Type": "application/json",
            "User-Agent": "PortalInteligenciaPeers (atualizacao automatica)",
            **(cabecalhos or {}),
        })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            bruto = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase respondeu {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None
    return json.loads(bruto) if bruto else None


def ler_secoes():
    """Todas as seções: {nome: conteúdo}."""
    return {l["nome"]: l["conteudo"] for l in chamar("GET", f"{TABELA}?select=nome,conteudo")}


def gravar_secao(nome, conteudo, quando):
    """Grava uma seção, substituindo a versão anterior."""
    chamar("POST", f"{TABELA}?on_conflict=nome",
           [{"nome": nome, "conteudo": conteudo, "atualizado_em": quando}],
           {"Prefer": "resolution=merge-duplicates,return=minimal"})
