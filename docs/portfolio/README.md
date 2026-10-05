# ResearchOS portfolio screenshots

Seven actual browser captures of the locally running application. The report and evidence use the explicitly labeled synthetic DEMO fixture; no live model or search provider was called. Dashboard counts come from the completed demo job.

| File | View |
| --- | --- |
| 01-dashboard.png | Workspace overview with completed research |
| 02-research-setup.png | Research question and execution controls |
| 03-plan-approval.png | Human approval before execution |
| 04-approved-report.png | Approved report, citations, and export controls |
| 05-source-evidence.png | Citation evidence and stored source passage |
| 06-agent-activity.png | Operational execution trace |
| 07-mobile-dashboard.png | Responsive mobile layout |

## Paste into the repository's root README

```markdown
## Product preview

ResearchOS brings research planning, human approval, cited reports, and operational traces into one workspace. These screenshots show its synthetic demo workflow.

![ResearchOS dashboard](docs/portfolio/01-dashboard.png)
![Approved research report](docs/portfolio/04-approved-report.png)
![Source evidence](docs/portfolio/05-source-evidence.png)

<details>
<summary>Research workflow and mobile preview</summary>

![Research setup](docs/portfolio/02-research-setup.png)
![Plan approval](docs/portfolio/03-plan-approval.png)
![Agent activity](docs/portfolio/06-agent-activity.png)
<img src="docs/portfolio/07-mobile-dashboard.png" alt="ResearchOS mobile dashboard" width="320" />

</details>
```

## Regenerate

With the local application running on port 3000, run `node scripts/capture-portfolio.mjs` from `apps/web`. Playwright and its Chromium browser must be installed. Each run creates a separate demo account, project, and completed demo job.
