/** Question card builder (work view). */
import { deps } from './deps.js';
import { state } from './runtime.js';
import {
    confidenceTooltip,
    normalizeCategoryLabel,
    normalizeRatingValue,
    normalizeText,
    ratingDisplayHint,
    ratingDisplayLabel,
    ratingKey,
    RATING_OPTIONS,
} from './form-utils.js';
import {
    applyDetailsFilters,
    createEl,
    detailsFilters,
    goToNextTodoQuestion,
    normalizeWorkflowState,
    parseEvidenceLinesSafe,
    ratingClass,
    updateFormQuestion,
} from './form-details.js';
import { scheduleLocalDraftSave } from './autosave.js';

function confidenceDots(level) {
    if (level === 'high') return '•••';
    if (level === 'medium') return '••';
    if (level === 'low') return '•';
    return '';
}

function hasAutoSuggestion(question) {
    const suggested = normalizeRatingValue(question.auto_suggested_rating);
    return !!(
        question.heuristic_rating
        || (suggested && suggested !== 'nehodnoceno')
        || question.proposal_source === 'auto'
    );
}

export function buildQuestion(sectionIndex, question, questionIndex) {
    const questionDetails = createEl('details', { class: 'qd q-item q-card' });
    const questionId = question.id ? `#${question.id}` : `#${sectionIndex + 1}-${questionIndex + 1}`;
    const baseId = `q_${sectionIndex}_${questionIndex}`;
    const isHeuristicEvaluated = !!question.heuristic_rating;
    const initialRating = normalizeRatingValue(question.rating);
    const description = (question.description || '').toString().trim();
    const heuristic = (question.heuristic || '').toString().trim();
    const categoryKey = `${question.category || ''}`.toLowerCase();
    const isMustCategory = categoryKey.startsWith('must');

    const summary = createEl('summary', { class: 'q-summary' });
    summary.appendChild(createEl('span', { class: 'caret', html: '▸' }));
    summary.appendChild(createEl('span', { class: 'q-card__tone', 'aria-hidden': 'true' }));
    const titleWrap = createEl('span', { class: 'q-title' });
    titleWrap.appendChild(createEl('span', { class: 'q-text', text: question.text || '' }));
    summary.appendChild(titleWrap);
    const humanStatus = createEl('span', {
        class: 'q-human-status',
        text: 'Doplň',
    });
    summary.appendChild(humanStatus);
    questionDetails.appendChild(summary);

    let syncSearchIndex = () => { };
    let currentStatusLabel = '';

    const body = createEl('div', { class: 'q-body q-body--stack' });

    const ratingBadge = createEl('span', {
        class: `q-rating badge ${ratingClass(initialRating)}`,
        text: ratingDisplayLabel(initialRating),
        hidden: true,
    });
    // Detached sync target for rating badge updates (not shown in chrome).

    const autoChip = createEl('span', {
        class: 'q-auto-chip',
        hidden: true,
    });
    autoChip.appendChild(createEl('span', { class: 'q-auto-chip__label', text: 'Automat' }));
    const autoDots = createEl('span', {
        class: 'q-auto-chip__dots',
        'aria-hidden': 'true',
    });
    autoChip.appendChild(autoDots);

    let actionsRow = null;
    let doneBtn = null;

    const syncActionsVisibility = () => {
        if (!actionsRow || !doneBtn) return;
        actionsRow.hidden = !!(doneBtn.hidden && autoChip.hidden);
    };

    const updateAutoChip = () => {
        const wf = (question.review_state || '').toString().toUpperCase();
        const show = hasAutoSuggestion(question) || wf === 'CONFIRM' || wf === 'AUTO';
        autoChip.hidden = !show;
        if (!show) {
            autoChip.removeAttribute('title');
            autoChip.dataset.level = '';
            questionDetails.dataset.confidence = '';
            syncActionsVisibility();
            return;
        }
        const conf = deps.resolveQuestionConfidence(question);
        const level = conf?.level || '';
        autoChip.dataset.level = level;
        autoDots.textContent = confidenceDots(level);
        autoChip.title = conf
            ? confidenceTooltip(conf.level)
            : (wf === 'MANUAL' && hasAutoSuggestion(question)
                ? 'Návrh automatu k přijetí — zkontroluj a potvrď.'
                : 'Výsledek předvyplnil automat — zkontroluj a potvrď.');
        questionDetails.dataset.confidence = level;
        syncActionsVisibility();
    };

    const updateRatingBadge = () => {
        const rating = normalizeRatingValue(question.rating);
        ratingBadge.textContent = ratingDisplayLabel(rating);
        ['ok', 'mid', 'err'].forEach(cls => ratingBadge.classList.remove(cls));
        const newClass = ratingClass(rating);
        if (newClass) ratingBadge.classList.add(newClass);
        questionDetails.dataset.rating = ratingKey(rating);
        segmentRoot?.querySelectorAll('.rating-segment__btn').forEach(btn => {
            btn.dataset.active = btn.dataset.value === rating ? 'true' : 'false';
        });
        updateAutoChip();
        syncDoneEnabled();
    };

    const syncDoneEnabled = () => {
        const rating = normalizeRatingValue(question.rating);
        const suggested = normalizeRatingValue(question.auto_suggested_rating);
        const canConfirm = rating !== 'nehodnoceno' || suggested !== 'nehodnoceno';
        doneBtn.disabled = !question.checked && !canConfirm;
    };

    const updateCardTone = (uiState) => {
        const needsAction = uiState !== 'done';
        questionDetails.dataset.cardTone = uiState === 'done'
            ? 'done'
            : (uiState === 'confirm' ? 'review' : 'todo');
        questionDetails.dataset.needsAction = needsAction ? 'true' : 'false';
        questionDetails.dataset.mustOpen = isMustCategory ? 'true' : 'false';
    };

    const syncNotePlaceholder = (uiState) => {
        if (uiState === 'confirm') {
            noteField.placeholder = 'Uprav nebo potvrď';
            noteField.classList.toggle('q-note-hero--auto', hasAutoSuggestion(question) || !!(question.note || '').trim());
        } else if (uiState === 'done') {
            noteField.placeholder = 'Poznámka';
            noteField.classList.remove('q-note-hero--auto');
        } else {
            noteField.placeholder = 'Co jsi ověřil…';
            noteField.classList.remove('q-note-hero--auto');
        }
    };

    const updateWorkflowBadge = () => {
        const wf = normalizeWorkflowState(question.review_state, question, question.rating);
        question.review_state = wf;
        if (wf === 'AUTO') {
            question.checked = true;
            question.checked_source = 'auto';
        }
        const isChecked = !!question.checked;
        const awaitingConfirm = !isChecked && (
            wf === 'CONFIRM'
            || hasAutoSuggestion(question)
        );

        let statusText = 'Doplň';
        let uiState = 'fill';
        if (isChecked) {
            statusText = 'Hotovo';
            uiState = 'done';
        } else if (awaitingConfirm) {
            statusText = hasAutoSuggestion(question) && wf === 'MANUAL'
                ? 'Přijmout návrh'
                : 'Potvrdit';
            uiState = 'confirm';
        }

        humanStatus.textContent = statusText;
        currentStatusLabel = statusText;
        question.requires_confirmation = awaitingConfirm;
        questionDetails.dataset.workflow = wf.toLowerCase();
        questionDetails.dataset.checked = isChecked ? 'true' : 'false';
        questionDetails.dataset.uiState = uiState;

        if (isChecked) {
            doneBtn.textContent = 'Hotovo ✓';
            doneBtn.classList.add('is-done');
            doneBtn.classList.remove('btn-primary');
            doneBtn.classList.add('btn-secondary');
            doneBtn.hidden = true;
        } else if (awaitingConfirm) {
            doneBtn.textContent = hasAutoSuggestion(question) && wf === 'MANUAL'
                ? 'Přijmout návrh'
                : 'Potvrdit';
            doneBtn.classList.remove('is-done');
            doneBtn.classList.add('btn-primary');
            doneBtn.classList.remove('btn-secondary');
            doneBtn.hidden = false;
        } else {
            doneBtn.textContent = 'Hotovo';
            doneBtn.classList.remove('is-done');
            doneBtn.classList.add('btn-primary');
            doneBtn.classList.remove('btn-secondary');
            doneBtn.hidden = false;
        }

        updateCardTone(uiState);
        updateAutoChip();
        syncNotePlaceholder(uiState);
        syncDoneEnabled();
        syncActionsVisibility();
    };

    const segmentRoot = createEl('div', {
        class: 'rating-segment',
        role: 'group',
        'aria-label': 'Výsledek',
    });
    const segmentOptions = [...RATING_OPTIONS];

    const applyRating = (rating) => {
        const normalized = normalizeRatingValue(rating);
        question.rating = normalized;
        updateFormQuestion(sectionIndex, questionIndex, 'rating', normalized);
        if (question.review_state === 'AUTO' && normalized !== 'splňuje') {
            question.review_state = 'CONFIRM';
            question.checked = false;
            question.checked_source = '';
        } else if (question.review_state === 'AUTO') {
            question.checked = true;
            question.checked_source = 'auto';
        } else if (question.checked && question.checked_source === 'manual') {
            // Editing after confirm → needs re-confirm
            question.checked = false;
            question.checked_source = '';
            if (hasAutoSuggestion(question) || question.review_state === 'CONFIRM') {
                question.review_state = 'CONFIRM';
            }
        }
        updateRatingBadge();
        updateWorkflowBadge();
        syncSearchIndex();
        applyDetailsFilters();
        deps.updateWorkRemaining(state.form);
        scheduleLocalDraftSave();
    };

    segmentOptions.forEach(option => {
        const btn = createEl('button', {
            type: 'button',
            class: `rating-segment__btn rating-segment__btn--${ratingKey(option)}`,
            text: ratingDisplayLabel(option),
            title: ratingDisplayHint(option),
        });
        btn.dataset.value = option;
        btn.dataset.active = option === initialRating ? 'true' : 'false';
        btn.addEventListener('click', () => applyRating(option));
        segmentRoot.appendChild(btn);
    });

    const actionsRowEl = createEl('div', { class: 'q-actions-row' }, [autoChip]);
    actionsRow = actionsRowEl;
    doneBtn = createEl('button', {
        type: 'button',
        class: 'q-done-btn btn-primary',
        text: 'Hotovo',
    });
    actionsRowEl.appendChild(doneBtn);

    const ratingField = createEl('div', { class: 'q-field q-field--rating' }, [
        createEl('label', { class: 'q-label q-label--compact', text: 'Výsledek' }),
        segmentRoot,
        actionsRowEl,
    ]);

    const noteField = createEl('textarea', {
        class: 'q-note-hero',
        placeholder: 'Co jsi ověřil…',
    });
    noteField.id = `${baseId}_note`;
    noteField.rows = 2;
    noteField.value = (question.note || '').toString();
    noteField.addEventListener('input', () => {
        updateFormQuestion(sectionIndex, questionIndex, 'note', noteField.value);
        syncSearchIndex();
        if (detailsFilters.search) applyDetailsFilters();
        scheduleLocalDraftSave();
    });

    const noteActions = createEl('div', { class: 'q-note-actions' });
    const aiBadge = createEl('span', {
        class: 'q-badge q-badge--ai',
        text: 'Návrh AI',
        hidden: true,
    });
    aiBadge.title = 'Toto navrhla AI — není ověřený závěr. Uprav nebo potvrď.';
    if (question.proposal_source === 'ai' || question.ai_note_pending) {
        aiBadge.hidden = false;
    }
    const showAiBadge = () => {
        aiBadge.hidden = false;
        question.proposal_source = 'ai';
        question.ai_note_pending = true;
        updateFormQuestion(sectionIndex, questionIndex, 'proposal_source', 'ai');
    };
    const hideAiBadgeIfEmpty = () => {
        if (!(noteField.value || '').trim()) {
            aiBadge.hidden = true;
            question.ai_note_pending = false;
        }
    };
    noteField.addEventListener('input', hideAiBadgeIfEmpty);

    if (state.ai?.available && deps.canWrite()) {
        const aiBtn = createEl('button', {
            type: 'button',
            class: 'q-ai-link',
            text: 'Navrhnout poznámku (AI)',
        });
        aiBtn.title = 'Návrh do pole poznámky — rating se nemění. Musíš potvrdit / upravit.';
        aiBtn.addEventListener('click', async () => {
            if (!deps.canWrite()) {
                deps.openAuthGate({ message: 'Pro AI návrh zadej přístupový kód.' });
                return;
            }
            aiBtn.disabled = true;
            const prev = aiBtn.textContent;
            aiBtn.textContent = 'Navrhuji…';
            try {
                const response = await fetch('/api/ai/suggest-note', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        evaluation_id: state.draftId || state.form?._evaluation_id || '',
                        question: {
                            id: question.id,
                            text: question.text,
                            description: question.description,
                            evidence: question.evidence,
                            note: noteField.value,
                            heuristic: question.heuristic,
                            rating: question.rating,
                            category: question.category,
                        },
                    }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) {
                    const detail = data.detail;
                    const msg = typeof detail === 'string'
                        ? detail
                        : (detail?.message || data.message || 'AI návrh selhal');
                    throw new Error(msg);
                }
                const suggestion = (data.suggestion || '').trim();
                if (!suggestion) throw new Error('Prázdný návrh');
                noteField.value = suggestion;
                updateFormQuestion(sectionIndex, questionIndex, 'note', suggestion);
                question.ai_model = data.model || '';
                question.ai_provider = data.provider || '';
                question.ai_suggested_at = data.timestamp || new Date().toISOString();
                updateFormQuestion(sectionIndex, questionIndex, 'ai_model', question.ai_model);
                updateFormQuestion(sectionIndex, questionIndex, 'ai_provider', question.ai_provider);
                updateFormQuestion(sectionIndex, questionIndex, 'ai_suggested_at', question.ai_suggested_at);
                showAiBadge();
                scheduleLocalDraftSave();
                deps.showToast('Návrh AI vložen — uprav a potvrď.', { ok: true });
            } catch (error) {
                deps.setStatus(error.message || 'AI návrh selhal', false);
            } finally {
                aiBtn.disabled = false;
                aiBtn.textContent = prev;
            }
        });
        noteActions.appendChild(aiBtn);
    }
    noteActions.appendChild(aiBadge);

    const noteFieldWrap = createEl('div', { class: 'q-field q-field--note' }, [
        createEl('label', { class: 'q-label q-label--compact', for: `${baseId}_note`, text: 'Poznámka' }),
        noteField,
        noteActions,
    ]);

    body.appendChild(createEl('div', { class: 'q-main' }, [ratingField, noteFieldWrap]));

    doneBtn.addEventListener('click', () => {
        let rating = normalizeRatingValue(question.rating);
        if (rating === 'nehodnoceno') {
            const suggested = normalizeRatingValue(question.auto_suggested_rating);
            if (suggested !== 'nehodnoceno') {
                rating = suggested;
            } else {
                deps.setStatus('Nejdřív zvol výsledek', false);
                segmentRoot.querySelector('.rating-segment__btn')?.focus();
                return;
            }
        }
        question.rating = rating;
        updateFormQuestion(sectionIndex, questionIndex, 'rating', rating);
        question.checked = true;
        question.checked_source = 'manual';
        if (question.review_state === 'AUTO') question.review_state = 'CONFIRM';
        updateRatingBadge();
        updateWorkflowBadge();
        syncSearchIndex();
        applyDetailsFilters();
        deps.updateWorkRemaining(state.form);
        scheduleLocalDraftSave();
        window.setTimeout(() => goToNextTodoQuestion({ announce: true }), 200);
    });

    const extras = createEl('details', { class: 'q-extras' });
    const categoryLabel = normalizeCategoryLabel(question.category) || '';
    const syncExtrasSummary = (count) => {
        const parts = ['Podklady'];
        if (count) parts[0] = `Podklady (${count})`;
        parts.push(questionId.replace(/^#/, ''));
        if (categoryLabel) parts.push(categoryLabel);
        extrasSummary.textContent = parts.join(' · ');
    };
    const extrasSummary = createEl('summary', { class: 'q-extras__summary' });
    syncExtrasSummary(parseEvidenceLinesSafe(question.evidence).length);
    extras.appendChild(extrasSummary);
    const extrasBody = createEl('div', { class: 'q-extras__body' });

    if (description || heuristic) {
        const context = createEl('div', { class: 'q-context-muted' });
        if (description) {
            context.appendChild(createEl('p', { class: 'q-desc', text: description }));
        }
        if (heuristic) {
            context.appendChild(createEl('p', {
                class: 'q-heuristic muted small',
                text: heuristic,
            }));
        }
        extrasBody.appendChild(context);
    }

    const evidenceList = createEl('ul', { class: 'q-evidence-list' });
    const evidenceAddInput = createEl('input', {
        type: 'url',
        class: 'q-evidence-add-input',
        placeholder: 'https://…',
    });
    evidenceAddInput.id = `${baseId}_evidence_add`;

    const parseEvidenceLines = parseEvidenceLinesSafe;

    const writeEvidence = lines => {
        const value = lines.join('\n');
        question.evidence = value;
        updateFormQuestion(sectionIndex, questionIndex, 'evidence', value);
        renderEvidenceList();
        const n = lines.length;
        syncExtrasSummary(n);
        syncSearchIndex();
        if (detailsFilters.search) applyDetailsFilters();
        scheduleLocalDraftSave();
    };

    const renderEvidenceList = () => {
        evidenceList.textContent = '';
        const lines = parseEvidenceLines(question.evidence);
        if (!lines.length) {
            evidenceList.appendChild(createEl('li', {
                class: 'q-evidence-list__empty muted small',
                text: 'Zatím žádné odkazy.',
            }));
            return;
        }
        lines.forEach((line, idx) => {
            const item = createEl('li', { class: 'q-evidence-list__item' });
            if (/^https?:\/\//i.test(line)) {
                const anchor = createEl('a', { href: line, text: line, target: '_blank', rel: 'noopener noreferrer' });
                item.appendChild(anchor);
            } else {
                item.appendChild(document.createTextNode(line));
            }
            const removeBtn = createEl('button', {
                type: 'button',
                class: 'btn-ghost q-evidence-remove',
                text: '×',
                title: 'Odebrat',
                'aria-label': 'Odebrat odkaz',
            });
            removeBtn.addEventListener('click', () => {
                const next = parseEvidenceLines(question.evidence).filter((_, i) => i !== idx);
                writeEvidence(next);
            });
            item.appendChild(removeBtn);
            evidenceList.appendChild(item);
        });
    };

    const addEvidenceBtn = createEl('button', {
        type: 'button',
        class: 'btn-secondary',
        text: 'Přidat',
    });
    addEvidenceBtn.addEventListener('click', () => {
        const value = (evidenceAddInput.value || '').trim();
        if (!value) {
            evidenceAddInput.focus();
            return;
        }
        const next = parseEvidenceLines(question.evidence);
        if (!next.includes(value)) next.push(value);
        writeEvidence(next);
        evidenceAddInput.value = '';
        evidenceAddInput.focus();
    });
    evidenceAddInput.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
            event.preventDefault();
            addEvidenceBtn.click();
        }
    });

    renderEvidenceList();
    extrasBody.appendChild(createEl('div', { class: 'q-field q-field--evidence' }, [
        evidenceList,
        createEl('div', { class: 'q-evidence-add' }, [evidenceAddInput, addEvidenceBtn]),
    ]));
    extras.appendChild(extrasBody);
    body.appendChild(extras);

    questionDetails.appendChild(body);

    syncSearchIndex = () => {
        const terms = [
            questionId,
            question.text,
            description,
            heuristic,
            question.rating,
            ratingDisplayLabel(question.rating),
            currentStatusLabel,
            question.review_state,
            question.checked ? 'hotovo' : 'k vyřízení',
            noteField.value,
            question.evidence,
            question.category,
        ]
            .filter(Boolean)
            .join(' ');
        questionDetails.dataset.search = normalizeText(terms);
    };

    questionDetails.dataset.rating = ratingKey(initialRating);
    questionDetails.dataset.eval = isHeuristicEvaluated ? 'heuristic' : 'manual';
    questionDetails.dataset.questionId = `${question.id || `${sectionIndex + 1}-${questionIndex + 1}`}`;
    questionDetails.dataset.mustOpen = isMustCategory ? 'true' : 'false';
    updateRatingBadge();
    updateWorkflowBadge();
    syncSearchIndex();

    return questionDetails;
}
