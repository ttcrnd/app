import { dom, state } from './runtime.js';
import {
    RATING_LABELS,
    RATING_OPTIONS,
    confidenceLabel,
    confidenceTooltip,
    normalizeCategoryLabel,
    normalizeRatingValue,
    normalizeText,
    ratingDisplayLabel,
    ratingKey,
} from './form-utils.js';
import { deps } from './deps.js';
import { scheduleLocalDraftSave } from './autosave.js';
import { buildQuestion } from './form-question.js';

export { buildQuestion };

export const RATING_KEYS = ['pass', 'partial', 'fail', 'unknown'];

export const EVALUATION_KEYS = ['manual', 'heuristic'];

export const EVALUATION_LABELS = {
    manual: 'Manuální',
    heuristic: 'Heuristika',
};

const WORKFLOW_STATES = ['AUTO', 'CONFIRM', 'MANUAL'];

const DETAILS_FILTER_DEFAULTS = {
    get rating() {
        return new Set(RATING_KEYS);
    },
    get evaluation() {
        return new Set(EVALUATION_KEYS);
    },
};

export function createDefaultDetailsFilters() {
    return {
        rawSearch: '',
        search: '',
        queueMode: 'all',
        rating: DETAILS_FILTER_DEFAULTS.rating,
        evaluation: DETAILS_FILTER_DEFAULTS.evaluation,
    };
}

export function createEmptyFilterRefs() {
    return {
        searchInput: null,
        searchClearBtn: null,
        queueTodoBtn: null,
        queueAllBtn: null,
        nextTodoBtn: null,
        ratings: new Map(),
        evaluation: new Map(),
        resultCount: null,
        totalCount: null,
        activeCount: null,
        activeSummary: null,
        emptyHint: null,
        emptyResetBtn: null,
        resetBtn: null,
        moreFilters: null,
    };
}

export let detailsFilters = createDefaultDetailsFilters();
export let detailsFilterRefs = createEmptyFilterRefs();

export function resetDetailsFilters() {
    detailsFilters = createDefaultDetailsFilters();
    deps.detailsFilters = detailsFilters;
}

export function questionItemNeedsAction(item) {
    if (!item) return false;
    const checked = item.dataset.checked === 'true';
    const rating = item.dataset.rating || 'unknown';
    return !checked || rating === 'unknown';
}

export function getActiveFilterState() {
    const selectedRatings = RATING_KEYS.filter(key => detailsFilters.rating.has(key));
    const selectedEvaluations = EVALUATION_KEYS.filter(key => detailsFilters.evaluation.has(key));
    const searchText = (detailsFilters.rawSearch || '').trim();
    const parts = [];
    let activeCount = 0;

    if (detailsFilters.queueMode === 'todo') {
        activeCount += 1;
        parts.push('Fronta: K vyřízení');
    }
    if (selectedRatings.length !== RATING_KEYS.length) {
        activeCount += 1;
        parts.push(`Stav: ${selectedRatings.map(key => RATING_LABELS[key]).join(', ')}`);
    }
    if (selectedEvaluations.length !== EVALUATION_KEYS.length) {
        activeCount += 1;
        parts.push(`Typ: ${selectedEvaluations.map(key => EVALUATION_LABELS[key]).join(', ')}`);
    }
    if (searchText) {
        activeCount += 1;
        parts.push(`Hledání: "${searchText}"`);
    }

    return {
        activeCount,
        hasActiveFilters: activeCount > 0,
        summaryText: activeCount > 0
            ? parts.join(' | ')
            : 'Zobrazeny všechny otázky.',
    };
}

export function normalizeWorkflowState(value, question, rating) {
    const normalized = (value || '').toString().trim().toUpperCase();
    if (WORKFLOW_STATES.includes(normalized)) return normalized;

    const isHeuristicEvaluated = !!question?.heuristic_rating;
    if (!isHeuristicEvaluated) return 'MANUAL';
    if (rating === 'splňuje') return 'AUTO';
    return 'CONFIRM';
}

