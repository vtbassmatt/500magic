from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from matchup.models import Matchup


class Command(BaseCommand):
    help = "Display statistics about unvoted matchups by age."

    def handle(self, *args, **options):
        now = timezone.now()
        
        # Get all unvoted matchups
        unvoted = Matchup.objects.filter(voted__isnull=True)
        total_unvoted = unvoted.count()
        
        if total_unvoted == 0:
            self.stdout.write("No unvoted matchups found.")
            return
        
        # Define time buckets
        buckets = [
            ("< 2 hours", timedelta(hours=0), timedelta(hours=2)),
            ("2-8 hours", timedelta(hours=2), timedelta(hours=8)),
            ("8-24 hours", timedelta(hours=8), timedelta(hours=24)),
            ("24+ hours", timedelta(hours=24), None),
        ]
        
        self.stdout.write(f"\nUnvoted Matchup Statistics")
        self.stdout.write("=" * 40)
        self.stdout.write(f"Total unvoted matchups: {total_unvoted}\n")
        
        for label, min_age, max_age in buckets:
            if max_age is None:
                # 24+ hours bucket
                cutoff = now - min_age
                count = unvoted.filter(created_at__lt=cutoff).count()
            else:
                # Time-bounded bucket
                min_cutoff = now - max_age
                max_cutoff = now - min_age
                count = unvoted.filter(
                    created_at__gte=min_cutoff,
                    created_at__lt=max_cutoff
                ).count()
            
            percentage = (count / total_unvoted * 100) if total_unvoted > 0 else 0
            self.stdout.write(f"{label:>12}: {count:>6} ({percentage:>5.1f}%)")
