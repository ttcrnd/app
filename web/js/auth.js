import { dom, state } from './runtime.js';
import { deps } from './deps.js';

export function canWrite() {
    if (!state.auth.enabled || state.auth.openMode) return true;
    if (!state.auth.authenticated) return false;
    if (typeof state.auth.canWrite === 'boolean') return state.auth.canWrite;
    return state.auth.role === 'reviewer' || state.auth.role === 'admin';
}

export function canManageUsers() {
    return !!state.auth.canManageUsers || state.auth.role === 'admin';
}

export function setAuthGateError(message) {
    if (!dom.authGateError) return;
    if (!message) {
        dom.authGateError.hidden = true;
        dom.authGateError.textContent = '';
        return;
    }
    dom.authGateError.hidden = false;
    dom.authGateError.textContent = message;
}

export function openAuthGate({ message = '' } = {}) {
    if (!dom.authGate) return;
    if (!state.auth.enabled || state.auth.openMode) return;
    dom.authGate.hidden = false;
    document.body.classList.add('auth-gate-open');
    setAuthGateError(message);
    window.setTimeout(() => dom.accessCodeInput?.focus(), 30);
}

export function closeAuthGate() {
    if (!dom.authGate) return;
    dom.authGate.hidden = true;
    document.body.classList.remove('auth-gate-open');
    setAuthGateError('');
}

export function applyAuthPayload(data) {
    if (!data || typeof data !== 'object') return;
    state.auth.enabled = !!data.enabled;
    state.auth.authenticated = !!data.authenticated;
    state.auth.openMode = !!data.open_mode;
    state.auth.role = data.role || null;
    state.auth.userId = data.user_id || null;
    state.auth.username = data.username || null;
    state.auth.canManageUsers = !!data.can_manage_users;
    state.auth.canWrite = typeof data.can_write === 'boolean'
        ? data.can_write
        : (state.auth.role === 'reviewer' || state.auth.role === 'admin');
    state.auth.userAuthEnabled = !!data.user_auth_enabled;
    state.auth.pilotCodeEnabled = !!data.pilot_code_enabled;
}

export function setAuthGateTab(tab) {
    const useUser = tab === 'user';
    dom.authTabCode?.classList.toggle('is-active', !useUser);
    dom.authTabUser?.classList.toggle('is-active', useUser);
    if (dom.authForm) dom.authForm.hidden = useUser;
    if (dom.authLoginForm) dom.authLoginForm.hidden = !useUser;
}

export function updateAuthChrome() {
    const needsLogin = state.auth.enabled && !state.auth.openMode && !state.auth.authenticated;
    const writable = canWrite();
    if (dom.authHeaderBtn) {
        if (!state.auth.enabled || state.auth.openMode) {
            dom.authHeaderBtn.hidden = true;
        } else if (state.auth.authenticated) {
            dom.authHeaderBtn.hidden = false;
            const label = state.auth.username && state.auth.username !== 'pilot'
                ? `Odhlásit (${state.auth.username})`
                : 'Odhlásit';
            dom.authHeaderBtn.textContent = label;
            dom.authHeaderBtn.dataset.mode = 'logout';
        } else {
            dom.authHeaderBtn.hidden = false;
            dom.authHeaderBtn.textContent = 'Vstoupit';
            dom.authHeaderBtn.dataset.mode = 'login';
        }
    }
    if (dom.authRoleBadge) {
        if (state.auth.authenticated && state.auth.role && !state.auth.openMode) {
            dom.authRoleBadge.hidden = false;
            dom.authRoleBadge.textContent = state.auth.role;
            dom.authRoleBadge.dataset.role = state.auth.role;
        } else {
            dom.authRoleBadge.hidden = true;
            dom.authRoleBadge.textContent = '';
        }
    }
    if (dom.navUsersBtn) {
        dom.navUsersBtn.hidden = !canManageUsers();
        if (!canManageUsers() && state.view === 'users') deps.setView('home');
    }
    if (dom.authHint) {
        dom.authHint.hidden = !(needsLogin && state.auth.browseWithoutCode);
        if (!dom.authHint.hidden && state.auth.userAuthEnabled) {
            dom.authHint.textContent =
                'Prohlížíš dokončený katalog. Pro zápis se přihlas kódem nebo účtem.';
        }
    }
    if (dom.newEvalBtn) {
        dom.newEvalBtn.hidden = !writable;
        dom.newEvalBtn.title = needsLogin
            ? 'Nejdřív se přihlas'
            : (!writable ? 'Role viewer nemůže spouštět hodnocení' : 'Spustit nové hodnocení');
    }
    if (dom.startOpensslBtn) {
        dom.startOpensslBtn.hidden = !writable;
    }
    deps.syncWorkFooter(state.form);
    if (dom.runBtn) {
        dom.runBtn.disabled = !writable;
    }
    if (dom.authTabCode) {
        dom.authTabCode.hidden = state.auth.enabled && !state.auth.pilotCodeEnabled && state.auth.userAuthEnabled;
    }
    if (dom.authTabUser) {
        dom.authTabUser.hidden = state.auth.enabled && !state.auth.userAuthEnabled && state.auth.pilotCodeEnabled;
    }
    if (state.auth.enabled && !state.auth.pilotCodeEnabled && state.auth.userAuthEnabled) {
        setAuthGateTab('user');
    } else if (state.auth.enabled && state.auth.pilotCodeEnabled && !state.auth.userAuthEnabled) {
        setAuthGateTab('code');
    }
    document.body.dataset.auth = state.auth.authenticated || state.auth.openMode || !state.auth.enabled
        ? 'in'
        : 'out';
    document.body.dataset.role = state.auth.role || '';
    document.body.dataset.canWrite = writable ? '1' : '0';
}

