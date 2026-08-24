from django.core.management.base import BaseCommand

from sales.models import Item

# Starting price list, carried over from the FRONT_OFFICE_SALES spreadsheet.
# Edit prices any time from /admin/ - this command only needs to run once.
DEFAULT_ITEMS = [
    ("STEAK", 900), ("KIMA", 900), ("TBONE", 750), ("STAFF", 650),
    ("FILLET", 1000), ("LIVER", 900), ("LEG", 900), ("MIX", 800),
    ("M.BONELESS", 1000), ("CHOPS", 800), ("SHAWARMA", 550), ("M.KIMA", 1000),
    ("W.CHICKEN", 450), ("B.BONELESS", 800), ("MIX.BONELESS", 700),
    ("WINGS", 450), ("NECKS", 300), ("GIZZARDS", 300), ("C.SOUP", 120),
    ("SOUP BONES", 300), ("COCKTAIL", 300), ("DOG MEAT", 100),
]


class Command(BaseCommand):
    help = "Seed the item/price list with the starting values from the spreadsheet."

    def handle(self, *args, **options):
        created = 0
        for name, price in DEFAULT_ITEMS:
            _, was_created = Item.objects.get_or_create(
                name=name, defaults={"price_per_kg": price}
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(
            f"Done. {created} new item(s) added, {len(DEFAULT_ITEMS) - created} already existed."
        ))
