import uuid
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings, TestCase

from .elo import expected_score, update_ratings
from .models import Card, CardIdentifiers, CardRating, Matchup, Vote

CARD_1_UUID = "aaaaaaaa-1111-1111-1111-111111111111"
CARD_2_UUID = "bbbbbbbb-2222-2222-2222-222222222222"
SCRYFALL_ID = "abcdef01-2345-6789-abcd-ef0123456789"


class CardIdentifiersModelTest(TestCase):
    databases = {"default", "mtgjson"}

    def test_scryfall_image_url(self):
        ident = CardIdentifiers(uuid=CARD_1_UUID, scryfallId=SCRYFALL_ID)
        url = ident.scryfall_image_url()
        self.assertEqual(
            url,
            f"https://cards.scryfall.io/normal/front/a/b/{SCRYFALL_ID}.jpg",
        )

    def test_scryfall_image_url_none(self):
        ident = CardIdentifiers(uuid=CARD_1_UUID, scryfallId=None)
        self.assertIsNone(ident.scryfall_image_url())


def _mock_matchup():
    return (
        {
            "uuid": CARD_1_UUID,
            "name": "Lightning Bolt",
            "image_url": f"https://cards.scryfall.io/normal/front/a/b/{SCRYFALL_ID}.jpg",
        },
        {
            "uuid": CARD_2_UUID,
            "name": "Black Lotus",
            "image_url": f"https://cards.scryfall.io/normal/front/c/d/{SCRYFALL_ID}.jpg",
        },
    )

@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class MatchupGetTest(TestCase):
    @patch("matchup.views._get_random_matchup", side_effect=lambda: _mock_matchup())
    def test_get_returns_200_with_two_cards(self, mock_get):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lightning Bolt")
        self.assertContains(response, "Black Lotus")
        self.assertContains(response, "matchup_token")

    @patch("matchup.views._get_random_matchup", side_effect=lambda: _mock_matchup())
    def test_get_creates_matchup_record(self, mock_get):
        self.assertEqual(Matchup.objects.count(), 0)
        self.client.get("/")
        self.assertEqual(Matchup.objects.count(), 1)
        m = Matchup.objects.first()
        self.assertEqual(m.card_1_uuid, CARD_1_UUID)
        self.assertEqual(m.card_2_uuid, CARD_2_UUID)
        self.assertIsNone(m.voted)

    @patch("matchup.views._get_random_matchup", return_value=(None, None))
    def test_get_shows_error_when_no_cards(self, mock_get):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Could not find cards")


