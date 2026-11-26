"""Generate the ready-made dashboards (electricity and gas) in ``dashboards/``.

All texts come from the integration's "Dashboard language" sensor (attribute ``t``, see
``custom_components/zse_energia/texts.py``), so one dashboard follows the Home Assistant language.

    python tools/make_dashboards.py
    python tools/make_dashboards.py --zu-electricity 6300000001 --zu-gas 6300000002 --personal-dir ..

Without arguments only the generic files (``__ZU__`` placeholder) are written. With ``--zu-*`` and
``--personal-dir`` copies with your account numbers are written there too: keep those private.
"""
from __future__ import annotations

import argparse
import pathlib

DASH_DIR = pathlib.Path(__file__).resolve().parents[1] / "dashboards"

HEADER = """# ZSE Energia - ready-made dashboard for {what} ("sections" layout, needs Home Assistant 2024.3 or newer).
#
# The texts follow the language of Home Assistant (Settings -> System -> General -> Language): Hungarian,
# Slovak or English, English for any other language. They are served by the integration's
# "Dashboard language" sensor, so one dashboard works for every language. After changing the language
# reload the integration (or restart Home Assistant) once.
#
# How to use
#   1. Replace every  __ZU__  with the number of the {what} contract account (the "variable symbol" on its
#      invoices, 10 digits). It is part of the statistic ids, e.g. zse_energia:advances_paid_6300000001.
#      PowerShell:  (Get-Content {file}) -replace '__ZU__','6300000001' | Set-Content zse_mine.yaml
#   2. Settings -> Dashboards -> Add dashboard -> New dashboard from scratch -> open it -> pencil ->
#      three dots -> "Raw configuration editor" and paste the whole file.
#
# The charts read long-term STATISTICS (written by the integration), so they show the whole history.
# Their legend names also come from the integration, in the Home Assistant language.
{extra}#
# If a statistics chart is empty: Developer tools -> Statistics -> look for "zse_energia:" entries
# (they appear a minute after the first update of the integration).
"""

EXTRA = {
    "electricity": "",
    "gas": (
        "#\n# Gas and electricity can be set up as two entries of the integration (two ZSE logins) or as one\n"
        "# (one login with both contracts). The cards pick the entities of their own commodity either way.\n"
    ),
}

LOAD = """{% set u = integration_entities('zse_energia') | select('is_state_attr', 'zse_key', 'ui') | list %}
{% set T = state_attr(u[0], 't') if u else none %}
"""

FALLBACK = (
    '*Update ZSE Energia to 0.5.0 or newer and restart Home Assistant: the dashboard texts come from '
    'its "Dashboard language" sensor.*'
)

NUM = """{% macro m2(v) -%}{{ '{:,.2f}'.format(v | float(0)) | replace(',', '#') | replace('.', T.ds) | replace('#', T.ts) }}{%- endmacro %}
{% macro m0(v) -%}{{ '{:,.0f}'.format(v | float(0)) | replace(',', '#') | replace('#', T.ts) }}{%- endmacro %}
"""

