"""FULLTEXT (ngram) indexes for catalog search (guide 6.7). MySQL only; other DBs use icontains."""
from django.db import migrations

INDEXES = [
    ("catalog_book", "ft_book_title", "title, title_alt"),
    ("catalog_author", "ft_author_name", "name"),
]


def add_fulltext(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cur:
        # Without this, the ngram parser drops every token containing a stopword letter such as "a".
        cur.execute("SET SESSION innodb_ft_enable_stopword = OFF")
        for table, name, cols in INDEXES:
            cur.execute(f"ALTER TABLE {table} ADD FULLTEXT INDEX {name} ({cols}) WITH PARSER ngram")


def drop_fulltext(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cur:
        for table, name, _ in INDEXES:
            cur.execute(f"ALTER TABLE {table} DROP INDEX {name}")


class Migration(migrations.Migration):
    atomic = False  # MySQL DDL is not transactional anyway
    dependencies = [("catalog", "0001_initial")]
    operations = [migrations.RunPython(add_fulltext, drop_fulltext)]