export function apiErrorPayload(data) {
    const detail = data?.detail;
    if (!detail) return { code: '', message: '' };
    if (typeof detail === 'string') return { code: '', message: detail };
    if (typeof detail === 'object') {
        return {
            code: `${detail.code || ''}`.trim(),
            message: `${detail.message || detail.msg || ''}`.trim() || JSON.stringify(detail),
        };
    }
    return { code: '', message: String(detail) };
}

export function hideTokenRowUnlessForced() {
    if (!dom.tokenRow) return;
    if (state.tokenRowForced || (state.tokenRequired && state.tokenRowForced)) {
        dom.tokenRow.hidden = false;
        return;
    }
    dom.tokenRow.hidden = true;
}

export function revealTokenRow(message) {
    state.tokenRequired = true;
    state.tokenRowForced = true;
    if (dom.tokenRow) dom.tokenRow.hidden = false;
    if (message) deps.setStatus(message, false);
    dom.tokenInput?.focus();
}

export async function refreshAuthStatus() {
    try {
        const data = await deps.fetchJSON('/api/auth/status');
        applyAuthPayload(data);
        if (state.auth.authenticated || state.auth.openMode || !state.auth.enabled) {
            state.auth.browseWithoutCode = false;
            closeAuthGate();
        }
        updateAuthChrome();
        return data;
    } catch {
        state.auth.enabled = false;
        state.auth.authenticated = true;
        state.auth.openMode = true;
        state.auth.canWrite = true;
        state.auth.canManageUsers = false;
        updateAuthChrome();
        return null;
    }
}

export async function handleAuthEnter(event) {
    event?.preventDefault?.();
    const code = dom.accessCodeInput?.value || '';
    setAuthGateError('');
    try {
        const response = await fetch('/api/auth/enter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ code }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const err = apiErrorPayload(data);
            setAuthGateError(err.message || 'Neplatný přístupový kód');
            return;
        }
        if (dom.accessCodeInput) dom.accessCodeInput.value = '';
        state.auth.browseWithoutCode = false;
        await refreshAuthStatus();
        closeAuthGate();
        deps.setStatus('Vstup povolen', true);
        await deps.refreshHomeCatalog();
        if (!state.form) await deps.restoreLastOpenEvaluation();
    } catch (error) {
        setAuthGateError(error.message || 'Vstup se nezdařil');
    }
}

export async function handleAuthLogin(event) {
    event?.preventDefault?.();
    const username = dom.loginUsername?.value || '';
    const password = dom.loginPassword?.value || '';
    setAuthGateError('');
    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ username, password }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const err = apiErrorPayload(data);
            setAuthGateError(err.message || 'Neplatné jméno nebo heslo');
            return;
        }
        if (dom.loginPassword) dom.loginPassword.value = '';
        state.auth.browseWithoutCode = false;
        await refreshAuthStatus();
        closeAuthGate();
        deps.setStatus(`Přihlášen: ${data.username || username}`, true);
        await deps.refreshHomeCatalog();
        if (!state.form) await deps.restoreLastOpenEvaluation();
    } catch (error) {
        setAuthGateError(error.message || 'Přihlášení se nezdařilo');
    }
}

