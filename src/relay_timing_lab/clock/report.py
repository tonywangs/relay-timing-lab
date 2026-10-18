"""Clock comparisons using the original safe, offline report renderer."""
import json
from ..report import TEMPLATE


def render(summary):
    template = TEMPLATE.replace('What timing protection costs', 'Clock uncertainty and traffic matching')
    template = template.replace('with synchronized clocks', 'with synthetic observer clock errors')
    template = template.replace('exact clocks, full observation', 'unknown egress offset and drift, full observation')
    template = template.replace('Matching uses normalized byte histograms, a frozen causal lag search, and exact L1 distance.',
        'Legacy matching uses the historical causal lag search. Aligned matching searches a bounded affine grid; offsets combine clock error and relay delay. Both use exact normalized histogram L1. Drift is a deliberately large stress test, not measured hardware behavior.')
    template = template.replace('<button id="reset">',
        '<label>Clock condition<select id="condition" aria-label="Clock condition"></select></label>'
        '<label>Matcher<select id="matcher" aria-label="Matcher"></select></label><button id="reset">')
    template = template.replace("['family','candidates','policy']", "['family','candidates','policy','condition','matcher']")
    template = template.replace("options('family',", "options('condition',data.rows.map(r=>r.condition));options('matcher',data.rows.map(r=>r.matcher));options('family',", 1)
    template = template.replace('${r.family} / ${r.candidates} / ${r.policy}', '${r.family} / ${r.candidates} / ${r.policy} / ${r.condition} / ${r.matcher}${r.comparison ? " / "+r.comparison : ""}')
    template = template.replace('<th>Policy</th><th>Top-one</th>', '<th>Policy</th><th>Clock</th><th>Matcher</th><th>Top-one</th>')
    template = template.replace('r.candidates,r.policy,fmt(r.top1)', 'r.candidates,r.policy,r.condition,r.matcher,fmt(r.top1)')
    template = template.replace('Paired changes from immediate forwarding', 'Paired matcher, clock and policy changes')
    template = template.replace('Policy minus immediate; same independent seeds', 'Named difference in each row; same independent seeds')
    template = template.replace('<th>Mean rank</th>', '<th>Mean rank [95% CI]</th>')
    template = template.replace('fmt(r.metrics.rank.mean)', 'ci(r.metrics.rank)')
    template = template.replace('Family / candidates / policy', 'Family / candidates / policy / clock / matcher')
    template = template.replace('Generated inputs, raw event accounting', 'Real alignment runtime is preserved in measurements.json.gz and runtime.json. Generated inputs, raw event accounting')
    data = json.dumps(summary, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return template.replace('__DATA__', data.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e'))
