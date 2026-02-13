import uuid
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

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
            language="en",
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
            language="ph",
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
            language="ja",
            availability="paper",
        )
        CardIdentifiers.objects.using("mtgjson").create(
            uuid="ja-card-3333-3333-3333-333333333333",
            scryfallId="cccccccc-3333-3333-3333-333333333333",
        )

    def test_language_filter_excludes_non_english_non_phyrexian(self):
        """Verify that only English and Phyrexian cards are selected."""
        from matchup.views import _get_random_matchup
        
        # Get 50 matchups and verify no Japanese cards appear
        seen_uuids = set()
        for _ in range(50):
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
