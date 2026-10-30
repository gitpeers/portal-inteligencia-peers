-- Visão comercial do Portal de Inteligência Peers: Mapa de Conexões, só para a lista de acesso.
-- Rodar uma vez no painel do Supabase: SQL Editor > New query > colar este arquivo > Run.
-- Pode rodar de novo sem problema (não apaga dados).
--
-- Diferente da tabela "secoes" (que todo e-mail @peers e @actar lê), as conexões ficam numa tabela própria que só
-- entrega dados a quem está em "acesso_comercial". Quem não está na lista não recebe nada, e a aba nem aparece.
--   1. acesso_comercial: os e-mails liberados. Cada pessoa só consegue ver a própria linha (para o portal saber se
--      mostra a aba); quem inclui ou tira alguém é o painel do Supabase (Table Editor), nunca o site.
--   2. conexoes: o Mapa de Conexões (linha "mapa"), gravado por Backend/publicar_conexoes.py, e a base de clientes da
--      Peers (linha "clientes"), gravada por Backend/publicar_clientes.py, ambos com a chave secreta.

-- 1. Lista de acesso ---------------------------------------------------------------------------------
create table if not exists public.acesso_comercial (
  email     text primary key,                -- sempre em minúsculas
  nome      text,
  perfil    text not null default 'marketing', -- marketing: vê a rede de todos, por empresa, e "ver como" qualquer
                                             -- executivo; executivo: a visão geral e só a própria carteira
  criado_em timestamptz not null default now()
);
alter table public.acesso_comercial enable row level security;
revoke all on public.acesso_comercial from anon, authenticated;
grant select on public.acesso_comercial to authenticated;
grant all on public.acesso_comercial to service_role;

drop policy if exists "Cada um vê a própria linha" on public.acesso_comercial;
create policy "Cada um vê a própria linha" on public.acesso_comercial
  for select
  to authenticated
  using (email = lower(auth.jwt() ->> 'email'));

insert into public.acesso_comercial (email, nome, perfil) values
  ('kayo.moreira@peers.com.br', 'Kayo Moreira', 'marketing'),
  ('andreas.bethanis@peers.com.br', 'Andreas Bethanis', 'marketing')
on conflict (email) do nothing;

-- 2. Conexões ----------------------------------------------------------------------------------------
create table if not exists public.conexoes (
  nome          text primary key,             -- "mapa"
  conteudo      jsonb not null,
  atualizado_em timestamptz not null default now()
);
alter table public.conexoes enable row level security;
revoke all on public.conexoes from anon, authenticated;
grant select on public.conexoes to authenticated;
grant all on public.conexoes to service_role;

drop policy if exists "Só a lista de acesso comercial" on public.conexoes;
create policy "Só a lista de acesso comercial" on public.conexoes
  for select
  to authenticated
  using (exists (select 1 from public.acesso_comercial a where a.email = lower(auth.jwt() ->> 'email')));
