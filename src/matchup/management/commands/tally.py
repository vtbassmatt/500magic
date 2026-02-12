from django.core.management.base import BaseCommand

from matchup.models import CardRating


class Command(BaseCommand):
    help = "Display card rankings by Elo rating."

    def add_arguments(self, parser):
        parser.add_argument(
            "-n",
            type=int,
            default=500,
            help="Number of top cards to display (default: 500)",
        )

    def handle(self, *args, **options):
        total = CardRating.objects.count()
        if total == 0:
            self.stdout.write("No ratings yet. Vote on some matchups first!")
            return

        top_n = options["n"]
        ratings = CardRating.objects.order_by("-rating")[:top_n]

        self.stdout.write(f"\nTop {min(top_n, total)} of {total} rated cards\n")
        self.stdout.write(f"{'Rank':<6}{'Card':<40}{'Rating':>8}{'Wins':>6}{'Losses':>8}")
        self.stdout.write("-" * 68)

        for i, cr in enumerate(ratings, 1):
            self.stdout.write(
                f"{i:<6}{cr.name:<40}{cr.rating:>8.1f}{cr.wins:>6}{cr.losses:>8}"
            )
