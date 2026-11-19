# Connector register

Reviewed 19 November 2026. The source slug identifies how a record was acquired. A program's platform identifies its publisher. A dataset revision is secondary evidence. Only a successful authenticated public program read can receive the official label.

| Source | Acquisition and access |
| --- | --- |
| HackerOne | Public dataset by handle. The authenticated Hacker API reads public-mode programs, paginated structured scope and reward-category exclusions. Visibility is checked before fetching detail. [API](https://api.hackerone.com/hacker-resources/) |
| Bugcrowd | Public program dataset. The optional authenticated health check requires a verified eligible account. Its engagement list covers programs the researcher can access and lacks a reliable public flag. Use the dataset or a permitted export for shared catalog ingestion. [Hacker API](https://docs.bugcrowd.com/hacker-api/getting-started/) |
| Intigriti | Public subset of dataset, or optional token for researcher program list and details. Preserve tier, rule description and testing requirements. Beta schema changes fail the source run. [Researcher API](https://kb.intigriti.com/en/articles/8529303-intigriti-researcher-api) |
| YesWeHack | Public dataset or optional personal token for official program list and details. Public flag is checked at both stages. [API](https://api.yeswehack.com/doc) |
| Independent | disclose.io links to published policies. Link reachability and program status are distinct. Unsupported independent sources use import preview. [Directory and license](https://github.com/disclose/diodb) |
| HackenProof | Manual import of permitted program information with source URL. No approved automated feed configured. [Directory](https://hackenproof.com/programs) |
| Immunefi | Official link and separately licensed or authorized material only. Section 4 addresses automated access and manual copying. [Terms](https://immunefi.com/terms-of-use/) |
| Code4rena, Sherlock, Cantina | Manual import of public contest metadata the operator may use, including time window, pool and scoped repository revision. [Code4rena](https://code4rena.com/audits), [Sherlock](https://audits.sherlock.xyz/contests), [Cantina](https://cantina.xyz/competitions) |

[Bounty Targets](https://github.com/arkadiyt/bounty-targets-data) publishes JSON feeds under its repository license. Each record carries attribution, source URL and a hash of the acquired feed. Policy text from other publishers remains subject to its own terms. Refresh jobs validate complete responses before writing. Conditional requests reuse validators for public datasets. Authentication failures and restricted sources are visible in Sources; changing a browsing backend never overrides an access decision.

## Import

In Sources → Import program records, paste one JSON object or an array, preview, then commit. Use stable external IDs. Supply original text and conditions. Missing facts stay unknown. A repository link alone does not establish scope. Web3 contract identity includes the chain; specify network, contract, version or commit where published. Example input below is synthetic and only illustrates the format.

```json
{"external_id":"policy-example","platform":"Independent","name":"Policy example","kind":"contest","status":"unknown","url":"https://example.org/policy","policy":"Review only the published revision.","scope":[{"kind":"repository","raw":"https://example.org/code","effect":"include","commit":"published revision"}],"starts_at":null,"ends_at":null,"prize_pool":null,"ambiguities":["Contest closing time unknown"]}
```