class VotePostTest(TestCase):
    databases = {"default", "mtgjson"}

    def _create_matchup(self):
        return Matchup.objects.create(
            card_1_uuid=CARD_1_UUID,
            card_2_uuid=CARD_2_UUID,
        )

    @patch("matchup.views._update_elo")
    def test_valid_vote_creates_vote_and_redirects(self, mock_elo):
        m = self._create_matchup()
        response = self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": CARD_1_UUID,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.count(), 1)
        vote = Vote.objects.first()
        self.assertEqual(vote.card_1_uuid, CARD_1_UUID)
        self.assertEqual(vote.card_2_uuid, CARD_2_UUID)
        self.assertEqual(vote.chosen_uuid, CARD_1_UUID)

    @patch("matchup.views._update_elo")
    def test_vote_marks_matchup_as_voted(self, mock_elo):
        m = self._create_matchup()
        self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": CARD_2_UUID,
        })
        m.refresh_from_db()
        self.assertIsNotNone(m.voted)

    @patch("matchup.views._update_elo")
    def test_replay_same_token_rejected(self, mock_elo):
        m = self._create_matchup()
        self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": CARD_1_UUID,
        })
        response = self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": CARD_1_UUID,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Vote.objects.count(), 1)

    @patch("matchup.views._update_elo")
    def test_fabricated_token_rejected(self, mock_elo):
        response = self.client.post("/", {
            "matchup_token": str(uuid.uuid4()),
            "chosen_uuid": CARD_1_UUID,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Vote.objects.count(), 0)

    @patch("matchup.views._update_elo")
    def test_invalid_token_format_rejected(self, mock_elo):
        response = self.client.post("/", {
            "matchup_token": "not-a-uuid",
            "chosen_uuid": CARD_1_UUID,
        })
        self.assertEqual(response.status_code, 400)

    @patch("matchup.views._update_elo")
    def test_chosen_uuid_not_in_matchup_rejected(self, mock_elo):
        m = self._create_matchup()
        response = self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": "cccccccc-3333-3333-3333-333333333333",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Vote.objects.count(), 0)

    @patch("matchup.views._update_elo")
    def test_missing_fields_rejected(self, mock_elo):
        response = self.client.post("/", {})
        self.assertEqual(response.status_code, 400)

    @patch("matchup.views._update_elo")
    def test_vote_records_ip_address(self, mock_elo):
        m = self._create_matchup()
        self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": CARD_1_UUID,
        })
        vote = Vote.objects.first()
        self.assertEqual(vote.ip_address, "127.0.0.1")

    @patch("matchup.views._update_elo")
    def test_vote_respects_x_forwarded_for(self, mock_elo):
        m = self._create_matchup()
        self.client.post(
            "/",
            {
                "matchup_token": str(m.token),
                "chosen_uuid": CARD_1_UUID,
            },
            HTTP_X_FORWARDED_FOR="203.0.113.50, 70.41.3.18",
        )
        vote = Vote.objects.first()
        self.assertEqual(vote.ip_address, "203.0.113.50")


class EloMathTest(TestCase):
    def test_equal_ratings_give_50_50(self):
        e = expected_score(1500, 1500)
        self.assertAlmostEqual(e, 0.5)

    def test_higher_rating_favored(self):
        e = expected_score(1700, 1500)
        self.assertGreater(e, 0.5)

    def test_expected_scores_sum_to_one(self):
        ea = expected_score(1600, 1400)
        eb = expected_score(1400, 1600)
        self.assertAlmostEqual(ea + eb, 1.0)

    def test_update_equal_ratings_winner_gains(self):
        new_a, new_b = update_ratings(1500, 1500, a_won=True)
        self.assertGreater(new_a, 1500)
        self.assertLess(new_b, 1500)
        # With K=32 and equal ratings, winner gains 16
        self.assertAlmostEqual(new_a, 1516.0)
        self.assertAlmostEqual(new_b, 1484.0)

    def test_update_ratings_are_symmetric(self):
        new_a, new_b = update_ratings(1500, 1500, a_won=True)
        # Total rating is conserved
        self.assertAlmostEqual(new_a + new_b, 3000.0)

    def test_upset_gives_bigger_swing(self):
        # Underdog (1300) beats favorite (1700)
        new_a_upset, _ = update_ratings(1300, 1700, a_won=True)
        # Favorite (1700) beats underdog (1300)
        new_a_expected, _ = update_ratings(1700, 1300, a_won=True)
        upset_gain = new_a_upset - 1300
        expected_gain = new_a_expected - 1700
        self.assertGreater(upset_gain, expected_gain)


