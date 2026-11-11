-- Reforço de segurança (11/11/2026). Rodar uma vez no painel do Supabase: SQL Editor > New query > colar > Run.
-- Pode rodar de novo sem problema.

-- A função rls_auto_enable (gatilho que liga a proteção por linha em tabelas novas) aparecia na API para quem não
-- fez login. Ela continua funcionando como gatilho; só deixa de poder ser chamada pela internet.
do $$
begin
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname = 'rls_auto_enable') then
    revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
  end if;
end $$;

-- A função dominio_permitido (usada pelas regras de leitura) não precisa ser chamada por quem não fez login.
revoke execute on function public.dominio_permitido(text) from public, anon;
grant execute on function public.dominio_permitido(text) to authenticated, service_role;

-- Conferência: deve listar só authenticated e service_role (e o dono) em cada função.
select p.proname as funcao, r.rolname as pode_executar
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
cross join pg_roles r
where n.nspname = 'public' and p.proname in ('rls_auto_enable', 'dominio_permitido')
  and r.rolname in ('anon', 'authenticated', 'service_role')
  and has_function_privilege(r.oid, p.oid, 'execute')
order by 1, 2;