export function normalizeQuestionWorkflow(question) {
    if (!question || typeof question !== 'object') return;

    let rating = normalizeRatingValue(question.rating);
    const hasChecked = Object.prototype.hasOwnProperty.call(question, 'checked');
    let checked = hasChecked ? !!question.checked : false;
    let checkedSource = (question.checked_source || '').toString().trim().toLowerCase();
    let suggested = normalizeRatingValue(question.auto_suggested_rating);
    let reviewState = normalizeWorkflowState(question.review_state, question, rating);

    if (reviewState === 'AUTO') {
        if (rating === 'nehodnoceno') rating = 'splňuje';
        checked = true;
        checkedSource = 'auto';
    } else if (reviewState === 'CONFIRM') {
        if (suggested === 'nehodnoceno' && rating !== 'nehodnoceno') {
            suggested = rating;
        }
        if (rating !== 'nehodnoceno' && (checked || !hasChecked)) {
            checked = true;
            checkedSource = 'manual';
        } else if (!checked) {
            checkedSource = '';
        }
    } else {
        if (suggested === 'nehodnoceno' && rating !== 'nehodnoceno') {
            suggested = rating;
        }
        if (rating !== 'nehodnoceno' && (checked || !hasChecked)) {
            checked = true;
            checkedSource = 'manual';
        } else if (!checked) {
            checkedSource = '';
        }
    }

    question.rating = rating;
    question.review_state = reviewState;
    question.checked = !!checked;
    question.checked_source = checkedSource;
    question.requires_confirmation = !question.checked;
    if (suggested !== 'nehodnoceno') {
        question.auto_suggested_rating = suggested;
    }
}

export function toggleFilterSet(type, value) {
    const targetSet = type === 'rating' ? detailsFilters.rating : detailsFilters.evaluation;
    if (targetSet.has(value)) {
        if (targetSet.size > 1) targetSet.delete(value);
        return;
    }
    targetSet.add(value);
}

export function updateAllFilterControls() {
    if (detailsFilterRefs.searchInput) {
        detailsFilterRefs.searchInput.value = detailsFilters.rawSearch || '';
    }
    if (detailsFilterRefs.searchClearBtn) {
        const hasText = (detailsFilters.rawSearch || '').trim().length > 0;
        detailsFilterRefs.searchClearBtn.hidden = !hasText;
        detailsFilterRefs.searchClearBtn.disabled = !hasText;
    }
    if (detailsFilterRefs.queueTodoBtn) {
        detailsFilterRefs.queueTodoBtn.dataset.active = detailsFilters.queueMode === 'todo' ? 'true' : 'false';
    }
    if (detailsFilterRefs.queueAllBtn) {
        detailsFilterRefs.queueAllBtn.dataset.active = detailsFilters.queueMode === 'all' ? 'true' : 'false';
    }
    detailsFilterRefs.ratings.forEach((chip, key) => {
        chip.dataset.active = detailsFilters.rating.has(key) ? 'true' : 'false';
    });
    detailsFilterRefs.evaluation.forEach((chip, key) => {
        chip.dataset.active = detailsFilters.evaluation.has(key) ? 'true' : 'false';
    });
    const activeState = getActiveFilterState();
    if (detailsFilterRefs.activeCount) {
        detailsFilterRefs.activeCount.textContent = String(activeState.activeCount);
    }
    if (detailsFilterRefs.activeSummary) {
        detailsFilterRefs.activeSummary.textContent = activeState.summaryText;
    }
    if (detailsFilterRefs.resetBtn) {
        detailsFilterRefs.resetBtn.disabled = !activeState.hasActiveFilters;
    }
    if (detailsFilterRefs.emptyResetBtn) {
        detailsFilterRefs.emptyResetBtn.hidden = !activeState.hasActiveFilters;
        detailsFilterRefs.emptyResetBtn.disabled = !activeState.hasActiveFilters;
    }
    if (detailsFilterRefs.emptyHint) {
        detailsFilterRefs.emptyHint.textContent = activeState.hasActiveFilters
            ? (detailsFilters.queueMode === 'todo'
                ? 'Nic nezbývá k vyřízení při aktuálních filtrech. Zkus „Vše“ nebo obnov filtry.'
                : 'Nic neodpovídá aktuálním filtrům. Uprav hledání nebo obnov výchozí filtry.')
            : 'Žádné otázky nejsou aktuálně k dispozici.';
    }
}

