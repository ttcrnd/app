import {
    CATEGORY_LABELS,
    RATING_LABELS,
    RATING_OPTIONS,
    confidenceLabel,
    confidenceTooltip,
    libraryDisplayName,
    normalizeCategoryLabel,
    normalizeRatingValue,
    normalizeText,
    ratingDisplayLabel,
    ratingKey,
} from './form-utils.js';
import {
    AUTOSAVE_LOCAL_MS,
    AUTOSAVE_SERVER_MS,
    EXAMPLE_CATALOG,
    LAST_OPEN_KEY,
    LOCAL_DRAFT_KEY,
    PIPELINE_STEP_LABELS,
    PIPELINE_STEPS,
    dom,
    state,
    timers,
} from './runtime.js';
import { bindDeps, deps } from './deps.js';
import * as auth from './auth.js';
import * as catalog from './catalog.js';
import * as work from './work.js';
import * as pipeline from './pipeline.js';
import * as autosave from './autosave.js';
import * as formDetails from './form-details.js';

const {
    canWrite,
    canManageUsers,
    setAuthGateError,
    openAuthGate,
    closeAuthGate,
    applyAuthPayload,
    setAuthGateTab,
    updateAuthChrome,
    apiErrorPayload,
    hideTokenRowUnlessForced,
    revealTokenRow,
    refreshAuthStatus,
    handleAuthEnter,
    handleAuthLogin,
    handleAuthLogout,
    setUsersFormError,
    loadUsersAdmin,
    handleCreateUser,
    browseExamplesWithoutCode,
} = auth;

const {
    exampleMeta,
    catalogStatusKind,
    hideLibraryDetail,
    renderLibraryDetail,
    openLibraryDetail,
    catalogStatusLabel,
    renderLibraryCatalog,
    loadLibrariesList,
    syncWorkToSelectedLibrary,
    syncSelectedLibraryFromForm,
} = catalog;

const {
    countRemainingWork,
    resolveQuestionConfidence,
    jumpToQuestionById,
    updateWorkRemaining,
    updateWorkStrip,
    syncWorkFooter,
    jumpToFlaggedQuestion,
    syncOfficialPdfButton,
    renderPdfReadiness,
} = work;

const {
    openPipelineDrawer,
    closePipelineDrawer,
    getPipelineStepEl,
    setPipelineCardStatus,
    setPipelineTitle,
    setPipelinePhase,
    updatePipelineAliveText,
    startPipelineAliveTicker,
    stopPipelineAliveTicker,
    markPipelineStep,
    updatePipelineProgress,
    resetPipelineProgress,
    activatePipelineStep,
    completePipelineStep,
    markPipelineStepAsFailed,
    failPipelineStep,
    startPipelineRun,
    finishPipelineRun,
    parsePipelineLog,
    appendLog,
} = pipeline;

const {
    formatSaveClock,
    setSaveStatus,
    buildEvaluationTitle,
    ensureEvaluationMeta,
    rememberLastOpen,
    writeLocalBackup,
    scheduleLocalDraftSave,
    scheduleAutosave,
    saveToServerNow,
    flushAutosaveSync,
} = autosave;

const {
    RATING_KEYS,
    EVALUATION_KEYS,
    EVALUATION_LABELS,
    createDefaultDetailsFilters,
    createEmptyFilterRefs,
    resetDetailsFilters,
    questionItemNeedsAction,
    getActiveFilterState,
    normalizeWorkflowState,
    normalizeQuestionWorkflow,
    toggleFilterSet,
    updateAllFilterControls,
    goToNextTodoQuestion,
    createEl,
    createFilterChip,
    createFilterGroup,
    buildDetailsToolbar,
    createRatingSelect,
    ratingClass,
    ratingScoreFromKey,
    setProgressTone,
    updateSectionProgress,
    createLinkifiedFragment,
    fillEvidencePreview,
    updateFormQuestion,
    orderSections,
    isGateSection,
    sectionTypeBadge,
    renderDetails,
    buildSection,
    parseEvidenceLinesSafe,
    buildQuestion,
    applyDetailsFilters,
} = formDetails;

async function setView(view) {
    const allowed = ['home', 'work', 'users'];
    const next = allowed.includes(view) ? view : 'home';
    const prev = state.view;
    state.view = next;
    const isHome = state.view === 'home';
    const isWork = state.view === 'work';
    const isUsers = state.view === 'users';
    if (dom.viewHome) dom.viewHome.hidden = !isHome;
    if (dom.viewWork) dom.viewWork.hidden = !isWork;
    if (dom.viewUsers) dom.viewUsers.hidden = !isUsers;
    dom.navHomeBtn?.classList.toggle('is-active', isHome);
    dom.navWorkBtn?.classList.toggle('is-active', isWork);
    dom.navUsersBtn?.classList.toggle('is-active', isUsers);
    if (dom.navWorkBtn) {
        dom.navWorkBtn.disabled = !(state.form || state.selectedLibraryId);
    }
    if (isUsers) {
        loadUsersAdmin();
    }
    if (!isWork) closeMoreMenu();
    if (prev !== next) {
        const panel = isHome ? dom.viewHome : (isWork ? dom.viewWork : dom.viewUsers);
        if (panel) {
            panel.classList.remove('view--enter');
            // force reflow for enter animation
            void panel.offsetWidth;
            panel.classList.add('view--enter');
            window.clearTimeout(setView._enterTimer);
            setView._enterTimer = window.setTimeout(() => {
                panel.classList.remove('view--enter');
            }, 220);
        }
    }
    if (isWork && state.selectedLibraryId && !state._libraryWorkSync) {
        await syncWorkToSelectedLibrary();
        if (dom.navWorkBtn) {
            dom.navWorkBtn.disabled = !(state.form || state.selectedLibraryId);
        }
    }
}



function showToast(message, { ok = true, ms = 4200 } = {}) {
    if (!dom.appToast) {
        setStatus(message, ok);
        return;
    }
    dom.appToast.hidden = false;
    dom.appToast.textContent = message;
    dom.appToast.dataset.ok = ok ? 'true' : 'false';
    dom.appToast.classList.remove('app-toast--out');
    dom.appToast.classList.add('app-toast--in');
    window.clearTimeout(showToast._timer);
    window.clearTimeout(showToast._outTimer);
    showToast._timer = window.setTimeout(() => {
        if (!dom.appToast) return;
        dom.appToast.classList.remove('app-toast--in');
        dom.appToast.classList.add('app-toast--out');
        showToast._outTimer = window.setTimeout(() => {
            if (dom.appToast) {
                dom.appToast.hidden = true;
                dom.appToast.classList.remove('app-toast--out');
            }
        }, 180);
    }, ms);
}

function closeMoreMenu() {
    if (dom.moreMenuPanel) dom.moreMenuPanel.hidden = true;
    if (dom.moreMenuBtn) dom.moreMenuBtn.setAttribute('aria-expanded', 'false');
}

