/** Late-bound cross-module callbacks (filled by main.js). */
export const deps = {};

export function bindDeps(partial) {
    Object.assign(deps, partial);
}
