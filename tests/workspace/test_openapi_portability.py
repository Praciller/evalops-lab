"""Keep Workspace OpenAPI deterministic across supported Python versions."""

from __future__ import annotations

import copy

import pytest

from scripts.export_workspace_openapi import canonicalize_openapi_status_422


@pytest.mark.parametrize("phrase", ["Unprocessable Entity", "Unprocessable Content"])
def test_default_validation_description_is_canonical(phrase: str) -> None:
    schema = {
        "paths": {
            "/api/v1/example": {
                "post": {
                    "responses": {
                        "200": {"description": "Successful Response"},
                        "422": {
                            "description": phrase,
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        },
                    }
                }
            }
        }
    }
    original_content = copy.deepcopy(
        schema["paths"]["/api/v1/example"]["post"]["responses"]["422"]["content"]
    )
    normalized = canonicalize_openapi_status_422(schema)
    responses = normalized["paths"]["/api/v1/example"]["post"]["responses"]["422"]
    assert responses["description"] == "Unprocessable Entity"
    assert responses["content"] == original_content
    assert normalized["paths"]["/api/v1/example"]["post"]["responses"]["200"] == {
        "description": "Successful Response"
    }
    assert canonicalize_openapi_status_422(normalized) == normalized


def test_custom_422_and_unrelated_text_are_never_rewritten() -> None:
    schema = {
        "info": {"description": "Unprocessable Content is a new HTTP reason phrase"},
        "paths": {
            "/example": {
                "get": {
                    "responses": {
                        "422": {"description": "Custom validation error"},
                        "400": {"description": "Unprocessable Content"},
                    }
                }
            }
        },
    }
    expected = copy.deepcopy(schema)
    assert canonicalize_openapi_status_422(schema) == expected
