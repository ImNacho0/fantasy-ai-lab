"""GitHub Actions dispatch integration.

The API only asks GitHub to start the existing simulation workflow. It never
runs simulation work in the Render process and never exposes the configured
credential in responses or errors.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GitHubActionsError(RuntimeError):
    """A safe, user-facing error raised when GitHub rejects a dispatch."""


class GitHubActionsConfigurationError(GitHubActionsError):
    """Raised when the Render service is missing the dispatch credential."""


@dataclass(frozen=True)
class GitHubActionsConfig:
    token: Optional[str]
    repository: str = "ImNacho0/fantasy-ai-lab"
    workflow: str = "simulate.yml"
    ref: str = "main"

    @classmethod
    def from_environment(cls) -> "GitHubActionsConfig":
        return cls(
            token=os.getenv("GITHUB_TOKEN"),
            repository=os.getenv("GITHUB_REPOSITORY", "ImNacho0/fantasy-ai-lab"),
            workflow=os.getenv("GITHUB_WORKFLOW", "simulate.yml"),
            ref=os.getenv("GITHUB_REF", "main"),
        )


class GitHubActionsClient:
    """Dispatch a workflow without adding a third-party HTTP dependency."""

    def __init__(self, config: Optional[GitHubActionsConfig] = None):
        self.config = config or GitHubActionsConfig.from_environment()

    @classmethod
    def from_environment(cls) -> "GitHubActionsClient":
        return cls(GitHubActionsConfig.from_environment())

    @property
    def configured(self) -> bool:
        return bool(self.config.token)

    def dispatch(self, inputs: Mapping[str, Any]) -> None:
        if not self.config.token:
            raise GitHubActionsConfigurationError(
                "GITHUB_TOKEN is required to dispatch the simulation workflow"
            )
        if "/" not in self.config.repository:
            raise GitHubActionsConfigurationError("GITHUB_REPOSITORY must use owner/repository format")

        owner, repository = self.config.repository.split("/", 1)
        url = (
            f"https://api.github.com/repos/{owner}/{repository}/actions/workflows/"
            f"{self.config.workflow}/dispatches"
        )
        payload = json.dumps({
            "ref": self.config.ref,
            "inputs": {key: str(value) for key, value in inputs.items()},
        }).encode("utf-8")
        request = Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.config.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "fantasy-ai-lab-render-api",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                if response.status not in (200, 201, 204):
                    raise GitHubActionsError(
                        f"GitHub rejected workflow dispatch with HTTP {response.status}"
                    )
        except HTTPError as exc:
            # Do not include the response body: GitHub can echo request details
            # and this path must never risk leaking an authorization credential.
            raise GitHubActionsError(
                f"GitHub rejected workflow dispatch with HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            raise GitHubActionsError("GitHub workflow dispatch could not be reached") from exc
        except TimeoutError as exc:
            raise GitHubActionsError("GitHub workflow dispatch timed out") from exc
