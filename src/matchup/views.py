from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import redirect, render

from .models import Card, CardIdentifiers, Matchup, Vote


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

        from django.utils import timezone

        m.voted = timezone.now()
        m.save(update_fields=['voted'])

        return redirect('matchup')

    return HttpResponseNotAllowed(['GET', 'POST'])
