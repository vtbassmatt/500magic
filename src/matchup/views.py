from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils import timezone

from .elo import update_ratings
from .models import Card, CardIdentifiers, CardRating, Matchup, Vote


def _get_random_matchup():
    """Pick two random distinct cards that have scryfall images.

    We join cards and cardIdentifiers, filter to "real" paper cards,
    and pick two at random using SQLite's RANDOM().
    """
    qs = (
        Card.objects.using('mtgjson')
        .exclude(isFunny=True)
        .exclude(isOnlineOnly=True)
        .exclude(isOversized=True)
        .exclude(side='b')
        .filter(availability__contains='paper')
    )

    # Get two random cards via ORDER BY RANDOM() on uuid
    random_cards = list(qs.order_by('?')[:2])
    if len(random_cards) < 2:
        return None, None

    results = []
    for card in random_cards:
        ident = (
            CardIdentifiers.objects.using('mtgjson')
            .filter(uuid=card.uuid)
            .exclude(scryfallId__isnull=True)
            .exclude(scryfallId='')
            .first()
        )
        if ident:
            results.append({
                'uuid': card.uuid,
                'name': card.name,
                'image_url': ident.scryfall_image_url(),
            })

    if len(results) < 2:
        return _get_random_matchup()  # retry

    return results[0], results[1]


def matchup(request):
    if request.method == 'GET':
        card1, card2 = _get_random_matchup()
        if not card1 or not card2:
            return render(request, 'matchup/error.html', {'message': 'Could not find cards.'})

        m = Matchup.objects.create(
            card_1_uuid=card1['uuid'],
            card_2_uuid=card2['uuid'],
        )

        return render(request, 'matchup/matchup.html', {
            'card1': card1,
            'card2': card2,
            'matchup_token': m.token,
        })

    elif request.method == 'POST':
        matchup_token = request.POST.get('matchup_token', '')
        chosen_uuid = request.POST.get('chosen_uuid', '')

        if not matchup_token or not chosen_uuid:
            return HttpResponseBadRequest('Missing fields')

        # Look up the matchup; reject if not found or already voted
        try:
            m = Matchup.objects.get(token=matchup_token, voted__isnull=True)
        except (Matchup.DoesNotExist, ValueError, ValidationError):
            return HttpResponseBadRequest('Invalid or already-used matchup')

        # Validate chosen card is one of the two in this matchup
        if chosen_uuid not in (m.card_1_uuid, m.card_2_uuid):
            return HttpResponseBadRequest('Invalid choice')

        # Verify both cards exist in mtgjson
        # We generated the matchup so this shouldn't be necessary
        # existing = set(
        #     Card.objects.using('mtgjson')
        #     .filter(uuid__in=[m.card_1_uuid, m.card_2_uuid])
        #     .values_list('uuid', flat=True)
        # )
        # if len(existing) != 2:
        #     return HttpResponseBadRequest('Card not found')

        # Get client IP, respecting X-Forwarded-For
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')

        Vote.objects.create(
            card_1_uuid=m.card_1_uuid,
            card_2_uuid=m.card_2_uuid,
            chosen_uuid=chosen_uuid,
            ip_address=ip,
        )

        # Update Elo ratings
        _update_elo(m.card_1_uuid, m.card_2_uuid, chosen_uuid)

        m.voted = timezone.now()
        m.save(update_fields=['voted'])

        return redirect('matchup')

    return HttpResponseNotAllowed(['GET', 'POST'])


def leaderboard(request):
    top_cards = CardRating.objects.order_by('-rating')[:10]

    # Resolve card names to image URLs via mtgjson
    cards = []
    for cr in top_cards:
        # Find any printing of this card with a scryfall image
        card = (
            Card.objects.using('mtgjson')
            .filter(name=cr.name)
            .first()
        )
        image_url = None
        if card:
            ident = (
                CardIdentifiers.objects.using('mtgjson')
                .filter(uuid=card.uuid)
                .exclude(scryfallId__isnull=True)
                .exclude(scryfallId='')
                .first()
            )
            if ident:
                image_url = ident.scryfall_image_url()
        cards.append({
            'name': cr.name,
            'rating': cr.rating,
            'wins': cr.wins,
            'losses': cr.losses,
            'image_url': image_url,
        })

    return render(request, 'matchup/leaderboard.html', {'cards': cards})


def _update_elo(card_1_uuid: str, card_2_uuid: str, chosen_uuid: str) -> None:
    """Resolve card UUIDs to names and update Elo ratings."""
    names = dict(
        Card.objects.using('mtgjson')
        .filter(uuid__in=[card_1_uuid, card_2_uuid])
        .values_list('uuid', 'name')
    )
    name_1 = names.get(card_1_uuid)
    name_2 = names.get(card_2_uuid)
    if not name_1 or not name_2:
        return

    rating_1, _ = CardRating.objects.get_or_create(name=name_1)
    rating_2, _ = CardRating.objects.get_or_create(name=name_2)

    a_won = chosen_uuid == card_1_uuid
    new_r1, new_r2 = update_ratings(rating_1.rating, rating_2.rating, a_won)

    rating_1.rating = new_r1
    rating_2.rating = new_r2
    if a_won:
        rating_1.wins += 1
        rating_2.losses += 1
    else:
        rating_2.wins += 1
        rating_1.losses += 1

    rating_1.save()
    rating_2.save()
