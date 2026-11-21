# Licensing records

This folder keeps the records of the rights that contributors give to
TAREEK. Only the maintainer adds files here.

## Contents

- `consents/<github-username>.md` records a signed
  [Contributor License Agreement](../CLA.md). A contributor signs with a
  comment on a pull request. See [CONTRIBUTING.md](../CONTRIBUTING.md).
- `consents/relicense-<github-username>.md` records a relicensing
  permission. A relicensing permission is a statement from a past
  contributor that lets the project change the license of their code.

## When a contributor signs the CLA (maintainer steps)

1. Make sure that the comment came from the account that opened the pull
   request, and that the text is the same as in CONTRIBUTING.md.
2. Make the file `consents/<github-username>.md` with this content:

   ```markdown
   # CLA signature: <github-username>

   - **Full name:** <name from the comment>
   - **GitHub username:** <github-username>
   - **CLA version:** 1.0
   - **Date signed:** <date of the comment, YYYY-MM-DD>
   - **Comment:** <link to the comment>

   ## Exact words of the comment

   > <copy the comment text here>
   ```

3. Commit the file, then merge the pull request.

Copy the text of the comment into the file. A contributor can edit or delete
a GitHub comment later, so the link alone is not a sufficient record.

## Rules for the records

- Do not change or delete a signed record. If a contributor signs a new CLA
  version, add a new file.
- Do not put postal addresses, telephone numbers, or private e-mail
  addresses here. This repository is public, and git keeps all history.
- Keep the full original of a permission (for example, the e-mail with its
  headers) in a private location. Put only a summary here: who gave it, the
  date, the scope, and the exact words of the permission.
