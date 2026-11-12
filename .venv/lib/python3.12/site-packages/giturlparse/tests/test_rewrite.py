import unittest

from giturlparse import parse

# Test data
REWRITE_URLS = (
    # GitHub SSH
    ("git@github.com:Org/Repo.git", "ssh", "git@github.com:Org/Repo.git"),
    ("git@github.com:Org/Repo.git/", "ssh", "git@github.com:Org/Repo.git"),
    ("git@github.com/Org/Repo", "ssh", "git@github.com:Org/Repo.git"),
    ("git@github.com/Org/Repo/", "ssh", "git@github.com:Org/Repo.git"),
    ("git@github.com:Org/Repo.git", "https", "https://github.com/Org/Repo.git"),
    ("git@github.com:Org/Repo.git", "git", "git://github.com/Org/Repo.git"),
    # GitHub HTTPS
    ("https://github.com/Org/Repo.git", "ssh", "git@github.com:Org/Repo.git"),
    ("https://github.com/Org/Repo.git", "https", "https://github.com/Org/Repo.git"),
    ("https://github.com/Org/Repo.git", "git", "git://github.com/Org/Repo.git"),
    # GitHub GIT
    ("git://github.com/Org/Repo.git", "ssh", "git@github.com:Org/Repo.git"),
    ("git://github.com/Org/Repo.git", "https", "https://github.com/Org/Repo.git"),
    ("git://github.com/Org/Repo.git", "git", "git://github.com/Org/Repo.git"),
    (
        "git://github.com/Org/Repo/blob/master/dir/subdir/path",
        "git",
        "git://github.com/Org/Repo.git/blob/master/dir/subdir/path",
    ),
    # BitBucket SSH
    ("git@bitbucket.org:Org/Repo.git", "ssh", "git@bitbucket.org:Org/Repo.git"),
    ("git@bitbucket.org:Org/Repo.git", "https", "https://Org@bitbucket.org/Org/Repo.git"),
    # BitBucket HTTPS
    ("https://Org@bitbucket.org/Org/Repo.git", "ssh", "git@bitbucket.org:Org/Repo.git"),
    ("https://Org@bitbucket.org/Org/Repo.git", "https", "https://Org@bitbucket.org/Org/Repo.git"),
    # Assembla GIT
    ("git://git.assembla.com/SomeRepoID.git", "ssh", "git@git.assembla.com:SomeRepoID.git"),
    ("git://git.assembla.com/SomeRepoID.git", "git", "git://git.assembla.com/SomeRepoID.git"),
    # Assembla SSH
    ("git@git.assembla.com:SomeRepoID.git", "ssh", "git@git.assembla.com:SomeRepoID.git"),
    ("git@git.assembla.com:SomeRepoID.git", "git", "git://git.assembla.com/SomeRepoID.git"),
    # FriendCode HTTPS
    ("https://friendco.de/Aaron@user/test-repo.git", "https", "https://friendco.de/Aaron@user/test-repo.git"),
    # Generic
    ("git://git.buildroot.net/buildroot", "https", "https://git.buildroot.net/buildroot.git"),
    ("https://git.buildroot.net/buildroot", "git", "git://git.buildroot.net/buildroot.git"),
    ("https://git.buildroot.net/buildroot", "ssh", "git@git.buildroot.net:buildroot.git"),
    # Gitlab SSH
    ("git@host.org:Org/Repo.git", "ssh", "git@host.org:Org/Repo.git"),
    ("git@host.org:9999/Org/Repo.git", "ssh", "git@host.org:9999/Org/Repo.git"),
    ("git@host.org:Org/Repo.git", "https", "https://host.org/Org/Repo.git"),
    ("git@host.org:9999/Org/Repo.git", "https", "https://host.org/Org/Repo.git"),
    # Gitlab HTTPS
    ("https://host.org/Org/Repo.git", "ssh", "git@host.org:Org/Repo.git"),
    ("https://host.org/Org/Repo.git", "https", "https://host.org/Org/Repo.git"),
    ("https://host.org/Org/Group/Repo.git", "ssh", "git@host.org:Org/Group/Repo.git"),
    (
        "https://host.org/Org/Group/Repo/-/blob/master/file.py",
        "ssh",
        "git@host.org:Org/Group/Repo.git/-/blob/master/file.py",
    ),
    (
        "https://host.org/Org/Group/Repo/blob/master/file.py",
        "ssh",
        "git@host.org:Org/Group/Repo.git/blob/master/file.py",
    ),
)

INVALID_PARSE_URLS = (
    ("SSH Bad Username", "gitx@github.com:Org/Repo.git"),
    ("SSH No Repo", "git@github.com:Org"),
    ("HTTPS No Repo", "https://github.com/Org"),
    ("GIT No Repo", "git://github.com/Org"),
)


REWRITE_COMPONENTS = {
    "name": {
        "source": "git@github.com:Org/Repo.git",
        "value": "New-repo",
        "expected": "git@github.com:Org/New-repo.git",
    },
    "owner": {
        "source": "git@github.com:Org/Repo.git",
        "value": "New-Org",
        "expected": "git@github.com:New-Org/Repo.git",
    },
}


class UrlRewriteTestCase(unittest.TestCase):
    def _test_rewrite(self, source, protocol, expected):
        parsed = parse(source)
        self.assertTrue(parsed.valid, f"Invalid Url: {source}")
        return self.assertEqual(parse(source).format(protocol), expected)

    def test_rewrites(self):
        for data in REWRITE_URLS:
            self._test_rewrite(*data)

    def _test_rewrite_components(self, field, data):
        parsed = parse(data["source"])
        setattr(parsed, field, data["value"])
        self.assertTrue(parsed.valid, f"Invalid Url: {data['source']}")
        return self.assertEqual(parsed.url, data["expected"])

    def test_rewrite_components(self):
        for field, data in REWRITE_COMPONENTS.items():
            self._test_rewrite_components(field, data)

    def test_generic_http_normalized(self):
        for domain in ("git.example.org", "git.example.org:8080"):
            for repo in ("project", "project.git", "Org/project.git"):
                source = f"http://{domain}/{repo}"
                expected = source if repo.endswith(".git") else source + ".git"
                with self.subTest(source=source):
                    parsed = parse(source)
                    self.assertTrue(parsed.valid)
                    self.assertEqual(parsed.platform, "base")
                    self.assertEqual(parsed.normalized, expected)

    def test_generic_http_rewrites(self):
        expected = {
            "ssh": "git@git.example.org:project.git",
            "http": "http://git.example.org/project.git",
            "https": "https://git.example.org/project.git",
            "git": "git://git.example.org/project.git",
        }
        for url in expected.values():
            for suffix in ("", ".git"):
                source = url[:-4] + suffix
                parsed = parse(source)
                with self.subTest(source=source, operation="urls"):
                    self.assertTrue(parsed.valid)
                    self.assertEqual(parsed.platform, "base")
                    self.assertEqual(parsed.urls, expected)
                with self.subTest(source=source, operation="url2http"):
                    self.assertEqual(parsed.url2http, expected["http"])
                    self.assertEqual(parsed.format("http"), expected["http"])

    def test_generic_http_name_update(self):
        for source in ("http://git.example.org/project", "http://git.example.org/project.git"):
            with self.subTest(source=source):
                parsed = parse(source)
                parsed.name = "new-project"
                self.assertEqual(parsed.url, "http://git.example.org/new-project.git")
                self.assertEqual(parsed.normalized, parsed.url)


# Test Suite
suite = unittest.TestLoader().loadTestsFromTestCase(UrlRewriteTestCase)
