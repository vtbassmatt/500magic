from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from matchup.models import Matchup


class Command(BaseCommand):
    help = "Delete unvoted matchups older than a specified age (default: 24 hours)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Delete matchups older than this many hours (default: 24)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        dry_run = options["dry_run"]
        
        cutoff_time = timezone.now() - timedelta(hours=hours)
        
        # Find unvoted matchups older than cutoff
        old_matchups = Matchup.objects.filter(
            voted__isnull=True,
            created_at__lt=cutoff_time
        )
        
        count = old_matchups.count()
        
        if count == 0:
            self.stdout.write(f"No unvoted matchups older than {hours} hours found.")
            return
        
        matchup_word = "matchup" if count == 1 else "matchups"
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would delete {count} unvoted {matchup_word} "
                    f"older than {hours} hours."
                )
            )
            # Show sample of what would be deleted
            sample = old_matchups[:10]
            if sample.exists():
                self.stdout.write("\nSample of matchups that would be deleted:")
                for m in sample:
                    age = timezone.now() - m.created_at
                    hours_old = age.total_seconds() / 3600
                    self.stdout.write(f"  - {m.token} (created {hours_old:.1f} hours ago)")
                if count > 10:
                    self.stdout.write(f"  ... and {count - 10} more")
        else:
            deleted_count, _ = old_matchups.delete()
            matchup_word = "matchup" if deleted_count == 1 else "matchups"
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully deleted {deleted_count} unvoted {matchup_word} "
                    f"older than {hours} hours."
                )
            )
