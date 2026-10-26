"""Publica o dashboard de resultados trimestrais na aba Análises trimestrais do portal.

O arquivo vai para o bucket privado "analises" do Supabase (ver Supabase/configuracao.sql, parte 5), nunca para o
repositório, que é público. O portal só o entrega a quem fez login. Rodar sempre que o dashboard for regerado:

    python Backend/publicar_trimestral.py "<pasta do projeto de resultados>/dashboard/index.html"

Precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY definidas no terminal (ver README).
"""
import sys
import urllib.error
import urllib.request
from pathlib import Path

from supabase_api import SUPABASE_CHAVE, SUPABASE_URL, exigir_configuracao

BUCKET, ARQUIVO = "analises", "trimestral.html"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    exigir_configuracao()
    origem = Path(sys.argv[1])
    conteudo = origem.read_bytes()
    if b"<html" not in conteudo[:2000].lower():
        sys.exit(f"{origem} não parece uma página HTML.")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ARQUIVO}", data=conteudo, method="POST",
        headers={"apikey": SUPABASE_CHAVE, "Authorization": f"Bearer {SUPABASE_CHAVE}",
                 "Content-Type": "text/html; charset=utf-8", "x-upsert": "true", "Cache-Control": "300"})
    try:
        with urllib.request.urlopen(req, timeout=120):
            pass
    except urllib.error.HTTPError as e:
        sys.exit(f"O Supabase recusou o envio ({e.code}): {e.read().decode('utf-8', 'replace')[:300]}")
    print(f"Publicado: {origem.name} ({len(conteudo) / 1e6:.1f} MB) na aba Análises trimestrais.")


if __name__ == "__main__":
    main()
