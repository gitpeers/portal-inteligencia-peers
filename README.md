# Portal de Inteligência Peers

Protótipo do portal da área de Research & Insights: Radar, Finanças dos players, Indicadores setoriais,
Movimentos estratégicos, Concorrência e Agenda setorial, filtráveis por indústria e offering.

O portal se atualiza sozinho: o GitHub Actions roda os scripts em Python todo dia, busca os dados em fontes
públicas (feeds de notícias, Banco Central, IBGE, CVM, Câmara) e grava no **Supabase**. Uma rotina do Claude
escreve as análises por cima. Os dados ficam só no Supabase, e o GitHub Pages publica só a página. Para ver os
dados, a pessoa entra com um **código enviado ao e-mail @peers.com.br ou @actar.com.br** (a Actar é do grupo Peers).

Os scripts trabalham com arquivos: antes de rodar, `baixar_dados.py` traz os dados do Supabase para
`Frontend/dados`; no fim, `enviar_dados.py` devolve o resultado. Esses arquivos são temporários e nunca vão para o
repositório, que é público.

## Estrutura

```
Frontend/
  index.html            a página do portal: tela de login + interface (os dados vêm do Supabase)
  dados/                cópia temporária dos dados, criada por baixar_dados.py (fora do repositório)
Backend/
  atualizar_portal.py   roda as atualizações respeitando a cadência de cada tipo de dado
  atualizar_noticias.py Radar e Movimentos, a partir dos feeds RSS
  atualizar_agenda.py   Agenda, a partir do calendário, do IBGE e da Câmara
  atualizar_indicadores.py  Indicadores setoriais (Banco Central, IBGE, Tesouro e outras fontes)
  atualizar_financas.py Finanças das companhias abertas, a partir da CVM e dos releases
  atualizar_concorrencia.py  Concorrência: movimentos das consultorias concorrentes, a partir do Google Notícias
  atualizar_aprofundamento.py  Indicadores: visão por player (setor contra as empresas), a partir dos dados acima
  baixar_dados.py       traz os dados do Supabase para Frontend/dados, antes dos scripts trabalharem
  enviar_dados.py       devolve os arquivos de Frontend/dados ao Supabase, depois dos scripts
  supabase_api.py       acesso à tabela secoes do Supabase (usado pelos dois acima)
  publicar_trimestral.py  envia o dashboard de resultados trimestrais para a aba Análises trimestrais
  publicar_conexoes.py  envia o Mapa de Conexões para a aba Conexões por empresa (só a lista de acesso comercial)
  validar_fontes.py     testa se cada fonte de notícias tem feed ativo (rodar uma vez por mês)
  ia/                   rotina de IA: instruções (ROTINA.md) e scripts que preparam e aplicam as análises
  comum.py              funções compartilhadas
  config/               o que a R&I pode ajustar sem mexer no código (ver abaixo)
Supabase/
  configuracao.sql      tabela, regras de acesso e trava do domínio (rodar uma vez no Supabase)
  comercial.sql         tabela fechada das conexões e lista de acesso comercial (rodar uma vez no Supabase)
.github/workflows/portal.yml  o agendamento (baixar, atualizar, devolver ao Supabase) e a publicação da página
```

## Como o acesso funciona

- O repositório é **público**, mas só tem código e configurações: os dados nunca entram nele.
- O site publica só a página. Ela pede os dados ao Supabase, cujas regras (RLS) só entregam a quem fez login
  com e-mail `@peers.com.br` ou `@actar.com.br`. A URL e a chave pública no `index.html` podem ser vistas por qualquer um: sozinhas
  não abrem nada.
- O código de login é enviado pelo Outlook da Peers, por um fluxo do Power Automate ligado ao Supabase
  (Send Email hook).
- O cadastro é automático no primeiro login; uma trava no banco recusa e-mails de outros domínios.
- Para liberar outro domínio: altere a função `dominio_permitido` em `Supabase/configuracao.sql` (rodar no SQL Editor)
  e a lista `DOMINIOS` no `Frontend/index.html`, nessa ordem.
- Para tirar o acesso de alguém: Supabase > Authentication > Users > apagar o usuário.

## O que se atualiza e quando