function todoQueuePriority(item) {
    const must = item?.dataset?.mustOpen === 'true' ? 0 : 1;
    const conf = `${item?.dataset?.confidence || ''}`.toLowerCase();
    const confRank = conf === 'low' ? 0 : conf === 'medium' ? 1 : conf === 'high' ? 2 : 3;
    return must * 10 + confRank;
}

export function goToNextTodoQuestion({ announce = false } = {}) {
    if (!dom.details) return;
    const items = Array.from(dom.details.querySelectorAll('.q-item'));
    if (!items.length) return;

    const visibleTodo = items.filter(item => !item.hidden && questionItemNeedsAction(item));
    const poolBase = visibleTodo.length
        ? visibleTodo
        : items.filter(item => questionItemNeedsAction(item));
    const pool = [...poolBase].sort((a, b) => {
        const byPri = todoQueuePriority(a) - todoQueuePriority(b);
        if (byPri !== 0) return byPri;
        return items.indexOf(a) - items.indexOf(b);
    });
    if (!pool.length) {
        deps.setStatus('Hotovo — nic dalšího k vyřízení', true);
        return;
    }

    const openItem = items.find(item => item.open);
    let startIdx = openItem ? pool.indexOf(openItem) : -1;
    if (startIdx < 0 && openItem) {
        const openPos = items.indexOf(openItem);
        startIdx = pool.findIndex(item => items.indexOf(item) > openPos) - 1;
    }
    const next = pool[(startIdx + 1) % pool.length];
    if (!next) return;

    if (detailsFilters.queueMode !== 'todo') {
        detailsFilters.queueMode = 'todo';
        updateAllFilterControls();
        applyDetailsFilters();
    }
    items.forEach(item => { item.open = false; });
    const section = next.closest('details.details-section');
    if (section) section.open = true;
    next.hidden = false;
    next.open = true;
    next.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const focusTarget = next.querySelector('.q-done-btn, .rating-segment__btn, textarea');
    focusTarget?.focus?.();
    if (announce) {
        const qId = next.querySelector('.q-id')?.textContent?.trim();
        deps.setStatus(qId ? `Další k vyřízení: ${qId}` : 'Další k vyřízení', true);
    }
}

export function createEl(tag, attrs = {}, children = []) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (key === 'class') el.className = value;
        else if (key === 'text') el.textContent = value;
        else if (key === 'html') el.innerHTML = value;
        else el.setAttribute(key, value);
    }
    children.forEach(child => el.appendChild(child));
    return el;
}

export function createFilterChip(type, value, label, toneClass = '') {
    const chip = createEl('button', {
        type: 'button',
        class: `filter-chip ${toneClass}`.trim(),
    });
    chip.textContent = label;
    chip.dataset.value = value;
    chip.dataset.group = type;
    chip.dataset.active = (type === 'rating' ? detailsFilters.rating : detailsFilters.evaluation).has(value)
        ? 'true'
        : 'false';
    chip.addEventListener('click', () => {
        toggleFilterSet(type, value);
        updateAllFilterControls();
        applyDetailsFilters();
    });
    return chip;
}

export function createFilterGroup(type, title, configs) {
    const group = createEl('div', { class: 'details-toolbar__group' });
    group.appendChild(createEl('span', { class: 'details-toolbar__label', text: title }));
    const wrap = createEl('div', { class: 'details-toolbar__chips' });
    const refs = new Map();
    configs.forEach(({ value, label, tone }) => {
        const chip = createFilterChip(type, value, label, tone);
        wrap.appendChild(chip);
        refs.set(value, chip);
    });
    group.appendChild(wrap);
    return { element: group, refs };
}