class EloVoteIntegrationTest(TestCase):
    databases = {"default", "mtgjson"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create unmanaged tables in the test mtgjson database
        from django.db import connections
        with connections["mtgjson"].cursor() as cursor:
            cursor.execute(
                'CREATE TABLE IF NOT EXISTS "cards" ('
                '"uuid" TEXT PRIMARY KEY, "name" TEXT, "setCode" TEXT, '
                '"rarity" TEXT, "layout" TEXT, "isFunny" INTEGER, '
                '"isOnlineOnly" INTEGER, "isOversized" INTEGER, '
                '"availability" TEXT, "side" TEXT, "language" TEXT)'
            )

    def _seed_mtgjson_cards(self):
        """Insert test cards into the mtgjson test database."""
        Card.objects.using("mtgjson").create(
            uuid=CARD_1_UUID,
            name="Lightning Bolt",
            setCode="LEA",
            rarity="common",
            layout="normal",
            language="en",
        )
        Card.objects.using("mtgjson").create(
            uuid=CARD_2_UUID,
            name="Black Lotus",
            setCode="LEA",
            rarity="rare",
            layout="normal",
            language="en",
        )

    def _vote(self, card_1, card_2, chosen):
        m = Matchup.objects.create(card_1_uuid=card_1, card_2_uuid=card_2)
        self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": chosen,
        })

    def test_vote_creates_card_ratings(self):
        self._seed_mtgjson_cards()
        self._vote(CARD_1_UUID, CARD_2_UUID, CARD_1_UUID)

        self.assertEqual(CardRating.objects.count(), 2)
        bolt = CardRating.objects.get(name="Lightning Bolt")
        lotus = CardRating.objects.get(name="Black Lotus")
        self.assertGreater(bolt.rating, 1500)
        self.assertLess(lotus.rating, 1500)
        self.assertEqual(bolt.wins, 1)
        self.assertEqual(bolt.losses, 0)
        self.assertEqual(lotus.wins, 0)
        self.assertEqual(lotus.losses, 1)

    def test_multiple_votes_accumulate(self):
        self._seed_mtgjson_cards()
        self._vote(CARD_1_UUID, CARD_2_UUID, CARD_1_UUID)
        self._vote(CARD_1_UUID, CARD_2_UUID, CARD_1_UUID)

        bolt = CardRating.objects.get(name="Lightning Bolt")
        self.assertEqual(bolt.wins, 2)
        self.assertGreater(bolt.rating, 1516)  # More than one win's worth

    def test_recalculate_matches_live(self):
        self._seed_mtgjson_cards()
        self._vote(CARD_1_UUID, CARD_2_UUID, CARD_1_UUID)
        self._vote(CARD_2_UUID, CARD_1_UUID, CARD_2_UUID)
        self._vote(CARD_1_UUID, CARD_2_UUID, CARD_2_UUID)

        # Capture live ratings
        bolt_live = CardRating.objects.get(name="Lightning Bolt")
        lotus_live = CardRating.objects.get(name="Black Lotus")

        # Recalculate from scratch
        call_command("recalculate_elo", stdout=open("/dev/null", "w"))

        bolt_recalc = CardRating.objects.get(name="Lightning Bolt")
        lotus_recalc = CardRating.objects.get(name="Black Lotus")

        self.assertAlmostEqual(bolt_live.rating, bolt_recalc.rating, places=6)
        self.assertAlmostEqual(lotus_live.rating, lotus_recalc.rating, places=6)
        self.assertEqual(bolt_live.wins, bolt_recalc.wins)
        self.assertEqual(lotus_live.losses, lotus_recalc.losses)


