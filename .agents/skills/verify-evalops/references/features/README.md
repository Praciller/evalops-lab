# Reviewer feature map

Use the [launch, doctor, and cleanup instructions](../../SKILL.md) for either
surface. Public paths below are relative to
`http://127.0.0.1:4174/evalops-lab/` in the local Pages build.

| Journey | Entry | Driver and evidence |
| --- | --- | --- |
| [Public overview](public-console.md#overview) | `/`, Start here | Pages Playwright; screenshots and local-only request assertions |
| [Regression comparison](public-console.md#regression-comparison) | `/comparisons/demo-retrieval-regression-v1/` | Pages Playwright and Python policy; comparison screenshot and safe fixture JSON |
| [Record change explorer](public-console.md#record-change-explorer) | `/comparisons/demo-retrieval-regression-v1/failures/` | Pages Playwright and unit tests; filter assertions and explorer screenshot |
| [Runs and deep links](public-console.md#runs-and-deep-links) | `/runs/`, `/runs/<artifactId>/`, `/comparisons/` | Pages Playwright; direct-load navigation, URL state and run screenshots |
| [Private evaluation and export](local-workspace.md) | `http://127.0.0.1:18234/` (source harness) | Workspace Playwright, Python API and clean wheel; synthetic run/export and failure results |
| [Public file boundary](public-console.md#public-file-boundary) | `/evidence/index.json`, built `out/` | Generator parity, repository/schema tests, Pages output inventory and hashes |

## Observed platform results

These counts are from the initial local audit of source revision
`e92e737d688a67343d77e52225454e9680fda596`. Record fresh results with their
own revision, platform, command, and log.

| Run | Observed result | Evidence to retain when rerunning |
| --- | --- | --- |
| Pages Playwright in Linux with Chromium | 20/20 passed, including direct links, axe checks and screenshot assertions | HTML report and command log |
| Pages Playwright on Windows with Chromium | 18/20 passed. `overview-mobile.png` and `shell-mobile.png` each differed by 12,711 pixels against a 10,700-pixel limit. | Command log and screenshot diffs |
| Workspace source Playwright on Windows | 16/16 passed, including cancellation, restart and rejected export | Command log and Playwright results |

The Windows overview case stopped at the screenshot assertion, before the
theme toggle. Some Workspace Python symlink tests need OS support and
permission to create symlinks. Use `pytest -ra` to record skips.