function toggleMoreMenu() {
    if (!dom.moreMenuPanel || !dom.moreMenuBtn) return;
    const open = dom.moreMenuPanel.hidden;
    dom.moreMenuPanel.hidden = !open;
    dom.moreMenuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function showNewEvalPanel(show) {
    if (!dom.newEvalPanel) return;
    if (show && !canWrite()) {
        if (state.auth.authenticated && state.auth.role === 'viewer') {
            setStatus('Role viewer je jen pro čtení katalogu.', false);
            return;
        }
        openAuthGate({ message: 'Pro nové hodnocení se nejdřív přihlas.' });
        return;
    }
    dom.newEvalPanel.hidden = !show;
    if (show) {
        hideTokenRowUnlessForced();
        dom.repoInput?.focus();
    }
}

function openCompleteDialog() {
    if (!dom.completeDialog) return;
    if (!state.draftId && !(state.form && (state.form._evaluation_id || state.form._draft_id))) {
        setStatus('Nejdřív ulož hodnocení, pak ho dokonči.', false);
        return;
    }
    if (dom.completeNote) dom.completeNote.value = '';
    if (dom.completeDialogError) {
        dom.completeDialogError.hidden = true;
        dom.completeDialogError.textContent = '';
    }
    const completedRadio = dom.completeDialog.querySelector('input[name="completeOutcome"][value="completed"]');
    if (completedRadio) completedRadio.checked = true;
    dom.completeDialog.hidden = false;
}

function closeCompleteDialog() {
    if (dom.completeDialog) dom.completeDialog.hidden = true;
}

async function submitCompleteDialog() {
    const evaluationId = state.draftId
        || state.form?._evaluation_id
        || state.form?._draft_id
        || state.form?.meta?.evaluation_id;
    if (!evaluationId) {
        if (dom.completeDialogError) {
            dom.completeDialogError.hidden = false;
            dom.completeDialogError.textContent = 'Chybí ID hodnocení — nejdřív ulož.';
        }
        return;
    }
    const outcomeEl = dom.completeDialog?.querySelector('input[name="completeOutcome"]:checked');
    const outcome = outcomeEl?.value || 'completed';
    const note = (dom.completeNote?.value || '').trim();
    if (note.length < 3) {
        if (dom.completeDialogError) {
            dom.completeDialogError.hidden = false;
            dom.completeDialogError.textContent = 'Poznámka je povinná (alespoň pár slov).';
        }
        return;
    }
    try {
        await saveToServerNow({ quiet: true });
        const response = await fetch(`/api/evaluations/${encodeURIComponent(evaluationId)}/complete`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ outcome, note }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || data.message || 'Dokončení selhalo');
        }
        if (state.form) {
            if (!state.form.meta) state.form.meta = {};
            state.form.meta.completion_status = data.status;
            state.form.meta.completion_note = note;
            state.form.meta.completion_label = data.status_label;
        }
        closeCompleteDialog();
        const label = data.status_label || catalogStatusLabel(data.status);
        showToast(`Označeno: ${label}`, { ok: true });
        setStatus(`Hodnocení označeno jako „${label}“`, true);
        openSignDialog(evaluationId);
    } catch (error) {
        if (dom.completeDialogError) {
            dom.completeDialogError.hidden = false;
            dom.completeDialogError.textContent = error.message || 'Dokončení selhalo';
        }
    }
}

function openSignDialog(evaluationId) {
    state.pendingSignEvaluationId = evaluationId || null;
    if (!dom.signDialog || !evaluationId) {
        refreshHomeCatalog().then(() => setView('home'));
        return;
    }
    if (dom.signDialogError) {
        dom.signDialogError.hidden = true;
        dom.signDialogError.textContent = '';
    }
    dom.signDialog.hidden = false;
}

function closeSignDialog() {
    if (dom.signDialog) dom.signDialog.hidden = true;
    state.pendingSignEvaluationId = null;
}

async function finishAfterComplete() {
    closeSignDialog();
    await refreshHomeCatalog();
    setView('home');
}

async function submitSignDialog() {
    const evaluationId = state.pendingSignEvaluationId;
    if (!evaluationId) {
        await finishAfterComplete();
        return;
    }
    try {
        const response = await fetch(`/api/evaluations/${encodeURIComponent(evaluationId)}/sign`, {
            method: 'POST',
            credentials: 'same-origin',
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(
                (typeof data.detail === 'string' ? data.detail : data.detail?.message)
                || data.message
                || 'Podpis selhal'
            );
        }
        showToast('Export podepsán (Ed25519)', { ok: true });
        if (state.form?.meta) {
            state.form.meta.signature = data.sig;
            state.form.meta.signed = true;
        }
        await finishAfterComplete();
    } catch (error) {
        if (dom.signDialogError) {
            dom.signDialogError.hidden = false;
            dom.signDialogError.textContent = `${error.message || 'Podpis selhal'} — hodnocení zůstalo uložené.`;
        }
    }
}

async function downloadSignedExport() {
    const evaluationId = state.draftId
        || state.form?._evaluation_id
        || state.form?._draft_id
        || state.form?.meta?.evaluation_id;
    if (!evaluationId) {
        setStatus('Nejdřív otevři dokončené hodnocení', false);
        return;
    }
    try {
        const response = await fetch(
            `/api/evaluations/${encodeURIComponent(evaluationId)}/signed-export`,
            { credentials: 'same-origin' }
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || 'Podepsaný export není k dispozici');
        }
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `signed_${evaluationId}.json`;
        a.click();
        URL.revokeObjectURL(url);
        setStatus('Podepsaný export stažen', true);
    } catch (error) {
        setStatus(error.message || 'Stažení podpisu selhalo', false);
    }
}


const WORKFLOW_STATES = ['AUTO', 'CONFIRM', 'MANUAL'];


function setStatus(text, ok = null) {
    dom.status.textContent = text;
    dom.status.className = 'muted status';
    if (ok === true) dom.status.className += ' badge ok';
    if (ok === false) dom.status.className += ' badge err';
}

function setFileStatus(text, ok = null) {
    if (!dom.fileStatus) return;
    dom.fileStatus.textContent = text || '';
    dom.fileStatus.className = 'muted small file-status';
    if (ok === true) dom.fileStatus.className += ' badge ok';
    if (ok === false) dom.fileStatus.className += ' badge err';
}

function describeValidationError(detail) {
    if (!detail) return 'Soubor se nepodařilo ověřit. Zkus to znovu.';
    if (typeof detail === 'string') return detail;
    if (typeof detail === 'object') {
        if (detail.message && detail.path) {
            return `${detail.message} (${detail.path})`;
        }
        if (detail.message) return detail.message;
    }
    return 'Soubor se nepodařilo ověřit. Zkontroluj jeho strukturu a zkus to znovu.';
}

function renderSummary(form) {
    if (!form?.summary) {
        dom.summary.textContent = '';
        return;
    }
    const cutoffsPass = !!form.summary.cutoffs?.passed;
    const cutoffs = cutoffsPass ? 'projde (must-have OK)' : 'neprojde (must-have selhalo)';
    const score = form.summary.overall_score;
    const gradeRaw = `${form.summary.grade || ''}`.trim().toUpperCase();
    const gradeMap = {
        A: 'A — výborné',
        B: 'B — dobré',
        C: 'C — přijatelné',
        D: 'D — slabé',
        F: 'F — nedostatečné',
    };
    const grade = gradeMap[gradeRaw] || (gradeRaw || '—');
    const calibrationProfile = form.summary.calibration?.profile || 'výchozí';
    const referencePositionRaw = form.summary.calibration?.reference_position || '';
    const referencePosition = {
        'reference-excellent': 'Referenční výborná',
        'reference-good': 'Referenční dobrá',
        'reference-min': 'Referenční minimum',
        'below-reference': 'Pod referencí',
    }[referencePositionRaw] || 'není k dispozici';
    dom.summary.innerHTML = `
    <div class="internal-score">
      <p class="muted small"><strong>Pozor:</strong> toto není oficiální verdikt NÚKIB — jen pracovní pomůcka.</p>
      <div><strong>Povinné body (must-have):</strong> ${cutoffs}</div>
      <div><strong>Interní skóre:</strong> ${score} %</div>
      <div><strong>Interní známka:</strong> ${grade}</div>
      <div><strong>Kalibrační profil:</strong> ${calibrationProfile}</div>
      <div><strong>Pozice vs. reference:</strong> ${referencePosition}</div>
      <div class="muted">Oficiální výstup = Formulář v1.0 dle metodiky (sekce 6.1–6.5).</div>
    </div>`;
}

