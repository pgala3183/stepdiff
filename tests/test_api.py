"""Tests for FastAPI application."""

from __future__ import annotations

from fastapi.testclient import TestClient

from stepdiff.main import app

client = TestClient(app)


def test_root_health() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_api_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_runs() -> None:
    response = client.get("/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_missing_run_returns_404() -> None:
    response = client.get("/runs/nonexistent_run_xyz")
    assert response.status_code == 404
