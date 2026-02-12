import uuid

from django.db import models


class Card(models.Model):
    """Unmanaged model for the mtgjson `cards` table."""

    uuid = models.TextField(primary_key=True)
    name = models.TextField()
    setCode = models.TextField(db_column='setCode')
    rarity = models.TextField()
    layout = models.TextField()
    isFunny = models.BooleanField(db_column='isFunny', null=True)
    isOnlineOnly = models.BooleanField(db_column='isOnlineOnly', null=True)
    isOversized = models.BooleanField(db_column='isOversized', null=True)
    availability = models.TextField(null=True)
    side = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = 'cards'

    def __str__(self):
        return f"{self.name} ({self.setCode})"


class CardIdentifiers(models.Model):
    """Unmanaged model for the mtgjson `cardIdentifiers` table."""

    uuid = models.TextField(primary_key=True)
    scryfallId = models.TextField(db_column='scryfallId', null=True)

    class Meta:
        managed = False
        db_table = 'cardIdentifiers'

    def scryfall_image_url(self):
        if not self.scryfallId:
            return None
        sid = self.scryfallId
        return f"https://cards.scryfall.io/normal/front/{sid[0]}/{sid[1]}/{sid}.jpg"
    
    def __str__(self):
        return self.uuid


class Matchup(models.Model):
    """A generated matchup that can be voted on exactly once."""

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    card_1_uuid = models.TextField()
    card_2_uuid = models.TextField()
    voted = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'matchup_matchup'


class Vote(models.Model):
    """Records a user's choice between two cards."""

    card_1_uuid = models.TextField()
    card_2_uuid = models.TextField()
    chosen_uuid = models.TextField()
    ip_address = models.GenericIPAddressField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'matchup_vote'

    def __str__(self):
        if self.chosen_uuid == self.card_1_uuid:
            return f"({self.card_1_uuid}) 👈 {self.card_2_uuid}"
        if self.chosen_uuid == self.card_2_uuid:
            return f"{self.card_1_uuid} 👉 ({self.card_2_uuid})"
        return f"{self.card_1_uuid} 🤷 {self.card_2_uuid}"