function renderSummaryHint(form) {
    if (!dom.summaryHint) return;
    if (!form || typeof form !== 'object') {
        dom.summaryHint.textContent = 'Kalibrované skóre vychází z bodů pro ratingy a z vah kategorií otázek definovaných ve formuláři (scoring).';
        return;
    }
    const scoring = form.scoring && typeof form.scoring === 'object' ? form.scoring : {};
    const points = scoring.rating_points && typeof scoring.rating_points === 'object'
        ? scoring.rating_points
        : {};
    const categories = scoring.category_weights && typeof scoring.category_weights === 'object'
        ? scoring.category_weights
        : {};
    const pPass = Number.isFinite(Number(points['splňuje'])) ? Number(points['splňuje']) : 1.0;
    const pPartial = Number.isFinite(Number(points['částečně splňuje'])) ? Number(points['částečně splňuje']) : 0.5;
    const pFail = Number.isFinite(Number(points['nesplňuje'])) ? Number(points['nesplňuje']) : 0.0;
    const pUnknown = Number.isFinite(Number(points['nehodnoceno'])) ? Number(points['nehodnoceno']) : 0.0;
    const wMust = Number.isFinite(Number(categories['must have'])) ? Number(categories['must have']) : 1.0;
    const wGood = Number.isFinite(Number(categories['good to have'])) ? Number(categories['good to have']) : 1.0;
    const wNice = Number.isFinite(Number(categories['nice to have'])) ? Number(categories['nice to have']) : 1.0;
    dom.summaryHint.textContent = `Kalibrované skóre (interní): splňuje ${(pPass * 100).toFixed(0)} %, částečně ${(pPartial * 100).toFixed(0)} %, nesplňuje ${(pFail * 100).toFixed(0)} %, nehodnoceno ${(pUnknown * 100).toFixed(0)} %. Váhy kategorií: must ${wMust.toFixed(2)}, good ${wGood.toFixed(2)}, nice ${wNice.toFixed(2)}. Oficiální odevzdávka = Formulář v1.0.`;
}

function resolveFormRepositoryMeta(form) {
    const rootMeta = form?.meta || {};
    const sectionMeta = (form?.sections || [])
        .find(section => section && typeof section === 'object' && section.meta && typeof section.meta === 'object')
        ?.meta || {};

    const repo = (
        rootMeta.repo
        || sectionMeta.repo
        || ''
    ).toString().trim();

    const version = (
        rootMeta.evaluated_repo_version
        || rootMeta.effective_ref
        || rootMeta.requested_ref
        || sectionMeta.effective_ref
        || sectionMeta.requested_ref
        || sectionMeta.default_branch
        || ''
    ).toString().trim();

    return { repo, version };
}

function formatStartedDate(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
        return `${iso}`.slice(0, 10);
    }
    return date.toLocaleDateString('cs-CZ', {
        day: 'numeric',
        month: 'numeric',
        year: 'numeric',
    });
}


function resolveFormIdentity(form) {
    const { repo, version } = resolveFormRepositoryMeta(form);
    const meta = form?.meta && typeof form.meta === 'object' ? form.meta : {};
    const startedAt = meta.started_at || form?._started_at || '';
    const evaluationId = form?._evaluation_id || meta.evaluation_id || meta.run_id || state.draftId || '';
    const commitSha = meta.commit_sha || meta.sha || '';
    const collectionStatus = meta.collection_status || '';
    return {
        repo,
        version,
        library: libraryDisplayName(repo),
        startedAt,
        evaluationId,
        commitSha,
        collectionStatus,
        runPath: meta.run_path || '',
    };
}

function renderRepositoryMeta(form) {
    if (!dom.repoMeta) return;
    if (!form) {
        dom.repoMeta.textContent = 'Hodnoceno: —';
        renderTechDetails(null);
        renderEvidencePack(null);
        renderMetaIdentity(null);
        renderRatingDiff(null);
        return;
    }
    const id = resolveFormIdentity(form);
    const parts = [];
    parts.push(id.library || id.repo || 'Hodnocení');
    if (id.version) parts.push(id.version);
    const started = formatStartedDate(id.startedAt);
    if (started) parts.push(started);
    const meta = form?.meta && typeof form.meta === 'object' ? form.meta : {};
    const libType = (meta.library_type || meta.type || '').toString().trim();
    if (libType) parts.push(libType);
    dom.repoMeta.textContent = parts.join(' · ');
    if (id.repo) {
        dom.repoMeta.title = id.repo + (id.version ? ` @ ${id.version}` : '');
    } else {
        dom.repoMeta.removeAttribute('title');
    }
    renderTechDetails(form);
    renderEvidencePack(form);
    renderMetaIdentity(form);
    void loadRatingDiff(form);
}

function renderEvidencePack(form) {
    if (!dom.evidencePack || !dom.evidencePackLinks) return;
    dom.evidencePackLinks.innerHTML = '';
    const pack = Array.isArray(form?.meta?.evidence_pack) ? form.meta.evidence_pack : [];
    const links = pack
        .filter(item => item && typeof item === 'object' && `${item.url || ''}`.startsWith('http'))
        .slice(0, 5);
    if (!links.length) {
        dom.evidencePack.hidden = true;
        return;
    }
    dom.evidencePack.hidden = false;
    links.forEach(item => {
        const a = createEl('a', {
            class: 'evidence-pack__link',
            href: item.url,
            text: item.label || item.url,
            target: '_blank',
            rel: 'noopener noreferrer',
        });
        a.title = item.url;
        dom.evidencePackLinks.appendChild(a);
    });
}

function renderMetaIdentity(form) {
    if (!dom.metaIdentity) return;
    if (!form) {
        dom.metaIdentity.hidden = true;
        return;
    }
    dom.metaIdentity.hidden = false;
    const meta = form.meta && typeof form.meta === 'object' ? form.meta : (form.meta = {});
    if (dom.metaLibraryType) {
        dom.metaLibraryType.value = (meta.library_type || meta.type || '').toString();
    }
    if (dom.metaAssessmentDate) {
        const raw = (meta.assessment_date || meta.started_at || '').toString();
        dom.metaAssessmentDate.value = raw.slice(0, 10);
    }
}

function syncMetaIdentityFromInputs() {
    if (!state.form) return;
    if (!state.form.meta || typeof state.form.meta !== 'object') state.form.meta = {};
    if (dom.metaLibraryType) {
        const value = (dom.metaLibraryType.value || '').trim();
        state.form.meta.library_type = value;
        state.form.meta.type = value;
    }
    if (dom.metaAssessmentDate) {
        const value = (dom.metaAssessmentDate.value || '').trim();
        if (value) state.form.meta.assessment_date = value;
    }
    scheduleLocalDraftSave();
    renderRepositoryMeta(state.form);
}

