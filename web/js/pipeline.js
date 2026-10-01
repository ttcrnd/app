import { dom, state, PIPELINE_STEPS, PIPELINE_STEP_LABELS } from './runtime.js';
import { deps } from './deps.js';

export function openPipelineDrawer() {
    if (!dom.pipelineDrawer) return;
    dom.pipelineDrawer.dataset.open = 'true';
    dom.pipelineDrawer.setAttribute('aria-hidden', 'false');
    if (dom.pipelineFab) dom.pipelineFab.hidden = true;
}

export function closePipelineDrawer({ keepFab = true } = {}) {
    if (!dom.pipelineDrawer) return;
    dom.pipelineDrawer.dataset.open = 'false';
    dom.pipelineDrawer.setAttribute('aria-hidden', 'true');
    if (dom.pipelineFab) {
        const busy = state.pipeline.status === 'running' || state.pipeline.status === 'queued';
        const done = state.pipeline.status === 'done' || state.pipeline.status === 'error';
        dom.pipelineFab.hidden = !(keepFab && (busy || done));
        dom.pipelineFab.textContent = busy ? 'Sběr…' : 'Sběr';
    }
}

export function getPipelineStepEl(step) {
    return document.querySelector(`[data-pipeline-step="${step}"]`);
}

export function setPipelineCardStatus(status) {
    if (!dom.pipelineCard) return;
    dom.pipelineCard.dataset.status = status;
}

export function setPipelineTitle(text) {
    if (!dom.pipelineTitle) return;
    dom.pipelineTitle.textContent = text;
}

export function setPipelinePhase(text) {
    state.pipeline.phaseMessage = text || '';
    if (!dom.pipelinePhase) return;
    dom.pipelinePhase.textContent = state.pipeline.phaseMessage;
}

export function updatePipelineAliveText() {
    if (!dom.pipelineAlive) return;
    if (state.pipeline.status === 'running' || state.pipeline.status === 'queued') {
        const now = Date.now();
        const elapsed = state.pipeline.startedAt > 0 ? Math.floor((now - state.pipeline.startedAt) / 1000) : 0;
        const sinceLog = state.pipeline.lastLogAt > 0 ? Math.floor((now - state.pipeline.lastLogAt) / 1000) : elapsed;
        dom.pipelineAlive.textContent = `Běh trvá ${elapsed}s | poslední log před ${sinceLog}s`;
        return;
    }
    if (state.pipeline.status === 'done') {
        dom.pipelineAlive.textContent = 'Pipeline dokončena.';
        return;
    }
    if (state.pipeline.status === 'error') {
        dom.pipelineAlive.textContent = 'Pipeline skončila chybou.';
        return;
    }
    dom.pipelineAlive.textContent = 'Čeká na spuštění.';
}

export function startPipelineAliveTicker() {
    stopPipelineAliveTicker();
    state.pipeline.aliveTimer = window.setInterval(updatePipelineAliveText, 1000);
    updatePipelineAliveText();
}

export function stopPipelineAliveTicker() {
    if (!state.pipeline.aliveTimer) return;
    window.clearInterval(state.pipeline.aliveTimer);
    state.pipeline.aliveTimer = null;
}

export function markPipelineStep(step, status) {
    const el = getPipelineStepEl(step);
    if (!el) return;
    el.dataset.status = status;
}

export function updatePipelineProgress() {
    if (!dom.pipelineProgressFill) return;
    const total = PIPELINE_STEPS.length;
    const doneCount = PIPELINE_STEPS.filter(step => state.pipeline.doneSteps.has(step)).length;
    let doneUnits = doneCount;
    if (
        state.pipeline.activeStep
        && !state.pipeline.doneSteps.has(state.pipeline.activeStep)
        && state.pipeline.status !== 'done'
    ) {
        doneUnits += 0.5;
    }
    let percent = total > 0 ? (doneUnits / total) * 100 : 0;
    if (state.pipeline.status === 'done') percent = 100;
    dom.pipelineProgressFill.style.width = `${Math.max(0, Math.min(100, percent)).toFixed(2)}%`;
}