export function buildDetailsToolbar(totalQuestions) {
    const toolbar = createEl('div', { class: 'details-toolbar' });

    const queueGroup = createEl('div', { class: 'details-toolbar__group details-toolbar__group--queue' });
    queueGroup.appendChild(createEl('span', { class: 'details-toolbar__label', text: 'Fronta' }));
    const queueRow = createEl('div', { class: 'details-toolbar__chips' });
    const queueTodoBtn = createEl('button', {
        type: 'button',
        class: 'filter-chip tone-waiting',
        text: 'K vyřízení',
    });
    const queueAllBtn = createEl('button', {
        type: 'button',
        class: 'filter-chip',
        text: 'Vše',
    });
    queueTodoBtn.addEventListener('click', () => {
        detailsFilters.queueMode = 'todo';
        updateAllFilterControls();
        applyDetailsFilters();
    });
    queueAllBtn.addEventListener('click', () => {
        detailsFilters.queueMode = 'all';
        updateAllFilterControls();
        applyDetailsFilters();
    });
    const nextTodoBtn = createEl('button', {
        type: 'button',
        class: 'btn-secondary details-toolbar__next',
        text: 'Další →',
        title: 'Další otázka k vyřízení (klávesa N)',
    });
    nextTodoBtn.addEventListener('click', () => goToNextTodoQuestion({ announce: true }));
    queueRow.appendChild(queueTodoBtn);
    queueRow.appendChild(queueAllBtn);
    queueRow.appendChild(nextTodoBtn);
    queueGroup.appendChild(queueRow);
    toolbar.appendChild(queueGroup);

    const moreFilters = createEl('details', { class: 'details-toolbar__more' });
    moreFilters.appendChild(createEl('summary', {
        class: 'details-toolbar__more-summary',
        text: 'Filtrovat…',
    }));
    const moreBody = createEl('div', { class: 'details-toolbar__more-body' });

    const searchGroup = createEl('div', {
        class: 'details-toolbar__group details-toolbar__group--search',
    });
    searchGroup.appendChild(createEl('span', { class: 'details-toolbar__label', text: 'Hledání' }));
    const searchRow = createEl('div', { class: 'details-toolbar__search-row' });
    const searchInput = createEl('input', {
        type: 'search',
        placeholder: 'Např. #1-2, podpis, SBOM…',
    });
    searchInput.value = detailsFilters.rawSearch || '';
    searchInput.addEventListener('input', () => {
        detailsFilters.rawSearch = searchInput.value;
        detailsFilters.search = normalizeText(searchInput.value);
        applyDetailsFilters();
    });
    searchInput.addEventListener('keydown', event => {
        if (event.key === 'Escape' && searchInput.value) {
            detailsFilters.rawSearch = '';
            detailsFilters.search = '';
            updateAllFilterControls();
            applyDetailsFilters();
        }
    });
    const searchClearBtn = createEl('button', {
        type: 'button',
        class: 'filter-clear',
        text: 'Vymazat',
    });
    searchClearBtn.addEventListener('click', () => {
        detailsFilters.rawSearch = '';
        detailsFilters.search = '';
        updateAllFilterControls();
        applyDetailsFilters();
        searchInput.focus();
    });
    searchRow.appendChild(searchInput);
    searchRow.appendChild(searchClearBtn);
    searchGroup.appendChild(searchRow);
    moreBody.appendChild(searchGroup);

    const ratingGroup = createFilterGroup('rating', 'Výsledek', [
        { value: 'pass', label: 'Splněno', tone: 'tone-pass' },
        { value: 'partial', label: 'Částečně splněno', tone: 'tone-partial' },
        { value: 'fail', label: 'Nesplňuje', tone: 'tone-fail' },
        { value: 'unknown', label: 'Nehodnoceno', tone: 'tone-unknown' },
    ]);
    moreBody.appendChild(ratingGroup.element);

    const metaGroup = createEl('div', { class: 'details-toolbar__meta' });
    const counter = createEl('div', {
        class: 'details-toolbar__counter',
        html: 'Zobrazeno <strong data-kind="visible">0</strong> / <span data-kind="total">0</span> ot.',
    });
    const activeInfo = createEl('div', {
        class: 'details-toolbar__active',
        html: 'Filtry: <strong data-kind="active">0</strong>',
    });
    const activeSummary = createEl('div', {
        class: 'details-toolbar__summary',
        text: 'Výchozí: otázky k vyřízení.',
    });
    metaGroup.appendChild(activeInfo);
    metaGroup.appendChild(activeSummary);
    metaGroup.appendChild(counter);
    const resetBtn = createEl('button', {
        type: 'button',
        class: 'filter-reset',
        text: 'Obnovit výchozí (K vyřízení)',
    });
    resetBtn.addEventListener('click', () => {
        resetDetailsFilters();
        updateAllFilterControls();
        applyDetailsFilters();
    });
    metaGroup.appendChild(resetBtn);
    moreBody.appendChild(metaGroup);
    moreFilters.appendChild(moreBody);
    toolbar.appendChild(moreFilters);

    detailsFilterRefs = {
        searchInput,
        searchClearBtn,
        queueTodoBtn,
        queueAllBtn,
        nextTodoBtn,
        ratings: ratingGroup.refs,
        evaluation: new Map(),
        resultCount: counter.querySelector('[data-kind="visible"]'),
        totalCount: counter.querySelector('[data-kind="total"]'),
        activeCount: activeInfo.querySelector('[data-kind="active"]'),
        activeSummary,
        emptyHint: null,
        emptyResetBtn: null,
        resetBtn,
        moreFilters,
    };
    if (detailsFilterRefs.totalCount) {
        detailsFilterRefs.totalCount.textContent = String(totalQuestions);
    }

    return toolbar;
}

