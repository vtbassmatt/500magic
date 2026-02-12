import uuid
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import CardIdentifiers, Matchup, Vote

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
    def _create_matchup(self):
        return Matchup.objects.create(
            card_1_uuid=CARD_1_UUID,
            card_2_uuid=CARD_2_UUID,
        )

    def test_valid_vote_creates_vote_and_redirects(self):
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

    def test_vote_marks_matchup_as_voted(self):
        m = self._create_matchup()
        self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": CARD_2_UUID,
        })
        m.refresh_from_db()
        self.assertIsNotNone(m.voted)

    def test_replay_same_token_rejected(self):
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

    def test_fabricated_token_rejected(self):
        response = self.client.post("/", {
            "matchup_token": str(uuid.uuid4()),
            "chosen_uuid": CARD_1_UUID,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Vote.objects.count(), 0)

    def test_invalid_token_format_rejected(self):
        response = self.client.post("/", {
            "matchup_token": "not-a-uuid",
            "chosen_uuid": CARD_1_UUID,
        })
        self.assertEqual(response.status_code, 400)

    def test_chosen_uuid_not_in_matchup_rejected(self):
        m = self._create_matchup()
        response = self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": "cccccccc-3333-3333-3333-333333333333",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Vote.objects.count(), 0)

    def test_missing_fields_rejected(self):
        response = self.client.post("/", {})
        self.assertEqual(response.status_code, 400)

    def test_vote_records_ip_address(self):
        m = self._create_matchup()
        self.client.post("/", {
            "matchup_token": str(m.token),
            "chosen_uuid": CARD_1_UUID,
        })
        vote = Vote.objects.first()
        self.assertEqual(vote.ip_address, "127.0.0.1")

    def test_vote_respects_x_forwarded_for(self):
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
