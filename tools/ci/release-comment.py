#!/usr/bin/env python3
"""
python3 release-comment.py <repo owner> <repo name> <release tag> <PR snippets ...>

This script takes paths to some number of changelog snippets with filenames in
the form "pr-PRNUM.md" and comments on each PR and associated issue(s)
announcing the release of the PR in the GitHub release with the given tag.

Requirements:
- Python 3.7+
- requests
"""

from __future__ import annotations

import argparse
import json
import os
import os.path
import re
import sys
from dataclasses import (
    InitVar,
    dataclass,
    field,
)

import requests

GITHUB_API_URL = os.environ.get("GITHUB_API_URL", "https://api.github.com")

GRAPHQL_API_URL = os.environ.get("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")


@dataclass
class ReleaseCommenter:
    repo_owner: str
    repo_name: str
    release_tag: str
    token: InitVar[str]
    session: requests.Session = field(init=False)

    def __post_init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"bearer {token}"

    def __enter__(self) -> ReleaseCommenter:
        return self

    def __exit__(self, *_exc) -> None:
        self.session.close()

    @property
    def release_url(self) -> str:
        return f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/tag/{self.release_tag}"

    def get_closed_issues(self, prnum: int) -> list[int]:
        q = (
            "query(\n"
            "  $repo_owner: String!,\n"
            "  $repo_name: String!,\n"
            "  $prnum: Int!,\n"
            "  $cursor: String,\n"
            ") {\n"
            "  repository(owner: $repo_owner, name: $repo_name) {\n"
            "    pullRequest(number: $prnum) {\n"
            "      closingIssuesReferences(\n"
            "        first: 50,\n"
            "        orderBy: {field: CREATED_AT, direction:ASC},\n"
            "        after: $cursor\n"
            "      ) {\n"
            "        nodes {\n"
            "          number\n"
            "        }\n"
            "        pageInfo {\n"
            "          endCursor\n"
            "          hasNextPage\n"
            "        }\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}\n"
        )
        variables = {
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "prnum": prnum,
            "cursor": None,
        }
        closed_issues: list[int] = []
        while True:
            r = self.session.post(
                GRAPHQL_API_URL, json={"query": q, "variables": variables}
            )
            r.raise_for_status()
            resp = r.json()
            if resp.get("errors"):
                sys.exit(
                    "GraphQL API Error:\n" + json.dumps(resp, sort_keys=True, indent=4)
                )
            page = resp["data"]["repository"]["pullRequest"]["closingIssuesReferences"]
            closed_issues.extend(n["number"] for n in page["nodes"])
            variables["cursor"] = page["pageInfo"]["endCursor"]
            if not page["pageInfo"]["hasNextPage"]:
                return closed_issues

    def comment_on_pr(self, prnum: int) -> None:
        self.comment_on_issueoid(
            prnum, f"PR released in [`{self.release_tag}`]({self.release_url})"
        )

    def comment_on_issue(self, issue_num: int) -> None:
        self.comment_on_issueoid(
            issue_num, f"Issue fixed in [`{self.release_tag}`]({self.release_url})"
        )

    def comment_on_issueoid(self, num: int, body: str) -> None:
        r = self.session.post(
            f"{GITHUB_API_URL}/repos/{self.repo_owner}/{self.repo_name}/issues/{num}/comments",
            json={"body": body},
            headers={"Accept": "application/vnd.github+json"},
        )
        r.raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_owner")
    parser.add_argument("repo_name")
    parser.add_argument("release_tag")
    parser.add_argument("pr_snippets", nargs="*")
    args = parser.parse_args()
    try:
        token = os.environ["GITHUB_TOKEN"]
    except KeyError:
        sys.exit("GITHUB_TOKEN not set")
    if not token:
        sys.exit("GITHUB_TOKEN is set to an empty value")
    print(f"GITHUB_TOKEN begins with {token[:6]}")
    with ReleaseCommenter(
        repo_owner=args.repo_owner,
        repo_name=args.repo_name,
        release_tag=args.release_tag,
        token=token,
    ) as rc:
        for name in args.pr_snippets:
            print(f"Processing {name}")
            basename = os.path.basename(name)
            m = re.fullmatch(r"pr-(\d+)(?:\.[a-z]+)?", basename)
            if m:
                prnum = int(m[1])
                rc.comment_on_pr(prnum)
                for issue in rc.get_closed_issues(prnum):
                    print(f" commenting on issue {issue}")
                    rc.comment_on_issue(issue)
            else:
                print(
                    "WARNING: Cannot extract PR number from path",
                    repr(name),
                    file=sys.stderr,
                )


if __name__ == "__main__":
    main()
