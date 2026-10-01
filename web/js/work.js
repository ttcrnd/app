import { dom, state } from './runtime.js';
import { normalizeRatingValue } from './form-utils.js';
import { deps } from './deps.js';

export function countRemainingWork(form) {
    let remaining = 0;
    let total = 0;
    let mustOpen = 0;
    let lowConfidence = 0;
    (form?.sections || []).forEach(section => {
        if (!section || deps.isAppendixSection(section)) return;
        (section.questions || []).forEach(question => {
            if (!question || typeof question !== 'object') return;
            total += 1;
            const checked = !!question.checked;
            const rating = normalizeRatingValue(question.rating);
            const needsAction = !checked || rating === 'nehodnoceno';
            if (needsAction) remaining += 1;
            const category = `${question.category || ''}`.toLowerCase();
            if (category.startsWith('must') && needsAction) mustOpen += 1;
            if (resolveQuestionConfidence(question)?.level === 'low') lowConfidence += 1;
        });
    });
    return { remaining, total, mustOpen, lowConfidence };
}

export function resolveQuestionConfidence(question) {
    if (!question || typeof question !== 'object') return null;
    const explicit = `${question.confidence || question.confidence_level || ''}`.trim().toLowerCase();
    const map = {
        high: 'high',
        medium: 'medium',
        low: 'low',
        vysoká: 'high',
        vysoka: 'high',
        střední: 'medium',
        stredni: 'medium',
        nízká: 'low',
        nizka: 'low',
    };
    if (map[explicit]) {
        return { level: map[explicit], source: 'explicit' };
    }
    if (!question.heuristic_rating) {
        return null;
    }
    const rating = normalizeRatingValue(question.rating);
    const wf = deps.normalizeWorkflowState(question.review_state, question, rating);
    if (wf === 'CONFIRM') return { level: 'low', source: 'derived' };
    if (wf === 'AUTO') return { level: 'high', source: 'derived' };
    if (rating === 'částečně splňuje') return { level: 'medium', source: 'derived' };
    return { level: 'medium', source: 'derived' };
}

