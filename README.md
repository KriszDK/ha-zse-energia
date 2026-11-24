# ZSE Energia (unofficial) for Home Assistant

Billing and contract data from the **ZSE customer zone** (Západoslovenská energetika, Slovakia) as Home Assistant sensors:
when the next payment is due and how much, advance payment, payment method, tariff, last settlement, next annual settlement, balance and monthly consumption.

> **Unofficial.** ZSE has no public API for customers. This integration signs in the same way the web portal does and reads the same JSON data. It can break whenever ZSE changes the portal, and ZSE's terms of use may not allow automated access — use it at your own risk. Not affiliated with ZSE.

## What you get

Per contract account (e.g. electricity), device **ZSE Elektrina …**:

| Entity | Meaning |
|---|---|
| Next payment due / amount | Earliest open invoice; if none, the next advance in the schedule (attribute `source`) |
| Next advance invoice | Date the next advance invoice will be issued |
| Advance payment | Monthly advance, with frequency and due day as attributes |
| Payment method | e.g. direct debit |
| Tariff | Product/tariff name; attributes: product code, settlement periodicity, measurement type, smart meter |
| Last settlement amount / date | Annual settlement invoice (negative = credit/overpayment) |
| Next annual settlement | First day of the month after the current billing period ends |
| Last payment received | Date of the most recent received payment |
| Consumption, latest month / 12-month average | kWh from the portal's monthly series |
| Invoice awaiting payment | Binary sensor (a direct debit may still collect it) |
| Advance due day, contract valid from, E-invoice enabled | Contract and payment settings |
| Distribution tariff, tariffication, HDO code, phases, main circuit breaker, distributor | Technical data (diagnostic) |
| — | Identifiers (EIC, delivery point number) and bank account numbers (IBAN) are deliberately **not** exposed |

Partner level, device **ZSE account**: amount to pay, overdue amount, overpayment, and a *Payment overdue* problem sensor.

## Payment statistics and charts

The portal keeps the whole invoice history (about 15 years). On every update the integration works out what was **actually paid and refunded** and writes it to Home Assistant's long-term statistics (`zse_energia:<series>_<account number>`), so charts reach back to the first invoice:

| Statistic | Meaning |
|---|---|
| `advances_paid` | Advance invoices paid (incl. service fees billed on the same invoice) |
| `settlements_paid` | Surcharges paid after an annual settlement |
| `other_paid` | Other payments (e.g. a corrective invoice) |
| `refunds_received` | Settlement refunds and credits (all negative items) |
| `net_paid` | Payments minus refunds |
| `consumption` | Monthly kWh from the portal |

Each is a cumulative sum, so the *statistics graph* card shows yearly or monthly totals with `stat_types: change`. Sensors: *Paid this year*, *Refunds this year*, *Paid / Refunds / Net paid in total* (the last one carries a per-year table as attributes).

A ready-made dashboard is in [`dashboards/zse_dashboard.yaml`](dashboards/zse_dashboard.yaml). Its texts follow the Home Assistant system language (Hungarian, Slovak or English; English for anything else): the integration's *Dashboard language* sensor serves them, so one dashboard fits every language (fixed-language copies are in `dashboards/static-language/`). It contains: overview, this/last year, yearly and monthly charts, running totals, consumption and a yearly table. Paste it into a dashboard's raw configuration (replace `__ZU__` with your account number first).

How items are counted: an invoice counts when it has been paid (part-paid items count for the paid part), on the date of its last payment (due date if the portal lists no payment). Positive amounts are payments, negative ones refunds/credits. The integration cannot tell what an "Akonto" item or a corrective invoice economically is — they are counted by sign only.

Data is cloud-polled every 6 hours by default (1–24 h in the options) — billing data changes at most daily.

## Low / high tariff (HDO)

The meter's HDO code (e.g. `659346` = programs 659 and 346) says when the low tariff applies. The times come from the public table of the distribution company ZSDIS ([page](https://www.zsdis.sk/Uvod/Online-sluzby/Casy-prepinania-nizkej-a-vysokej-tarify), no API: the integration reads the table data out of the page).

| Entity | Meaning |
|---|---|
| Low tariff active (binary sensor) | on during the low tariff; attributes: today's low and high windows, next change |
| Next tariff change | timestamp of the next switch |
| High tariff hours today | hours of high tariff in today's schedule |
| Low / high tariff (calendar) | low and high periods as events (dashboard, automations) |
| Tariff table (HDO) data | diagnostic: up to date / built-in copy / update failed |

The states change at the exact switching time (no polling). The table is downloaded about once a month and kept in Home Assistant's storage; if the page is unreachable or its layout changed, the previous data stays in use, the *Tariff table data* sensor shows *Update failed* and a warning is logged. A copy shipped with the integration (`hdo_programs.json`) is the last resort. Supplementary programs without a tariff (like 346, "only with 359/659") do not switch the tariff and are ignored. Option *HDO device keeps winter time all year*: some devices ignore daylight saving, so in summer they switch one hour later by the wall clock.

## Installation (HACS custom repository)

1. HACS → ⋮ → *Custom repositories* → add this repository, category *Integration*.
2. Install **ZSE Energia (unofficial)**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → ZSE Energia*, enter the e-mail and password of your ZSE customer zone.

Manual: copy `custom_components/zse_energia` into your Home Assistant `config/custom_components/`.

## Limitations

- Only **e-mail + password** accounts. Google/Facebook sign-in, MFA or a captcha are not supported.
- The password is stored in Home Assistant's config entry (like most integrations that sign in). Use a password you use nowhere else.
- Home Assistant signs in again when its token (about 4 h) expires, i.e. a few times a day. If the portal only allows one session per account, this may sign you out of the website now and then.
- New contract accounts appearing later need an integration reload.
- Statistics for the Energy dashboard are not imported (this is about billing data).

## Development

```text
python -m unittest discover -s tests -v     # offline parser tests
python tools/check_live.py                  # sign in for real, print what the sensors would show (needs: pip install aiohttp)
```

`custom_components/zse_energia/api.py` and `parser.py` have no Home Assistant imports, so they can be exercised on their own.
