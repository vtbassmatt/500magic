from django.core.management.base import BaseCommand

from matchup.elo import update_ratings
from matchup.models import Card, CardRating, Vote


class Command(BaseCommand):
    help = "Recalculate all Elo ratings by replaying votes in chronological order."

    def handle(self, *args, **options):
        votes = Vote.objects.order_by("created_at")
        vote_count = votes.count()
        if vote_count == 0:
            self.stdout.write("No votes to replay.")
            return

        # Collect all UUIDs and resolve to names in one query
        all_uuids = set()
        for v in votes.iterator():
            all_uuids.add(v.card_1_uuid)
            all_uuids.add(v.card_2_uuid)

        uuid_to_name = dict(
            Card.objects.using("mtgjson")
            .filter(uuid__in=list(all_uuids))
            .values_list("uuid", "name")
        )

        # Wipe existing ratings
        deleted_count, _ = CardRating.objects.all().delete()
        self.stdout.write(f"Cleared {deleted_count} existing ratings.")

        # Replay all votes
        ratings: dict[str, float] = {}
        wins: dict[str, int] = {}
        losses: dict[str, int] = {}

        for v in votes.iterator():
            name_1 = uuid_to_name.get(v.card_1_uuid)
            name_2 = uuid_to_name.get(v.card_2_uuid)
            if not name_1 or not name_2:
                continue

            r1 = ratings.get(name_1, 1500.0)
            r2 = ratings.get(name_2, 1500.0)
            a_won = v.chosen_uuid == v.card_1_uuid

            new_r1, new_r2 = update_ratings(r1, r2, a_won)
            ratings[name_1] = new_r1
            ratings[name_2] = new_r2

            wins.setdefault(name_1, 0)
            wins.setdefault(name_2, 0)
            losses.setdefault(name_1, 0)
            losses.setdefault(name_2, 0)

            if a_won:
                wins[name_1] += 1
                losses[name_2] += 1
            else:
                wins[name_2] += 1
                losses[name_1] += 1

        # Bulk create all ratings
        CardRating.objects.bulk_create([
            CardRating(
                name=name,
                rating=ratings[name],
                wins=wins.get(name, 0),
                losses=losses.get(name, 0),
            )
            for name in ratings
        ])

        self.stdout.write(
            f"Replayed {vote_count} votes. "
            f"{len(ratings)} cards rated."
        )
