# Commit Identity Discipline

**Rule (2026-11-18 closure batch):** every commit to this repository — human or
agent — uses the author/committer identity

```
jacky510 <jacky510@users.noreply.github.com>
```

## Why

GitHub maps commit author emails to accounts. `jacky510@users.noreply.github.com`
resolves to the repository owner; any other address either displays unattributed
or can collide with an unrelated account (an early batch of commits authored as
`stdraw@users.noreply.github.com` was publicly attributed to a third-party
GitHub user until the 2026-11-18 history rewrite fixed the attribution).

## Enforcement

The repo-local git config pins the identity; agents must not override it with
`-c user.email=...` at commit time:

```bash
git config user.name    # jacky510
git config user.email   # jacky510@users.noreply.github.com
```

Post-hoc check (must list exactly the identity above for agent-only history):

```bash
git log --format='%ae%n%ce' | sort -u
```

## History note

2026-11-18: the nine early commits authored as
`stdraw@users.noreply.github.com` (author and, in five cases, committer) were
rewritten to the identity above with `git hash-object -t commit` object-level
rebuild — trees, dates and messages byte-preserved; tags rebuilt; content diff
against the pre-rewrite tip empty.
