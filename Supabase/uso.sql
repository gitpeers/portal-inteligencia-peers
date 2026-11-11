-- Registro de uso do portal (11/11/2026). Rodar uma vez no painel do Supabase: SQL Editor > New query > colar > Run.
-- O portal grava uma linha quando a pessoa troca de aba ou gera um briefing: aba, evento, perfil (geral, executivo,
-- marketing; +clientes) e um número de sessão sorteado a cada visita. NÃO grava e-mail, nome nem o conteúdo visto.
-- Quem está logado só consegue gravar; ninguém lê pela página. A leitura é pelo Backend/relatorio_uso.py (chave de serviço).

create table if not exists public.uso_portal (
  id      bigint generated always as identity primary key,
  em      timestamptz not null default now(),
  evento  text not null check (char_length(evento) <= 40),   -- aba, briefing, briefing_conta, briefing_concorrentes...
  aba     text check (char_length(aba) <= 40),
  detalhe text check (char_length(detalhe) <= 80),          -- ex.: "roda" dentro de Oportunidades, "5 itens"
  perfil  text check (char_length(perfil) <= 30),
  sessao  text check (char_length(sessao) <= 40)
);
alter table public.uso_portal enable row level security;

revoke all on public.uso_portal from anon, authenticated;
grant insert (evento, aba, detalhe, perfil, sessao) on public.uso_portal to authenticated;
grant all on public.uso_portal to service_role;

drop policy if exists "Quem é da Peers registra o uso" on public.uso_portal;
create policy "Quem é da Peers registra o uso" on public.uso_portal
  for insert
  to authenticated
  with check (public.dominio_permitido(auth.jwt() ->> 'email'));

create index if not exists uso_portal_em on public.uso_portal (em);
