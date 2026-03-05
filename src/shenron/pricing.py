"""Model pricing table — Equivalent API Cost for Claude Max subscribers.

Prices are in USD per 1,000,000 tokens (MTok) from the Anthropic API pricing page.
Claude Max subscribers are billed a flat monthly fee; these figures show the
*equivalent API cost* of your token consumption if billed at pay-as-you-go rates.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    """Pricing for a single model (USD per MTok)."""
    input_mtok: float        # standard input
    output_mtok: float       # output
    cache_write_mtok: float  # cache creation (prompt caching write)
    cache_read_mtok: float   # cache read (prompt caching read)


# Anthropic API pricing as of 2026-03 (USD per MTok)
# https://www.anthropic.com/pricing
PRICING: dict[str, ModelPrice] = {
    "claude-opus-4-6": ModelPrice(
        input_mtok=15.00,
        output_mtok=75.00,
        cache_write_mtok=18.75,
        cache_read_mtok=1.50,
    ),
    "claude-sonnet-4-6": ModelPrice(
        input_mtok=3.00,
        output_mtok=15.00,
        cache_write_mtok=3.75,
        cache_read_mtok=0.30,
    ),
    "claude-haiku-4-5-20251001": ModelPrice(
        input_mtok=0.80,
        output_mtok=4.00,
        cache_write_mtok=1.00,
        cache_read_mtok=0.08,
    ),
    "claude-haiku-4-5": ModelPrice(
        input_mtok=0.80,
        output_mtok=4.00,
        cache_write_mtok=1.00,
        cache_read_mtok=0.08,
    ),
}

# Fallback: unknown models use Sonnet pricing
_FALLBACK = PRICING["claude-sonnet-4-6"]


def get_price(model: str | None) -> ModelPrice:
    """Return pricing for a model; fall back to Sonnet if unknown."""
    if not model:
        return _FALLBACK
    # Exact match first
    if model in PRICING:
        return PRICING[model]
    # Partial match (e.g. "claude-sonnet" matches "claude-sonnet-4-6")
    model_lower = model.lower()
    for key, price in PRICING.items():
        if key in model_lower or model_lower in key:
            return price
    return _FALLBACK


def compute_cost(
    model: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Return equivalent API cost in USD for the given token counts."""
    price = get_price(model)
    mtok = 1_000_000
    return (
        input_tokens * price.input_mtok / mtok
        + output_tokens * price.output_mtok / mtok
        + cache_write_tokens * price.cache_write_mtok / mtok
        + cache_read_tokens * price.cache_read_mtok / mtok
    )
