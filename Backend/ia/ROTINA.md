# Rotina de IA do Portal de Inteligência Peers

Receita seguida pela rotina agendada do Claude, todo dia às 07h05 (Brasília), depois do robô das 6h.
O robô coleta e publica os dados, sem IA; esta rotina escreve as análises por cima e publica de novo.
Os dados do portal ficam só no Supabase: a rotina baixa os dados para arquivos, trabalha neles e devolve ao Supabase.
Quem for reproduzir a rotina só precisa apontar o agendamento para este arquivo (instruções no fim).

## Regras que valem sempre

- **Só texto.** Nunca altere números, datas, links, classificações ou arquivos de dados à mão. Os scripts gravam.
- **Só fatos das fontes.** Use o que está nos itens pendentes e conhecimento público geral. Não invente números,
  causas, valores de transação ou citações. Na dúvida, escreva menos.
- **Conteúdo de mercado apenas.** O portal exige login, mas qualquer pessoa da Peers o lê: nada de nomes de
  clientes, propostas, oportunidades comerciais ou conteúdo interno da Peers.
- **Repositório público.** Nunca envie ao repositório arquivos de `Frontend/dados` (os dados ficam só no Supabase)
  nem mostre ou grave as variáveis `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` em arquivos, mensagens ou no resumo.
- **Português do Brasil**, frases curtas e diretas, sem jargão vazio ("sinergias", "disruptivo") e sem exclamações.
- **Leitor:** consultores e sócios da Peers, que abrem o portal antes de uma reunião com cliente.
- Não cite consultorias concorrentes.

## Passo 1. Preparar

```
git pull origin main
python Backend/baixar_dados.py
python Backend/ia/preparar.py
```

`baixar_dados.py` traz os dados do Supabase para `Frontend/dados`. Se ele falhar (variáveis do Supabase ausentes ou
erro de acesso), encerre sem publicar e diga isso no resumo final.

- Saída **3** (robô ainda não terminou): aguarde 10 minutos (`sleep 600`) e rode de novo os dois comandos
  (`baixar_dados.py` e `preparar.py`), até 6 vezes.
  Se continuar 3, encerre sem publicar e diga isso no resumo final.
- Saída **4** (nada pendente): encerre sem publicar.
- Saída **0**: leia `Backend/ia/trabalho/pendencias.json` e siga.

## Passo 2. Escrever

Escreva as respostas em `Backend/ia/trabalho/respostas.json`. Com muitos itens, divida em partes
(`respostas_1.json`, `respostas_2.json`...): o script junta todas. Formato:

```json
{
  "radar":       { "<id>": { "resumo": "...", "porQueImporta": "...", "anguloPeers": "..." } },
  "movimentos":  { "<id>": { "tese": "...", "leitura": "..." } },
  "financas":    { "<Indústria>|<Divisão>": "..." },
  "indicadores": { "<id do segmento>": "..." },
  "descartar":   { "<id>": "motivo" },
  "revisar":     { "<id>": "motivo" }
}
```

Responda todos os itens de `radar` e `movimentos` (em `radar`/`movimentos` ou em `descartar`) e todas as chaves de `financas` e `indicadores` que vierem
nas pendências. Seções ausentes nas pendências ficam fora das respostas.

### Radar (cada notícia)

- **resumo** (até 350 caracteres): o fato em 2 ou 3 frases: quem, o quê, quanto e quando, com o que está na
  manchete e no trecho. Sem opinião.
- **porQueImporta** (até 220): uma frase sobre o efeito no setor: custo, demanda, regulação, concorrência ou risco.
- **anguloPeers** (até 240, pode ficar vazio): comece pelo nome exato de uma offering da lista em
  `referencia.offerings`, seguido de dois-pontos, e diga que trabalho a Peers poderia oferecer a quem é afetado.
  Ex.: `Strategy + M&A: avaliar alvos de consolidação entre seguradoras regionais com a nova regra de capital.`
  Se não houver ângulo claro, deixe `""` (o site esconde o campo). Melhor vazio que genérico.
- **descartar**: notícia sem relação com negócios (curiosidade, oferta de produto, acidente, esporte, lista de vagas,
  perfil pessoal, agenda política) vai para `descartar` com o motivo, e não para `radar`. O item some do site.
- **revisar**: notícia de negócios na indústria errada vai para `revisar` com o motivo, além de `radar`.
  O item continua no portal; a lista vai para o relatório.

### Movimentos (cada movimento)

- **tese** (até 200): uma frase com o player, o que fez e o objetivo aparente.
  Modelo: `<Player> compra a <empresa> para ampliar <oferta> em <mercado>.`
