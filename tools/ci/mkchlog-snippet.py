#!/usr/bin/env python3
"""
python3 mkchlog-snippet.py [-d <outdir>] <repo owner> <repo name> <PR number>

This script generates a changelog snippet for a given pull request in a GitHub
repository.  The snippet is saved to a file in the `changelog.d` directory by
default or to another directory specified with the `-d` option.

Requirements:
- Python 3.7+
- requests
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import requests

SEMVER_LABELS = [
    # (Label name, category name) in descending order of precedence
    # The categories must align with the category names in
    # changelog.d/scriv.ini
    ("semver-major", "Breaking Changes"),
    ("semver-minor", "Enhancements and New Features"),
    ("semver-patch", "Bug Fixes"),
    ("semver-dependencies", "Dependencies"),
    ("semver-documentation", "Documentation"),
    ("semver-internal", "Internal"),
    ("semver-performance", "Performance"),
    ("semver-tests", "Tests"),
]

GRAPHQL_API_URL = os.environ.get("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")


@dataclass
class Actor:
    login: str
    url: str

    def as_link(self) -> str:
        return f"[@{self.login}]({self.url})"


@dataclass
class Issue:
    number: int
    url: str

    def as_link(self) -> str:
        return f"[#{self.number}]({self.url})"


@dataclass
class PullRequest:
    title: str
    number: str
    url: str
    author: Actor
    closed_issues: list[Issue]
    labels: set[str]

    @property
    def category(self) -> str:
        for lbl, cat in SEMVER_LABELS:
            if lbl in self.labels:
                return cat
        sys.exit("Pull request lacks semver labels")

    def as_link(self) -> str:
        return f"[PR #{self.number}]({self.url})"

    def as_snippet(self) -> str:
        item = self.title.strip()
        if not item.endswith((".", "!", "?")):
            item += "."
        item += "  "
        if self.closed_issues:
            item += (
                "Fixes "
                + ", ".join(i.as_link() for i in self.closed_issues)
                + " via "
            )
        item += f"{self.as_link()} (by {self.author.as_link()})"
        item = textwrap.fill(
            item,
            width=79,
            initial_indent="- ",
            subsequent_indent="  ",
            break_long_words=False,
            break_on_hyphens=False,
        )
        return f"### {self.category}\n\n{item}\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--outdir", default="changelog.d", type=Path)
    parser.add_argument("repo_owner")
    parser.add_argument("repo_name")
    parser.add_argument("prnum", type=int)
    args = parser.parse_args()
    try:
        token = os.environ["GITHUB_TOKEN"]
    except KeyError:
        sys.exit("GITHUB_TOKEN not set")
    pr = get_pr_info(
        repo_owner=args.repo_owner,
        repo_name=args.repo_name,
        prnum=args.prnum,
        token=token,
    )
    args.outdir.mkdir(parents=True, exist_ok=True)
    outfile = args.outdir / f"pr-{args.prnum}.md"
    outfile.write_text(pr.as_snippet())
    print("Changelog snippet saved to", outfile)


def get_pr_info(repo_owner: str, repo_name: str, prnum: int, token: str) -> PullRequest:
    q = (
        "query(\n"
        "  $repo_owner: String!,\n"
        "  $repo_name: String!,\n"
        "  $prnum: Int!,\n"
        "  $closing_cursor: String,\n"
        "  $label_cursor: String\n"
        ") {\n"
        "  repository(owner: $repo_owner, name: $repo_name) {\n"
        "    pullRequest(number: $prnum) {\n"
        "      title\n"
        "      number\n"
        "      url\n"
        "      author {\n"
        "        login\n"
        "        url\n"
        "      }\n"
        "      closingIssuesReferences(\n"
        "        first: 50,\n"
        "        orderBy: {field: CREATED_AT, direction:ASC},\n"
        "        after: $closing_cursor\n"
        "      ) {\n"
        "        nodes {\n"
        "          number\n"
        "          url\n"
        "        }\n"
        "        pageInfo {\n"
        "          endCursor\n"
        "          hasNextPage\n"
        "        }\n"
        "      }\n"
        "      labels(first: 50, after: $label_cursor) {\n"
        "        nodes {\n"
        "          name\n"
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
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "prnum": prnum,
        "closing_cursor": None,
        "label_cursor": None,
    }
    closed_issues: list[str] = []
    labels: set[str] = set()
    with requests.Session() as s:
        s.headers["Authorization"] = f"bearer {token}"
        # We need to loop in order to get all pages of closed issues & labels.
        # The other PR details will be the same in every response, so we just
        # grab the last set of details once the pagination is done.
        while True:
            r = s.post(GRAPHQL_API_URL, json={"query": q, "variables": variables})
            r.raise_for_status()
            resp = r.json()
            if resp.get("errors"):
                sys.exit(
                    "GraphQL API Error:\n" + json.dumps(resp, sort_keys=True, indent=4)
                )
            data = resp["data"]["repository"]["pullRequest"]
            issue_page = data["closingIssuesReferences"]
            closed_issues.extend(Issue(**n) for n in issue_page["nodes"])
            variables["closing_cursor"] = issue_page["pageInfo"]["endCursor"]
            label_page = data["labels"]
            labels.update([n["name"] for n in label_page["nodes"]])
            variables["label_cursor"] = label_page["pageInfo"]["endCursor"]
            if (
                not issue_page["pageInfo"]["hasNextPage"]
                and not label_page["pageInfo"]["hasNextPage"]
            ):
                return PullRequest(
                    title=data["title"],
                    number=data["number"],
                    url=data["url"],
                    author=Actor(**data["author"]),
                    closed_issues=closed_issues,
                    labels=labels,
                )


if __name__ == "__main__":
    main()
