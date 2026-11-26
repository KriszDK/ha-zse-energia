# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for a security problem. Use GitHub's private reporting instead:
*Security → Report a vulnerability* on this repository. You will get an answer as soon as possible.

Never post your ZSE e-mail address, password, tokens, account numbers, invoice data or logs that contain them
in an issue. Remove them from diagnostics and logs first.

## Supported versions

Only the latest release is supported.

## What the integration handles

- It stores the e-mail address and password of your ZSE customer zone in Home Assistant's config entry
  (like most integrations that sign in). Use a password you use nowhere else.
- It talks only to `zse.sk`, `zseenergia.b2clogin.com` and `www.zsdis.sk` (tariff table) over HTTPS.
- Identifiers (EIC, delivery point number) and bank account numbers are not exposed as entities, and the
  diagnostics download redacts the e-mail address and account data.