function renderRatingDiff(payload) {
    if (!dom.ratingDiffBanner || !dom.ratingDiffList) return;
    dom.ratingDiffList.innerHTML = '';
    if (!payload || !payload.has_previous) {
        dom.ratingDiffBanner.hidden = true;
        return;
    }
    const changes = Array.isArray(payload.changes) ? payload.changes : [];
    if (!changes.length) {
        dom.ratingDiffBanner.hidden = true;
        return;
    }
    dom.ratingDiffBanner.hidden = false;
    if (dom.ratingDiffDetail) {
        const prev = payload.previous_id ? ` (předchozí: ${payload.previous_id.slice(0, 8)}…)` : '';
        dom.ratingDiffDetail.textContent = `${changes.length} změn ratingu${prev}`;
    }
    changes.slice(0, 12).forEach(change => {
        dom.ratingDiffList.appendChild(createEl('li', {
            text: `${change.id}: ${change.from} → ${change.to}`,
        }));
    });
}

async function loadRatingDiff(form) {
    const evalId = form?._evaluation_id || form?.meta?.evaluation_id || state.draftId || '';
    if (!evalId) {
        renderRatingDiff(null);
        return;
    }
    try {
        const res = await fetch(`/api/evaluations/${encodeURIComponent(evalId)}/diff-previous`, {
            credentials: 'same-origin',
        });
        if (!res.ok) {
            renderRatingDiff(null);
            return;
        }
        const data = await res.json();
        renderRatingDiff(data);
    } catch {
        renderRatingDiff(null);
    }
}

function renderTechDetails(form) {
    if (!dom.techDetails) return;
    dom.techDetails.innerHTML = '';
    if (!form) return;
    const id = resolveFormIdentity(form);
    const rows = [
        ['Knihovna (repo)', id.repo || '—'],
        ['Verze / ref', id.version || '—'],
        ['Typ knihovny', (form?.meta?.library_type || form?.meta?.type || '—').toString()],
        ['Datum hodnocení', (form?.meta?.assessment_date || '').toString().slice(0, 10) || (id.startedAt ? formatStartedDate(id.startedAt) : '—')],
        ['Datum zahájení', id.startedAt ? formatStartedDate(id.startedAt) : '—'],
        ['Commit SHA', id.commitSha || '—'],
        ['ID hodnocení', id.evaluationId || '—'],
        ['Stav sběru', id.collectionStatus || '—'],
    ];
    rows.forEach(([label, value]) => {
        const dt = createEl('dt', { text: label });
        const dd = createEl('dd', { text: value });
        if (label === 'ID hodnocení' || label === 'Commit SHA') {
            dd.className = 'tech-details__mono';
        }
        dom.techDetails.appendChild(dt);
        dom.techDetails.appendChild(dd);
    });
}

function collectionDoneCount() {
    return PIPELINE_STEPS.filter(step => step !== 'finalize' && state.pipeline.doneSteps.has(step)).length;
}

function updateCollectionBanner() {
    if (!dom.collectionBanner) return;
    const status = state.pipeline.humanStatus || state.pipeline.status;
    const busy = status === 'queued' || status === 'running' || status === 'collecting';
    const terminal = status === 'done' || status === 'partial' || status === 'failed' || status === 'error';
    if (!busy && !terminal) {
        dom.collectionBanner.hidden = true;
        return;
    }
    dom.collectionBanner.hidden = false;
    dom.collectionBanner.dataset.status = status;
    const done = collectionDoneCount();
    if (dom.collectionBannerProgress) {
        dom.collectionBannerProgress.textContent = `${done}/5`;
    }
    if (dom.collectionRetryBtn) {
        dom.collectionRetryBtn.hidden = !(status === 'failed' || status === 'error' || status === 'partial');
    }
    if (status === 'queued' || status === 'running' || status === 'collecting') {
        if (dom.collectionBannerTitle) {
            dom.collectionBannerTitle.textContent = `Sbírám podklady… ${done}/5`;
        }
        if (dom.collectionBannerDetail) {
            dom.collectionBannerDetail.textContent = state.pipeline.phaseMessage
                || 'Automat stahuje veřejné signály z GitHubu a dalších zdrojů.';
        }
        return;
    }
    if (status === 'done') {
        if (dom.collectionBannerTitle) dom.collectionBannerTitle.textContent = 'Sběr hotov';
        if (dom.collectionBannerDetail) {
            dom.collectionBannerDetail.textContent = 'Podklady jsou připravené. Pokračuj frontou K vyřízení.';
        }
        window.setTimeout(() => {
            if (state.pipeline.humanStatus === 'done' && dom.collectionBanner) {
                dom.collectionBanner.hidden = true;
            }
        }, 4500);
        return;
    }
    if (status === 'partial') {
        const failed = [...(state.pipeline.failedSteps || [])].filter(s => s !== 'finalize');
        if (dom.collectionBannerTitle) {
            dom.collectionBannerTitle.textContent = 'Sběr částečně hotov';
        }
        if (dom.collectionBannerDetail) {
            dom.collectionBannerDetail.textContent = failed.length
                ? `Něco se nepodařilo (kroky ${failed.join(', ')}). Můžeš hodnotit to, co je, nebo sběr zopakovat.`
                : 'Některé podklady chybí. Můžeš pokračovat nebo sběr zopakovat.';
        }
        return;
    }
    if (dom.collectionBannerTitle) dom.collectionBannerTitle.textContent = 'Sběr selhal';
    if (dom.collectionBannerDetail) {
        dom.collectionBannerDetail.textContent = state.pipeline.phaseMessage
            || 'Zkontroluj log a zkus sběr znovu.';
    }
}

