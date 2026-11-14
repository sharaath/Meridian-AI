import pytest
from app.config import Settings
from app.routes.auth import google_oauth_url
from app.schemas.auth import OAuthExchangeRequest
from unittest.mock import MagicMock, patch


def test_google_oauth_url_generation():
    with patch("app.routes.auth.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            is_supabase_auth_configured=True,
            supabase_url="https://ocqnzkjcffaicqhymwvm.supabase.co",
            supabase_anon_key="anon_test_key",
        )

        # Basic redirect
        res1 = google_oauth_url(redirect_to="https://meridian-ai-frontend.vercel.app/login")
        assert "url" in res1
        assert "https://ocqnzkjcffaicqhymwvm.supabase.co/auth/v1/authorize?provider=google" in res1["url"]
        assert "redirect_to=https%3A%2F%2Fmeridian-ai-frontend.vercel.app%2Flogin" in res1["url"]
        assert "code_challenge" not in res1["url"]

        # With PKCE code_challenge
        res2 = google_oauth_url(
            redirect_to="https://meridian-ai-frontend.vercel.app/login",
            code_challenge="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        )
        assert "code_challenge=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk" in res2["url"]
        assert "code_challenge_method=s256" in res2["url"]


def test_oauth_exchange_request_schema():
    req1 = OAuthExchangeRequest(code="sample_code_123")
    assert req1.code == "sample_code_123"
    assert req1.code_verifier is None

    req2 = OAuthExchangeRequest(code="sample_code_456", code_verifier="sample_verifier_xyz")
    assert req2.code == "sample_code_456"
    assert req2.code_verifier == "sample_verifier_xyz"

