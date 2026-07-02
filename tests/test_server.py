from fastapi.testclient import TestClient

import server


def test_api_requires_local_token():
    client = TestClient(server.APP)

    assert client.get("/api/settings").status_code == 403
    token = client.get("/api/session").json()["token"]
    assert client.get("/api/settings", headers={"X-Skill-Manager-Token": token}).status_code == 200