# {kind} is filled in per dashboard; an entity without zse_kinds (older integration) matches everything
IDS = """{% set kind = '{kind}' %}
{% set ids = integration_entities('zse_energia') %}
{% macro find(key) -%}
{%- set ns = namespace(r='') -%}
{%- for x in ids | select('is_state_attr', 'zse_key', key) -%}
{%- set k = state_attr(x, 'zse_kinds') -%}
{%- if not ns.r and (not k or kind in k) -%}{%- set ns.r = x -%}{%- endif -%}
{%- endfor -%}
{{ ns.r }}
{%- endmacro %}
{% macro val(key) -%}
{%- set x = find(key) -%}
{%- if x and states(x) not in ['unknown', 'unavailable'] -%}
{%- set st = states(x) -%}
{%- set un = state_attr(x, 'unit_of_measurement') -%}
{%- if un and is_number(st) -%}{{ m0(st) }}{{ T.nb }}{{ un }}{%- else -%}{{ st }}{%- endif -%}
{%- else -%}–{%- endif -%}
{%- endmacro %}
{% macro eur(key) -%}
{%- set x = find(key) -%}
{%- if x and states(x) not in ['unknown', 'unavailable'] -%}{{ m2(states(x)) }}{{ T.nb }}€{%- else -%}–{%- endif -%}
{%- endmacro %}
{% macro hrs(key) -%}
{%- set x = find(key) -%}
{%- if x and states(x) not in ['unknown', 'unavailable'] -%}{{ m2(states(x)) }}{{ T.nb }}h{%- else -%}–{%- endif -%}
{%- endmacro %}
{% macro yn(key) -%}
{%- set x = find(key) -%}
{%- if x and states(x) in ['on', 'off'] -%}{{ T.yes if states(x) == 'on' else T.no }}{%- else -%}–{%- endif -%}
{%- endmacro %}
"""

HIST = """{% set kind = '{kind}' %}
{% set hn = namespace(m=[]) %}
{% for x in integration_entities('zse_energia') | select('is_state_attr', 'zse_history', true) %}{% set k = state_attr(x, 'zse_kinds') %}{% if not k or kind in k %}{% set hn.m = hn.m + [x] %}{% endif %}{% endfor %}
{% set m = hn.m %}
"""


def icon(name: str, text_expr: str) -> str:
    return f'<ha-icon icon="mdi:{name}"></ha-icon> **{{{{ {text_expr} }}}}**'


