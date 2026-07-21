from app.main import create_app


EXPECTED_OPERATIONS = {
    ("get", "/api/health"),
    ("get", "/api/papers"),
    ("post", "/api/papers"),
    ("get", "/api/papers/{paper_id}"),
    ("delete", "/api/papers/{paper_id}"),
    ("get", "/api/papers/{paper_id}/file"),
    ("head", "/api/papers/{paper_id}/file"),
    ("post", "/api/papers/{paper_id}/retry"),
    ("get", "/api/tasks/{task_id}"),
    ("post", "/api/papers/{paper_id}/chat"),
    ("get", "/api/papers/{paper_id}/messages"),
    ("delete", "/api/papers/{paper_id}/messages"),
    ("post", "/api/papers/{paper_id}/explain-text"),
    ("post", "/api/papers/{paper_id}/explain-region"),
    ("get", "/api/papers/{paper_id}/assets/{asset_id}"),
    ("post", "/api/papers/{paper_id}/card"),
    ("get", "/api/papers/{paper_id}/card"),
    ("get", "/api/papers/{paper_id}/annotations"),
    ("post", "/api/papers/{paper_id}/annotations"),
    ("delete", "/api/papers/{paper_id}/annotations/{annotation_id}"),
    ("get", "/api/settings/status"),
    ("put", "/api/settings"),
}


def test_openapi_contains_exactly_the_22_documented_operations() -> None:
    paths = create_app().openapi()["paths"]
    actual = {
        (method, path)
        for path, item in paths.items()
        for method in item
        if method in {"get", "post", "put", "delete", "head"}
    }
    assert actual == EXPECTED_OPERATIONS


def test_all_declared_json_errors_use_unified_schema() -> None:
    paths = create_app().openapi()["paths"]
    for path, item in paths.items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "delete", "head"}:
                continue
            for status, response in operation["responses"].items():
                if int(status) < 400 or "content" not in response:
                    continue
                schema = response["content"]["application/json"]["schema"]
                assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, (
                    method,
                    path,
                    status,
                )


def test_paper_routes_declare_required_status_codes() -> None:
    paths = create_app().openapi()["paths"]

    assert set(paths["/api/papers"]["post"]["responses"]) == {
        "200",
        "202",
        "400",
        "413",
        "415",
        "422",
        "507",
    }
    assert set(paths["/api/papers/{paper_id}"]["get"]["responses"]) == {
        "200",
        "404",
        "422",
    }
    assert set(paths["/api/papers/{paper_id}"]["delete"]["responses"]) == {
        "204",
        "404",
        "409",
        "422",
        "500",
    }
    assert set(paths["/api/papers/{paper_id}/file"]["get"]["responses"]) == {
        "200",
        "206",
        "404",
        "410",
        "416",
        "422",
    }
    assert set(paths["/api/papers/{paper_id}/file"]["head"]["responses"]) == {
        "200",
        "404",
        "410",
        "422",
    }


def test_declared_paper_errors_use_unified_schema() -> None:
    paths = create_app().openapi()["paths"]
    operations = [
        paths["/api/papers"]["post"],
        paths["/api/papers/{paper_id}"]["get"],
        paths["/api/papers/{paper_id}"]["delete"],
        paths["/api/papers/{paper_id}/file"]["get"],
    ]

    for operation in operations:
        for status, response in operation["responses"].items():
            if int(status) < 400:
                continue
            schema = response["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ErrorResponse"}


def test_head_errors_declare_no_response_body() -> None:
    responses = create_app().openapi()["paths"]["/api/papers/{paper_id}/file"]["head"][
        "responses"
    ]

    for status in ("404", "410", "422"):
        assert "content" not in responses[status]