export function createRatingSelect(value) {
    const select = createEl('select');
    RATING_OPTIONS.forEach(option => {
        const item = createEl('option', {
            value: option,
            text: RATING_LABELS[ratingKey(option)] || option,
        });
        if (normalizeRatingValue(option) === normalizeRatingValue(value)) item.selected = true;
        select.appendChild(item);
    });
    return select;
}

export function ratingClass(value) {
    const normalized = normalizeRatingValue(value);
    if (normalized === 'splňuje') return 'ok';
    if (normalized === 'částečně splňuje') return 'mid';
    if (normalized === 'nesplňuje') return 'err';
    return '';
}

export function ratingScoreFromKey(key) {
    if (key === 'pass') return 100;
    if (key === 'partial') return 50;
    if (key === 'fail') return 0;
    if (key === 'unknown') return 25;
    return 0;
}

export function orderQuestionsForReview(questions) {
    return questions
        .map((question, index) => ({ question, index }))
        .sort((a, b) => {
            const aCat = `${a.question?.category || ''}`.toLowerCase();
            const bCat = `${b.question?.category || ''}`.toLowerCase();
            const aMust = aCat.startsWith('must') ? 0 : 1;
            const bMust = bCat.startsWith('must') ? 0 : 1;
            if (aMust !== bMust) return aMust - bMust;
            const confRank = (q) => {
                const level = `${q?.confidence || q?.confidence_level || ''}`.toLowerCase();
                if (level === 'low') return 0;
                if (level === 'medium') return 1;
                if (level === 'high') return 2;
                return 3;
            };
            const byConf = confRank(a.question) - confRank(b.question);
            if (byConf !== 0) return byConf;
            return a.index - b.index;
        })
        .map(({ question, index }) => ({ question, originalIndex: index }));
}

export function setProgressTone(barEl, toneClass) {
    if (!barEl) return;
    barEl.classList.remove('tone-done', 'tone-waiting', 'tone-manual', 'tone-neutral');
    barEl.classList.add(toneClass);
}