class Builder:
    def __init__(self, kind: str, zu: str = "__ZU__") -> None:
        self.kind = kind
        self.zu = zu  # placeholder of the contract-account number in the statistic ids

    # ------------------------------------------------------------------------------------ plumbing
    def md(self, body: str, *, ids: bool = False, hist: bool = False) -> str:
        """A Markdown card whose content is localized through T."""
        parts = [LOAD, "{% if T %}\n", NUM]
        if ids:
            parts.append(IDS.replace("{kind}", self.kind))
        if hist:
            parts.append(HIST.replace("{kind}", self.kind))
        parts += [body.strip("\n"), "\n{% else %}\n", FALLBACK, "\n{% endif %}"]
        text = "".join(parts)
        pad = " " * 14
        lines = "\n".join((pad + line) if line else "" for line in text.split("\n"))
        return "          - type: markdown\n            content: |\n" + lines + "\n"

    def chart(self, entities, *, kind, period, days, stat="change", legend="") -> str:
        ents = "".join(
            f"              - entity: zse_energia:{k}_{self.zu}\n                color: '{c}'\n" for k, c in entities
        )
        return (
            "          - type: statistics-graph\n"
            f"            chart_type: {kind}\n"
            f"            period: {period}\n"
            f"            days_to_show: {days}\n"
            f"            stat_types:\n              - {stat}\n"
            + {"hide": "            hide_legend: true\n", "expand": "            expand_legend: true\n"}.get(legend, "")
            + f"            entities:\n{ents}"
        )

    def title_card(self, icon_name: str, key: str, note: str = "") -> str:
        extra = f"\n*{{{{ {note} }}}}*" if note else ""
        return self.md(icon(icon_name, key) + extra)

    # ------------------------------------------------------------------------------------- cards
    def next_payment(self) -> str:
        return self.md(
            icon("calendar-clock", "T.h_next")
            + """

## {{ val('next_payment_date') }}
### {{ eur('next_payment_amount') }}
*{{ T.l_pay_caption }}*

- {{ T.l_open }}: **{{ eur('to_pay') }}**
- {{ T.l_overdue }}: **{{ eur('overdue') }}**
- {{ T.l_advance }}: **{{ eur('advance_amount') }}**
- {{ T.l_method }}: **{{ val('payment_method') }}**
""",
            ids=True,
        )

    def settlement(self) -> str:
        return self.md(
            icon("file-document-check", "T.h_settle")
            + """

## {{ val('next_settlement') }}
*{{ T.l_settle_caption }}*

- {{ T.l_last_settle }}: **{{ eur('last_settlement_amount') }}** ({{ val('last_settlement_date') }})
- {{ T.l_tariff }}: **{{ val('tariff') }}**

*{{ T.l_settle_note }}*
""",
            ids=True,
        )

    def tariff(self) -> str:
        """Electricity only: the low/high tariff (HDO) band."""
        return self.md(icon("flash-triangle", "T.h_tariff") + "\n" + TARIFF_BODY, ids=True)

    def this_last(self) -> str:
        return self.md(
            icon("chart-box", "T.h_years")
            + """

{% macro blk(ys, year, label) -%}
{%- set r = ys | selectattr('year', 'eq', year) | list -%}
### {{ year }} · {{ label }}
{% if r -%}
{%- set y = r[0] -%}
## {{ m2(y.net) }}{{ T.nb }}€
*{{ T.net_caption }}*
- {{ T.adv }}: {{ m2(y.advances) }}{{ T.nb }}€
- {{ T.extra }}: {{ m2(y.settlements + y.other) }}{{ T.nb }}€
- {{ T.refund }}: {{ m2(y.refunds) }}{{ T.nb }}€
{%- else -%}
–
{%- endif -%}
{%- endmacro %}
{% if m %}
{% set ys = state_attr(m[0], 'yearly') or [] %}
{{ blk(ys, now().year, T.this_label) }}

{{ blk(ys, now().year - 1, T.last_label) }}

*{{ T.years_note }}*
{% else %}
{{ T.notfound }}
{% endif %}
""",
            hist=True,
        )

    def table(self) -> str:
        return self.md(
            icon("table", "T.h_table")
            + """

{% if m %}
{% set e = m[0] %}
{% set ys = state_attr(e, 'yearly') or [] %}
{% set since = (state_attr(e, 'since') or '') | string %}
{% set done = ys | selectattr('year', 'lt', now().year) | list %}
{% set recent = done[-5:] %}
{{ T.t_intro }}

| {{ T.c_year }} | {{ T.c_paid }} | {{ T.c_ref }} | {{ T.c_net }} |
|---|--:|--:|--:|
{% for y in ys | reverse -%}
| {{ y.year }}{% if y.year == now().year %} *({{ T.ongoing }})*{% elif ys and y.year == ys[0].year and since[5:] != '01-01' %} *({{ T.partial }})*{% endif %} | {{ m2(y.paid) }}{{ T.nb }}€ | {{ m2(y.refunds) }}{{ T.nb }}€ | **{{ m2(y.net) }}{{ T.nb }}€** |
{% endfor %}
{% if recent %}
{% set n = recent | length %}
{% set avg_y = (recent | map(attribute='net') | sum) / n %}
{{ T.t_avg | replace('{y}', m0(avg_y)) | replace('{m}', m0(avg_y / 12)) | replace('{n}', n | string) }}
{% endif %}

*{{ T.t_note }}*
{% else %}
{{ T.notfound }}
{% endif %}
""",
            hist=True,
        )

    def totals(self) -> str:
        return self.md(
            icon("sigma", "T.h_totals")
            + """

- {{ T.d_paid_total }}: **{{ eur('paid_total') }}**
- {{ T.d_refunds_total }}: **{{ eur('refunds_total') }}**
- {{ T.d_net_total }}: **{{ eur('net_paid_total') }}**
- {{ T.d_paid_year }}: **{{ eur('paid_this_year') }}**
- {{ T.d_refunds_year }}: **{{ eur('refunds_this_year') }}**
- {{ T.d_overpay }}: **{{ eur('overpayment') }}**
""",
            ids=True,
        )

    def billing(self) -> str:
        return self.md(
            icon("receipt-text-clock", "T.h_billing")
            + """

- {{ T.d_last_pay }}: **{{ val('last_payment_date') }}**
- {{ T.d_next_inv }}: **{{ val('next_invoice_date') }}**
- {{ T.d_due_day }}: **{{ val('advance_due_day') }}**
- {{ T.d_pending }}: **{{ yn('payment_pending') }}**
- {{ T.d_overdue_flag }}: **{{ yn('overdue_flag') }}**
""",
            ids=True,
        )

    def consumption(self) -> str:
        if self.kind == "gas":
            return self.md(
                icon("fire", "T.h_cons")
                + """

{% set gl = find('gas_consumption_last') %}
{% set mr = find('meter_reading') %}
{% set vol = state_attr(gl, 'volume_m3') if gl else none %}
- {{ T.d_gas_last }}: **{{ val('gas_consumption_last') }}**{% if vol %} ({{ m0(vol) }}{{ T.nb }}m³){% endif %}
{% if gl and state_attr(gl, 'period_from') %}- {{ T.t_period }}: {{ state_attr(gl, 'period_from') }} – {{ state_attr(gl, 'period_to') }}
{% endif %}- {{ T.d_expected }}: **{{ val('expected_consumption') }}**
- {{ T.d_meter }}: **{{ val('meter_reading') }}**{% if mr and state_attr(mr, 'reading_date') %} ({{ state_attr(mr, 'reading_date') }}){% endif %}
""",
                ids=True,
            )
        return self.md(
            icon("flash", "T.h_cons")
            + """

- {{ T.d_cons_last }}: **{{ val('consumption_latest_month') }}**
- {{ T.d_cons_avg }}: **{{ val('consumption_monthly_average') }}**
""",
            ids=True,
        )

    def contract(self) -> str:
        if self.kind == "gas":
            return self.md(
                icon("file-document-outline", "T.h_contract")
                + """

{% set pl = find('price_list') %}
{% set tf = find('tariff') %}
- {{ T.d_valid }}: **{{ val('contract_valid_from') }}**
- {{ T.d_distributor }}: **{{ val('distributor') }}**
- {{ T.d_dist_tariff }}: **{{ val('distribution_tariff') }}**
- {{ T.d_pricing }}: **{{ val('price_list') }}**
{% if tf and state_attr(tf, 'settlement_periodicity') %}- {{ T.d_periodicity }}: **{{ state_attr(tf, 'settlement_periodicity') }}**
{% endif %}{% if pl and state_attr(pl, 'usage') %}- {{ T.d_use }}: **{% for u in state_attr(pl, 'usage') %}{{ T['u_' ~ u] }}{% if not loop.last %}, {% endif %}{% endfor %}**
{% endif %}- {{ T.d_einvoice }}: **{{ yn('e_invoice') }}**
""",
                ids=True,
            )
        return self.md(
            icon("file-document-outline", "T.h_contract")
            + """

- {{ T.d_valid }}: **{{ val('contract_valid_from') }}**
- {{ T.d_distributor }}: **{{ val('distributor') }}**
- {{ T.d_dist_tariff }}: **{{ val('distribution_tariff') }}**
- {{ T.d_tariffication }}: **{{ val('tariffication') }}**
- {{ T.d_hdo }}: **{{ val('hdo_code') }}**
- {{ T.d_phases }}: **{{ val('phases') }}**
- {{ T.d_breaker }}: **{{ val('circuit_breaker') }}**
- {{ T.d_einvoice }}: **{{ yn('e_invoice') }}**
""",
            ids=True,
        )

    def periods_table(self) -> str:
        """Gas: every billing period as the portal reports it (kWh), newest first."""
        return self.md(
            icon("table", "T.t_period")
            + """

{% set gl = find('gas_consumption_last') %}
{% set ps = (state_attr(gl, 'periods') or []) if gl else [] %}
{% if ps %}
| {{ T.t_period }} | kWh |
|---|--:|
{% for q in ps | reverse -%}
| {{ q['from'] }} – {{ q['to'] }} | **{{ m0(q.kwh) }}** |
{% endfor %}

*{{ T.t_period_note }}*
{% else %}
{{ T.notfound }}
{% endif %}
""",
            ids=True,
        )

    @staticmethod
    def folding(head: str, body: str) -> str:
        """A card with ``head`` always visible; a click on it folds ``body`` out (HACS: expander-card).

        ``head`` is one grid card, ``body`` any number of them (indent 10); they are nested one level deeper.
        """
        first, *rest = head.split("\n")
        title = "\n".join(
            ["  " + ln for ln in [first.replace("- ", "  ", 1)] + rest if ln.strip()]
        )
        # the children sit in a plain grid card (one column): its own gap keeps the cards apart, whatever
        # spacing options the installed expander-card version has
        inner = "\n".join(("        " + ln) if ln else "" for ln in body.rstrip("\n").split("\n"))
        return (
            "          - type: custom:expander-card\n"
            "            grid_options:\n              columns: full\n"
            "            clear: true\n"
            "            padding: 0px\n"
            "            child-padding: 8px 0px 0px 0px\n"  # top only: the gap under the header
            "            title-card-padding: 0px\n"
            "            title-card-button-overlay: true\n"
            "            title-card:\n" + title + "\n"
            "            cards:\n"
            "              - type: grid\n                columns: 1\n                square: false\n"
            "                cards:\n" + inner + "\n"
        )

    # ------------------------------------------------------------------------------------ whole
    def payments_cards(self) -> str:
        tariff = "" if self.kind == "gas" else self.tariff()
        return self.next_payment() + self.settlement() + self.this_last() + tariff

    def details_cards(self) -> str:
        return self.totals() + self.billing() + self.consumption() + self.contract()

    def charts_cards(self) -> str:
        blue, orange, grey, green, purple, yellow = "#3d7ee0", "#e0803d", "#9b9b9b", "#2e9e5b", "#7a4de0", "#e0c23d"
        gas = self.kind == "gas"
        charts = (
            self.title_card("chart-bar", "T.c_pay_year")
            + self.chart(
                [("advances_paid", blue), ("settlements_paid", orange), ("other_paid", grey),
                 ("refunds_received", green), ("net_paid", purple)],
                kind="bar", period="year", days=7000, legend="expand",
            )
            + self.title_card("fire" if gas else "flash", "T.c_cons_period" if gas else "T.c_cons_year")
        )
        charts += self.chart([("consumption", yellow)], kind="bar", period="year", days=7000 if gas else 3000, legend="hide")
        if gas:
            charts += self.periods_table()
        if not gas:  # gas is only known per billing period, a monthly chart would be a made-up flat line
            charts += self.title_card("flash", "T.c_cons_month") + self.chart(
                [("consumption", yellow)], kind="bar", period="month", days=1100, legend="hide"
            )
        return charts

    # ------------------------------------------------------------------------------------ whole
    def build(self, file_name: str) -> str:
        grid = "      - type: grid\n        cards:\n"
        what = self.kind
        return (
            HEADER.format(what=what, file=file_name, extra=EXTRA[self.kind])
            + f"title: ZSE {what}\nviews:\n"
            + "  - path: zse-payments\n    icon: mdi:cash-multiple\n    type: sections\n    max_columns: 2\n    sections:\n"
            + grid + self.payments_cards()
            + grid + self.charts_cards()
            + "  - path: zse-table\n    icon: mdi:table\n    type: sections\n    max_columns: 2\n    sections:\n"
            + grid + self.table()
            + "  - path: zse-details\n    icon: mdi:information-outline\n    type: sections\n    max_columns: 2\n    sections:\n"
            + grid + self.totals() + self.billing() + self.consumption()
            + grid + self.contract()
        )