class LanguageFilterTest(TestCase):
    databases = {"default", "mtgjson"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create unmanaged tables in the test mtgjson database
        from django.db import connections
        with connections["mtgjson"].cursor() as cursor:
            cursor.execute(
                'CREATE TABLE IF NOT EXISTS "cards" ('
                '"uuid" TEXT PRIMARY KEY, "name" TEXT, "setCode" TEXT, '
                '"rarity" TEXT, "layout" TEXT, "isFunny" INTEGER, '
                '"isOnlineOnly" INTEGER, "isOversized" INTEGER, '
                '"availability" TEXT, "side" TEXT, "language" TEXT)'
            )
            cursor.execute(
                'CREATE TABLE IF NOT EXISTS "cardIdentifiers" ('
                '"uuid" TEXT PRIMARY KEY, "scryfallId" TEXT)'
            )

    def setUp(self):
        """Seed test database with cards in different languages."""
        # English card
        Card.objects.using("mtgjson").create(
            uuid="en-card-1111-1111-1111-111111111111",
            name="English Card",
            setCode="TST",
            rarity="common",
            layout="normal",
            language="English",
            availability="paper",
        )
        CardIdentifiers.objects.using("mtgjson").create(
            uuid="en-card-1111-1111-1111-111111111111",
            scryfallId="aaaaaaaa-1111-1111-1111-111111111111",
        )
        
        # Phyrexian card
        Card.objects.using("mtgjson").create(
            uuid="ph-card-2222-2222-2222-222222222222",
            name="Phyrexian Card",
            setCode="TST",
            rarity="common",
            layout="normal",
            language="Phyrexian",
            availability="paper",
        )
        CardIdentifiers.objects.using("mtgjson").create(
            uuid="ph-card-2222-2222-2222-222222222222",
            scryfallId="bbbbbbbb-2222-2222-2222-222222222222",
        )
        
        # Japanese card (should be filtered out)
        Card.objects.using("mtgjson").create(
            uuid="ja-card-3333-3333-3333-333333333333",
            name="Japanese Card",
            setCode="TST",
            rarity="common",
            layout="normal",
            language="Japanese",
            availability="paper",
        )
        CardIdentifiers.objects.using("mtgjson").create(
            uuid="ja-card-3333-3333-3333-333333333333",
            scryfallId="cccccccc-3333-3333-3333-333333333333",
        )

    def test_language_filter_excludes_non_english_non_phyrexian(self):
        """Verify that only English and Phyrexian cards are selected."""
        from matchup.views import _get_random_matchup
        
        NUM_TEST_ITERATIONS = 50
        # Get multiple matchups and verify no Japanese cards appear
        seen_uuids = set()
        for _ in range(NUM_TEST_ITERATIONS):
            card1, card2 = _get_random_matchup()
            if card1 and card2:
                seen_uuids.add(card1['uuid'])
                seen_uuids.add(card2['uuid'])
        
        # Verify we saw some cards
        self.assertGreater(len(seen_uuids), 0)
        
        # Verify no Japanese card was selected
        self.assertNotIn("ja-card-3333-3333-3333-333333333333", seen_uuids)
        
        # Verify we can see English and/or Phyrexian cards
        english_or_phyrexian = {
            "en-card-1111-1111-1111-111111111111",
            "ph-card-2222-2222-2222-222222222222",
        }
        self.assertTrue(seen_uuids.issubset(english_or_phyrexian))

@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class LeaderboardTest(TestCase):
    databases = {"default", "mtgjson"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create unmanaged tables in the test mtgjson database
        from django.db import connections
        with connections["mtgjson"].cursor() as cursor:
            cursor.execute(
                'CREATE TABLE IF NOT EXISTS "cards" ('
                '"uuid" TEXT PRIMARY KEY, "name" TEXT, "setCode" TEXT, '
                '"rarity" TEXT, "layout" TEXT, "isFunny" INTEGER, '
                '"isOnlineOnly" INTEGER, "isOversized" INTEGER, '
                '"availability" TEXT, "side" TEXT, "language" TEXT)'
            )
            cursor.execute(
                'CREATE TABLE IF NOT EXISTS "cardIdentifiers" ('
                '"uuid" TEXT PRIMARY KEY, "scryfallId" TEXT)'
            )

    def setUp(self):
        """Seed test data with cards and ratings."""
        # Create test cards
        Card.objects.using("mtgjson").create(
            uuid=CARD_1_UUID,
            name="Lightning Bolt",
            setCode="LEA",
            rarity="common",
            layout="normal",
            language="English",
        )
        CardIdentifiers.objects.using("mtgjson").create(
            uuid=CARD_1_UUID,
            scryfallId="aaaaaaaa-1111-1111-1111-111111111111",
        )

        Card.objects.using("mtgjson").create(
            uuid=CARD_2_UUID,
            name="Black Lotus",
            setCode="LEA",
            rarity="rare",
            layout="normal",
            language="English",
        )
        CardIdentifiers.objects.using("mtgjson").create(
            uuid=CARD_2_UUID,
            scryfallId="bbbbbbbb-2222-2222-2222-222222222222",
        )

    def test_leaderboard_shows_total_votes_zero(self):
        """Test that leaderboard displays zero votes when no votes exist."""
        response = self.client.get("/leaderboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0 total votes")

    def test_leaderboard_shows_total_votes_after_voting(self):
        """Test that leaderboard displays correct total vote count."""
        # Create some votes
        Vote.objects.create(
            card_1_uuid=CARD_1_UUID,
            card_2_uuid=CARD_2_UUID,
            chosen_uuid=CARD_1_UUID,
            ip_address="127.0.0.1",
        )
        Vote.objects.create(
            card_1_uuid=CARD_1_UUID,
            card_2_uuid=CARD_2_UUID,
            chosen_uuid=CARD_2_UUID,
            ip_address="127.0.0.1",
        )
        Vote.objects.create(
            card_1_uuid=CARD_1_UUID,
            card_2_uuid=CARD_2_UUID,
            chosen_uuid=CARD_1_UUID,
            ip_address="127.0.0.1",
        )

        response = self.client.get("/leaderboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3 total votes")

    def test_leaderboard_displays_card_ratings(self):
        """Test that leaderboard shows card ratings when they exist."""
        # Create card ratings
        CardRating.objects.create(name="Lightning Bolt", rating=1600, wins=5, losses=2)
        CardRating.objects.create(name="Black Lotus", rating=1550, wins=3, losses=4)

        response = self.client.get("/leaderboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lightning Bolt")
        self.assertContains(response, "Black Lotus")
        self.assertContains(response, "1600 Elo")
        self.assertContains(response, "5W 2L")

class MatchupStatsCommandTest(TestCase):
    def test_stats_with_no_matchups(self):
        """Test stats command with no unvoted matchups."""
        from io import StringIO
        out = StringIO()
        call_command("matchup_stats", stdout=out)
        output = out.getvalue()
        self.assertIn("No unvoted matchups found", output)

    def test_stats_with_various_age_matchups(self):
        """Test stats command with matchups of different ages."""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        
        # Create matchups with different ages
        # 1 hour old (should be in < 2 hours bucket)
        m1 = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID)
        Matchup.objects.filter(pk=m1.pk).update(created_at=now - timedelta(hours=1))
        
        # 5 hours old (should be in 2-8 hours bucket)
        m2 = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID)
        Matchup.objects.filter(pk=m2.pk).update(created_at=now - timedelta(hours=5))
        
        # 12 hours old (should be in 8-24 hours bucket)
        m3 = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID)
        Matchup.objects.filter(pk=m3.pk).update(created_at=now - timedelta(hours=12))
        
        # 30 hours old (should be in 24+ hours bucket)
        m4 = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID)
        Matchup.objects.filter(pk=m4.pk).update(created_at=now - timedelta(hours=30))
        
        # Already voted matchup (should not be counted)
        m5 = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID, voted=now)
        Matchup.objects.filter(pk=m5.pk).update(created_at=now - timedelta(hours=50))
        
        from io import StringIO
        out = StringIO()
        call_command("matchup_stats", stdout=out)
        output = out.getvalue()
        
        # Verify the output contains expected information
        self.assertIn("Total unvoted matchups: 4", output)
        self.assertIn("< 2 hours", output)
        self.assertIn("2-8 hours", output)
        self.assertIn("8-24 hours", output)
        self.assertIn("24+ hours", output)


