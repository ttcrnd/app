from __future__ import annotations

from typing import Any

_STRINGS: dict[str, Any] = {
    "common": {
        "evaluate_done": "[evaluate] {function_name} done",
        "ratings": {
            "meets": "splňuje",
            "partial": "částečně splňuje",
            "not_met": "nesplňuje",
        },
        "errors": {
            "fetching": "chyba při zjišťování",
            "github_api": "GitHub API error",
            "generic": "ERROR: {message}",
            "http_error": "HTTPError {code}: {body}",
        },
        "boolean": {
            "yes": "yes",
            "no": "no",
        },
    },
    "script3": {
        "section": {
            "title": "Kvalita kódu",
            "category": "good to have",
            "auto_prefix": "Auto: {message}",
        },
        "q3_1": {
            "note_full": "Detekován style guide (.clang-format/.clang-tidy/.editorconfig) a lint v CI.",
            "note_partial": "Zachyceny částečné signály (style soubory nebo lint v CI); doporučeno vynucení v CI.",
            "note_none": "Nebyly nalezeny style soubory ani lint v CI.",
            "auto": "Workflow lint={lint} ; presence of style files: {files}",
        },
        "q3_2": {
            "note_full": "CI spouští testy a je indikována SAST/coverage.",
            "note_partial": "Zachyceny dílčí signály (testy/SAST/coverage), doporučeno doplnit chybějící část.",
            "note_none": "Nelze potvrdit testy ani SAST/coverage v CI.",
            "auto": "SAST detected={sast} ; tests detected in CI={tests} ; coverage hints={coverage}",
        },
        "q3_3": {
            "note_no_alerts": "Code Scanning API dostupné a bez otevřených alertů (vzorek).",
            "note_limited": "Nelze plně ověřit (omezený přístup nebo služba nevypnuta/není k dispozici). Zkontrolujte UI nebo dodané reporty.",
            "note_alerts": "Zaznamenány alerty v Code Scanning – vyžaduje triáž závažnosti.",
            "auto": "code_scanning_api_status={status} count_sample={count}",
        },
        "q3_4": {
            "note_safe": "Primárně paměťově bezpečné jazyky.",
            "note_mixed": "Smíšené jazyky; u C/C++ požaduj mitigace (sanitizery, fuzzing, review).",
            "note_risky": "Projekt primárně v C/C++; ověř mitigace paměťových chyb.",
            "auto": "Detected languages: {languages} ; memory-safe heuristic={memory_safe}",
        },
        "q3_5": {
            "note_full": "Indikováno nastavení 'warnings-as-errors' / -Werror v CI.",
            "note_partial": "Detekován lint/testy; doporučeno zapnout striktní build flags (-Werror apod.).",
            "note_none": "Nelze doložit striktní kompilaci ani lint/testy.",
            "auto": "Hledej -Werror/strict flags v build receptech a CI; tento skript poskytuje odkazy k manuálnímu ověření.",
        },
        "q3_6": {
            "note_full": "Detekována podpora fuzz testů (OSS-Fuzz/repo).",
            "note_partial": "Zachyceny nepřímé signály (workflow s fuzz/sanitizery).",
            "note_none": "Nebyla nalezena evidence fuzz testů.",
            "auto": "OSS-Fuzz present={has_oss_fuzz} ; in-repo fuzz dirs={fuzz_dirs}",
        },
        "q3_7": {
            "note_full": "Existují style soubory a modulární struktura (cmake/include/library).",
            "note_partial": "Částečné signály čitelnosti/modularity; bez metrik je nutné ruční posouzení.",
            "note_none": "Chybí signály modulární struktury i style soubory.",
            "auto": "Pro komplexitu je vhodné doplnit lokální metriky (např. lizard/cyclomatic) – mimo scope veřejných API; zde odkazy k ručnímu auditu struktury.",
        },
        "cli": {
            "description": "Collect evidence for Section 3 – Kvalita kódu",
            "help_repo": "owner/repo (e.g., owner/name)",
            "help_out": "Output JSON path (default: ./data/<repo>_code_quality_evidence.json)",
            "help_input": "Existing form JSON to update (aggregation mode)",
            "help_output": "Path to write updated form JSON (aggregation mode)",
            "error_repo_format": "--repo must be in the form owner/repo",
            "error_repo_required": "--repo must be provided (owner/repo) or set REPO env variable",
            "audit_repo": "[i] Auditing repo: {owner}/{repo}",
            "merged": "[✓] Merged Section 3 into {path}",
            "raw_written": "[i] Raw evidence snapshots written under ./data/raw/",
            "wrote": "[✓] Wrote {path}",
            "api_note": "[i] Note: Some APIs (e.g., Code Scanning) may require GITHUB_TOKEN even for public repos.",
            "token_note": "[i] To maximize reliability, export GITHUB_TOKEN (classic 'public_repo' or fine-grained with 'security events' read).",
            "interrupted": "Interrupted.",
        },
    },
    "script1": {
        "errors": {
            "http_error": "HTTPError {code}: {body}",
        },
        "evaluate_q_1_1": {
            "note_owner_verified": "Oficiální org. verifikace a/nebo ověřený podpis commitu/tagu. Distribuce probíhá přes HTTPS/GitHub.",
            "note_release_only": "K dispozici je oficiální release a HTTPS distribuce; chybí jasný důkaz podpisů/tagů nebo org. verifikace.",
            "note_basic": "HTTPS distribuce a základní identifikační znaky; doporučeno doložit podpisy tagů/release a org. verifikaci.",
        },
        "evaluate_q_1_2": {
            "note_full": "README a základní meta k projektu k dispozici; jazyky={languages}, stars={stars}, forks={forks}.",
            "note_partial": "Základní popis/README existuje, ale chybí další podklady (popis rozsahu, alternativy, poptávka).",
            "note_missing": "Chybí README/description pro posouzení vhodnosti.",
        },
        "evaluate_q_1_3": {
            "note_no_hits": "Textové vyhledávání nezachytilo známé indikátory škodlivosti.",
            "note_benign": "Zaznamenány ojedinělé nálezy (≈{total_hits}); vypadají benigně (dokumentace/testy).",
            "note_risky": "Zachyceny náznaky rizikových vzorů (≈{total_hits}); vyžaduje ruční ověření kontextu.",
        },
        "form": {
            "title": "Předpoklady",
            "category": "must have",
            "questions": {
                "1-1": {
                    "text": "Hodnocená knihovna je opravdu ta, za kterou se vydává (...) a distribuce používá mechanismus odolný proti narušení autenticity a integrity.",
                    "description": "Ověření identity projektu/artefaktů, oficiální repozitář, podpisy tagů/release, HTTPS distribuce apod.",
                },
                "1-2": {
                    "text": "Knihovna nabízí potřebnou funkcionalitu a neexistuje jednodušší/důvěryhodnější způsob jí dosáhnout.",
                    "description": "Shromáždi fakta pro rozhodnutí: účel, jazyky, velikost, aktivita, transitive deps (pokud relevantní), přítomnost balíčkovacích metadat ap.",
                },
                "1-3": {
                    "text": "Knihovna nevykazuje známky škodlivosti (obfuskace, exfiltrace, podezřelé instalační skripty...).",
                    "description": "Textové vyhledávání indikátorů (bez spouštění čehokoli): patterny curl|sh, wget, base64|sh, přístup k ~/.ssh, atd.",
                },
            },
        },
        "payload": {
            "title": "Formulář pro hodnocení software (sekce 1 – Předpoklady)",
            "version": "2.0",
            "language": "cs",
        },
        "cli": {
            "description": "Audit sekce 'Předpoklady' pro OSS knihovnu (GitHub).",
            "help_input": "Cesta k existujícímu JSON formuláři (agregační režim)",
            "help_output": "Kam zapsat aktualizovaný formulář (agregační režim)",
            "success_merge": "✅ Hotovo. Sekce 1 doplněna do: {path}",
            "success_write": "✅ Hotovo. Výstup uložen do: {path}",
        },
    },
    "script2": {
        "evaluate_q_2_1": {
            "note": "Commity posledních 12 měsíců: {commits}, release za 12 měsíců: {releases}.",
        },
        "evaluate_q_2_1a": {
            "note": "Poslední release: {release_name}, datum: {release_date}, prerelease={is_prerelease}.",
        },
        "evaluate_q_2_1b": {
            "note": "Commity: {commits}, issues (12m): {issues}, releasy (12m): {releases}.",
        },
        "evaluate_q_2_1c": {
            "note": "Odhad reakce správců na issues (12m): {responses}/{issues} (~{percentage:.1f} %).",
        },
        "evaluate_q_2_1d": {
            "note": "Poslední release tag/name: {release_name}.",
        },
        "evaluate_q_2_2": {
            "note_exists": "README existuje.",
            "note_missing": "README nenalezen.",
        },
        "evaluate_q_2_3": {
            "note": "CONTRIBUTING.md: {has_contributing}, SECURITY.md: {has_security}.",
        },
        "evaluate_q_2_4": {
            "note_with_security": "SECURITY.md definuje reportování a policy.",
            "note_without_security": "SECURITY.md nenalezen – spoléháme na release notes/advisories.",
        },
        "evaluate_q_2_5": {
            "note": "Repo využívá git; branch policies a podpisy tagů nelze plně ověřit z veřejného REST API bez speciálních oprávnění.",
        },
        "evaluate_q_2_6": {
            "note": "OSV nalezl záznamy: {vulns_count} (bez detailní analýzy dopadu/verzí).",
        },
        "evaluate_q_2_7": {
            "note": "Indikace testů v repu: {has_tests}.",
        },
        "evaluate_q_2_8": {
            "note": "Poslední release notes přítomny: {has_release_notes}; CVE zmínky: {has_cve}.",
        },
        "evaluate_q_2_9": {
            "note": "Z veřejných dat nelze plně ověřit policy; CI je přítomno => předpoklad formálního PR procesu.",
        },
        "evaluate_q_2_10": {
            "note": "Nelze automaticky ověřit vynucení CODEOWNERS; přítomnost CI a aktivita maintainerů naznačuje proces review.",
        },
        "evaluate_q_2_11": {
            "note": "SECURITY.md/maintainers může indikovat roli; bez explicitního důkazu neoznačujeme jako splněno.",
        },
        "evaluate_q_2_12": {
            "note": "Odhad přispěvatelů: {contributors_count} (core >= 2: {has_core}).",
        },
        "evaluate_q_2_13": {
            "note": "Konkrétní schvalovací kvórum nelze z REST ověřit bez přístupu k repo settings.",
        },
        "evaluate_q_2_14": {
            "note": "Funding/sponzoring soubor může indikovat placený čas; bez důkazu ponecháváme částečně.",
        },
        "evaluate_q_2_15": {
            "note": "Stars: {stars}, forks: {forks}, watchers: {watchers}.",
        },
        "evaluate_q_2_16": {
            "note": "GitHub Actions přítomny: {has_actions}.",
        },
        "evaluate_q_2_17": {
            "note": "Heuristika z release/commit aktivity naznačuje průběžnou údržbu; detailní SCA nad SBOM vyžaduje samostatnou triáž.",
        },
        "evaluate_q_2_18": {
            "note": "Bez ruční četby dokumentace nelze potvrdit formální assurance case.",
        },
        "evaluate_q_2_19": {
            "note": "Licence dle GitHub API: {license_id}.",
        },
        "evaluate_q_2_20": {
            "note": "Veřejné audity z REST/OSV nelze spolehlivě vyhledat (vyžadovalo by manuální citace).",
        },
        "evaluate_q_2_21": {
            "note": "Diskuse/issues naznačují interakci; formalizované konzultace nejsou doloženy.",
        },
        "evaluate_q_2_22": {
            "note": "Formální CMVP/FIPS status nelze automaticky ověřit bez dotazu do NIST databáze a mapování komponent/verzí.",
        },
        "cli": {
            "description": "Naplní sekci 'Open-source vývoj' (id:2) v zadané kostře pro repo.",
            "help_repo": "GitHub repo ve tvaru owner/repo (např. owner/repo)",
            "help_skeleton": "Cesta k JSON kostře (tvůj formulář)",
            "help_out": "Kam zapsat obohacený JSON",
            "error_repo_format": "Parametr --repo musí být ve tvaru owner/repo",
            "error_missing_section": "V kostře nebyla nalezena sekce s id == 2 (Open-source vývoj).",
            "success_saved": "Hotovo. Výstup uložen do: {path}",
            "tip_token": "Tip: nastav si GITHUB_TOKEN pro vyšší rate-limit a přesnější výsledky.",
        },
    },
    "script4": {
        "q4_1": {
            "note_full": "Nalezeny instalační instrukce a signály plné API reference (docs/Doxygen/Sphinx/MkDocs).",
            "note_partial": "Chybí jasné instalační kroky nebo explicitní API reference (nalezeny jen částečné náznaky).",
        },
        "q4_2": {
            "note_full": "Detekovány ukázky kódu (README/docs/examples).",
            "note_partial": "Nebyly nalezeny zjevné ukázky kódu; vyžaduje ruční ověření v dokumentaci.",
        },
        "q4_3": {
            "note_full": "Dokumentace obsahuje zřetelné sekce s varováními/bezpečnostními poznámkami.",
            "note_partial": "Varování k nebezpečným volbám nebyla jasně detekována; doporučeno ruční ověření.",
        },
        "q4_4": {
            "note_full": "Rozpoznána dokumentační platforma ({doc_system}) se zabudovaným vyhledáváním.",
            "note_partial": "Strukturovaná dokumentace nebo vyhledávání nebyly spolehlivě detekovány.",
        },
        "q4_5": {
            "note_full": "Nalezeny how-to/průvodci/recipes pro běžné scénáře.",
            "note_partial": "Nejsou jasné how-to/recipes; dokumentace může být primárně referenční.",
        },
        "q4_6": {
            "note_full": "K dispozici je úvod/overview se základy a odkazy na správné postupy.",
            "note_partial": "Úvodní stránky se základy nejsou jasně detekovány; spíše referenční dokumentace.",
        },
        "q4_7": {
            "note": "Vyžaduje ruční rychlokontrolu kvality neoficiálních odpovědí (SO/Google). Přiloženy externí odkazy z README/homepage pro rychlý průzkum.",
        },
        "errors": {
            "github_api": "GitHub API error {status} for {path}",
            "missing_section": "Form does not contain section with id==4",
            "repo_format": "❌ --repo musí být ve formátu owner/repo (např. owner/repo)",
        },
        "cli": {
            "description": "Audit sekce 4 (Dokumentace) pro OSS knihovnu z GitHubu.",
            "help_repo": "owner/repo (např. owner/repo)",
            "help_input": "Cesta k JSON formuláři (váš původní soubor).",
            "help_output": "Kam zapsat aktualizovaný JSON.",
            "success": "✅ Hotovo. Aktualizovaný formulář uložen v: {path}",
        },
    },
    "script5": {
        "q5_1": {
            "note_found": "Nalezeny moduly: {modules}",
            "note_missing": "Automatické ověření pokrytí API selhalo; zvaž ruční kontrolu přítomnosti hlavních modulů (EVP, RSA, EC, X509, SSL, RAND).",
        },
        "q5_2": {
            "note": "Detekovány vyšší abstrakce (EVP/SSL/X509); úplnost je doporučeno ověřit ručně.",
        },
        "q5_3": {
            "note_strong": "Detekovány TLS preset/ciphersuite definice a konfigurace; výchozí hodnoty jsou zdokumentované.",
            "note_partial": "Detekovány TLS preset/ciphersuite definice; automatická validace bezpečnosti výchozích hodnot je nad rámec heuristiky.",
            "note_missing": "Bez explicitních důkazů o bezpečných defaultech v dokumentaci/konfiguraci.",
        },
        "q5_4": {
            "note_full": "Přítomny CSPRNG rozhraní (např. RAND_bytes) a/nebo odpovídající hlavičky.",
            "note_none": "Nebyly nalezeny CSPRNG moduly/volání.",
        },
        "q5_5": {
            "note_full": "Mapování chybových kódů na čitelné řetězce (např. ERR_error_string).",
            "note_none": "Evidence o čitelnosti chyb nebyla nalezena.",
        },
        "q5_6": {
            "note_full": "Detekováno generování klíčů a práce s IV (např. EC/RSA keygen, RAND_bytes, EVP rozhraní).",
            "note_none": "Explicitní API pro generování klíčů/IV nebylo prokazatelně nalezeno v kódu.",
        },
        "q5_7": {
            "note_found": "Detekovány runtime guardrails/assert-like kontroly parametrů.",
            "note_none": "Nebyly nalezeny explicitní runtime guardrails.",
        },
        "q5_8": {
            "note_some": "Dokumentace/EVP naznačuje mapování na konkrétní algoritmy a providery.",
            "note_none": "Nebyly nalezeny explicitní mapovací tabulky; vyžaduje manuální audit dokumentace.",
        },
        "q5_9": {
            "note": "Konfigurace umožňuje měnit parametry; varování/deperecations částečně přítomny.",
            "note_none": "Override parametrů neprokázán automaticky.",
        },
        "q5_10": {
            "note": "Detekována označení deprecated/slabých algoritmů; pojmenování může být neutrální (jazyk C).",
            "note_none": "Jasné označení nebezpečných voleb nemusí být konzistentní napříč API.",
        },
        "q5_11": {
            "note": "C API používá struktury/opaque typy, ale nelze dosáhnout přísné typové bezpečnosti jako v Rust/Java.",
        },
        "q5_12": {
            "note": "Jazyk C nemá výjimky/Result typy; knihovna používá chybové kódy.",
        },
        "q5_13": {
            "note": "API je procedurální; fluent interface se běžně nepoužívá.",
        },
        "q5_14": {
            "note_full": "K dispozici helpery typu zeroize/constant-time compare.",
            "note_none": "Nebyla nalezena evidence helperů.",
        },
        "q5_15": {
            "note": "Nalezeny odkazy na guidelines (např. MISRA/CERT-C).",
            "note_none": "Evidence k jazykovým bezpečnostním standardům nenalezena automaticky.",
        },
        "q5_16": {
            "note": "Existují testovací build příznaky; není garantováno, že oslabují bezpečnost jen v test profilu.",
            "note_none": "Specifický 'test mode' s oslabenou bezpečností nebyl automaticky identifikován.",
        },
        "ecosystem": {
            "note_manual": (
                "D7: Automatické vyhodnocení crypto API je vázané na C/OpenSSL. "
                "Detekované jazyky: {languages}. Důvod: {reason}. "
                "Vyžaduje ruční posouzení; automat nepřenáší C heuristiky na jiný ekosystém."
            ),
        },
        "form": {
            "title": "Formulář v1.0: Hodnocení open-source knihovny (dle metodiky)",
            "version": "2.0",
            "language": "cs",
            "section_title": "Kvalitní a bezpečný návrh kryptografického API",
            "category": "good to have",
        },
        "cli": {
            "description": "Evaluate '5-sec:api' for a GitHub repo and augment your form JSON.",
            "help_owner": "GitHub owner/org (např. owner)",
            "help_repo": "GitHub repo (např. repo)",
            "help_ref": "Git reference: branch or tag (default: repo default branch)",
            "help_input": "Path to input JSON (your form). If omitted, a minimal shell is used.",
            "help_output": "Path to write augmented JSON.",
            "success": "✓ Hotovo. Vypsáno do: {path}",
            "note": "Pozn.: Některá hodnocení jsou konzervativní 'částečně splňuje' kvůli limitům automatizace a jazyku C.",
            "hint": "      Pro změnu heuristik upravte evaluate_section_5().",
        },
        "errors": {
            "repo_read": "Failed to read repo: {owner}/{repo} (HTTP {status})\n{detail}",
            "missing_section": "Vstupní JSON neobsahuje sekci '5-sec:api'.",
        },
    },
}


def text(*keys: str, **kwargs: Any) -> str:
    node: Any = _STRINGS
    for key in keys:
        if not isinstance(node, dict):
            raise KeyError("Localization path does not lead to a string")
        if key not in node:
            raise KeyError(f"Missing localization key: {'/'.join(keys)}")
        node = node[key]
    if not isinstance(node, str):
        raise KeyError("Localization value is not a string")
    return node.format(**kwargs)


def boolean_text(value: bool) -> str:
    return text("common", "boolean", "yes" if value else "no")
