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
- Não cite consultorias concorrentes, **exceto na seção Concorrência** (abaixo), que existe para acompanhá-las.

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
  "aprofundamento": { "<id do segmento>|<nome do indicador>": "..." },
  "descartar":   { "<id>": "motivo" },
  "revisar":     { "<id>": "motivo" },
  "concorrencia":          { "<id>": { "fato": "...", "sinal": "...", "impacto": "...", "selo": "...", "offering": "..." } },
  "descartarConcorrencia": { "<id>": "motivo" },
  "concorrenciaSemana":    [ "...", "...", "..." ],
  "concorrenciaBriefing":  { "sumario": ["...", "..."], "conclusao": ["...", "..."], "soWhat": "...",
                             "recomendacoes": [ { "tema": "...", "texto": "..." } ] },
  "sowhat":      { "<segmento>|<indicador>": { "oQue": "...", "porQue": "...", "fontes": ["<id>"], "impacto": "...", "oportunidade": "..." } }
}
```

Responda todos os itens de `radar` e `movimentos` (em `radar`/`movimentos` ou em `descartar`), todos os itens de
`concorrencia` (em `concorrencia` ou em `descartarConcorrencia`) e todas as chaves de `financas`, `indicadores`,
`aprofundamento` e `sowhat` que vierem nas pendências. Seções ausentes nas pendências ficam fora das respostas.

### Radar (cada notícia)

- **resumo** (até 350 caracteres): o fato em 2 ou 3 frases: quem, o quê, quanto e quando, com o que está na
  manchete e no trecho. Sem opinião. O resumo é lido em voz alta no podcast: ignore legenda de foto e crédito de
  imagem que venham no trecho (ex.: "Reprodução/BBC", "Arquivo Pessoal", "Daniel Corrá/g1").
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

### Concorrência (cada movimento de concorrente, quando vier `concorrencia` nas pendências)

A única seção em que se fala das consultorias concorrentes. O robô achou a notícia e marcou o tipo de movimento;
a IA diz o que aconteceu, o que o movimento revela e o que muda para a Peers. Em `referencia.concorrentes` está o
grupo de cada concorrente e as offerings em que ele disputa projetos com a Peers.

**Quem é a Peers, para o impacto.** Consultoria brasileira de estratégia, gestão e tecnologia (Peers Consulting +
Technology). Atua com as offerings de `referencia.offerings` e nas indústrias do portal (Financial Services, Varejo,
Health, Power & Utilities, A&B + Agro, Manufacturing & Natural Resources, TI & Telecom, Transportes & Logística,
Educação, Public Services). Disputa projetos com as estratégicas globais, as Big Four, as consultorias de tecnologia
e as consultorias brasileiras da lista.

- **fato** (até 300): o que aconteceu, em 1 ou 2 frases: quem, o quê, com quem, quanto e onde, só com o que a manchete
  e a fonte dizem. Se a matéria é de fora do Brasil, diga o país.
- **sinal** (até 240): o que o movimento revela sobre a aposta do concorrente (capacidade que compra, mercado que
  quer, oferta que empacota). Uma frase. Não invente motivos que a notícia não sustenta.
- **impacto** (até 300): o que muda para a Peers, em uma ou duas frases, terminando no que fazer. Ex.: `Reforça o
  concorrente em IA aplicada a bancos, onde a Peers disputa projetos de Analytics + IA; vale levar casos próprios de IA
  em produção às propostas de Financial Services.` Fale da Peers como empresa, sem nomes de clientes ou de pessoas
  da Peers, sem propostas em andamento e sem nada que não seja público.
- **selo**, um de três, pelo critério abaixo (sempre o mesmo, para o leitor confiar no selo):
  - `Ameaça`: o concorrente ganha capacidade, parceria, cliente ou presença numa offering ou indústria em que a Peers
    atua no Brasil (aquisição de consultoria, aliança com big tech, nova oferta, projeto ganho, centro aberto aqui).
  - `Oportunidade`: o movimento abre espaço para a Peers: problema de reputação, multa, investigação, conflito de
    independência (auditoria × consultoria), saída de mercado, cortes ou perda de sócios.
  - `Monitorar`: movimento relevante, mas sem efeito direto agora (nomeação, resultado financeiro, movimento só em
    outro país).
- **offering**: o nome exato de uma offering de `referencia.offerings`, a mais afetada. O robô sugere uma no item;
  troque se não for a melhor.
- **descartarConcorrencia** (com o motivo): a notícia não é um movimento do concorrente (homônimo, ex-funcionário,
  estudo ou opinião, comentário de ações, evento social, contratação de uma pessoa vinda do concorrente) ou repete
  um fato que já está em outro item. O item some do site.

### Leitura da semana da Concorrência (quando vier `concorrenciaSemana` nas pendências; semanal)

De 3 a 5 pontos (até 300 caracteres cada), para quem tem 30 segundos. Procure padrões, não repita notícias:
vários concorrentes indo na mesma direção, uma corrida (IA generativa, aquisições de boutiques, centros no Brasil),
uma fragilidade que se repete. Cada ponto cita os concorrentes envolvidos e termina no que importa para a Peers.
Use os itens de `concorrenciaSemana.itens` com as análises que você escreveu hoje para os itens pendentes. Semana
sem movimento relevante: 3 pontos curtos dizendo isso e o que vale observar.

### Síntese do Briefing de Concorrentes (quando vier `concorrenciaBriefing` nas pendências)

O site gera o "Briefing de Concorrentes" em PDF, para os últimos 1 a 30 dias. Esta síntese cobre os últimos 30 dias
(`concorrenciaBriefing.itens`, com as análises que você escreveu hoje para os itens pendentes) e vira o sumário, a
conclusão, o So What e as recomendações do documento. Ela vem nas pendências quando entra movimento novo, ou a cada 7
dias. O modelo é o briefing quinzenal de inteligência competitiva da Peers: uma leitura de padrões, não uma lista de
notícias.

- **sumario** (de 3 a 6 pontos, até 320 caracteres cada): os fatos mais importantes do período. Cada ponto começa com
  um título curto terminado em ponto, que o PDF põe em negrito, seguido do fato com números e datas. Ex.:
  `Accenture acelera aquisições, inclusive no Brasil. Em 26/10/2026 anunciou a compra da Verum Partners (Belo
  Horizonte, 180 pessoas), e a Ryan comprou a Comtax (São Paulo).`
- **conclusao** (1 ou 2 parágrafos, até 650 caracteres cada): os padrões que se repetem entre concorrentes e
  categorias (por exemplo, consolidação por compra de boutiques, migração para IA e serviços gerenciados), com os nomes
  envolvidos. O segundo parágrafo diz o que isso significa no Brasil.
- **soWhat** (até 750): a implicação mais importante para a Peers, como empresa: que escolha ela precisa fazer agora e
  o risco de não fazer. Um parágrafo direto.
- **recomendacoes** (de 3 a 5): `tema`, curto (até 60 caracteres, ex.: `Serviços gerenciados`), e `texto` (até 380),
  com o fato que sustenta a recomendação e a ação concreta. Ex.: `a Deloitte busca triplicar sua divisão de
  outsourcing até 2030; avaliar uma oferta recorrente da Peers em dados e tecnologia, para reduzir a dependência de
  projetos pontuais.` Não repita o mesmo texto em mais de uma recomendação nem copie o impacto de um item.

As mesmas regras da Concorrência valem aqui: só fatos públicos das fontes dos itens, sem nomes de clientes nem de
pessoas da Peers, sem propostas em andamento. Os números e as datas precisam estar nos itens.

### Visão por player dos Indicadores (cada chave, quando vier `aprofundamento` nas pendências)

É o texto do painel que abre ao clicar no indicador: o setor contra as empresas. Cada chave traz o indicador, o
`setor` (valor, variação e, em `referencia`, o número usado na comparação, com `periodoReferencia`), os `players`
com a métrica de cada um (`valor`), a `diferenca` para o setor e a `posicao` (acima, abaixo, em linha), além do
`nivel` da comparação e da `nota` de método.

Até 420 caracteres, 2 ou 3 frases: quem está acima e quem está abaixo do setor, com dois ou três números e o
período, e o que isso indica (ganho ou perda de participação, risco maior ou menor). Use só os números do arquivo.
- `nivel` aproximada: diga que a comparação é indicativa (ex.: "a receita das empresas, que é nominal, cresceu...").
- `nivel` contexto ou sem `referencia` (sem comparação direta): descreva os players (quem cresce mais, quem recua) e a
  relação deles com o indicador, sem falar em "acima do setor".
- Capag (estados ou capitais): quantos têm nota A ou B, quais estão nas piores notas e o que a nota permite.
- Empresa com variação fora do comum (acima de 50% ou queda acima de 30%): cite como caso à parte; costuma ser
  aquisição, venda de ativo ou base fraca no ano anterior, e o arquivo não diz qual.

### So what dos Indicadores (cada chave, quando vier `sowhat` nas pendências)

É o que o consultor leva para a conversa com o cliente: o que o indicador mostra, por que, o que isso faz no
resultado das empresas e que trabalho a Peers pode oferecer. Cada chave (`<segmento>|<indicador>`) traz o
`indicador` (valor, variação, período, fonte e, quando houver, o `historico`), os `outrosIndicadoresDoSegmento`, as
`empresas` da divisão em Finanças (números do último trimestre, em R$ milhões e %), a `visaoPorPlayer` (quando
houver), as `noticias` recentes do Radar da mesma indústria e a `fonteOficial` (nome e `sites` de quem publica o
indicador). Formato da resposta:

```json
"sowhat": { "<chave>": { "oQue": "...", "porQue": "...",
                          "fontes": ["<id da notícia>", {"url": "https://...", "titulo": "...", "trecho": "..."}],
                          "impacto": "...", "oportunidade": "..." } }