TARIFF_BODY = r"""
{% set b = ids | select('is_state_attr', 'zse_key', 'low_tariff') | list %}
{% set d = ids | select('is_state_attr', 'zse_key', 'hdo_data') | list %}
{% if b %}
{% set e = b[0] %}
{% set hh = state_attr(e, 'high_hours_today') | float(0) %}
{% set G = 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%201%201%22%20preserveAspectRatio%3D%22none%22%3E%3Crect%20width%3D%221%22%20height%3D%221%22%20fill%3D%22%238bc34a%22%2F%3E%3C%2Fsvg%3E' %}
{% set O = 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%201%201%22%20preserveAspectRatio%3D%22none%22%3E%3Crect%20width%3D%221%22%20height%3D%221%22%20fill%3D%22%23f26a21%22%2F%3E%3C%2Fsvg%3E' %}
{% set B = 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%201%201%22%20preserveAspectRatio%3D%22none%22%3E%3Crect%20width%3D%221%22%20height%3D%221%22%20fill%3D%22%232196f3%22%2F%3E%3C%2Fsvg%3E' %}
{% set SCALE %}data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22720%22%20height%3D%2218%22%20viewBox%3D%220%200%20720%2018%22%20font-family%3D%22sans-serif%22%20font-size%3D%2212%22%20fill%3D%22%239aa0a6%22%3E%3Ctext%20x%3D%220%22%20y%3D%2213%22%3E0%3C%2Ftext%3E%3Ctext%20x%3D%2290%22%20y%3D%2213%22%20text-anchor%3D%22middle%22%3E3%3C%2Ftext%3E%3Ctext%20x%3D%22180%22%20y%3D%2213%22%20text-anchor%3D%22middle%22%3E6%3C%2Ftext%3E%3Ctext%20x%3D%22270%22%20y%3D%2213%22%20text-anchor%3D%22middle%22%3E9%3C%2Ftext%3E%3Ctext%20x%3D%22360%22%20y%3D%2213%22%20text-anchor%3D%22middle%22%3E12%3C%2Ftext%3E%3Ctext%20x%3D%22450%22%20y%3D%2213%22%20text-anchor%3D%22middle%22%3E15%3C%2Ftext%3E%3Ctext%20x%3D%22540%22%20y%3D%2213%22%20text-anchor%3D%22middle%22%3E18%3C%2Ftext%3E%3Ctext%20x%3D%22630%22%20y%3D%2213%22%20text-anchor%3D%22middle%22%3E21%3C%2Ftext%3E%3Ctext%20x%3D%22720%22%20y%3D%2213%22%20text-anchor%3D%22end%22%3E24%3C%2Ftext%3E%3C%2Fsvg%3E{% endset %}
{% set nm = now().hour * 60 + now().minute %}
{% macro seg(a, b, k) -%}
<img src="{{ B if k == 'N' else (O if k == 'H' else G) }}" width="{{ ((b - a) / 1440 * 99) | round(2) }}%" height="24" title="{{ (T.t_now ~ ' ' ~ ('%02d:%02d' | format(nm // 60, nm % 60))) if k == 'N' else ('%02d:%02d–%02d:%02d' | format(a // 60, a % 60, b // 60, b % 60) ~ ' · ' ~ (T.t_high if k == 'H' else T.t_low) ~ ' · ' ~ (b - a) ~ ' min') }}">
{%- endmacro %}
{% macro emit(a, b, k) -%}
{%- if a <= nm and nm < b -%}
{%- set m2 = [nm + 10, b] | min -%}
{%- if nm > a -%}{{ seg(a, nm, k) }}{%- endif -%}{{ seg(nm, m2, 'N') }}{%- if b > m2 -%}{{ seg(m2, b, k) }}{%- endif -%}
{%- else -%}{{ seg(a, b, k) }}{%- endif -%}
{%- endmacro %}
{% macro strip(ws) -%}
{%- set ns = namespace(cur=0, out='') -%}
{%- for w in ws -%}
{%- set p = w.split('-') -%}
{%- set a = p[0][0:2] | int * 60 + p[0][3:5] | int -%}
{%- set z = p[1][0:2] | int * 60 + p[1][3:5] | int -%}
{%- if a > ns.cur -%}{%- set ns.out = ns.out ~ emit(ns.cur, a, 'L') -%}{%- endif -%}
{%- set ns.out = ns.out ~ emit(a, z, 'H') -%}
{%- set ns.cur = z -%}
{%- endfor -%}
{%- if ns.cur < 1440 -%}{%- set ns.out = ns.out ~ emit(ns.cur, 1440, 'L') -%}{%- endif -%}
{{ ns.out }}
{%- endmacro %}
## {{ T.t_low if is_state(e, 'on') else T.t_high }}
*{{ T.t_until }} {{ state_attr(e, 'changes_at_local') or '–' }}*

<img src="{{ G }}" width="12" height="12"> {{ T.t_low }} ({{ '%g' | format(24 - hh) }} h)&nbsp;&nbsp;&nbsp;<img src="{{ O }}" width="12" height="12"> {{ T.t_high }} ({{ '%g' | format(hh) }} h)&nbsp;&nbsp;&nbsp;<img src="{{ B }}" width="4" height="12"> {{ T.t_now }}

{{ strip(state_attr(e, 'high_windows_today') or []) }}
<img src="{{ SCALE }}" width="99%">

- {{ T.t_high }}:
{% for w in (state_attr(e, 'high_windows_today') or []) %}{% set q = w.split('-') %}{% set mins = (q[1][0:2] | int * 60 + q[1][3:5] | int) - (q[0][0:2] | int * 60 + q[0][3:5] | int) %}  - {{ q[0] }}–{{ q[1] }} ({{ mins }} min)
{% endfor %}
<br>

- {{ T.t_hours }}: **{{ hrs('high_tariff_hours_today') }}**
- {{ T.t_program }}: **{{ (state_attr(e, 'programs') or []) | join(' + ') or '–' }}**
{% if d %}- {{ T.t_data }}: **{{ T['t_' ~ states(d[0])] if states(d[0]) in ['up_to_date', 'built_in', 'error'] else '–' }}**{% endif %}
{% else %}
{{ T.t_none }}
{% endif %}
"""


