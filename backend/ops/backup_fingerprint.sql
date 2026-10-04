-- Отпечаток базы для проверки резервной копии.
--
-- Один и тот же файл запускается против рабочей базы и против копии, восстановленной в
-- отдельную базу; совпавший вывод — и есть доказательство, что копия полная. Строки
-- сравниваются целиком, поэтому порядок и заголовки важны: выводите результат в файл и
-- diffs/compare, а не глазами.
--
--   psql -U befos -d befos                 -X -q -P pager=off -f backup_fingerprint.sql > source.txt
--   psql -U befos -d befos_restore_drill  -X -q -P pager=off -f backup_fingerprint.sql > restored.txt
--
-- Числа на 2026-10-04 (dev-база 11 МБ, 23 таблицы): copy совпала по всем строкам.

\pset title rowcounts
SELECT t.relname || '=' ||
  (xpath('/row/c/text()',
          query_to_xml('SELECT count(*) AS c FROM public.' || quote_ident(t.relname), false, true, '')))[1]::text
FROM (
  SELECT c.relname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
) t
ORDER BY 1;

\pset title stamp
SELECT 'alembic=' || version_num FROM alembic_version;

\pset title schema
SELECT 'tables=' || count(*) FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r';

-- Функциональный индекс lower(city) должен пережить копию: копия, потерявшая индексы,
-- возвращается медленнее, чем была рабочая база.
SELECT 'indexes=' || count(*) FROM pg_indexes WHERE schemaname = 'public';

SELECT 'sequences=' || count(*) FROM information_schema.sequences
  WHERE sequence_schema = 'public';