export async function handleAuthLogout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
    } catch {
        // ignore
    }
    state.auth.authenticated = false;
    state.auth.role = null;
    state.auth.userId = null;
    state.auth.username = null;
    state.auth.canManageUsers = false;
    state.auth.canWrite = false;
    state.auth.browseWithoutCode = false;
    await refreshAuthStatus();
    if (state.auth.enabled && !state.auth.openMode) {
        openAuthGate();
    }
    deps.setView('home');
    await deps.refreshHomeCatalog();
    deps.setStatus('Odhlášeno', true);
}

export function setUsersFormError(message) {
    if (!dom.usersFormError) return;
    if (!message) {
        dom.usersFormError.hidden = true;
        dom.usersFormError.textContent = '';
        return;
    }
    dom.usersFormError.hidden = false;
    dom.usersFormError.textContent = message;
}

export async function loadUsersAdmin() {
    if (!canManageUsers() || !dom.usersList) return;
    setUsersFormError('');
    try {
        const data = await deps.fetchJSON('/api/users');
        const users = Array.isArray(data.users) ? data.users : [];
        dom.usersList.replaceChildren();
        if (!users.length) {
            const empty = document.createElement('p');
            empty.className = 'muted';
            empty.textContent = 'Zatím žádní uživatelé.';
            dom.usersList.appendChild(empty);
            return;
        }
        users.forEach(u => {
            const self = u.id === state.auth.userId;
            const isPilot = u.id === 'pilot' || u.username === 'pilot';
            const canDelete = !self && !isPilot;
            const row = document.createElement('article');
            row.className = 'users-list__row';
            row.dataset.userId = u.id;

            const meta = document.createElement('div');
            meta.className = 'users-list__meta';
            const name = document.createElement('strong');
            name.textContent = u.username || '';
            const display = document.createElement('span');
            display.className = 'muted small';
            display.textContent = u.display_name || '';
            meta.append(name, display);

            const roleLabel = document.createElement('label');
            roleLabel.className = 'users-list__role';
            const roleSelect = document.createElement('select');
            roleSelect.setAttribute('aria-label', `Role ${u.username}`);
            ['viewer', 'reviewer', 'admin'].forEach(role => {
                const opt = document.createElement('option');
                opt.value = role;
                opt.textContent = role;
                if (u.role === role) opt.selected = true;
                roleSelect.appendChild(opt);
            });
            if (self) roleSelect.disabled = true;
            roleSelect.addEventListener('change', async () => {
                try {
                    await deps.fetchJSON(`/api/users/${encodeURIComponent(u.id)}`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ role: roleSelect.value }),
                    });
                    deps.setStatus('Role uložena', true);
                } catch (error) {
                    setUsersFormError(error.message || 'Změna role selhala');
                    await loadUsersAdmin();
                }
            });
            roleLabel.appendChild(roleSelect);

            const delBtn = document.createElement('button');
            delBtn.type = 'button';
            delBtn.className = 'btn-ghost';
            delBtn.textContent = 'Smazat';
            delBtn.hidden = !canDelete;
            delBtn.addEventListener('click', async () => {
                if (!window.confirm('Smazat tohoto uživatele?')) return;
                try {
                    await deps.fetchJSON(`/api/users/${encodeURIComponent(u.id)}`, { method: 'DELETE' });
                    deps.setStatus('Uživatel smazán', true);
                    await loadUsersAdmin();
                } catch (error) {
                    setUsersFormError(error.message || 'Smazání selhala');
                }
            });

            row.append(meta, roleLabel, delBtn);
            dom.usersList.appendChild(row);
        });
    } catch (error) {
        dom.usersList.replaceChildren();
        setUsersFormError(error.message || 'Nelze načíst uživatele');
    }
}

export async function handleCreateUser(event) {
    event?.preventDefault?.();
    if (!canManageUsers()) return;
    setUsersFormError('');
    const username = dom.newUserUsername?.value || '';
    const password = dom.newUserPassword?.value || '';
    const role = dom.newUserRole?.value || 'reviewer';
    try {
        await deps.fetchJSON('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role }),
        });
        if (dom.newUserUsername) dom.newUserUsername.value = '';
        if (dom.newUserPassword) dom.newUserPassword.value = '';
        if (dom.newUserRole) dom.newUserRole.value = 'reviewer';
        deps.setStatus(`Účet ${username} vytvořen`, true);
        await loadUsersAdmin();
    } catch (error) {
        setUsersFormError(error.message || 'Vytvoření selhalo');
    }
}

export function browseExamplesWithoutCode() {
    state.auth.browseWithoutCode = true;
    closeAuthGate();
    updateAuthChrome();
    deps.setView('home');
    deps.refreshHomeCatalog();
    deps.setStatus('Prohlížíš dokončený katalog. Zápis a nové běhy až po vstupu.', true);
}
