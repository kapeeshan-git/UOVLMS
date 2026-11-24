from django.db import models


class SectionPolicy(models.Model):
    """REFERENCE / STACK: hours and fine rate. A collection without a section is in-library use only."""

    code = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=100)
    issue_start = models.TimeField()
    issue_end = models.TimeField()
    return_start = models.TimeField()
    return_end = models.TimeField()
    fine_per_day = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(fine_per_day__gte=0), name="section_fine_non_negative")]


class Category(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ["name"]


class Author(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    biography = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]


class Book(models.Model):
    title = models.CharField(max_length=500, db_index=True)
    title_alt = models.CharField(max_length=500, blank=True)
    isbn = models.CharField(max_length=20, blank=True, db_index=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT, related_name="books")
    call_number = models.CharField(max_length=100, blank=True, db_index=True)
    publisher = models.CharField(max_length=200, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)
    authors = models.ManyToManyField(Author, through="BookAuthor", related_name="books")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]


class BookAuthor(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    author = models.ForeignKey(Author, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["book", "author"], name="uniq_book_author")]


class Collection(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    section = models.ForeignKey(SectionPolicy, null=True, blank=True, on_delete=models.PROTECT,
                                db_column="section_code", related_name="collections")

    class Meta:
        ordering = ["name"]


class BookCopy(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE"
        ON_LOAN = "ON_LOAN"
        IN_REPAIR = "IN_REPAIR"
        LOST = "LOST"
        WITHDRAWN = "WITHDRAWN"

    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="copies")
    accession_number = models.CharField(max_length=50, unique=True)  # barcode
    collection = models.ForeignKey(Collection, on_delete=models.PROTECT, related_name="copies")
    shelf_location = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    condition = models.CharField(max_length=100, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["accession_number"]