function buildPendingEvaluation(repoInput, evaluationId) {
    const startedAt = new Date().toISOString();
    let ownerRepo = `${repoInput || ''}`.trim();
    try {
        if (/^https?:\/\//i.test(ownerRepo)) {
            const url = new URL(ownerRepo);
            const parts = url.pathname.split('/').filter(Boolean);
            if (parts.length >= 2) ownerRepo = `${parts[0]}/${parts[1].replace(/\.git$/, '')}`;
        }
    } catch {
        // keep raw
    }
    const refMatch = `${repoInput || ''}`.match(/\/tree\/([^?#]+)/);
    const requestedRef = refMatch ? decodeURIComponent(refMatch[1]) : '';
    return {
        meta: {
            repo: ownerRepo,
            requested_ref: requestedRef,
            effective_ref: requestedRef,
            evaluated_repo_version: requestedRef,
            evaluation_id: evaluationId,
            run_id: evaluationId,
            started_at: startedAt,
            collection_status: 'running',
        },
        _evaluation_id: evaluationId,
        _draft_id: evaluationId,
        _started_at: startedAt,
        rating_options: [...RATING_OPTIONS],
        sections: [],
        summary: null,
    };
}

function normalizeFormRatings(form) {
    if (!form || typeof form !== 'object') return form;

    const sourceOptions = Array.isArray(form.rating_options) ? form.rating_options : [];
    const normalizedOptions = sourceOptions
        .map(option => normalizeRatingValue(option))
        .filter((option, idx, arr) => arr.indexOf(option) === idx);
    const withDefaultOptions = normalizedOptions.length
        ? normalizedOptions
        : [...RATING_OPTIONS];
    if (!withDefaultOptions.includes('nehodnoceno')) {
        withDefaultOptions.unshift('nehodnoceno');
    }
    form.rating_options = withDefaultOptions;

    const sections = Array.isArray(form.sections) ? form.sections : [];
    sections.forEach(section => {
        const questions = Array.isArray(section?.questions) ? section.questions : [];
        questions.forEach(question => {
            if (!question || typeof question !== 'object') return;
            normalizeQuestionWorkflow(question);
        });
    });

    return form;
}

function clearWorkForm() {
    state.form = null;
    state.draftId = null;
    if (dom.details) dom.details.innerHTML = '';
    if (dom.json) dom.json.textContent = '';
    if (dom.repoMeta) dom.repoMeta.textContent = 'Hodnoceno: —';
    if (dom.summary) dom.summary.textContent = '';
    if (dom.summaryHint) dom.summaryHint.textContent = '';
    if (dom.metaIdentity) dom.metaIdentity.hidden = true;
    if (dom.ratingDiffBanner) dom.ratingDiffBanner.hidden = true;
    if (dom.evidencePack) dom.evidencePack.hidden = true;
    updateWorkRemaining(null);
    syncOfficialPdfButton(null);
    renderPdfReadiness(null);
    if (dom.navWorkBtn) {
        dom.navWorkBtn.disabled = !state.selectedLibraryId;
    }
}

function handleFormLoaded(form) {
    const normalizedForm = normalizeFormRatings(form);
    state.form = normalizedForm;
    const existingId = normalizedForm?._draft_id
        || normalizedForm?._evaluation_id
        || normalizedForm?.meta?.evaluation_id
        || '';
    state.draftId = existingId ? `${existingId}` : null;
    ensureEvaluationMeta(normalizedForm);
    syncSelectedLibraryFromForm(normalizedForm);
    if (dom.navWorkBtn) dom.navWorkBtn.disabled = false;
    renderRepositoryMeta(normalizedForm);
    updateWorkRemaining(normalizedForm);
    renderSummaryHint(normalizedForm);
    renderSummary(normalizedForm);
    if (dom.json) dom.json.textContent = JSON.stringify(normalizedForm, null, 2);
    renderDetails(normalizedForm);
    setView('work');
    showNewEvalPanel(false);
    rememberLastOpen();
    scheduleAutosave();
}

function isAppendixSection(section) {
    const type = `${section?.type ?? ''}`.toLowerCase();
    return type === 'appendix' || type === 'informational' || type === 'info';
}

function findUnevaluatedOfficialQuestions(form) {
    const missing = [];
    (form?.sections || []).forEach(section => {
        if (!section || isAppendixSection(section)) return;
        (section.questions || []).forEach(question => {
            const rating = `${question?.rating ?? ''}`.trim().toLowerCase();
            if (rating === 'splňuje'
                || rating === 'částečně splňuje'
                || rating === 'nesplňuje') return;
            const id = `${question?.id || '?'}`.trim() || '?';
            const text = `${question?.text || ''}`.trim();
            missing.push({ id, text });
        });
    });
    return missing;
}

async function fetchJSON(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', ...options });
    if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try {
            const data = await response.json();
            const err = apiErrorPayload(data);
            if (err.message) detail = err.message;
            const error = new Error(detail);
            error.status = response.status;
            error.code = err.code;
            throw error;
        } catch (parseError) {
            if (parseError.status) throw parseError;
            const error = new Error(detail);
            error.status = response.status;
            throw error;
        }
    }
    return response.json();
}

async function loadExamplesList() {
    try {
        const data = await fetchJSON('/api/examples');
        state.exampleFiles = data.files || [];
        if (dom.exampleSelect) {
            dom.exampleSelect.innerHTML = '';
            state.exampleFiles.forEach(file => dom.exampleSelect.appendChild(new Option(file, file)));
        }
    } catch {
        state.exampleFiles = [];
        if (dom.exampleSelect) {
            dom.exampleSelect.innerHTML = '';
            dom.exampleSelect.appendChild(new Option('(chyba načítání ukázek)', ''));
        }
    }
}

async function loadPilotStatus() {
    if (!dom.pilotStatusBanner) return;
    try {
        const data = await fetchJSON('/api/pilot/status');
        const rate = data?.empirie?.heuristic_accept_rate_pct;
        const parts = [
            data?.d10_closed ? 'Pilot D10: uzavřen' : 'Pilot D10: doplňuje se',
            `${data?.libraries_terminal || 0}/${data?.libraries || 0} s výsledkem`,
            `${data?.not_recommended || 0}× Nedoporučeno`,
        ];
        if (typeof rate === 'number') {
            parts.push(`AUTO accept ~${rate} %`);
        }
        dom.pilotStatusBanner.textContent = parts.join(' · ');
        dom.pilotStatusBanner.hidden = false;
    } catch {
        dom.pilotStatusBanner.hidden = true;
    }
}

async function refreshHomeCatalog() {
    hideLibraryDetail();
    await Promise.all([
        loadExamplesList(),
        loadDraftsList(),
        loadLibrariesList(),
        loadPilotStatus(),
    ]);
    renderLibraryCatalog();
}

async function loadExampleByName(name) {
    if (!name) {
        setStatus('Ukázka není k dispozici', false);
        return;
    }
    stopStreaming();
    if (dom.summary) dom.summary.textContent = '';
    if (dom.json) dom.json.textContent = '';
    resetPipelineProgress();
    setStatus(`Načítám ukázku: ${name}…`);
    try {
        const data = await fetchJSON(`/api/examples/${encodeURIComponent(name)}`);
        handleFormLoaded(data);
        setStatus(`Načteno: ${exampleMeta(name).title}`, true);
    } catch (error) {
        setStatus(error.message || 'Chyba načtení ukázky', false);
    }
}

async function loadServerDraftById(id) {
    if (!id) {
        setStatus('Koncept není k dispozici', false);
        return;
    }
    try {
        setStatus('Načítám rozpracované hodnocení…');
        const response = await fetch(`/api/drafts/${encodeURIComponent(id)}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data?.detail || 'Načtení selhalo');
        state.draftId = data.id || id;
        handleFormLoaded(data.form);
        setStatus('Rozpracované hodnocení načteno', true);
    } catch (error) {
        setStatus(error.message || 'Chyba načtení', false);
    }
}

async function loadTokenConfig() {
    // Token field stays hidden until a run actually requires it (krok 5).
    if (!dom.tokenRow) return;
    try {
        const data = await fetchJSON('/api/config');
        state.tokenRequired = !!data.needs_token;
        if (data?.auth) {
            applyAuthPayload(data.auth);
            updateAuthChrome();
        }
        if (data?.ai) {
            state.ai.enabled = !!data.ai.enabled;
            state.ai.available = !!data.ai.available;
            state.ai.provider = data.ai.provider || null;
        }
    } catch {
        state.tokenRequired = false;
    }
    hideTokenRowUnlessForced();
    if (!state.tokenRowForced && dom.tokenInput) dom.tokenInput.value = '';
}

async function handleRunClick() {
    if (!canWrite()) {
        if (state.auth.role === 'viewer') {
            setStatus('Role viewer nemůže spouštět sběr.', false);
            return;
        }
        openAuthGate({ message: 'Pro spuštění sběru se přihlas.' });
        return;
    }
    const repo = dom.repoInput?.value.trim();
    setFileStatus('');
    if (!repo) {
        setStatus('Zadej repo URL nebo owner/repo');
        return;
    }
    const tokenValue = dom.tokenInput?.value.trim() || '';
    if (state.tokenRowForced && !tokenValue) {
        setStatus('Zadej GitHub token pro tento běh');
        dom.tokenInput?.focus();
        return;
    }

    stopStreaming();
    if (dom.log) dom.log.textContent = '';
    startPipelineRun({ openDrawer: false });
    state.pipeline.repoInput = repo;
    setStatus('Spouštím…');

    try {
        const payload = tokenValue ? { repo, token: tokenValue } : { repo };
        const response = await fetch('/api/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const err = apiErrorPayload(data);
            if (response.status === 401 || err.code === 'auth_required') {
                state.auth.authenticated = false;
                updateAuthChrome();
                openAuthGate({ message: err.message || 'Zadej přístupový kód.' });
                throw new Error(err.message || 'Vyžadován přístupový kód');
            }
            if (err.code === 'token_required' || /token/i.test(err.message || '')) {
                revealTokenRow(err.message || 'Pro tento běh je potřeba GitHub token.');
                throw new Error(err.message || 'GitHub token chybí');
            }
            throw new Error(err.message || 'Start selhal');
        }

        const jobId = data.evaluation_id || data.job_id;
        state.pipeline.evaluationId = jobId;
        state.draftId = jobId;
        handleFormLoaded(buildPendingEvaluation(repo, jobId));
        setStatus('Sbírám podklady…');
        setPipelineTitle('Sběr běží');
        setPipelinePhase('Automat sbírá podklady. Sleduj banner nahoře nebo otevři log.');
        updateCollectionBanner();
        startStreaming(jobId);
    } catch (error) {
        console.error(error);
        setStatus(error.message || 'Chyba', false);
        finishPipelineRun(false, error.message || 'Sběr se nepodařilo spustit.');
    }
}

function stopStreaming() {
    if (!state.eventSource) return;
    state.eventSource.close();
    state.eventSource = null;
}

function resetOutput() {
    if (dom.json) dom.json.textContent = '';
    if (dom.summary) dom.summary.textContent = '';
    if (dom.log) dom.log.textContent = '';
    renderRepositoryMeta(null);
    updateWorkRemaining(null);
    renderSummaryHint(null);
    resetPipelineProgress();
    setFileStatus('');
}

function startStreaming(jobId) {
    state.eventSource = new EventSource(`/api/events/${jobId}`);
    state.eventSource.addEventListener('log', event => appendLog(event.data));
    state.eventSource.addEventListener('done', event => handleJobDone(jobId, event));
    state.eventSource.addEventListener('error', () => {
        if (state.pipeline.status === 'running' || state.pipeline.status === 'queued') {
            setPipelinePhase('Čekám na obnovení spojení se streamem logů…');
        }
    });
}

async function handleJobDone(jobId, event) {
    stopStreaming();
    try {
        const snapshot = JSON.parse(event.data);
        if (snapshot.status !== 'done') {
            setStatus(snapshot.error || 'Chyba', false);
            finishPipelineRun(false, snapshot.error || 'Sběr skončil chybou.');
            return;
        }
        setStatus('Sběr dokončen', true);
        const result = await fetchJSON(`/api/result/${jobId}`);
        const collectionStatus = `${result?.meta?.collection_status || ''}`.toLowerCase();
        if (collectionStatus === 'partial') {
            const failed = Array.isArray(result?.meta?.collection_failed_steps)
                ? result.meta.collection_failed_steps
                : [];
            failed.forEach(step => state.pipeline.failedSteps.add(`${step}`));
            finishPipelineRun(true, 'Sběr doběhl částečně.');
        } else if (collectionStatus === 'failed') {
            finishPipelineRun(false, 'Sběr selhal ve všech krocích.');
        } else {
            finishPipelineRun(true, 'Sběr dokončen. Otevírám frontu k vyřízení.');
        }
        handleFormLoaded(result);
        formDetails.detailsFilters.queueMode = 'all';
        updateAllFilterControls();
        applyDetailsFilters();
        updateCollectionBanner();
        const { remaining } = countRemainingWork(state.form);
        const pointsWord = remaining === 1 ? 'bod' : (remaining >= 2 && remaining <= 4 ? 'body' : 'bodů');
        if (collectionStatus === 'partial') {
            showToast(`Nasbíráno částečně. Zbývá ${remaining} ${pointsWord}.`, { ok: true });
        } else {
            showToast(`Nasbíráno. Zbývá ${remaining} ${pointsWord}.`, { ok: true });
        }
        closePipelineDrawer({ keepFab: true });
    } catch (error) {
        setStatus('Hotovo (nelze načíst výsledek)', false);
        finishPipelineRun(false, 'Sběr doběhl, ale výsledek se nepodařilo načíst.');
    }
}

async function handleExampleClick() {
    const name = dom.exampleSelect?.value || '';
    await loadExampleByName(name);
}

async function handleFileLoadClick() {
    const file = dom.formFileInput?.files?.[0];
    if (!file) {
        setStatus('Vyber JSON soubor k nahrání');
        setFileStatus('Není vybraný žádný soubor.', false);
        return;
    }

    stopStreaming();
    resetOutput();
    setStatus(`Načítám soubor: ${file.name}…`);
    setFileStatus('Kontroluji JSON formát souboru…');

    let parsedForm;
    try {
        const rawText = await file.text();
        parsedForm = JSON.parse(rawText);
    } catch {
        const message = 'Soubor není validní JSON. Zkontroluj závorky, uvozovky a čárky.';
        setStatus(message, false);
        setFileStatus(message, false);
        appendLog(`[WARN] Upload JSON syntax error file=${file.name}`);
        return;
    }

    setFileStatus('Ověřuji strukturu formuláře proti schématu…');
    try {
        const response = await fetch('/api/validate-form', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ form: parsedForm }),
        });
        const data = await response.json();
        if (!response.ok) {
            const message = describeValidationError(data?.detail);
            const reason = data?.detail?.reason ? ` Důvod: ${data.detail.reason}` : '';
            const hint = data?.detail?.hint ? ` Rada: ${data.detail.hint}` : '';
            setStatus(message, false);
            setFileStatus(message, false);
            appendLog(`[WARN] Upload JSON schema validation failed.${reason}${hint}`);
            return;
        }

        const normalizedForm = data?.form || parsedForm;
        handleFormLoaded(normalizedForm);
        setStatus(`Soubor načten: ${file.name}`, true);
        setFileStatus('Soubor je validní a byl úspěšně načten.', true);
        appendLog(`[DONE] Upload JSON validated file=${file.name}`);
    } catch {
        const message = 'Soubor se nepodařilo ověřit na serveru. Zkus to prosím znovu.';
        setStatus(message, false);
        setFileStatus(message, false);
        appendLog(`[WARN] Upload JSON validation request failed file=${file.name}`);
    }
}

async function handleRecalculateClick() {
    if (!state.form) {
        setStatus('Není načten žádný výsledek');
        return;
    }
    try {
        setStatus('Přepočítávám…');
        const response = await fetch('/api/recalculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(state.form),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data?.detail || 'Přepočet selhal');
        handleFormLoaded(data.form || state.form);
        setStatus('Přehodnoceno', true);
    } catch (error) {
        setStatus(error.message || 'Chyba přepočtu', false);
    }
}

function downloadBlob(blob, filename) {
    const anchor = document.createElement('a');
    anchor.download = filename;
    anchor.href = URL.createObjectURL(blob);
    document.body.appendChild(anchor);
    anchor.click();
    setTimeout(() => {
        URL.revokeObjectURL(anchor.href);
        anchor.remove();
    }, 0);
}

function resolveRepoSlug() {
    const repo = resolveFormRepositoryMeta(state.form).repo;
    return repo || 'review';
}

function handleJsonDownload() {
    if (!state.form) {
        setStatus('Není načten žádný výsledek');
        return;
    }
    try {
        const blob = new Blob([JSON.stringify(state.form, null, 2)], { type: 'application/json' });
        downloadBlob(blob, `form_${resolveRepoSlug().replace(/\//g, '_')}.json`);
        setStatus('Pracovní JSON stažen', true);
    } catch {
        setStatus('Nepodařilo se vygenerovat JSON ke stažení', false);
    }
}

async function downloadPdf({ draft = false } = {}) {
    if (!state.form) {
        setStatus('Není načten žádný výsledek');
        return;
    }
    if (!draft) {
        const missing = findUnevaluatedOfficialQuestions(state.form);
        if (missing.length) {
            renderPdfReadiness(state.form);
            const preview = missing.slice(0, 5).map(item => item.id).join(', ');
            const more = missing.length > 5 ? ` a další (${missing.length - 5})` : '';
            setStatus(
                `Oficiální PDF nejde stáhnout — doplň rozhodnutí u: ${preview}${more}. Seznam chybějících je nahoře (klik = skok). Nebo použij „PDF koncept“.`,
                false,
            );
            if (dom.pdfReadiness) dom.pdfReadiness.hidden = false;
            dom.pdfReadiness?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            return;
        }
    }
    try {
        setStatus(draft ? 'Generuji koncept PDF…' : 'Generuji oficiální PDF…');
        const url = draft ? '/api/pdf?draft=1' : '/api/pdf';
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(state.form),
        });
        if (!response.ok) {
            let message = 'Chyba generování PDF';
            const raw = await response.text();
            try {
                const data = JSON.parse(raw);
                message = data?.detail?.message || data?.detail || message;
            } catch {
                message = raw || message;
            }
            throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
        }
        const blob = await response.blob();
        const suffix = draft ? '_draft' : '';
        downloadBlob(blob, `form_${resolveRepoSlug().replace(/\//g, '_')}${suffix}.pdf`);
        setStatus(draft ? 'Koncept PDF stažen' : 'Oficiální PDF staženo', true);
    } catch (error) {
        setStatus(error.message || 'Chyba PDF', false);
    }
}

async function handlePdfDownload() {
    await downloadPdf({ draft: false });
}

async function handlePdfDraftDownload() {
    closeMoreMenu();
    await downloadPdf({ draft: true });
}

async function handleSaveDraftClick() {
    if (!state.form) {
        setStatus('Není načtené žádné hodnocení');
        return;
    }
    const ok = await saveToServerNow({ quiet: false });
    if (ok) appendLog(`[DONE] Evaluation saved id=${state.draftId || ''}`);
}

function handleRestoreDraftClick() {
    try {
        const raw = localStorage.getItem(LOCAL_DRAFT_KEY);
        if (!raw) {
            setStatus('V prohlížeči není záloha hodnocení', false);
            return;
        }
        const payload = JSON.parse(raw);
        const form = payload?.form;
        if (!form || typeof form !== 'object') {
            setStatus('Záloha v prohlížeči je neplatná', false);
            return;
        }
        if (payload.draftId) state.draftId = payload.draftId;
        handleFormLoaded(form);
        setSaveStatus('local', payload.savedAt || new Date().toISOString());
        setStatus('Obnoveno ze zálohy prohlížeče', true);
    } catch {
        setStatus('Zálohu se nepodařilo obnovit', false);
    }
}

async function loadDraftsList() {
    if (!canWrite()) {
        state.drafts = [];
        if (dom.draftSelect) {
            dom.draftSelect.innerHTML = '';
        }
        return;
    }
    try {
        const response = await fetch('/api/drafts', { credentials: 'same-origin' });
        if (response.status === 401) {
            state.drafts = [];
            return;
        }
        const data = await response.json();
        state.drafts = Array.isArray(data?.drafts)
            ? data.drafts
            : (Array.isArray(data?.evaluations) ? data.evaluations : []);
        if (dom.draftSelect) {
            dom.draftSelect.innerHTML = '';
            state.drafts.forEach(draft => {
                const label = [
                    draft.title || draft.repo || draft.id?.slice(0, 8),
                    draft.updated_at ? draft.updated_at.slice(0, 19) : '',
                ].filter(Boolean).join(' · ');
                dom.draftSelect.appendChild(new Option(label, draft.id));
            });
        }
    } catch {
        state.drafts = [];
        if (dom.draftSelect) {
            dom.draftSelect.innerHTML = '';
            dom.draftSelect.appendChild(new Option('(seznam hodnocení nedostupný)', ''));
        }
    }
}

async function restoreLastOpenEvaluation() {
    try {
        const raw = localStorage.getItem(LOCAL_DRAFT_KEY);
        if (raw) {
            const payload = JSON.parse(raw);
            if (payload?.form && typeof payload.form === 'object') {
                if (payload.draftId) state.draftId = payload.draftId;
                handleFormLoaded(payload.form);
                setSaveStatus(
                    payload.draftId ? 'saved' : 'local',
                    payload.savedAt || new Date().toISOString(),
                );
                return true;
            }
        }
    } catch {
        // fall through
    }

    try {
        const lastRaw = localStorage.getItem(LAST_OPEN_KEY);
        const last = lastRaw ? JSON.parse(lastRaw) : null;
        const lastId = last?.draftId;
        if (lastId && canWrite()) {
            await loadServerDraftById(lastId);
            return Boolean(state.form);
        }
    } catch {
        // stay on home
    }
    return false;
}

async function handleLoadServerDraftClick() {
    const id = dom.draftSelect?.value;
    await loadServerDraftById(id);
}

function registerSectionToggles() {
    if (dom.expandAllBtn) {
        dom.expandAllBtn.addEventListener('click', () => {
            document.querySelectorAll('details.qd').forEach(d => { d.open = true; });
        });
    }
    if (dom.collapseAllBtn) {
        dom.collapseAllBtn.addEventListener('click', () => {
            document.querySelectorAll('details.qd').forEach(d => { d.open = false; });
        });
    }
}

async function initEvents() {
    dom.navHomeBtn?.addEventListener('click', () => setView('home'));
    dom.navWorkBtn?.addEventListener('click', () => {
        if (state.form || state.selectedLibraryId) setView('work');
    });
    dom.navUsersBtn?.addEventListener('click', () => {
        if (canManageUsers()) setView('users');
    });
    dom.backHomeBtn?.addEventListener('click', () => {
        closeMoreMenu();
        setView('home');
        refreshHomeCatalog();
    });
    dom.newEvalBtn?.addEventListener('click', () => showNewEvalPanel(true));
    dom.cancelNewEvalBtn?.addEventListener('click', () => showNewEvalPanel(false));
    dom.refreshHomeBtn?.addEventListener('click', () => refreshHomeCatalog());
    dom.libraryDetailBack?.addEventListener('click', () => {
        hideLibraryDetail();
        renderLibraryCatalog();
    });
    let catalogSearchTimer = null;
    dom.catalogSearch?.addEventListener('input', () => {
        state.catalogQ = dom.catalogSearch.value || '';
        clearTimeout(catalogSearchTimer);
        catalogSearchTimer = setTimeout(async () => {
            await loadLibrariesList();
            renderLibraryCatalog();
        }, 200);
    });
    dom.catalogStatusFilter?.addEventListener('change', async () => {
        state.catalogStatus = dom.catalogStatusFilter.value || 'all';
        await loadLibrariesList();
        renderLibraryCatalog();
    });
    dom.createUserForm?.addEventListener('submit', handleCreateUser);
    dom.authTabCode?.addEventListener('click', () => setAuthGateTab('code'));
    dom.authTabUser?.addEventListener('click', () => setAuthGateTab('user'));
    dom.authLoginForm?.addEventListener('submit', handleAuthLogin);
    dom.completeEvalBtn?.addEventListener('click', () => openCompleteDialog());
    dom.workMustOpen?.addEventListener('click', () => jumpToFlaggedQuestion('must'));
    dom.workLowConf?.addEventListener('click', () => jumpToFlaggedQuestion('lowconf'));
    dom.completeDialogCancel?.addEventListener('click', () => closeCompleteDialog());
    dom.completeDialogBackdrop?.addEventListener('click', () => closeCompleteDialog());
    dom.completeDialogConfirm?.addEventListener('click', () => submitCompleteDialog());
    dom.signDialogSkip?.addEventListener('click', () => finishAfterComplete());
    dom.signDialogBackdrop?.addEventListener('click', () => finishAfterComplete());
    dom.signDialogConfirm?.addEventListener('click', () => submitSignDialog());
    dom.startOpensslBtn?.addEventListener('click', () => {
        const openssl = state.exampleFiles.find(name => name.includes('openssl'))
            || 'form_openssl_openssl.json';
        loadExampleByName(openssl);
    });
    dom.moreMenuBtn?.addEventListener('click', event => {
        event.stopPropagation();
        toggleMoreMenu();
    });
    document.addEventListener('click', event => {
        if (!dom.moreMenuPanel || dom.moreMenuPanel.hidden) return;
        const menu = document.getElementById('moreMenu');
        if (menu && !menu.contains(event.target)) closeMoreMenu();
    });
    window.addEventListener('beforeunload', () => {
        flushAutosaveSync();
    });
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden' && state.form) {
            flushAutosaveSync();
            saveToServerNow({ quiet: true });
        }
    });
    dom.toggleTechBtn?.addEventListener('click', () => {
        closeMoreMenu();
        if (dom.techPanel) {
            dom.techPanel.open = true;
            dom.techPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
    dom.toggleTechDetailsBtn?.addEventListener('click', () => {
        closeMoreMenu();
        if (dom.techDetailsPanel) {
            dom.techDetailsPanel.open = true;
            renderTechDetails(state.form);
            dom.techDetailsPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
    dom.collectionLogBtn?.addEventListener('click', () => openPipelineDrawer());
    dom.collectionRetryBtn?.addEventListener('click', () => {
        if (state.pipeline.repoInput && dom.repoInput) {
            dom.repoInput.value = state.pipeline.repoInput;
        }
        showNewEvalPanel(true);
        handleRunClick();
    });
    dom.metaLibraryType?.addEventListener('change', syncMetaIdentityFromInputs);
    dom.metaLibraryType?.addEventListener('blur', syncMetaIdentityFromInputs);
    dom.metaAssessmentDate?.addEventListener('change', syncMetaIdentityFromInputs);
    dom.pipelineCloseBtn?.addEventListener('click', () => closePipelineDrawer({ keepFab: true }));
    dom.pipelineBackdrop?.addEventListener('click', () => closePipelineDrawer({ keepFab: true }));
    dom.pipelineFab?.addEventListener('click', () => openPipelineDrawer());
    document.addEventListener('keydown', event => {
        if (event.defaultPrevented) return;
        if (event.key !== 'n' && event.key !== 'N') return;
        const tag = (event.target?.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select' || event.target?.isContentEditable) return;
        if (state.view !== 'work' || !state.form) return;
        event.preventDefault();
        goToNextTodoQuestion({ announce: true });
    });

    dom.runBtn?.addEventListener('click', handleRunClick);
    dom.authForm?.addEventListener('submit', handleAuthEnter);
    dom.authBrowseBtn?.addEventListener('click', browseExamplesWithoutCode);
    dom.authHeaderBtn?.addEventListener('click', () => {
        if (dom.authHeaderBtn?.dataset.mode === 'logout') {
            handleAuthLogout();
        } else {
            openAuthGate();
        }
    });
    dom.loadExampleBtn?.addEventListener('click', handleExampleClick);
    dom.loadFileBtn?.addEventListener('click', handleFileLoadClick);
    dom.formFileInput?.addEventListener('change', () => {
        const file = dom.formFileInput?.files?.[0];
        if (file) {
            setFileStatus(`Vybraný soubor: ${file.name}`);
        } else {
            setFileStatus('');
        }
    });
    dom.recalcBtn?.addEventListener('click', () => { closeMoreMenu(); handleRecalculateClick(); });
    dom.downloadBtn?.addEventListener('click', () => { closeMoreMenu(); handleJsonDownload(); });
    dom.downloadSignedBtn?.addEventListener('click', () => { closeMoreMenu(); downloadSignedExport(); });
    dom.downloadPdfBtn?.addEventListener('click', handlePdfDownload);
    dom.downloadPdfDraftBtn?.addEventListener('click', handlePdfDraftDownload);
    dom.saveDraftBtn?.addEventListener('click', () => { closeMoreMenu(); handleSaveDraftClick(); });
    dom.restoreDraftBtn?.addEventListener('click', () => { closeMoreMenu(); handleRestoreDraftClick(); });
    dom.refreshDraftsBtn?.addEventListener('click', () => loadDraftsList());
    dom.loadDraftBtn?.addEventListener('click', handleLoadServerDraftClick);
    registerSectionToggles();
}

function bindModuleDeps() {
    bindDeps({
        setView,
        setStatus,
        showToast,
        syncWorkFooter,
        fetchJSON,
        refreshHomeCatalog,
        restoreLastOpenEvaluation,
        canWrite,
        openAuthGate,
        showNewEvalPanel,
        createEl,
        loadServerDraftById,
        loadExampleByName,
        formatStartedDate,
        openCompleteDialog,
        downloadSignedExport,
        handleFormLoaded,
        clearWorkForm,
        saveToServerNow,
        flushAutosaveSync,
        isAppendixSection,
        normalizeWorkflowState,
        updateAllFilterControls,
        applyDetailsFilters,
        findUnevaluatedOfficialQuestions,
        questionItemNeedsAction,
        detailsFilters: formDetails.detailsFilters,
        updateCollectionBanner,
        apiErrorPayload,
        resolveFormIdentity,
        resolveFormRepositoryMeta,
        updateAuthChrome,
        loadDraftsList,
        renderLibraryCatalog,
        scheduleAutosave,
        countRemainingWork,
        resolveQuestionConfidence,
        updateWorkStrip,
        updateWorkRemaining,
        syncOfficialPdfButton,
        renderPdfReadiness,
        jumpToQuestionById,
    });
}

async function init() {
    bindModuleDeps();
    resetPipelineProgress();
    setFileStatus('');
    setView('home');
    closePipelineDrawer({ keepFab: false });
    initEvents();
    await refreshAuthStatus();
    await loadTokenConfig();
    hideTokenRowUnlessForced();
    await refreshHomeCatalog();
    const gated = state.auth.enabled && !state.auth.openMode && !state.auth.authenticated;
    if (gated) {
        openAuthGate();
    } else {
        await restoreLastOpenEvaluation();
    }
}

init();
