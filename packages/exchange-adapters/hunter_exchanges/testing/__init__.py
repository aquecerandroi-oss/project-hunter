"""Test doubles and recorded fixtures for hunter_exchanges consumers.

``FakeExchangeAdapter`` lets the market-worker (and anything else depending
on :class:`hunter_exchanges.base.ExchangeAdapter`) test against a scripted,
deterministic adapter without any network access. ``fixtures/`` holds small
JSON snapshots of real Binance public responses, recorded once by
``hunter_exchanges.testing.record`` (see that module's docstring for
provenance of each file).
"""