export function updateSectionProgress(sectionEl) {
    if (!sectionEl) return;
    const questions = Array.from(sectionEl.querySelectorAll('.q-item'));
    const total = questions.length;

    const checkedCount = questions.filter(item => item.dataset.checked === 'true').length;
    const remainingCount = questions.filter(item => item.dataset.needsAction === 'true').length;
    const pendingConfirm = questions.filter(item => item.dataset.checked !== 'true' && item.dataset.workflow === 'confirm').length;
    const pendingManual = questions.filter(item => item.dataset.checked !== 'true' && item.dataset.workflow === 'manual').length;
    const confirmedPercent = total > 0 ? (checkedCount / total) * 100 : 0;

    const remainingEl = sectionEl.querySelector('[data-remaining="badge"]');
    if (remainingEl) {
        remainingEl.textContent = remainingCount > 0 ? `Zbývá ${remainingCount}` : 'Hotovo';
        remainingEl.dataset.empty = remainingCount === 0 ? 'true' : 'false';
    }

    const confirmedValueEl = sectionEl.querySelector('[data-progress="confirmed-value"]');
    const confirmedFillEl = sectionEl.querySelector('[data-progress="confirmed-fill"]');
    const confirmedBarEl = sectionEl.querySelector('[data-progress="confirmed-bar"]');
    if (confirmedValueEl) confirmedValueEl.textContent = `${checkedCount}/${total}`;
    if (confirmedFillEl) confirmedFillEl.style.width = `${Math.max(0, Math.min(100, confirmedPercent)).toFixed(2)}%`;
    if (confirmedBarEl) {
        let toneClass = 'tone-neutral';
        if (total > 0 && checkedCount === total) toneClass = 'tone-done';
        else if (pendingManual > 0) toneClass = 'tone-manual';
        else if (pendingConfirm > 0 || checkedCount > 0) toneClass = 'tone-waiting';
        setProgressTone(confirmedBarEl, toneClass);
    }

    const scored = questions
        .map(item => ratingScoreFromKey(item.dataset.rating || 'unknown'))
        .filter(value => value !== null && Number.isFinite(value));
    const score = scored.length > 0
        ? scored.reduce((sum, value) => sum + value, 0) / scored.length
        : 0;
    const ratingValueEl = sectionEl.querySelector('[data-progress="rating-value"]');
    if (ratingValueEl) ratingValueEl.textContent = `${Math.round(score)} %`;
}

