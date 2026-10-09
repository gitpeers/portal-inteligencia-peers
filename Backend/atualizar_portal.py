"""Roda as atualizações do portal respeitando a cadência de cada tipo de dado.

Chamado todo dia pelo GitHub Actions. Cada tipo de dado só é atualizado quando passou o número de dias
definido em CADENCIA, contado pela data em Brasília (poupa chamadas às fontes). Uma rodada manual fora
do horário não faz a rodada das 6h do dia seguinte ser pulada. Use --forcar para atualizar tudo de uma vez.

    python Backend/atualizar_portal.py            # respeita a cadência
    python Backend/atualizar_portal.py --forcar   # atualiza tudo agora
"""
import sys
from datetime import datetime

import atualizar_agenda
import atualizar_concorrencia
import atualizar_financas
import atualizar_indicadores
import atualizar_noticias
from comum import DADOS, FUSO_BR, agora, ler_json, log

# dias de calendário (em Brasília) entre duas atualizações de cada tipo de dado
CADENCIA = {
    "noticias": 1,       # Radar e Movimentos: diária
    "agenda": 1,         # Agenda: diária (só tira o que passou e roda os eventos anuais)
    "indicadores": 30,   # Indicadores: mensal (as fontes publicam mensalmente ou com menos frequência)
    "financas": 7,       # Finanças: semanal (a CVM recebe os ITRs ao longo da temporada de resultados)
    "concorrencia": 1,   # Concorrência: diária (Google Notícias dos últimos 7 dias)
}
TAREFAS = {
    "noticias": atualizar_noticias.main,
    "agenda": atualizar_agenda.main,
    "indicadores": atualizar_indicadores.main,
    "financas": atualizar_financas.main,
    "concorrencia": atualizar_concorrencia.main,
}


def vencido(chave, ultimas):
    if chave not in ultimas:
        return True
    ultima = datetime.fromisoformat(ultimas[chave]).astimezone(FUSO_BR).date()
    return (agora().date() - ultima).days >= CADENCIA[chave]


def main():
    forcar = "--forcar" in sys.argv
    ultimas = ler_json(DADOS / "edicao.json").get("atualizadoEm", {})
    erros = 0
    for chave, tarefa in TAREFAS.items():
        if forcar or vencido(chave, ultimas):
            log(f"== {chave}")
            try:
                tarefa()
            except Exception as e:   # uma fonte fora do ar não impede as outras atualizações
                erros += 1
                log(f"ERRO em {chave}: {e}")
        else:
            log(f"== {chave}: ainda dentro da cadência, nada a fazer")
    sys.exit(1 if erros == len(TAREFAS) else 0)


if __name__ == "__main__":
    main()
