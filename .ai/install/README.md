# AI-Kit installation

`.ai/` is the self-contained AI-Kit root. To install it into a project, copy
the `.ai` directory into the project root and run:

```bash
bash .ai/install/install.sh
bash .ai/scripts/bootstrap.sh
bash .ai/scripts/doctor.sh
```

The installer keeps the `.ai` tree and materializes root-level adapters such
as `AGENTS.md`, `CLAUDE.md`, `ANTIGRAVITY.md`, Cursor/Copilot/Claude support,
and the Git hook from templates under `.ai/install/templates/`. Use
`--target <project-root>` when the project is elsewhere, `--dry-run` to preview
copies, and `--force` to replace conflicting managed files.
