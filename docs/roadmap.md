# DocuMind improvement roadmap

This is a proposed 14-day cycle from the start of the next development sprint. It describes future work. The initial showcase is a snapshot of an already-developed and tested MVP.

| Days | Focus | Done when |
| --- | --- | --- |
| 1–2 | Repository and security review | Document the supported local threat model, verify dependency alerts, and test that release exports exclude secrets and runtime data. |
| 3–4 | Document management | Add a collection filter for unfiled documents and make it clear how to retry individual files after a mixed upload batch. Verify existing documents survive updates. |
| 5–6 | Retrieval | Build a small synthetic PDF/TXT query fixture set. Compare ranking on keyword, multi-term, and no-match queries before tuning. Check that source pages and passage IDs remain accurate. |
| 7–8 | Responsive interface | Check keyboard focus, dialogs, touch targets, and long filenames at laptop and phone widths. Add a browser regression check for upload through citation. |
| 9–10 | Backend reliability | Exercise concurrent uploads and retention cleanup. Document SQLite backup and restore, and add a regression test for the most consequential failure found. |
| 11–12 | Tests, CI, and documentation | Document the merge gate, test a clean Docker start without credentials, and update the troubleshooting guide. |
| 13 | Demo preparation | Build a demo using generated or licensed sample files. Capture current screenshots and verify the walkthrough on a clean machine. |
| 14 | Release review | Audit the approved export, run CI, publish a tagged source update with release notes, and link follow-up issues. No hosted deployment is planned. |

See the [showcase issue tracker](https://github.com/azrvus/documind/issues) for individual improvements and the [release workflow](release-workflow.md) for how code is published.
