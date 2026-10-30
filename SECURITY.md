# Security Policy

## Scope

The installable skill contains instructions and metadata only. It adds no executable code, network access, telemetry, external assets, or runtime dependencies.

Security concerns may still include instructions that encourage unsafe conduct, expose sensitive information, misstate evidence, or weaken the refusal boundaries described in `SKILL.md`.

## Reporting a concern

Use the repository host's private vulnerability reporting channel when one is available. The repository's Security tab shows whether private vulnerability reporting is enabled; when it is, use its option to report a vulnerability. Describe the affected file, the risk, a minimal reproduction, and a proposed safe outcome.

Do not include credentials, private data, or suspected secret values in a report. Redact sensitive values and provide only the minimum information needed to reproduce the issue. If no private reporting channel exists, provide a minimal redacted report without publishing exploit details.

## Handling sensitive material

Do not submit personal details, employer or client content, local paths, account identifiers, credentials, private prompts, or proprietary examples. Use only synthetic test material within the permitted example topics.

Reports that request illegal, deceptive, reckless, exploitative, or unsafe behavior will not be treated as feature requests.

## Optional offline tooling

The full package includes an optional Python CLI. It reads local JSON and creates
reports; it does not run proposed actions or request network resources. Input is
limited to 1 MB and 64 levels of nesting, rejects duplicate keys, non-finite
numbers, and invalid Unicode, and validates documented fields. Output creation
is exclusive and rejects existing files and destination symlinks. Choose a trusted
output directory: ancestor directories are user-selected, not a filesystem sandbox.

`scripts/install_skill.py` copies only the skill files listed in
`package-manifest.json`. It writes a hidden staging directory beside the chosen
destination, renames it to the destination, and removes the staging directory
on any failure. It refuses an existing destination, never overwrites, merges,
or deletes an installed skill, creates `.agents/skills` inside a `--project`
directory when missing (refusing when a file stands where either directory
should be), and reads no environment variable. A hard crash or
power loss during installation can leave a hidden `.unconventional-skill-*`
directory holding a partial copy, including a `SKILL.md`, beside the
destination; delete it yourself before another host scans that skills
directory. `--check` only reads.

Lexical screens are conservative review aids with false positives and false
negatives. Neither their results nor schemas certify safety. Sources, selection,
consent, and observations remain declarations; hashes and recomputed unsigned
handoffs establish internal consistency only, not authorship or truth.