export function createLinkifiedFragment(text) {
    const fragment = document.createDocumentFragment();
    const urlRe = /(https?:\/\/[\w\-._~:\/?#\[\]@!$&'()*+,;=%]+)/gi;
    let cursor = 0;
    let match;
    while ((match = urlRe.exec(text)) !== null) {
        if (match.index > cursor) {
            fragment.appendChild(document.createTextNode(text.slice(cursor, match.index)));
        }
        const [url] = match;
        try {
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.textContent = url;
            anchor.target = '_blank';
            anchor.rel = 'noopener noreferrer';
            fragment.appendChild(anchor);
        } catch {
            fragment.appendChild(document.createTextNode(url));
        }
        cursor = match.index + url.length;
    }
    if (cursor < text.length) fragment.appendChild(document.createTextNode(text.slice(cursor)));
    return fragment;
}

export function fillEvidencePreview(container, rawValue) {
    const normalized = (rawValue || '').replace(/\r/g, '');
    container.textContent = '';
    if (!normalized.trim()) {
        container.textContent = 'Žádné odkazy zatím nejsou vyplněné.';
        container.classList.add('is-empty');
        return;
    }
    container.classList.remove('is-empty');
    const lines = normalized.split(/\n/);
    lines.forEach((line, index) => {
        if (index > 0) container.appendChild(document.createElement('br'));
        container.appendChild(createLinkifiedFragment(line));
    });
}

export function updateFormQuestion(sectionIndex, questionIndex, key, value) {
    const section = state.form?.sections?.[sectionIndex];
    const question = section?.questions?.[questionIndex];
    if (!question) return;
    question[key] = value;
    scheduleLocalDraftSave();
}

export function orderSections(sections) {
    return sections
        .map((section, index) => ({ section, index }))
        .sort((a, b) => {
            const aIsGate = isGateSection(a.section);
            const bIsGate = isGateSection(b.section);
            if (aIsGate === bIsGate) return a.index - b.index;
            return aIsGate ? 1 : -1;
        });
}

export function isGateSection(section) {
    // Legacy name: sorts non-methodology appendix blocks last if present.
    const type = `${section?.type ?? ''}`.toLowerCase();
    return type === 'appendix' || type === 'informational' || type === 'info';
}

export function sectionTypeBadge(section) {
    const type = `${section?.type ?? ''}`.toLowerCase();
    if (type === 'appendix' || type === 'informational' || type === 'info') return 'příloha';
    if (type === 'gate') return 'gate';
    return section?.type || '';
}

export function renderDetails(form) {
    if (!dom.details) return;
    dom.details.innerHTML = '';
    detailsFilters = createDefaultDetailsFilters();
    detailsFilterRefs = createEmptyFilterRefs();
    const sections = Array.isArray(form?.sections) ? form.sections : [];
    if (sections.length === 0) {
        dom.details.appendChild(createEl('div', {
            class: 'muted',
            text: 'Zatím nic k zobrazení. Na Domů spusť nové hodnocení.',
        }));
        return;
    }

    const ordered = orderSections(sections);
    const totalQuestions = ordered.reduce((acc, { section }) => {
        const questions = Array.isArray(section.questions) ? section.questions : [];
        return acc + questions.length;
    }, 0);

    const wrapper = createEl('div', { class: 'details-wrapper' });
    const toolbar = buildDetailsToolbar(totalQuestions);
    wrapper.appendChild(toolbar);

    const content = createEl('div', { class: 'details-content' });
    ordered.forEach(({ section, index }) => {
        content.appendChild(buildSection(section, index));
    });
    wrapper.appendChild(content);

    const emptyIndicator = createEl('div', {
        class: 'details-empty muted',
    });
    const emptyHint = createEl('span', {
        class: 'details-empty__text',
        text: 'Nic neodpovídá aktuálním filtrům. Uprav hledání nebo obnov výchozí filtry.',
    });
    const emptyResetBtn = createEl('button', {
        type: 'button',
        class: 'filter-reset details-empty__reset',
        text: 'Obnovit výchozí filtry',
    });
    emptyResetBtn.addEventListener('click', () => {
        resetDetailsFilters();
        updateAllFilterControls();
        applyDetailsFilters();
    });
    emptyIndicator.appendChild(emptyHint);
    emptyIndicator.appendChild(emptyResetBtn);
    emptyIndicator.hidden = true;
    wrapper.appendChild(emptyIndicator);
    detailsFilterRefs.emptyHint = emptyHint;
    detailsFilterRefs.emptyResetBtn = emptyResetBtn;

    dom.details.appendChild(wrapper);
    updateAllFilterControls();
    applyDetailsFilters();

    const firstTodo = dom.details.querySelector('.q-item[data-needs-action="true"]:not([hidden])');
    if (firstTodo) {
        const section = firstTodo.closest('details.details-section');
        if (section) section.open = true;
        firstTodo.open = true;
    }
}

export function buildSection(section, sectionIndex) {
    const container = createEl('details', { class: 'qd sd details-section' });
    container.open = false;

    const summary = createEl('summary', { class: 'section-summary' });
    summary.appendChild(createEl('span', { class: 'caret', html: '▸' }));

    const title = section.title || `Sekce ${section.id ?? sectionIndex + 1}`;
    const titleWrap = createEl('span', { class: 'section-title' });
    titleWrap.appendChild(createEl('strong', { text: title }));
    if (section.type) {
        titleWrap.appendChild(createEl('span', { class: 'q-badge', text: sectionTypeBadge(section) }));
    }
    summary.appendChild(titleWrap);
    summary.appendChild(createEl('span', { class: 'section-spacer' }));

    const questions = Array.isArray(section.questions) ? section.questions : [];
    const orderedQuestions = orderQuestionsForReview(questions);

    const remainingBadge = createEl('span', {
        class: 'section-remaining',
        'data-remaining': 'badge',
        text: 'Zbývá 0',
    });
    summary.appendChild(remainingBadge);

    const progressWrap = createEl('div', { class: 'section-progress section-progress--compact' });
    const confirmMeta = createEl('div', { class: 'section-progress__meta' }, [
        createEl('span', { class: 'section-progress__label', text: 'Potvrzeno' }),
        createEl('span', { class: 'section-progress__value', 'data-progress': 'confirmed-value', text: `0/${questions.length}` }),
    ]);
    const confirmBar = createEl('div', { class: 'section-progress__bar tone-neutral', 'data-progress': 'confirmed-bar' }, [
        createEl('span', { class: 'section-progress__fill', 'data-progress': 'confirmed-fill' }),
    ]);
    progressWrap.appendChild(createEl('div', { class: 'section-progress__item' }, [confirmMeta, confirmBar]));

    progressWrap.appendChild(createEl('span', {
        class: 'section-rating-pct',
        'data-progress': 'rating-value',
        text: '0 %',
        title: 'Průměrné hodnocení sekce',
    }));

    summary.appendChild(progressWrap);

    summary.appendChild(createEl('span', {
        class: 'section-counter',
        text: `${questions.length} ot.`,
    }));

    container.appendChild(summary);

    const body = createEl('div', { class: 'section-body' });
    orderedQuestions.forEach(({ question, originalIndex }) => {
        body.appendChild(buildQuestion(sectionIndex, question, originalIndex));
    });
    container.appendChild(body);

    const emptyState = createEl('div', {
        class: 'section-empty muted small',
        text: 'V této sekci nic neodpovídá filtrům.',
    });
    emptyState.hidden = true;
    container.appendChild(emptyState);

    updateSectionProgress(container);
    return container;
}

export function parseEvidenceLinesSafe(raw) {
    return (raw || '')
        .toString()
        .split(/\r?\n|;/)
        .map(line => line.trim())
        .filter(Boolean);
}


export function applyDetailsFilters() {
    if (!dom.details) return;
    const items = dom.details.querySelectorAll('.q-item');
    const totalQuestions = items.length;
    let visibleQuestions = 0;
    items.forEach(item => {
        const matchesRating = detailsFilters.rating.has(item.dataset.rating || 'unknown');
        const matchesEvaluation = detailsFilters.evaluation.has(item.dataset.eval || 'manual');
        const matchesSearch = !detailsFilters.search || (item.dataset.search || '').includes(detailsFilters.search);
        const matchesQueue = detailsFilters.queueMode === 'all' || questionItemNeedsAction(item);
        const visible = matchesRating && matchesEvaluation && matchesSearch && matchesQueue;
        item.hidden = !visible;
        if (visible) visibleQuestions += 1;
    });

    const sections = dom.details.querySelectorAll('.details-section');
    sections.forEach(section => {
        const questions = section.querySelectorAll('.q-item');
        const visibleItems = Array.from(questions).filter(node => !node.hidden);
        updateSectionProgress(section);

        const counter = section.querySelector('.section-counter');
        if (counter) counter.textContent = `${visibleItems.length}/${questions.length} ot.`;

        const emptyState = section.querySelector('.section-empty');
        if (emptyState) emptyState.hidden = visibleItems.length > 0;
        section.classList.toggle('is-empty', visibleItems.length === 0);
        if (visibleItems.length === 0) section.open = false;
    });

    const emptyIndicator = dom.details.querySelector('.details-empty');
    if (emptyIndicator) emptyIndicator.hidden = visibleQuestions > 0;

    if (detailsFilterRefs.resultCount) {
        detailsFilterRefs.resultCount.textContent = String(visibleQuestions);
    }
    if (detailsFilterRefs.totalCount) {
        detailsFilterRefs.totalCount.textContent = String(totalQuestions);
    }
    updateAllFilterControls();
}
