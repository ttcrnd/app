/** Pure form/rating helpers and shared labels — no DOM. */

export const RATING_OPTIONS = [
    'nehodnoceno',
    'splňuje',
    'částečně splňuje',
    'nesplňuje',
];

export const RATING_LABELS = {
    pass: 'Splněno',
    partial: 'Částečně splněno',
    fail: 'Nesplňuje',
    unknown: 'Nehodnoceno',
};

export const CATEGORY_LABELS = {
    'must have': 'Povinné',
    'must-have': 'Povinné',
    'good to have': 'Doporučené',
    'good-to-have': 'Doporučené',
    'nice to have': 'Volitelné',
    'nice-to-have': 'Volitelné',
};

export function normalizeText(value) {
    if (!value) return '';
    return value
        .toString()
        .normalize('NFD')
        .replace(/[\u0000-\u001f\u0300-\u036f]/g, '')
        .toLowerCase();
}

export function ratingKey(value) {
    const normalized = normalizeRatingValue(value);
    if (normalized === 'splňuje') return 'pass';
    if (normalized === 'částečně splňuje') return 'partial';
    if (normalized === 'nesplňuje') return 'fail';
    return 'unknown';
}

export function normalizeRatingValue(value) {
    const normalized = (value || '').toString().trim().toLowerCase();
    // Legacy N/A folds into „Nehodnoceno“ (covers both pending and not-applicable).
    if (normalized === 'nevztahuje se') return 'nehodnoceno';
    if (RATING_OPTIONS.includes(normalized)) return normalized;
    return 'nehodnoceno';
}

export function ratingDisplayLabel(value) {
    return RATING_LABELS[ratingKey(value)] || RATING_LABELS.unknown;
}

export function ratingDisplayHint(value) {
    const key = ratingKey(value);
    if (key === 'unknown') {
        return 'Ještě nehodnoceno, nebo se kritérium knihovny netýká.';
    }
    if (key === 'pass') return 'Kritérium je splněno.';
    if (key === 'partial') return 'Kritérium je splněno jen částečně.';
    if (key === 'fail') return 'Kritérium není splněno.';
    return '';
}

export function normalizeCategoryLabel(value) {
    const raw = `${value || ''}`.trim();
    if (!raw) return '';
    const normalized = raw.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
    return CATEGORY_LABELS[normalized] || raw;
}

export function confidenceLabel(level) {
    if (level === 'high') return 'Vysoká jistota automatu';
    if (level === 'medium') return 'Střední jistota automatu';
    if (level === 'low') return 'Nízká jistota automatu';
    return '';
}

export function confidenceTooltip(level) {
    if (level === 'high') {
        return 'Automat má přímý důkaz odpovídající otázce. I tak můžeš výsledek upravit.';
    }
    if (level === 'medium') {
        return 'Signál je relevantní, ale nepokrývá celé kritérium — ověř poznámku a důkazy.';
    }
    if (level === 'low') {
        return 'Automat našel jen nepřímé signály; verdikt vyžaduje lidské potvrzení.';
    }
    return 'Tuto otázku má posoudit člověk; automat ji nepředvyplnil.';
}

export function libraryDisplayName(repo) {
    const raw = `${repo || ''}`.trim();
    if (!raw) return 'Hodnocení';
    const parts = raw.split('/').filter(Boolean);
    return parts[parts.length - 1] || raw;
}
