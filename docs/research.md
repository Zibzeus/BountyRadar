# Research connections

A researcher can summarize the current public program snapshot using a personal provider connection. An administrator can also provide a shared connection. The result is a candidate for review. Each citation points to the snapshot or public page used during that run.

| Connection kind | Endpoint example | Credential |
| --- | --- | --- |
| `openai` | `https://api.openai.com/v1` or a compatible gateway | Provider key and model ID |
| `anthropic` | `https://api.anthropic.com/v1` | Provider key and model ID |
| `firecrawl` | `https://api.firecrawl.dev` or a self-hosted API origin | Firecrawl key when required |
| `agent_reach` | `http://agent-reach:8787` inside Compose | Sidecar token configured by the operator |

Endpoint fields take a base URL. BountyRadar appends the appropriate resource path and sends credentials only to the configured origin. Replacing the endpoint requires re-entering the key. Store the deployment master key separately from database backups. Losing it requires reconnecting providers.

## Browsing permissions

Approve individual HTTPS policy URLs only after reviewing the platform terms, publisher permission, robots directives, and any requirements concerning third-party processing. Add exact URLs to `BOUNTYRADAR_APPROVED_POLICY_URLS`, one per line. Approval applies only to the public policy document. Approved URLs can be revoked without modifying snapshots. Scope assets, repository source files, and links in returned pages are never automatically scheduled.

Firecrawl returns plain Markdown from its v2 API. The reader requests basic proxy mode and does not request browser actions or credential forwarding. The self-hosted service requires network controls protecting internal resources from its outbound browser. See the [Firecrawl scrape API](https://docs.firecrawl.dev/api-reference/endpoint/scrape) and [self-host guide](https://docs.firecrawl.dev/contributing/self-host).

The optional Agent Reach container uses the public web channel at a pinned upstream commit. Its reader sends approved URLs to Jina Reader. It does not mount a user browser profile or expose a general CLI. See [the pinned WebChannel implementation](https://github.com/Panniantong/Agent-Reach/blob/c70ae6da5d39bc90e09ad2ae0575ccc89f31e284/agent_reach/channels/web.py).

An administrator may allow exact internal service origins with `BOUNTYRADAR_PRIVATE_ORIGINS`, comma-separated, for trusted self-hosted gateways and the sidecar. This exception applies to provider connections only. Public policy URL checks do not consult that list.

Immunefi disallows automatic access for monitoring and copying. Its site cannot be browsed through either provider. Store a direct link or use material with independent permission. [Immunefi Terms of Use](https://immunefi.com/terms-of-use/)
