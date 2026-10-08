"""Funções compartilhadas pelos scripts de atualização do portal. Só usa a biblioteca padrão do Python."""
import gzip
import hashlib
import json
import re
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "Frontend" / "dados"
CONFIG = Path(__file__).resolve().parent / "config"
FUSO_BR = timezone(timedelta(hours=-3))


def agora():
    return datetime.now(FUSO_BR)


def hoje_iso():
    return agora().strftime("%Y-%m-%d")


def ler_json(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def gravar_json(caminho, obj):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def baixar(url, tentativas=3, timeout=40):
    """Baixa uma URL e devolve bytes; tenta de novo em caso de falha passageira."""
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (PortalInteligenciaPeers; atualizacao automatica)",
                "Accept-Encoding": "gzip",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                bruto = r.read()
            if bruto[:2] == b"\x1f\x8b":
                bruto = gzip.decompress(bruto)
            return bruto
        except Exception as e:  # rede instável: espera e tenta de novo
            erro = e
            time.sleep(3 * (i + 1))
    raise erro


def baixar_json(url, **kw):
    return json.loads(baixar(url, **kw).decode("utf-8"))


def normalizar(texto):
    """Minúsculas e sem acentos, para comparar com as palavras-chave."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " " + re.sub(r"\s+", " ", texto.lower()) + " "


def identificador(prefixo, texto):
    return prefixo + hashlib.sha1(texto.encode("utf-8")).hexdigest()[:10]


def registrar_atualizacao(chave):
    """Guarda em edicao.json quando cada tipo de dado foi atualizado pela última vez."""
    caminho = DADOS / "edicao.json"
    edicao = ler_json(caminho)
    edicao.setdefault("atualizadoEm", {})[chave] = agora().isoformat(timespec="minutes")
    gravar_json(caminho, edicao)


def log(msg):
    print(f"[{agora():%H:%M:%S}] {msg}", flush=True)
