"""Celery tasks for the pricing app — scheduled market-stat refresh."""

from celery import shared_task


@shared_task
def update_market_stats():
    """Recompute MarketStat rows for every (area, room_type) segment.

    Mirrors `pricing.management.commands.update_market_stats`; scheduled
    daily so the fraud engine's price-anomaly detector and the pricing
    insight endpoints always read fresh market baselines.
    """
    from pricing.services.market_stats import calculate_market_stats

    stats = calculate_market_stats()
    return {"segments": len(stats) if stats else 0}
