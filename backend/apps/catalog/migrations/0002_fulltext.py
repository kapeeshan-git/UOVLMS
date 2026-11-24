from django.db import migrations


def add_fulltext_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE catalog_book ADD FULLTEXT INDEX ft_book_title (title, title_alt) WITH PARSER ngram"
        )
        cursor.execute(
            "ALTER TABLE catalog_author ADD FULLTEXT INDEX ft_author_name (name) WITH PARSER ngram"
        )


def drop_fulltext_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE catalog_book DROP INDEX ft_book_title")
        cursor.execute("ALTER TABLE catalog_author DROP INDEX ft_author_name")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_fulltext_indexes, drop_fulltext_indexes),
    ]