COMBINED_HEADER = """# ZSE Energia - ready-made dashboard: electricity and gas in one ("sections" layout, Home Assistant 2024.3+).
#
# Two sections side by side on every view (electricity and gas), plus a view with the charts and a stacked
# chart of the net amount paid per year. Works with two entries of the integration (two ZSE logins) or one
# login with both contracts. Texts follow the Home Assistant language.
#
# How to use
#   1. Replace  __ZU_E__  with the electricity and  __ZU_G__  with the gas contract-account number
#      (10 digits, the variable symbol on the invoices).
#   2. Settings -> Dashboards -> Add dashboard -> New dashboard from scratch -> open it -> pencil ->
#      three dots -> "Raw configuration editor" and paste the whole file.
#
# If a statistics chart is empty: Developer tools -> Statistics -> look for "zse_energia:" entries.
"""


def build_combined(labels: tuple[str, str, str], charts_title: str, expander: bool = False) -> str:
    """Electricity and gas on the same views; charts in a view of their own."""
    el, gs = Builder("electricity", "__ZU_E__"), Builder("gas", "__ZU_G__")

    def section(label: str, icon_name: str, cards: str, color: str | None = None) -> str:
        text = (
            "      - type: grid\n        cards:\n"
            f"          - type: heading\n            icon: mdi:{icon_name}\n            heading: {label}\n"
            "            heading_style: title\n" + cards
        )
        if color:
            text += f"        background:\n          color: {color}\n          opacity: 10\n"
        return text

    def view(path: str, icon_name: str, title: str = "") -> str:
        head = f"  - type: sections\n    path: {path}\n    icon: mdi:{icon_name}\n"
        if title:
            head += f"    title: {title}\n"
        return head + "    max_columns: 2\n    sections:\n"

    e_label, g_label, t_label = labels
    total = (
        # stacked bars: the bar height is the total, so the sum statistic (energy_net_paid) is not drawn as a series
        "          - type: statistics-graph\n            chart_type: bar-stack\n            period: year\n"
        "            days_to_show: 7000\n            stat_types:\n              - change\n"
        "            expand_legend: true\n            entities:\n"
        f"              - entity: zse_energia:net_paid___ZU_E__\n                name: {e_label}\n                color: '#e0803d'\n"
        f"              - entity: zse_energia:net_paid___ZU_G__\n                name: {g_label}\n                color: '#e5533d'\n"
    )
    total_cards = Builder("electricity").title_card("chart-bar", "T.c_total") + total

    def charts_view() -> str:
        if not expander:  # three sections side by side
            return (
                view("grafikonok", "chart-bar", charts_title)
                + section(e_label, "lightning-bolt", el.charts_cards())
                + section(g_label, "fire", gs.charts_cards())
                + section(t_label, "cash-multiple", total_cards)
            )
        # one full-width section with three folding blocks (HACS: expander-card), all closed at first

        def fold(label: str, icon_name: str, cards: str) -> str:
            # a markdown card is a thick, button-like header (a heading card is only one line high)
            head = (
                "          - type: markdown\n            content: |\n"
                f'              ## <ha-icon icon="mdi:{icon_name}"></ha-icon> {label}\n'
            )
            return Builder.folding(head, cards)

        return (
            view("grafikonok", "chart-bar", charts_title)
            + "      - type: grid\n        column_span: 2\n        cards:\n"
            + fold(e_label, "lightning-bolt", el.charts_cards())
            + fold(g_label, "fire", gs.charts_cards())
            + fold(t_label, "cash-multiple", total_cards)
        )

    return (
        COMBINED_HEADER
        + "title: ZSE\nviews:\n"
        + view("zse-payments", "cash-multiple")
        + section(e_label, "lightning-bolt", el.payments_cards())
        + section(g_label, "fire", gs.payments_cards())
        + view("zse-table", "table")
        + section(e_label, "lightning-bolt", el.table(), "orange")
        + section(g_label, "fire", gs.table(), "red")
        + view("zse-details", "information-outline")
        + section(e_label, "lightning-bolt", el.details_cards(), "orange")
        + section(g_label, "fire", gs.details_cards(), "red")
        + charts_view()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zu-electricity", help="electricity contract-account number (for the private copy)")
    parser.add_argument("--zu-gas", help="gas contract-account number (for the private copy)")
    parser.add_argument("--personal-dir", type=pathlib.Path, help="where to write the private copies")
    args = parser.parse_args()

    combined = build_combined(("Electricity", "Gas", "Total"), "Charts")
    (DASH_DIR / "zse_dashboard_combined.yaml").write_text(combined, encoding="utf-8", newline="\n")
    print("written zse_dashboard_combined.yaml", len(combined), "chars")
    if args.zu_electricity and args.zu_gas and args.personal_dir:
        mine = build_combined(("Villany", "Gáz", "Összesen"), "Grafikonok", expander=True)
        mine = mine.replace("__ZU_E__", args.zu_electricity).replace("__ZU_G__", args.zu_gas)
        path = args.personal_dir / "zse_dashboard_personal_combined.yaml"
        path.write_text(mine, encoding="utf-8", newline="\n")
        print("written", path)

    for kind, name, zu in (
        ("electricity", "zse_dashboard.yaml", args.zu_electricity),
        ("gas", "zse_dashboard_gas.yaml", args.zu_gas),
    ):
        text = Builder(kind).build(name)
        (DASH_DIR / name).write_text(text, encoding="utf-8", newline="\n")
        print("written", name, len(text), "chars")
        if zu and args.personal_dir:
            stem = name.removesuffix(".yaml").replace("zse_dashboard", "zse_dashboard_personal")
            if kind == "electricity":
                stem += "_electricity"
            personal = args.personal_dir / (stem + ".yaml")
            personal.write_text(text.replace("__ZU__", zu), encoding="utf-8", newline="\n")
            print("written", personal)


if __name__ == "__main__":
    main()