export function resetPipelineProgress() {
    state.pipeline.status = 'idle';
    state.pipeline.humanStatus = 'idle';
    state.pipeline.activeStep = null;
    state.pipeline.failedStep = null;
    state.pipeline.failedSteps = new Set();
    state.pipeline.doneSteps = new Set();
    state.pipeline.startedAt = 0;
    state.pipeline.lastLogAt = 0;
    PIPELINE_STEPS.forEach(step => markPipelineStep(step, 'pending'));
    setPipelineCardStatus('idle');
    setPipelineTitle('Sběr připraven');
    setPipelinePhase('Čeká na spuštění.');
    stopPipelineAliveTicker();
    updatePipelineProgress();
    updatePipelineAliveText();
    deps.updateCollectionBanner();
}

export function activatePipelineStep(step, message) {
    if (!PIPELINE_STEPS.includes(step)) return;
    if (state.pipeline.activeStep && state.pipeline.activeStep !== step && !state.pipeline.doneSteps.has(state.pipeline.activeStep)) {
        markPipelineStep(state.pipeline.activeStep, 'done');
        state.pipeline.doneSteps.add(state.pipeline.activeStep);
    }
    state.pipeline.status = 'running';
    state.pipeline.humanStatus = 'collecting';
    state.pipeline.activeStep = step;
    markPipelineStep(step, 'active');
    setPipelineCardStatus('running');
    setPipelineTitle('Sběr běží');
    setPipelinePhase(message || `Probíhá ${PIPELINE_STEP_LABELS[step] || `krok ${step}`}.`);
    updatePipelineProgress();
    updatePipelineAliveText();
    deps.updateCollectionBanner();
}

export function completePipelineStep(step, message) {
    if (!PIPELINE_STEPS.includes(step)) return;
    state.pipeline.doneSteps.add(step);
    if (state.pipeline.activeStep === step) {
        state.pipeline.activeStep = null;
    }
    markPipelineStep(step, 'done');
    setPipelinePhase(message || `${PIPELINE_STEP_LABELS[step] || `krok ${step}`} dokončen.`);
    updatePipelineProgress();
    updatePipelineAliveText();
    deps.updateCollectionBanner();
}

export function markPipelineStepAsFailed(step, message) {
    if (!PIPELINE_STEPS.includes(step)) return;
    state.pipeline.failedStep = step;
    state.pipeline.failedSteps.add(step);
    if (state.pipeline.activeStep === step) {
        state.pipeline.activeStep = null;
    }
    markPipelineStep(step, 'error');
    if (state.pipeline.status !== 'error') {
        state.pipeline.status = 'running';
        state.pipeline.humanStatus = 'collecting';
        setPipelineCardStatus('running');
        setPipelineTitle('Sběr běží (s varováním)');
    }
    setPipelinePhase(message || `${PIPELINE_STEP_LABELS[step] || `Krok ${step}`} skončil s varováním.`);
    updatePipelineProgress();
    updatePipelineAliveText();
    deps.updateCollectionBanner();
}

export function failPipelineStep(step, message) {
    if (step && PIPELINE_STEPS.includes(step)) {
        state.pipeline.failedStep = step;
        state.pipeline.failedSteps.add(step);
        markPipelineStep(step, 'error');
    }
    state.pipeline.status = 'error';
    state.pipeline.humanStatus = 'failed';
    state.pipeline.activeStep = null;
    setPipelineCardStatus('error');
    setPipelineTitle('Sběr selhal');
    if (message) setPipelinePhase(message);
    updatePipelineProgress();
    stopPipelineAliveTicker();
    updatePipelineAliveText();
    deps.updateCollectionBanner();
}

export function startPipelineRun({ openDrawer = false } = {}) {
    resetPipelineProgress();
    state.pipeline.status = 'queued';
    state.pipeline.humanStatus = 'collecting';
    state.pipeline.startedAt = Date.now();
    state.pipeline.lastLogAt = state.pipeline.startedAt;
    setPipelineCardStatus('queued');
    setPipelineTitle('Sběr se spouští');
    setPipelinePhase('Připravuji kroky 1–5.');
    startPipelineAliveTicker();
    deps.updateCollectionBanner();
    if (openDrawer) openPipelineDrawer();
    else closePipelineDrawer({ keepFab: true });
}