| Dado | Fonte | Cadência |
|---|---|---|
| Radar e Movimentos | Feeds RSS dos veículos validados (`config/fontes_noticias.json`) | Diária |
| Agenda | Calendário (`config/calendario.json`), IBGE e Câmara (`config/agenda_fontes.json`) | Diária |
| Indicadores setoriais | Banco Central, IBGE, Tesouro e outras (`config/indicadores_fontes.json`) | Mensal |
| Finanças · companhias abertas | CVM e releases (`config/financas_cvm.json`, `config/financas_releases.json`); carteira, ROE e CET1 dos demais bancos pelo IF.data do Banco Central | Semanal |
| Finanças · Valor 1000 | Planilha do ranking | Manual, uma vez por ano |
| Indicadores · visão por player | Indicadores, Finanças (companhias abertas), Valor 1000 e Capag do Tesouro (`config/indicadores_players.json`) | Diária (recalcula; a leitura da IA muda quando Indicadores ou Finanças mudam) |
| Concorrência | Google Notícias, edições Brasil e EUA (lista de concorrentes no Supabase; regras em `config/concorrencia_regras.json`) | Diária |
| Análises (resumos, "Por que importa", Ângulo Peers, leituras, impacto da concorrência) | Rotina de IA (`Backend/ia/ROTINA.md`) | Diária, às 07h05 |
| So what dos Indicadores (o que aconteceu, por que, impacto financeiro, oportunidade) | Rotina de IA, com os números do portal e notícias do Radar como única fonte da causa | Quando o indicador muda; até 60 por dia |

## Ajustes sem programar (pasta Backend/config)

- `fontes_noticias.json`: incluir ou tirar um veículo (precisa ter feed RSS ativo).
- `fontes_candidatas.json`: fontes testadas por `validar_fontes.py`; inclua aqui uma fonte nova para testá-la antes.
- `classificacao.json`: palavras-chave de indústrias, temas, offerings, tipos de movimento e exclusões.
- `calendario.json`: eventos da Agenda; use `"recorrencia": "anual"` para eventos que se repetem.
- `indicadores_fontes.json`: ligar um indicador a uma série pública.
- `indicadores_players.json`: qual indicador de cada segmento abre a visão por player, quais empresas entram, a
  métrica de cada uma e o cuidado de método mostrado no painel. O indicador ligado aparece primeiro no cartão.
- `concorrencia_regras.json`: palavras de cada tipo de movimento dos concorrentes, filtros de ruído e a lista de
  empresas de tecnologia do mapa de parcerias. Não tem nomes de concorrentes (ver abaixo).
- `sowhat_fontes.json`: sites oficiais de cada fonte de indicador aceitos como prova do "por que" no so what. A
  rotina de IA cita a página com um trecho copiado dela, e o `aplicar.py` abre a página e confere o trecho; os
  mesmos sites precisam estar liberados na rede do ambiente da rotina.

Depois de editar um arquivo pelo site do GitHub, rode a atualização manualmente: aba **Actions** >
**Atualizar e publicar o portal** > **Run workflow**.

## Concorrência: a lista de concorrentes fica no Supabase

O repositório é público; por isso a lista de consultorias que a Peers monitora não fica em `Backend/config`, e sim na
seção `concorrentes` da tabela `secoes` do Supabase (só quem faz login vê). Para incluir, tirar ou ajustar um
concorrente: Supabase > Table Editor > `secoes` > linha `concorrentes` > editar o JSON. Cada concorrente tem `id`,
`nome`, `grupo`, `buscar` (termos da busca no Google Notícias), `nomes` (grafias que contam como menção na manchete),
`excluir` (homônimos) e `concorreEm` (offerings da Peers em que disputa projetos). Concorrente novo ganha uma carga
dos últimos 6 meses na rodada seguinte do robô.

O robô registra no log do GitHub (público) só contagens, nunca nomes nem manchetes, e o relatório da rotina de IA
(`Backend/relatorio_ia.json`) também não traz os itens da Concorrência. A seção fica fora do briefing, que é montado
para o cliente.

## Configuração (uma vez)

- **Supabase:** rodar `Supabase/configuracao.sql` no SQL Editor; Send Email hook apontando para o fluxo do
  Power Automate.
- **GitHub:** Secrets `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` (Settings > Secrets and variables > Actions).
  A `SUPABASE_SERVICE_KEY` é a chave secreta (service_role): nunca a coloque no `index.html` nem em arquivos.
- **GitHub Pages:** Settings > Pages > Source: GitHub Actions.
- **Rotina de IA:** ver o fim de `Backend/ia/ROTINA.md` (inclui as variáveis do Supabase no ambiente da rotina).
  Manter só uma rotina ativa por vez.

## Testar no computador

