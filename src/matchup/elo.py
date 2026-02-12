K_FACTOR = 32
DEFAULT_RATING = 1500.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Calculate the expected score for player A against player B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_ratings(
    rating_a: float, rating_b: float, a_won: bool
) -> tuple[float, float]:
    """Compute new Elo ratings after a matchup.

    Returns (new_rating_a, new_rating_b).
    """
    ea = expected_score(rating_a, rating_b)
    eb = 1.0 - ea
    score_a = 1.0 if a_won else 0.0
    score_b = 1.0 - score_a

    new_a = rating_a + K_FACTOR * (score_a - ea)
    new_b = rating_b + K_FACTOR * (score_b - eb)
    return new_a, new_b
