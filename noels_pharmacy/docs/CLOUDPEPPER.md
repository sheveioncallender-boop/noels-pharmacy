# Cloudpepper Git deployment checklist

- Use a private Git repository and a protected production branch.
- Place the single `noels_pharmacy` folder in the repository root and point Cloudpepper's addons path to the repository root.
- Keep Odoo core and Odoo Mates repositories separate from this repository.
- Deploy immutable tags (for example `19.0.2.0.1`) after staging approval.
- Back up both PostgreSQL and filestore before every module upgrade.
- Restart workers after deployment; close/reopen POS sessions after POS asset changes.
- Update the Apps list and install or upgrade only `noels_pharmacy`.
- Keep uploaded prescriptions in the Odoo filestore/database backup policy.
- Restrict server/database/backup access because the system contains health data.
- Review Odoo logs after rollout for asset, view, access and scheduled-worker errors.
