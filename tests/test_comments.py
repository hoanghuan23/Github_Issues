from app.services.comment_service import maybe_fetch_comments


class FakeClient:
    def __init__(self):
        self.calls = 0

    def list_issue_comments(self, repo_full_name: str, issue_number: int):
        self.calls += 1
        return [{"github_comment_id": 1}]


def test_comment_api_not_called_when_include_comments_false():
    client = FakeClient()
    comments = maybe_fetch_comments(client, "acme/repo", 1, False, True, True)
    assert comments == []
    assert client.calls == 0


def test_comment_api_called_for_new_issue_when_include_comments_true():
    client = FakeClient()
    comments = maybe_fetch_comments(client, "acme/repo", 1, True, True, False)
    assert comments == [{"github_comment_id": 1}]
    assert client.calls == 1

