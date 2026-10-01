import { dom, state, timers, LOCAL_DRAFT_KEY, LAST_OPEN_KEY, AUTOSAVE_LOCAL_MS, AUTOSAVE_SERVER_MS } from './runtime.js';
import { deps } from './deps.js';

export function formatSaveClock(isoOrDate) {
    const date = isoOrDate ? new Date(isoOrDate) : new Date();
    if (Number.isNaN(date.getTime())) {
        return new Date().toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
    }
    return date.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
}

export function setSaveStatus(kind, detail = '') {
    timers.lastSaveStatus = { kind, at: detail };
    if (!dom.saveStatus) return;
    const show = Boolean(state.form) && Boolean(kind);
    if (dom.saveStatusSep) dom.saveStatusSep.hidden = !show;
    if (!show) {
        dom.saveStatus.textContent = '';
        dom.saveStatus.dataset.kind = '';
        return;
    }
    dom.saveStatus.dataset.kind = kind;
    if (kind === 'saving') {
        dom.saveStatus.textContent = 'Ukládám…';
    } else if (kind === 'saved') {
        dom.saveStatus.textContent = `Uloženo ${formatSaveClock(detail || undefined)}`;
    } else if (kind === 'local') {
        const clock = formatSaveClock(detail || undefined);
        dom.saveStatus.textContent = `Uloženo v prohlížeči ${clock}`;
    } else if (kind === 'error') {
        dom.saveStatus.textContent = detail || 'Uložení selhalo';
    } else {
        dom.saveStatus.textContent = detail || '';
    }
}

export function buildEvaluationTitle(form) {
    const { repo, version } = deps.resolveFormRepositoryMeta(form);
    const library = (repo || '').trim() || 'hodnocení';
    const ref = (version || '').trim() || 'aktuální';
    const date = new Date().toISOString().slice(0, 10);
    return `${library} @ ${ref} · ${date}`;
}

export function ensureEvaluationMeta(form) {
    if (!form || typeof form !== 'object') return form;
    if (!form.meta || typeof form.meta !== 'object') form.meta = {};
    const title = buildEvaluationTitle(form);
    form.meta.title = title;
    form._evaluation_title = title;
    if (state.draftId) {
        form._draft_id = state.draftId;
        form._evaluation_id = state.draftId;
        form.meta.evaluation_id = state.draftId;
    }
    if (!form.meta.assessment_date) {
        const started = `${form.meta.started_at || ''}`.trim();
        form.meta.assessment_date = started.slice(0, 10) || new Date().toISOString().slice(0, 10);
    }
    const pack = Array.isArray(form.meta.evidence_pack) ? form.meta.evidence_pack : [];
    if (!pack.length) {
        const repo = `${form.meta.repo || ''}`.trim();
        if (repo.includes('/')) {
            const [owner, name] = repo.split('/');
            form.meta.evidence_pack = [
                { label: 'GitHub', url: `https://github.com/${owner}/${name}` },
                {
                    label: 'Scorecard',
                    url: `https://securityscorecards.dev/viewer/?uri=github.com/${owner}/${name}`,
                },
                { label: 'SECURITY.md', url: `https://github.com/${owner}/${name}/blob/HEAD/SECURITY.md` },
                { label: 'Releases', url: `https://github.com/${owner}/${name}/releases` },
            ];
        }
    }
    return form;
}

export function rememberLastOpen() {
    try {
        localStorage.setItem(LAST_OPEN_KEY, JSON.stringify({
            draftId: state.draftId || null,
            savedAt: new Date().toISOString(),
        }));
    } catch {
        // ignore
    }
}

export function writeLocalBackup() {
    if (!state.form) return null;
    ensureEvaluationMeta(state.form);
    const payload = {
        savedAt: new Date().toISOString(),
        draftId: state.draftId,
        title: state.form._evaluation_title || state.form.meta?.title || '',
        form: state.form,
    };
    try {
        localStorage.setItem(LOCAL_DRAFT_KEY, JSON.stringify(payload));
        rememberLastOpen();
        return payload;
    } catch {
        return null;
    }
}

export function scheduleLocalDraftSave() {
    scheduleAutosave();
}

export function scheduleAutosave() {
    if (!state.form) return;
    if (timers.localDraft) clearTimeout(timers.localDraft);
    timers.localDraft = setTimeout(() => {
        writeLocalBackup();
    }, AUTOSAVE_LOCAL_MS);

    if (timers.serverDraft) clearTimeout(timers.serverDraft);
    timers.serverDraft = setTimeout(() => {
        saveToServerNow({ quiet: true });
    }, AUTOSAVE_SERVER_MS);
}

export async function saveToServerNow({ quiet = true } = {}) {
    if (!state.form) return false;
    if (!deps.canWrite()) {
        writeLocalBackup();
        setSaveStatus('local', new Date().toISOString());
        if (!quiet) {
            deps.openAuthGate({ message: 'Pro uložení na server zadej přístupový kód.' });
        }
        return false;
    }
    if (timers.serverDraft) {
        clearTimeout(timers.serverDraft);
        timers.serverDraft = null;
    }
    ensureEvaluationMeta(state.form);
    writeLocalBackup();
    const gen = ++timers.serverSaveGeneration;
    setSaveStatus('saving');
    try {
        const response = await fetch('/api/drafts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                id: state.draftId || undefined,
                title: state.form._evaluation_title,
                form: state.form,
            }),
        });
        const data = await response.json().catch(() => ({}));
        if (gen !== timers.serverSaveGeneration) return false;
        if (!response.ok) {
            const err = deps.apiErrorPayload(data);
            if (response.status === 401 || err.code === 'auth_required') {
                state.auth.authenticated = false;
                deps.updateAuthChrome();
                writeLocalBackup();
                setSaveStatus('local', new Date().toISOString());
                if (!quiet) deps.openAuthGate({ message: err.message || 'Zadej přístupový kód.' });
                return false;
            }
            throw new Error(err.message || 'Uložení selhalo');
        }
        state.draftId = data.id;
        if (state.form) {
            state.form._draft_id = data.id;
            state.form._evaluation_id = data.id;
            if (!state.form.meta || typeof state.form.meta !== 'object') state.form.meta = {};
            state.form.meta.evaluation_id = data.id;
            if (data.title) {
                state.form._evaluation_title = data.title;
                state.form.meta.title = data.title;
            }
        }
        writeLocalBackup();
        setSaveStatus('saved', data.updated_at || new Date().toISOString());
        if (!quiet) {
            deps.setStatus('Uloženo', true);
            await deps.loadDraftsList();
            deps.renderLibraryCatalog();
        }
        return true;
    } catch (error) {
        if (gen !== timers.serverSaveGeneration) return false;
        writeLocalBackup();
        setSaveStatus('local', new Date().toISOString());
        if (!quiet) {
            deps.setStatus(error.message || 'Server nedostupný — uloženo v prohlížeči', false);
        }
        return false;
    }
}

export function flushAutosaveSync() {
    if (!state.form) return;
    writeLocalBackup();
}

