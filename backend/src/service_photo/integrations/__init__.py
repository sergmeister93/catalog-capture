"""
Gemini integration package.

The active /inbound pipeline imports RealGeminiClient directly (see
services/inbound_extraction.py) — there is no mock/real factory anymore.
The MockGeminiClient and its USE_MOCK_GEMINI switch were removed along with
the dormant /jobs pipeline; inbound tests stub at the run_extraction level
instead of swapping the client.
"""
