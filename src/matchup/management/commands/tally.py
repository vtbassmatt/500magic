from collections import defaultdict

from django.core.management.base import BaseCommand

from matchup.models import Card, Vote


class Command(BaseCommand):
    help = "Tally votes and rank cards by fame. Votes are grouped by card name across all printings."

    def add_arguments(self, parser):
        parser.add_argument(
            "-n",
            type=int,
            default=500,
            help="Number of top cards to display (default: 500)",
        )

    def handle(self, *args, **options):
        votes = Vote.objects.all()
        vote_count = votes.count()
        if vote_count == 0:
            self.stdout.write("No votes recorded yet.")
            return

        # Collect all referenced UUIDs and resolve to card names in one query
        all_uuids = set()
        for v in votes.iterator():
            all_uuids.add(v.card_1_uuid)
            all_uuids.add(v.card_2_uuid)

        uuid_to_name = {}
        for card in (
            Card.objects.using("mtgjson")
            .filter(uuid__in=list(all_uuids))
            .values_list("uuid", "name")
        ):
            uuid_to_name[card[0]] = card[1]

        # Tally wins and appearances by card name
        wins = defaultdict(int)
        appearances = defaultdict(int)

        for v in votes.iterator():
            name_1 = uuid_to_name.get(v.card_1_uuid)
            name_2 = uuid_to_name.get(v.card_2_uuid)
            if not name_1 or not name_2:
                continue

            appearances[name_1] += 1
            appearances[name_2] += 1
            winner_name = uuid_to_name.get(v.chosen_uuid)
            if winner_name:
                wins[winner_name] += 1

        # Rank by win rate (min 1 appearance), break ties by total wins
        ranked = sorted(
            appearances.keys(),
            key=lambda name: (wins[name] / appearances[name], wins[name]),
            reverse=True,
        )

        top_n = options["n"]
        self.stdout.write(f"\nTop {min(top_n, len(ranked))} cards ({vote_count} votes tallied)\n")
        self.stdout.write(f"{'Rank':<6}{'Card':<40}{'Wins':>6}{'Shown':>7}{'Win %':>8}")
        self.stdout.write("-" * 67)

        for i, name in enumerate(ranked[:top_n], 1):
            w = wins[name]
            a = appearances[name]
            pct = (w / a * 100) if a else 0
            self.stdout.write(f"{i:<6}{name:<40}{w:>6}{a:>7}{pct:>7.1f}%")
