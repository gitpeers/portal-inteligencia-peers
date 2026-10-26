"""Publica o dashboard de resultados trimestrais na aba Análises trimestrais do portal.

O HTML vai para a linha "trimestral" da tabela secoes do Supabase (a mesma regra de leitura dos dados do portal: só
quem fez login), nunca para o repositório, que é público. O portal só o baixa quando alguém abre a aba.

    python publicar_trimestral.py "<pasta do projeto de resultados>"               # publica agora
    python publicar_trimestral.py "<pasta do projeto de resultados>" --automatico  # só se mudou e se está na main

O modo --automatico é o da tarefa agendada no computador (ver README): publica só quando o projeto está na branch
main (o trabalho em andamento, em outras branches, não aparece no portal), quando o index.html terminou de ser gravado
há mais de 2 minutos e quando ele é diferente da versão já publicada.

Precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path

from comum import agora, log
from supabase_api import TRIMESTRAL, chamar, exigir_configuracao, gravar_secao

BRANCH_PUBLICADA = "main"
MINUTOS_SEM_EDICAO = 2


def branch_atual(projeto):
    cabeca = (projeto / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    return cabeca.rsplit("/", 1)[-1] if cabeca.startswith("ref:") else None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    automatico = "--automatico" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    projeto = Path(args[0])
    arquivo = projeto / "dashboard" / "index.html"
    if not arquivo.exists():
        sys.exit(f"Não encontrei {arquivo}.")
    if automatico:
        branch = branch_atual(projeto)
        if branch != BRANCH_PUBLICADA:
            return            # trabalho em andamento: não publica (silencioso, a tarefa roda a cada 15 minutos)
        if time.time() - arquivo.stat().st_mtime < MINUTOS_SEM_EDICAO * 60:
            return            # o build pode estar gravando o arquivo; tenta na próxima rodada
    html = arquivo.read_text(encoding="utf-8")
    if "<html" not in html[:2000].lower():
        sys.exit(f"{arquivo} não parece uma página HTML.")
    sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
    exigir_configuracao()
    if automatico:
        atual = chamar("GET", f"secoes?select=sha:conteudo->>sha&nome=eq.{TRIMESTRAL}")
        if atual and atual[0].get("sha") == sha:
            return            # nada novo
    gravado = datetime.fromtimestamp(arquivo.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
    gravar_secao(TRIMESTRAL, {"html": html, "sha": sha, "geradoEm": gravado, "branch": branch_atual(projeto)},
                 agora().isoformat())
    log(f"Publicado na aba Análises trimestrais: dashboard gerado em {gravado} ({len(html) / 1e6:.1f} MB).")


if __name__ == "__main__":
    main()