```

- **oQue** (até 260): o fato em uma ou duas frases, com o valor, a variação e o período. Se o `historico` mostrar
  uma virada (sobe depois de cair, maior ou menor valor da série), diga.
- **porQue** (até 280): a causa da variação, só com fonte. Duas fontes valem (até 2 no total em `fontes`):
  1. **A publicação oficial** (a melhor): quando houver `fonteOficial`, procure (WebSearch e WebFetch) a divulgação
     de quem publica o indicador sobre o mesmo `periodo` (ex.: a nota do IBGE na Agência de Notícias sobre a
     produção industrial de agosto; o levantamento da Conab da safra; a nota do Banco Central sobre crédito). A
     página precisa ser de um dos `fonteOficial.sites`. Em `fontes`, ponha `{"url", "titulo", "trecho"}`: o
     endereço exato da página, o título dela e um `trecho` de 20 a 400 caracteres **copiado literalmente** da
     página, que mostre a causa. O `aplicar.py` abre a página e recusa se o trecho não estiver lá (em PDF, confere
     só se o arquivo existe). Os números do `porQue` podem vir desse trecho.
  2. **Uma das `noticias`** do Radar deste indicador que mostre a causa: ponha o id dela em `fontes`.
  Sem fonte que explique, escreva exatamente `Causa não identificada nas fontes do portal.` e deixe `fontes` vazio.
  Não use conhecimento geral para a causa: o consultor vai repetir isso ao cliente. Divida as buscas entre os
  subagentes; se uma página não abrir, tente outra do mesmo site ou fique sem causa.
- **impacto** (até 320): o que o movimento do indicador faz no resultado das empresas (receita, margem, crédito,
  inadimplência), citando duas ou três `empresas` ou `visaoPorPlayer.players` com o número e o período. Se as empresas
  andaram na direção contrária do setor, diga. Sem empresas no arquivo (ex.: Public Services), fale do efeito no
  setor sem citar empresa.
- **oportunidade** (até 260): comece pelo nome exato de uma offering de `referencia.offerings`, seguido de
  dois-pontos, e diga que trabalho a Peers pode oferecer a quem é afetado. Ex.: `Supply Chain: planejar armazenagem
  e escoamento para cooperativas com safra recorde e frete pressionado.`
- **Números:** só os que estão na pendência deste indicador, iguais ou arredondados (pode passar de milhões para
  bilhões). Não calcule números novos (somas, diferenças, médias). O `aplicar.py` recusa número que não esteja lá.

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
respostas e rode de novo. Nunca edite `radar.json`, `movimentos.json`, `concorrencia.json` ou `analises.json` à mão.
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

Responda em até 5 linhas: quantos itens escreveu em cada seção (na Concorrência, também quantos descartou e se
escreveu a Leitura da semana), o que ficou para o dia seguinte, os itens em `revisar` (com o título e o motivo de
cada um) e qualquer falha. É aqui que quem acompanha a rotina vê o que precisa
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
