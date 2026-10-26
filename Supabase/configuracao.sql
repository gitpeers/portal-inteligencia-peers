-- Configuração do banco do Portal de Inteligência Peers no Supabase.
-- Rodar uma vez no painel do Supabase: SQL Editor > New query > colar este arquivo > Run.
-- Pode rodar de novo sem problema (não apaga dados).
--
-- O que este arquivo faz:
--   1. Cria a tabela "secoes": uma linha por seção do portal (radar, agenda, valor1000...), com o JSON inteiro.
--   2. Define o domínio de e-mail permitido (@peers.com.br) num lugar só.
--   3. Só deixa ler os dados quem fez login com e-mail do domínio (RLS). Ninguém escreve pelo site:
--      só os scripts do Backend, que usam a chave secreta.
--   4. Barra o cadastro de qualquer e-mail de fora do domínio (nem o código chega a ser enviado).

-- 1. Tabela ------------------------------------------------------------------------------------------
create table if not exists public.secoes (
  nome          text primary key,             -- radar, movimentos, agenda, indicadores, valor1000...
  conteudo      jsonb not null,               -- o mesmo JSON que ficava em Frontend/dados/<nome>.json
  atualizado_em timestamptz not null default now()
);

-- 2. Domínios permitidos: Peers e Actar, do grupo Peers (para mudar, altere aqui e em DOMINIOS no index.html) ---
create or replace function public.dominio_permitido(email text)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select lower(coalesce(email, '')) like '%@peers.com.br'
      or lower(coalesce(email, '')) like '%@actar.com.br'
$$;

-- 3. Quem pode ler -----------------------------------------------------------------------------------
alter table public.secoes enable row level security;

-- permissões explícitas: funcionam mesmo com "Automatically expose new tables" desligado
revoke all on public.secoes from anon, authenticated;
grant select on public.secoes to authenticated;
grant all on public.secoes to service_role;
grant execute on function public.dominio_permitido(text) to authenticated, service_role;

drop policy if exists "Leitura para e-mails da Peers" on public.secoes;
create policy "Leitura para e-mails da Peers" on public.secoes
  for select
  to authenticated
  using (public.dominio_permitido(auth.jwt() ->> 'email'));

-- 4. Quem pode se cadastrar --------------------------------------------------------------------------
-- O login por código cria o usuário no primeiro acesso; esta trava recusa e-mails de fora do domínio
-- (também se alguém tentar trocar o e-mail de uma conta depois).
create or replace function public.barrar_email_de_fora()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not public.dominio_permitido(new.email) then
    raise exception 'Acesso restrito a e-mails @peers.com.br e @actar.com.br';
  end if;
  return new;
end;
$$;

drop trigger if exists barrar_email_de_fora on auth.users;
create trigger barrar_email_de_fora
  before insert or update of email on auth.users
  for each row execute function public.barrar_email_de_fora();
