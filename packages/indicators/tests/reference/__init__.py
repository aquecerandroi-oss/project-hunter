"""Frozen copies of production code, kept **only** to prove an optimisation.

``windows_v0.py`` is ``features/windows.py`` exactly as it stood before T2.2b
(commit ``551d542``). It is not imported by anything under
``hunter_indicators``; it exists so a test can run the whole engine on the old
code path and compare canonical bytes with the new one. Never fix a bug here —
if the old code was wrong, the new one is too and the test would hide it.
"""
