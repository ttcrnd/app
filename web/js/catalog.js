import { dom, state, EXAMPLE_CATALOG } from './runtime.js';
import { deps } from './deps.js';

export function exampleMeta(filename) {
    if (EXAMPLE_CATALOG[filename]) return EXAMPLE_CATALOG[filename];
    const bare = filename.replace(/^form_/, '').replace(/\.json$/, '').replace(/_/g, '/');
    return {
        title: bare.split('/')[1] || bare,
        repo: bare.includes('/') ? bare : '',
        blurb: 'Ukázkové hodnocení',
    };
}

export function catalogStatusKind(status) {
    if (status === 'completed') return 'completed';
    if (status === 'not_recommended') return 'not_recommended';
    if (status === 'in_progress' || status === 'draft') return 'draft';
    if (status === 'none' || !status) return 'none';
    return 'draft';
}

function normalizeRepoKey(repo) {
    return `${repo || ''}`
        .trim()
        .toLowerCase()
        .replace(/^https?:\/\/(www\.)?github\.com\//, '')
        .replace(/\.git$/, '')
        .replace(/\/+$/, '');
}

export function formBelongsToLibrary(form, library) {
    if (!form || !library) return false;
    const formLibId = form?.meta?.library_id || form?._library_id || '';
    if (formLibId && library.id && `${formLibId}` === `${library.id}`) return true;
    const formRepo = normalizeRepoKey(
        deps.resolveFormRepositoryMeta?.(form)?.repo || form?.meta?.repo || '',
    );
    const libRepo = normalizeRepoKey(library.repo);
    return Boolean(formRepo && libRepo && formRepo === libRepo);
}

export function syncSelectedLibraryFromForm(form) {
    if (!form) return;
    const repo = normalizeRepoKey(
        deps.resolveFormRepositoryMeta?.(form)?.repo || form?.meta?.repo || '',
    );
    if (!repo) return;
    const match = (state.libraries || []).find(lib => normalizeRepoKey(lib.repo) === repo);
    if (match?.id) {
        state.selectedLibraryId = match.id;
    }
}

function pickEvaluationForLibrary(detail) {
    if (!detail) return null;
    const evals = Array.isArray(detail.evaluations) ? detail.evaluations : [];
    const openEval = evals.find(ev => ev.status === 'in_progress' || ev.status === 'draft');
    if (openEval) return openEval;
    if (evals[0]) return evals[0];
    return detail.latest_evaluation || null;
}

async function resolveLibraryContext(libraryId) {
    if (!libraryId) return null;
    if (state.selectedLibraryDetail?.id === libraryId) {
        return state.selectedLibraryDetail;
    }
    try {
        return await deps.fetchJSON(`/api/libraries/${encodeURIComponent(libraryId)}`);
    } catch {
        const listed = (state.libraries || []).find(lib => lib.id === libraryId);
        if (!listed) return null;
        return {
            ...listed,
            evaluations: listed.latest_evaluation ? [listed.latest_evaluation] : [],
        };
    }
}

/**
 * Keep Work (Hodnocení) aligned with the library selected in the catalog.
 * Call when entering the work view or after changing library selection.
 */
export async function syncWorkToSelectedLibrary() {
    const libraryId = state.selectedLibraryId;
    if (!libraryId) return false;
    if (state._libraryWorkSync) return false;
    state._libraryWorkSync = true;
    try {
        const detail = await resolveLibraryContext(libraryId);
        if (!detail) return false;

        if (formBelongsToLibrary(state.form, detail)) {
            return true;
        }

        if (state.form) {
            if (deps.canWrite?.()) {
                try {
                    await deps.saveToServerNow?.({ quiet: true });
                } catch {
                    deps.flushAutosaveSync?.();
                }
            } else {
                deps.flushAutosaveSync?.();
            }
        }

        const chosen = pickEvaluationForLibrary(detail);
        if (chosen?.id) {
            await deps.loadServerDraftById(chosen.id);
            return true;
        }

        deps.clearWorkForm?.();
        deps.showNewEvalPanel?.(true);
        if (dom.repoInput && detail.repo) dom.repoInput.value = detail.repo;
        deps.setStatus?.(
            `Vybraná knihovna ${detail.name || detail.repo} — spusť nové hodnocení`,
            true,
        );
        return true;
    } finally {
        state._libraryWorkSync = false;
    }
}

export function hideLibraryDetail() {
    // Keep selectedLibraryId so Hodnocení stays bound to the last chosen library.
    state.selectedLibraryDetail = null;
    if (dom.libraryDetail) dom.libraryDetail.hidden = true;
    if (dom.libraryList) dom.libraryList.hidden = false;
    if (dom.libraryListHead) dom.libraryListHead.hidden = false;
    if (dom.catalogSearch?.closest('.catalog-toolbar')) {
        dom.catalogSearch.closest('.catalog-toolbar').hidden = false;
    }
}

export function renderLibraryDetail(detail) {
    if (!dom.libraryDetail || !detail) return;
    state.selectedLibraryDetail = detail;
    state.selectedLibraryId = detail.id;
    dom.libraryDetail.hidden = false;
    if (dom.libraryList) dom.libraryList.hidden = true;
    if (dom.libraryListHead) dom.libraryListHead.hidden = true;
    if (dom.catalogSearch?.closest('.catalog-toolbar')) {
        dom.catalogSearch.closest('.catalog-toolbar').hidden = true;
    }
    if (dom.homeEmpty) dom.homeEmpty.hidden = true;

    if (dom.libraryDetailTitle) dom.libraryDetailTitle.textContent = detail.name || detail.repo || 'Knihovna';
    if (dom.libraryDetailMeta) {
        const statusLabel = detail.catalog_status_label || 'Bez hodnocení';
        dom.libraryDetailMeta.textContent = `${detail.repo || ''} · ${statusLabel}`.replace(/^ · /, '');
    }
    if (dom.libraryDetailBlurb) {
        dom.libraryDetailBlurb.textContent = detail.blurb || '';
        dom.libraryDetailBlurb.hidden = !detail.blurb;
    }

    const evals = Array.isArray(detail.evaluations) ? detail.evaluations : [];
    const openEval = evals.find(e => e.status === 'in_progress' || e.status === 'draft');
    if (dom.libraryDetailContinue) {
        dom.libraryDetailContinue.hidden = !(openEval && deps.canWrite());
        dom.libraryDetailContinue.onclick = () => {
            if (openEval) deps.loadServerDraftById(openEval.id);
        };
    }
    if (dom.libraryDetailNew) {
        dom.libraryDetailNew.hidden = !deps.canWrite();
        dom.libraryDetailNew.onclick = () => {
            state.selectedLibraryId = detail.id;
            deps.showNewEvalPanel(true);
            if (dom.repoInput && detail.repo) dom.repoInput.value = detail.repo;
            deps.setView?.('work');
        };
    }
    if (dom.libraryDetailDelete) {
        dom.libraryDetailDelete.hidden = !deps.canWrite();
        dom.libraryDetailDelete.onclick = () => deleteLibraryById(detail.id, detail.name || detail.repo);
    }

    if (dom.libraryDetailTimeline) {
        dom.libraryDetailTimeline.innerHTML = '';
        if (!evals.length) {
            const empty = deps.createEl('li', {
                class: 'library-timeline__empty muted',
                text: 'Zatím žádné hodnocení této knihovny.',
            });
            dom.libraryDetailTimeline.appendChild(empty);
        } else {
            evals.forEach(ev => {
                const li = deps.createEl('li', { class: 'library-timeline__item' });
                const when = (ev.updated_at || ev.completed_at || '').slice(0, 16).replace('T', ' ');
                const head = deps.createEl('div', { class: 'library-timeline__head' });
                head.appendChild(deps.createEl('strong', {
                    text: ev.title || `${ev.repo || detail.repo} @ ${ev.ref || '—'}`,
                }));
                const badge = deps.createEl('span', {
                    class: 'status-mark',
                    text: ev.status_label || catalogStatusLabel(ev.status),
                });
                badge.dataset.kind = catalogStatusKind(ev.status);
                head.appendChild(badge);
                li.appendChild(head);
                li.appendChild(deps.createEl('p', {
                    class: 'library-timeline__meta muted small',
                    text: [when, ev.ref ? `ref ${ev.ref}` : ''].filter(Boolean).join(' · '),
                }));
                if (deps.canWrite() && (ev.status === 'in_progress' || ev.status === 'draft')) {
                    const btn = deps.createEl('button', {
                        type: 'button',
                        class: 'btn-ghost',
                        text: 'Pokračovat',
                    });
                    btn.addEventListener('click', () => deps.loadServerDraftById(ev.id));
                    li.appendChild(btn);
                } else if (deps.canWrite() || ev.status === 'completed' || ev.status === 'not_recommended') {
                    const btn = deps.createEl('button', {
                        type: 'button',
                        class: 'btn-ghost',
                        text: 'Otevřít',
                    });
                    btn.addEventListener('click', () => deps.loadServerDraftById(ev.id));
                    li.appendChild(btn);
                }
                dom.libraryDetailTimeline.appendChild(li);
            });
        }
    }
}

export async function openLibraryDetail(libraryId) {
    if (!libraryId) return;
    try {
        const detail = await deps.fetchJSON(`/api/libraries/${encodeURIComponent(libraryId)}`);
        renderLibraryDetail(detail);
        if (state.view === 'work') {
            await syncWorkToSelectedLibrary();
        }
    } catch (error) {
        deps.setStatus(error.message || 'Detail knihovny se nepodařilo načíst', false);
    }
}

export async function deleteLibraryById(libraryId, label = '') {
    if (!libraryId || !deps.canWrite()) return;
    const name = (label || libraryId).trim() || 'tuto knihovnu';
    if (!window.confirm(`Smazat knihovnu „${name}“ včetně všech jejích hodnocení?`)) return;
    const openRepo = normalizeRepoKey(deps.resolveFormRepositoryMeta?.(state.form)?.repo || '');
    const wasSelected = state.selectedLibraryId === libraryId;
    try {
        await deps.fetchJSON(`/api/libraries/${encodeURIComponent(libraryId)}`, { method: 'DELETE' });
        if (wasSelected) {
            state.selectedLibraryId = null;
            state.selectedLibraryDetail = null;
        }
        hideLibraryDetail();
        await loadLibrariesList();
        if (state.form && openRepo) {
            const stillThere = (state.libraries || []).some(
                lib => normalizeRepoKey(lib.repo) === openRepo,
            );
            if (!stillThere) {
                deps.clearWorkForm?.();
            }
        }
        renderLibraryCatalog();
        deps.setStatus(`Knihovna „${name}“ smazána`, true);
    } catch (error) {
        deps.setStatus(error.message || 'Smazání knihovny selhalo', false);
    }
}

export function catalogStatusLabel(status) {
    if (status === 'completed') return 'Hotovo';
    if (status === 'not_recommended') return 'Nedoporučeno';
    if (status === 'in_progress' || status === 'draft') return 'Rozpracováno';
    return 'Bez hodnocení';
}

export function renderLibraryCatalog() {
    if (!dom.libraryList) return;
    if (state.selectedLibraryDetail) {
        renderLibraryDetail(state.selectedLibraryDetail);
        return;
    }
    hideLibraryDetail();
    dom.libraryList.innerHTML = '';
    const cards = [];

    (state.libraries || []).forEach(lib => {
        const latest = lib.latest_evaluation;
        const status = lib.catalog_status || (latest ? latest.status : 'none');
        const statusLabel = lib.catalog_status_label
            || (latest && latest.status_label)
            || catalogStatusLabel(status);
        const signed = !!(latest && latest.signed);
        const isOpen = status === 'in_progress' || status === 'draft';
        const isTerminal = status === 'completed' || status === 'not_recommended';
        const when = latest?.updated_at
            ? latest.updated_at.slice(0, 16).replace('T', ' ')
            : '';
        const version = (latest?.ref || '').trim() || '—';
        let primaryLabel = 'Nové';
        if (isOpen && deps.canWrite()) primaryLabel = 'Pokračovat';
        else if (!deps.canWrite() && isTerminal) primaryLabel = 'Otevřít';
        cards.push({
            kind: catalogStatusKind(status),
            key: `lib:${lib.id}`,
            libraryId: lib.id,
            title: lib.name || lib.repo,
            repo: lib.repo || '',
            version,
            when,
            statusLabel,
            signed,
            primaryLabel,
            primaryDisabled: !deps.canWrite() && isOpen && !isTerminal,
            onPrimary: () => {
                state.selectedLibraryId = lib.id;
                if (isOpen && latest?.id && deps.canWrite()) {
                    deps.loadServerDraftById(latest.id);
                    return;
                }
                if (!deps.canWrite() && isTerminal && latest?.id) {
                    deps.loadServerDraftById(latest.id);
                    return;
                }
                if (!deps.canWrite()) {
                    openLibraryDetail(lib.id);
                    return;
                }
                deps.showNewEvalPanel(true);
                if (dom.repoInput && lib.repo) dom.repoInput.value = lib.repo;
                deps.setView?.('work');
            },
            onDetail: () => openLibraryDetail(lib.id),
            onDelete: deps.canWrite()
                ? () => deleteLibraryById(lib.id, lib.name || lib.repo)
                : null,
        });
    });

    if (state.exampleFiles.length) {
        state.exampleFiles.forEach(filename => {
            const meta = exampleMeta(filename);
            cards.push({
                kind: 'example',
                key: `example:${filename}`,
                title: meta.title,
                repo: meta.repo || filename,
                version: '—',
                when: '',
                statusLabel: 'Ukázka',
                primaryLabel: 'Otevřít',
                onPrimary: () => deps.loadExampleByName(filename),
            });
        });
    }

    if (dom.homeEmpty) {
        dom.homeEmpty.hidden = cards.length > 0;
    }
    if (dom.libraryListHead) {
        dom.libraryListHead.hidden = cards.length === 0;
    }

    cards.forEach(card => {
        const row = deps.createEl('article', {
            class: 'library-row',
            'data-key': card.key,
            'data-kind': card.kind,
        });
        if (card.libraryId && card.libraryId === state.selectedLibraryId) {
            row.classList.add('is-selected');
        }

        const nameCell = deps.createEl('div', { class: 'library-row__name' });
        const titleBtn = deps.createEl('button', {
            type: 'button',
            class: 'library-row__title',
            text: card.title,
        });
        if (card.onDetail) titleBtn.addEventListener('click', card.onDetail);
        else titleBtn.addEventListener('click', card.onPrimary);
        nameCell.appendChild(titleBtn);
        if (card.repo) {
            nameCell.appendChild(deps.createEl('span', {
                class: 'library-row__repo muted small',
                text: card.repo,
            }));
        }

        const versionCell = deps.createEl('div', {
            class: 'library-row__version',
            text: card.version || '—',
        });

        const statusCell = deps.createEl('div', { class: 'library-row__status' });
        const status = deps.createEl('span', {
            class: 'status-mark',
            text: card.statusLabel,
        });
        status.dataset.kind = card.kind;
        statusCell.appendChild(status);
        if (card.signed) {
            const signedBadge = deps.createEl('span', {
                class: 'status-mark',
                text: 'Podepsáno',
            });
            signedBadge.dataset.kind = 'signed';
            statusCell.appendChild(signedBadge);
        }

        const whenCell = deps.createEl('div', {
            class: 'library-row__when muted small',
            text: card.when || '—',
        });

        const actions = deps.createEl('div', { class: 'library-row__actions' });
        if (card.onDetail) {
            const detailBtn = deps.createEl('button', {
                type: 'button',
                class: 'btn-ghost',
                text: 'Detail',
            });
            detailBtn.addEventListener('click', card.onDetail);
            actions.appendChild(detailBtn);
        }
        if (card.onDelete) {
            const deleteBtn = deps.createEl('button', {
                type: 'button',
                class: 'btn-ghost',
                text: 'Smazat',
            });
            deleteBtn.addEventListener('click', card.onDelete);
            actions.appendChild(deleteBtn);
        }
        const primary = deps.createEl('button', {
            type: 'button',
            class: card.kind === 'example' ? 'btn-secondary' : 'btn-primary',
            text: card.primaryLabel,
        });
        if (card.primaryDisabled) primary.disabled = true;
        primary.addEventListener('click', card.onPrimary);
        actions.appendChild(primary);

        row.append(nameCell, versionCell, statusCell, whenCell, actions);
        dom.libraryList.appendChild(row);
    });
}

export async function loadLibrariesList() {
    const params = new URLSearchParams();
    const q = (state.catalogQ || '').trim();
    const status = state.catalogStatus || 'all';
    if (q) params.set('q', q);
    if (status && status !== 'all') params.set('status', status);
    const qs = params.toString();
    try {
        const data = await deps.fetchJSON(`/api/libraries${qs ? `?${qs}` : ''}`);
        state.libraries = Array.isArray(data?.libraries) ? data.libraries : [];
    } catch {
        state.libraries = [];
    }
}