class CleanupMatchupsCommandTest(TestCase):
    def test_cleanup_no_old_matchups(self):
        """Test cleanup when there are no old unvoted matchups."""
        from io import StringIO
        out = StringIO()
        call_command("cleanup_matchups", stdout=out)
        output = out.getvalue()
        self.assertIn("No unvoted matchups older than 24 hours found", output)

    def test_cleanup_dry_run(self):
        """Test cleanup in dry-run mode."""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        
        # Create old matchup
        old_matchup = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID)
        Matchup.objects.filter(pk=old_matchup.pk).update(created_at=now - timedelta(hours=30))
        
        from io import StringIO
        out = StringIO()
        call_command("cleanup_matchups", "--dry-run", stdout=out)
        output = out.getvalue()
        
        self.assertIn("DRY RUN", output)
        self.assertIn("Would delete 1 unvoted matchup", output)
        
        # Verify matchup was NOT deleted
        self.assertTrue(Matchup.objects.filter(token=old_matchup.token).exists())

    def test_cleanup_deletes_old_matchups(self):
        """Test that cleanup actually deletes old unvoted matchups."""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        
        # Create old unvoted matchup (should be deleted)
        old_matchup = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID)
        Matchup.objects.filter(pk=old_matchup.pk).update(created_at=now - timedelta(hours=30))
        
        # Create recent unvoted matchup (should NOT be deleted)
        recent_matchup = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID)
        Matchup.objects.filter(pk=recent_matchup.pk).update(created_at=now - timedelta(hours=1))
        
        # Create old voted matchup (should NOT be deleted)
        old_voted_matchup = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID, voted=now)
        Matchup.objects.filter(pk=old_voted_matchup.pk).update(created_at=now - timedelta(hours=30))
        
        from io import StringIO
        out = StringIO()
        call_command("cleanup_matchups", stdout=out)
        output = out.getvalue()
        
        self.assertIn("Successfully deleted 1 unvoted matchup", output)
        
        # Verify correct matchups were deleted/kept
        self.assertFalse(Matchup.objects.filter(token=old_matchup.token).exists())
        self.assertTrue(Matchup.objects.filter(token=recent_matchup.token).exists())
        self.assertTrue(Matchup.objects.filter(token=old_voted_matchup.token).exists())

    def test_cleanup_with_custom_hours(self):
        """Test cleanup with custom hour threshold."""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        
        # Create matchup that's 10 hours old
        matchup = Matchup.objects.create(card_1_uuid=CARD_1_UUID, card_2_uuid=CARD_2_UUID)
        Matchup.objects.filter(pk=matchup.pk).update(created_at=now - timedelta(hours=10))
        
        from io import StringIO
        
        # Should not delete with default 24 hour threshold
        out = StringIO()
        call_command("cleanup_matchups", stdout=out)
        self.assertTrue(Matchup.objects.filter(token=matchup.token).exists())
        
        # Should delete with 8 hour threshold
        out = StringIO()
        call_command("cleanup_matchups", "--hours", "8", stdout=out)
        output = out.getvalue()
        self.assertIn("Successfully deleted 1 unvoted matchup", output)
        self.assertFalse(Matchup.objects.filter(token=matchup.token).exists())

    def test_cleanup_multiple_matchups(self):
        """Test cleanup handles multiple old unvoted matchups correctly."""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        
        # Create 3 old matchups
        for i in range(3):
            m = Matchup.objects.create(
                card_1_uuid=f"test-{i}-1",
                card_2_uuid=f"test-{i}-2"
            )
            Matchup.objects.filter(pk=m.pk).update(created_at=now - timedelta(hours=30))
        
        from io import StringIO
        
        # Test dry-run with multiple matchups
        out = StringIO()
        call_command("cleanup_matchups", "--dry-run", stdout=out)
        output = out.getvalue()
        self.assertIn("Would delete 3 unvoted matchup", output)
        self.assertEqual(Matchup.objects.filter(voted__isnull=True).count(), 3)
        
        # Test actual deletion
        out = StringIO()
        call_command("cleanup_matchups", stdout=out)
        output = out.getvalue()
        self.assertIn("Successfully deleted 3 unvoted matchup", output)
        self.assertEqual(Matchup.objects.filter(voted__isnull=True).count(), 0)