export function jumpToQuestionById(questionId) {
    if (!dom.details || !questionId) return false;
    const needle = `${questionId}`.replace(/^#/, '');
    const item = dom.details.querySelector(`.q-item[data-question-id="${CSS.escape(needle)}"]`);
    if (!item) {
        deps.setStatus(`Otázka ${needle} není v aktuálním pohledu`, false);
        return false;
    }
    deps.detailsFilters.queueMode = 'all';
    deps.updateAllFilterControls();
    deps.applyDetailsFilters();
    item.hidden = false;
    const section = item.closest('details.details-section');
    if (section) section.open = true;
    item.open = true;
    item.scrollIntoView({ behavior: 'smooth', block: 'start' });
    item.querySelector('.q-done-btn, .rating-segment__btn, textarea')?.focus?.();
    return true;
}

export function updateWorkRemaining(form) {
    updateWorkStrip(form);
}

export function updateWorkStrip(form) {
    if (!form) {
        if (dom.workRemaining) dom.workRemaining.textContent = 'Zbývá: —';
        if (dom.workMustOpen) {
            dom.workMustOpen.hidden = true;
            dom.workMustOpen.textContent = 'Povinné: —';
        }
        if (dom.workLowConf) {
            dom.workLowConf.hidden = true;
            dom.workLowConf.textContent = 'Nízká jistota: —';
        }
        syncWorkFooter(null);
        renderPdfReadiness(null);
        return;
    }
    const { remaining, total, mustOpen, lowConfidence } = countRemainingWork(form);
    if (dom.workRemaining) {
        dom.workRemaining.textContent = `Zbývá ${remaining}`;
        dom.workRemaining.title = `K vyřízení: ${remaining} z ${total}`;
    }
    if (dom.workMustOpen) {
        if (mustOpen > 0) {
            dom.workMustOpen.hidden = false;
            dom.workMustOpen.textContent = `Povinné: ${mustOpen}`;
            dom.workMustOpen.title = 'Skok na první povinnou otázku k vyřízení';
        } else {
            dom.workMustOpen.hidden = true;
        }
    }
    if (dom.workLowConf) {
        if (lowConfidence > 0) {
            dom.workLowConf.hidden = false;
            dom.workLowConf.textContent = `Nízká jistota: ${lowConfidence}`;
            dom.workLowConf.title = 'Skok na první otázku s nízkou jistotou';
        } else {
            dom.workLowConf.hidden = true;
        }
    }
    syncWorkFooter(form, remaining);
    renderPdfReadiness(form);
}

export function syncWorkFooter(form, remaining = null) {
    const writable = deps.canWrite();
    let left = remaining;
    if (left === null && form) left = countRemainingWork(form).remaining;
    const show = !!form && writable && left === 0;
    if (dom.workFooter) dom.workFooter.hidden = !show;
    if (dom.completeEvalBtn) {
        dom.completeEvalBtn.hidden = !show;
    }
}

export function jumpToFlaggedQuestion(kind) {
    if (!dom.details) return;
    const items = Array.from(dom.details.querySelectorAll('.q-item'));
    const match = items.find(item => {
        if (kind === 'must') {
            return item.dataset.mustOpen === 'true' && deps.questionItemNeedsAction(item);
        }
        if (kind === 'lowconf') {
            return item.dataset.confidence === 'low';
        }
        return false;
    });
    if (!match) {
        deps.setStatus(kind === 'must' ? 'Žádná povinná otázka k vyřízení' : 'Žádná otázka s nízkou jistotou', true);
        return;
    }
    if (deps.detailsFilters.queueMode !== 'todo' && kind === 'must') {
        deps.detailsFilters.queueMode = 'todo';
        deps.updateAllFilterControls();
        deps.applyDetailsFilters();
    }
    items.forEach(item => { item.open = false; });
    const section = match.closest('details.details-section');
    if (section) section.open = true;
    match.hidden = false;
    match.open = true;
    match.scrollIntoView({ behavior: 'smooth', block: 'start' });
    match.querySelector('.q-done-btn, .rating-segment__btn, textarea')?.focus?.();
}

export function syncOfficialPdfButton(ready) {
    if (!dom.downloadPdfBtn) return;
    dom.downloadPdfBtn.disabled = !ready;
    dom.downloadPdfBtn.title = ready
        ? 'Oficiální PDF formuláře v1.0'
        : 'Nejdřív doplň rozhodnutí u všech oficiálních otázek (nebo použij PDF koncept)';
}

export function renderPdfReadiness(form) {
    if (!dom.pdfReadinessStatus || !dom.pdfMissingList) return;
    if (!form) {
        dom.pdfReadinessStatus.textContent = '—';
        dom.pdfReadiness?.classList.remove('is-ready', 'is-blocked');
        if (dom.pdfReadiness) dom.pdfReadiness.hidden = true;
        dom.pdfMissingList.hidden = true;
        dom.pdfMissingList.innerHTML = '';
        syncOfficialPdfButton(false);
        return;
    }
    const missing = deps.findUnevaluatedOfficialQuestions(form);
    if (!missing.length) {
        dom.pdfReadinessStatus.textContent = '';
        dom.pdfReadiness?.classList.remove('is-ready', 'is-blocked');
        if (dom.pdfReadiness) dom.pdfReadiness.hidden = true;
        dom.pdfMissingList.hidden = true;
        dom.pdfMissingList.innerHTML = '';
        syncOfficialPdfButton(true);
        return;
    }
    // Show only when blocked — keep chrome quiet when ready.
    if (dom.pdfReadiness) dom.pdfReadiness.hidden = false;
    dom.pdfReadinessStatus.textContent = `Chybí rozhodnutí u ${missing.length} otázek`;
    dom.pdfReadiness?.classList.add('is-blocked');
    dom.pdfReadiness?.classList.remove('is-ready');
    syncOfficialPdfButton(false);
    dom.pdfMissingList.hidden = false;
    dom.pdfMissingList.innerHTML = '';
    dom.pdfMissingList.className = 'pdf-missing-list';

    const truncate = (text, max = 72) => {
        const clean = `${text || ''}`.replace(/\s+/g, ' ').trim();
        if (!clean) return '';
        if (clean.length <= max) return clean;
        return `${clean.slice(0, max - 1)}…`;
    };

    missing.forEach(item => {
        const id = typeof item === 'string' ? item : (item?.id || '?');
        const text = typeof item === 'string' ? '' : (item?.text || '');
        const label = truncate(text) || `Otázka ${id}`;
        const btn = deps.createEl('button', {
            type: 'button',
            class: 'pdf-missing-chip',
            role: 'listitem',
            title: text ? `${id}: ${text}` : id,
        });
        btn.appendChild(deps.createEl('span', { class: 'pdf-missing-chip__id', text: id }));
        btn.appendChild(deps.createEl('span', { class: 'pdf-missing-chip__text', text: label }));
        btn.addEventListener('click', () => jumpToQuestionById(id));
        dom.pdfMissingList.appendChild(btn);
    });
}
