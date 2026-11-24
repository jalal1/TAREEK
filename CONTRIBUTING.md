# Contributing to TAREEK

Thank you for your help with TAREEK. This page tells you what to do
before we can merge your pull request.

## Contributor License Agreement (CLA)

All pull requests need a signed CLA before we merge them. This rule applies
to every contributor and to every change, also small ones. It also applies
to the example folders in `examples/` of this repository.

The CLA is in [CLA.md](CLA.md). Read it before you sign. In summary:

- You keep the copyright in your contributions.
- You give Jalal Khalil, and his successors and assigns, a broad license to
  use your contributions. This license includes the right to sublicense.
  Thus, the project can change the license of the code that you contribute.
- You confirm that you have the right to give this license. If your employer
  or university can own the code that you write, get their permission first.
  This is also necessary if a grant or a contract pays you for the work.

You sign the CLA one time. It then applies to all your contributions.

## How to sign the CLA

You sign with one comment on your first pull request.

1. Open your pull request as usual.
2. Post this comment on the pull request from your own GitHub account.
   Replace `<your full name>` with your legal name.

   ```text
   I have read the TAREEK CLA, version 1.0
   (https://github.com/jalal1/TAREEK/blob/main/CLA.md), and I agree
   to its terms for all my present and future contributions.
   Full name: <your full name>
   ```

3. Do not edit or delete the comment after you post it.

That is all. The maintainer records your signature in `licensing/consents/`.
For your next pull requests, you do not sign again.

Only the maintainer can merge a pull request. The maintainer does not merge a
pull request from a person who did not sign.

If you cannot sign in public, contact the maintainer through
[jalal1.github.io](https://jalal1.github.io/) before you start.

## Pull requests

- Keep each pull request on one topic.
- Fill in the pull request template. Tick the CLA box.
- Run the fast tests (`pytest`) before you open the pull request. If you
  change the pipeline, also run the related tests or a small experiment. See
  the test tiers in [pyproject.toml](pyproject.toml).
- If you change the web app (`webapp/`), add screenshots to the pull request.
  For a change to an existing feature, add a screenshot before and after the
  change.
- If you change how to install, configure, or run TAREEK, update
  [README.md](README.md) or the related guide.
- Do not commit API keys, passwords, or other secrets. Replace them with
  placeholders such as `YOUR_CENSUS_API_KEY_HERE`.

## Experiment contributions

You can share a completed TAREEK run in the
[TAREEK-examples](https://github.com/jalal1/TAREEK-examples) repository. Follow its
[CONTRIBUTING.md](https://github.com/jalal1/TAREEK-examples/blob/main/CONTRIBUTING.md) for the folder name, the
files, and the size limit. To show the run as a preset in the web app, also
add `examples/<id>/` to this repository with only `README.md`,
`config_used.json` and `config.xml`. These rules also apply:

- You must have the right to share all files in the experiment, also the
  data in them and the data that the results come from.
- In the `README.md` of the experiment, give the source and the license of
  each input dataset. For example:
  - Road network and points of interest: OpenStreetMap,
    © OpenStreetMap contributors, Open Database License (ODbL).
  - A local travel survey: its publisher, a link, and its license.
- If you cannot find the license of a dataset, do not include that data.
  Tell us the dataset name in the pull request.
- Do not include personal data, such as data about the persons in a travel
  survey that can identify them.

## Where code comes from

Send only code that you wrote yourself.

- Do not copy code from other projects, and do not ask an AI tool to
  translate code from other projects. A translation is also a copy.
- You can use an algorithm from a paper, a standard, or a specification.
  Give the source in a code comment or in the pull request.
- If you looked at the code of another project while you wrote yours, name
  that project in the pull request.
- If you must include code from another source, follow section 7 of the
  [CLA](CLA.md). Send it separately, and give its source and its license.

## AI-assisted contributions

You can use AI tools to write your contribution. We judge a contribution by
its quality, not by the tool that wrote it.

The person who opens a pull request is responsible for it:

- You read the change, and you can explain what it does and why.
- You ran the change and looked at the result yourself. Do not trust only
  the summary of a tool.
- The description and your replies in the review are true for the change.

## Report a problem or ask a question

- Bugs and feature requests:
  [open an issue](https://github.com/jalal1/TAREEK/issues/new/choose).
- Questions: use
  [Discussions](https://github.com/jalal1/TAREEK/discussions).
- Security problems: see [SECURITY.md](SECURITY.md). Do not open a public
  issue.