Rode um servidor local na pasta Frontend e acesse http://localhost:8000 (inclua esse endereço em Supabase >
Authentication > URL Configuration > Redirect URLs):

```
cd Frontend
python -m http.server 8000
```

Para rodar as atualizações no computador, defina as duas variáveis no PowerShell e rode, na pasta Backend:

```
$env:SUPABASE_URL = "https://<seu-projeto>.supabase.co"
$env:SUPABASE_SERVICE_KEY = "<chave secreta>"
python baixar_dados.py
python atualizar_portal.py --forcar
python enviar_dados.py --todos
```

Para corrigir uma seção à mão (ex.: Valor 1000): `baixar_dados.py`, editar o arquivo em `Frontend/dados` e
`python enviar_dados.py valor1000`.

**Aba Análises trimestrais.** Abre em tela cheia o dashboard do projeto de resultados trimestrais (pasta
02. Workspace / Resultados 3T26), guardado na linha `trimestral` da tabela secoes, e não no repositório. Só é baixado
quando alguém abre a aba; os scripts do robô não o leem. Quem publica é a tarefa agendada "Portal Peers - Publicar
análises trimestrais", no computador do Kayo: a cada 15 minutos, se o projeto está na branch main e o
`dashboard/index.html` mudou, ela roda `publicar_trimestral.py --automatico`. A chave do Supabase fica guardada
criptografada pelo Windows em `%USERPROFILE%\.portal-peers-git\supabase_chave.txt` (só a conta do Windows que a gravou
consegue ler). Para publicar na hora, na pasta Backend, com as duas variáveis definidas:
`python publicar_trimestral.py "<pasta do projeto>"`.

## Editar pela pasta do SharePoint

A pasta do portal no SharePoint (Research & Insights - Ativos do Site) fica sincronizada com este repositório por
uma tarefa agendada no computador do Kayo ("Portal Peers - Sincronizar GitHub", a cada 5 minutos):

- Quem edita um arquivo na pasta e salva vê a mudança no site em poucos minutos. A tarefa espera 2 minutos sem
  edições antes de enviar, para não publicar um arquivo pela metade.
- O que é publicado direto no GitHub (por colaboradores, pelo robô ou pela rotina de IA) aparece na pasta sozinho.
- Com o computador do Kayo desligado, as alterações ficam na pasta e são enviadas quando ele ligar.
- Se algo der errado (conflito, muitos arquivos apagados de uma vez, dados prestes a ir para o repositório), nada é
  enviado e aparece o arquivo `SINCRONIZACAO_COM_ERRO.txt` na pasta, explicando o motivo.
- Os arquivos de `Frontend/dados` na pasta são cópias temporárias: editá-los não muda o site (os dados ficam no
  Supabase).

## Observações

- O GitHub pausa agendamentos de repositórios sem atividade por 60 dias. Os envios automáticos de dados contam
  como atividade; se a pausa acontecer, reative em Actions.

**Aba Conexões por empresa (visão comercial).** Mostra, por empresa, quem da Peers conhece alguém lá (Mapa de Conexões,
conexões de 1º grau no LinkedIn), com o link do perfil, os leads em bando e as notícias e movimentos da empresa no
portal; também põe o quadro "Quem da Peers chega a..." no Radar, em Movimentos e na ficha da empresa. Os dados ficam na
tabela `conexoes`, que só entrega a quem está em `acesso_comercial` (Supabase/comercial.sql); para os demais a aba não
aparece. Para dar ou tirar acesso: Supabase > Table Editor > acesso_comercial (e-mail em minúsculas). O perfil
`marketing` vê a visão geral e pode "ver como" qualquer executivo; o perfil `executivo` vê a visão geral e só a
própria carteira (o executivo cujo nome bate com o e-mail). Na lista de empresas, a caixinha ao lado do nome marca a
empresa para a planilha de relacionamentos: "Baixar planilha (Excel)" gera no navegador (ExcelJS) o mesmo formato da
planilha feita para a BytePlus (visão geral com quem procurar primeiro, contatos com o LinkedIn e premissas). Vai para o portal
só executivo, lead (nome, cargo, senioridade, LinkedIn), empresa e indústria: sem e-mail, rede interna, classificações
comerciais nem funil. Para publicar a base mais recente (base_conexoes_peers_v<N>.xlsx, na pasta Extração de Leads), na
pasta Backend, com as duas variáveis definidas: `python publicar_conexoes.py "<pasta Extração de Leads>"`.
