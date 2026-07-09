"""
Tests that the OpenAPI docs surface is disabled in production (A6-10, docs volet).

The app object is built once at import time (in dev mode under the test env), so
we exercise main._docs_urls() directly for the ENV=production branch and build a
throwaway app to prove the wiring hides the schema.
"""
from fastapi import FastAPI

import main


class TestDocsUrls:
    def test_dev_exposes_docs(self, monkeypatch):
        monkeypatch.delenv("ENV", raising=False)
        urls = main._docs_urls()
        assert urls["docs_url"] == "/api/docs"
        assert urls["redoc_url"] == "/api/redoc"
        assert urls["openapi_url"] == "/api/openapi.json"

    def test_prod_hides_all_docs_urls(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        assert main._docs_urls() == {
            "docs_url": None,
            "redoc_url": None,
            "openapi_url": None,
        }

    def test_prod_app_has_no_openapi_route(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        app_prod = FastAPI(**main._docs_urls())
        assert app_prod.openapi_url is None
        assert app_prod.docs_url is None
        assert app_prod.redoc_url is None

    def test_current_test_app_exposes_openapi(self):
        # Sanity: under the (non-prod) test env, the real app still serves docs.
        assert main.app.openapi_url == "/api/openapi.json"