- **leitura** (até 300): o que o movimento revela sobre a aposta do player e qual offering da Peers se conecta,
  em uma ou duas frases. Não comente o que a notícia não informa (motivo, sucessor, valor): diga o que o fato mostra.
- Movimento que não é movimento de empresa (esporte, nota sem relação com o player) vai para `descartar`.

### Finanças (cada indústria e divisão, quando vier nas pendências; semanal)

Até 480 caracteres, 2 ou 3 frases: como a divisão foi no trimestre pela mediana (crescimento e margem; nos bancos,
ROE e lucro) e quem se destacou acima ou abaixo dela. Use só os números do arquivo, arredondados, com o período
(ex.: 2T26). Não explique causas que os números não mostram. Divisão com uma ou duas empresas: descreva as empresas.

### Indicadores (cada segmento, quando vier nas pendências; mensal)

Até 380 caracteres, 1 ou 2 frases: o que os indicadores dizem sobre o momento do segmento (crescimento, preço,
crédito, demanda), citando dois ou três valores com o período. Só os valores do arquivo.

### Sessão trimestral de Finanças (quando vier `releases` nas pendências)

Os releases do novo trimestre estão prontos. Para cada empresa em `releases.prontos`:

1. Abra o link do release.
2. Em `Backend/config/financas_releases.json`, atualize a empresa com os mesmos campos do trimestre anterior
   (`metr`, `fin`, `op`), com os números ajustados do release; guarde o link em `release` e, em `paginas`,
   a página de cada número de `metr` (ex.: `{"receita": 12, "ebitda": 14}`). Número não divulgado: `"n.d."`.
3. Quando todas as empresas prontas estiverem feitas, troque `periodo` para o novo trimestre e rode
   `python Backend/atualizar_financas.py`.

Empresas em `releases.faltam` continuam com o número contábil da CVM. Este é o único passo em que a IA escreve
números: copie exatamente o que está no release. A pessoa responsável confere uma amostra depois.

## Passo 3. Aplicar

```
python Backend/ia/aplicar.py
python Backend/enviar_dados.py --todos
```

O `aplicar.py` confere tamanhos, campos e ids, e só então grava nos arquivos. Se apontar problemas, corrija as
respostas e rode de novo. Nunca edite `radar.json`, `movimentos.json` ou `analises.json` à mão.
O `enviar_dados.py` devolve os dados ao Supabase: é a partir dele que o portal mostra as análises. Só rode depois
que o `aplicar.py` terminar sem problemas.

## Passo 4. Publicar

```
git add Backend/ia/estado.json Backend/relatorio_ia.json
git add Backend/config/financas_releases.json   # só na sessão trimestral
git commit -m "Análises de IA (DD/MM/AAAA)"
git pull --rebase origin main
git push origin main
```

Se o envio for recusado, repita `git pull --rebase origin main` e `git push`. Nunca use `--force`.
Os dados já foram para o Supabase no passo 3; o envio ao repositório guarda só o controle da rotina.

## Passo 5. Resumo final

Responda em até 5 linhas: quantos itens escreveu em cada seção, o que ficou para o dia seguinte, os itens em
`revisar` (com o título e o motivo de cada um) e qualquer falha. É aqui que quem acompanha a rotina vê o que precisa
de atenção.

---

## Como reproduzir a rotina (para quem for configurar)

1. Em claude.ai/code, conecte o GitHub e dê acesso de escrita ao repositório `gitpeers/portal-inteligencia-peers`.
2. Crie uma rotina agendada (Routines) nesse repositório, todo dia às 07h05 no fuso de Brasília.
3. No ambiente da rotina, cadastre as variáveis de ambiente `SUPABASE_URL` (URL do projeto no Supabase) e
   `SUPABASE_SERVICE_KEY` (chave service_role, em Supabase > Project Settings > API Keys). Sem elas a rotina não
   consegue baixar nem devolver os dados.
4. No pedido da rotina, escreva: `Siga as instruções de Backend/ia/ROTINA.md.`
5. Rode uma vez à mão e confira o relatório em `Backend/relatorio_ia.json` e as análises no portal.

A rotina usa a assinatura do Claude de quem a criou. Para mudar tom, limites ou tarefas, edite este arquivo:
a próxima execução já segue a versão nova. Mantenha só uma rotina ativa por vez: duas rotinas escrevendo as
mesmas análises entram em conflito.

**Ao passar a rotina para outra pessoa:** a nova pessoa cria a rotina dela (passos 1 a 5), confere que funcionou e
só então a anterior é desativada. Depois, gere uma nova chave service_role no Supabase e atualize-a nos dois lugares
que a usam: o Secret `SUPABASE_SERVICE_KEY` do GitHub e as variáveis de ambiente da rotina nova.