export function finishPipelineRun(ok, message) {
    const failedContent = [...(state.pipeline.failedSteps || [])].filter(s => s !== 'finalize');
    if (ok && failedContent.length === 0) {
        state.pipeline.status = 'done';
        state.pipeline.humanStatus = 'done';
        PIPELINE_STEPS.forEach(step => {
            state.pipeline.doneSteps.add(step);
            markPipelineStep(step, 'done');
        });
        setPipelineCardStatus('done');
        setPipelineTitle('Sběr hotov');
        setPipelinePhase(message || 'Kroky 1–5 i finalizace jsou hotové.');
        updatePipelineProgress();
        stopPipelineAliveTicker();
        updatePipelineAliveText();
        deps.updateCollectionBanner();
        window.setTimeout(() => closePipelineDrawer({ keepFab: true }), 800);
        return;
    }
    if (ok && failedContent.length > 0) {
        state.pipeline.status = 'done';
        state.pipeline.humanStatus = 'partial';
        setPipelineCardStatus('done');
        setPipelineTitle('Sběr částečně hotov');
        setPipelinePhase(message || `Některé kroky selhaly (${failedContent.join(', ')}).`);
        updatePipelineProgress();
        stopPipelineAliveTicker();
        updatePipelineAliveText();
        deps.updateCollectionBanner();
        closePipelineDrawer({ keepFab: true });
        return;
    }
    failPipelineStep(state.pipeline.failedStep, message || 'Běh skončil chybou.');
    closePipelineDrawer({ keepFab: true });
}

export function parsePipelineLog(line) {
    const text = (line || '').toString();
    if (!text) return;

    if (/\[START\]\s+\[server\]\s+JOB queued/i.test(text)) {
        state.pipeline.status = 'queued';
        setPipelineCardStatus('queued');
        setPipelineTitle('Pipeline ve frontě');
        setPipelinePhase('Běh je zařazen do fronty serveru.');
        return;
    }
    if (/\[START\]\s+\[server\]\s+JOB running/i.test(text)) {
        state.pipeline.status = 'running';
        setPipelineCardStatus('running');
        setPipelineTitle('Pipeline běží');
        setPipelinePhase('Server spustil pipeline proces.');
        return;
    }

    const stepStart = text.match(/\[STEP\]\s+([1-5])\/5 START/i);
    if (stepStart) {
        const step = stepStart[1];
        activatePipelineStep(step, `Probíhá ${PIPELINE_STEP_LABELS[step] || `krok ${step}`}.`);
        return;
    }

    const stepDone = text.match(/\[DONE\]\s+([1-5])\/5 DONE/i);
    if (stepDone) {
        const step = stepDone[1];
        completePipelineStep(step, `${PIPELINE_STEP_LABELS[step] || `Krok ${step}`} dokončen.`);
        return;
    }

    const stepFail = text.match(/\[WARN\]\s+([1-5])\/5 FAIL/i);    if (stepFail) {
        const step = stepFail[1];
        markPipelineStepAsFailed(step, `Krok ${step} skončil chybou, pipeline pokračuje best-effort.`);
        return;
    }

    if (/\[STEP\]\s+FINALIZE START/i.test(text)) {
        activatePipelineStep('finalize', 'Probíhá finalizace výsledků (normalizace, validace, scoring).');
        return;
    }
    if (/\[DONE\]\s+FINALIZE DONE/i.test(text)) {
        completePipelineStep('finalize', 'Finalizace výsledků dokončena.');
        return;
    }

    if (/\[DONE\]\s+PIPELINE DONE/i.test(text)) {
        finishPipelineRun(true, 'Pipeline úspěšně dokončena, načítám výsledek.');
        return;
    }

    if (/\[WARN\]\s+\[server\]\s+JOB completed with error/i.test(text) || /\[WARN\]\s+PIPELINE ABORT/i.test(text)) {
        failPipelineStep(state.pipeline.activeStep, 'Pipeline narazila na problém. Zkontroluj log.');
    }
}

export function appendLog(line) {
    dom.log.textContent += `${line}\n`;
    dom.log.scrollTop = dom.log.scrollHeight;
    state.pipeline.lastLogAt = Date.now();
    parsePipelineLog(line);
    updatePipelineAliveText();
}

