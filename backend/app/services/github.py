"""A minimal GitHub REST client for MATT's own repository (change requests only).

It needs MATT_GITHUB_TOKEN: a fine-grained token limited to the one repository, with only
"Contents: read and write" and "Pull requests: read and write". MATT uses it to read files, push
a new branch and open a pull request. It never pushes to the deploy branch and never merges.
"""

import base64
from typing import Any

import httpx

from app.core.config import Settings
from app.services.errors import ServiceError

API = "https://api.github.com"


class GitHubError(ServiceError):
    status_code = 502


class GitHub:
    def __init__(self, settings: Settings) -> None:
        if not settings.github_token:
            raise ServiceError(
                "Add MATT_GITHUB_TOKEN in Render (a fine-grained token for this repository only, "
                "with Contents and Pull requests read/write) to let MATT open pull requests"
            )
        self.repo = settings.github_repo
        self.headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _call(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = httpx.request(method, f"{API}/repos/{self.repo}{path}", headers=self.headers,
                              timeout=30, **kw)  # fmt: skip
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub unreachable: {exc}") from exc
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise GitHubError(f"GitHub HTTP {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    def branch_sha(self, branch: str) -> str:
        data = self._call("GET", f"/git/ref/heads/{branch}")
        if not data:
            raise GitHubError(f"Branch {branch} not found")
        return str(data["object"]["sha"])

    def tree(self, sha: str) -> list[str]:
        data = self._call("GET", f"/git/trees/{sha}", params={"recursive": "1"}) or {}
        return [str(t["path"]) for t in data.get("tree", []) if t.get("type") == "blob"]

    def file(self, path: str, ref: str) -> tuple[str, str] | None:
        """(text, blob sha) of a file at a ref, or None if it does not exist."""
        data = self._call("GET", f"/contents/{path}", params={"ref": ref})
        if not data or data.get("type") != "file":
            return None
        return base64.b64decode(data["content"]).decode("utf-8", "replace"), str(data["sha"])

    def create_branch(self, name: str, sha: str) -> None:
        self._call("POST", "/git/refs", json={"ref": f"refs/heads/{name}", "sha": sha})

    def put_file(self, path: str, text: str, branch: str, message: str) -> None:
        existing = self.file(path, branch)
        body: dict[str, Any] = {
            "message": message, "branch": branch,
            "content": base64.b64encode(text.encode()).decode(),
        }  # fmt: skip
        if existing:
            body["sha"] = existing[1]
        self._call("PUT", f"/contents/{path}", json=body)

    def open_pull(self, title: str, body: str, head: str, base: str) -> str:
        data = self._call("POST", "/pulls", json={"title": title, "body": body, "head": head,
                                                   "base": base})  # fmt: skip
        return str(data["html_url"])
