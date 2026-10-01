> Zdroje pro srovnání: CISA Attestation (aktuální formulář + instrukce), OMB M-22-18/M-23-16 kontext; OpenSSF Best Practices Badge kritéria a aplikace; OpenSSF Concise Guide. ([cisa.gov][1]) ([bestpractices.dev][2]) ([OpenSSF Best Practices Working Group][3])

---

# 1) Předpoklady

**Jak si vede:**

* Velmi dobře pokrývá „identitu a integritu“ balíčku (proti typosquattingu, podepisování, provenance) a „nutnost závislosti“. To je vyloženě v duchu CISA (SSDF: ochrana integrity zdrojů a artefaktů) a OpenSSF Guide (vyhnout se zbytečným závislostem, ověřit oficiální zdroj). Doplnit bych formálnější **důkazní artefakty** (odkazy na podepsané releasy, SLSA/attestace), které CISA výslovně čeká. ([cisa.gov][1])
* „Neškodnost“ skriptů/instalačních hooků je výborný praktický checkpoint, souzní s OpenSSF Badge (kontroly nad CI a buildy) – ale formuluj ho měřitelněji (co projde/neprojde). ([bestpractices.dev][2])

**Co doplnit / zkonkretizovat:**

* Vlož povinnost **doložit provenance** (např. odkaz na SLSA provenance/attestaci nebo ekvivalent) a **způsob ověření podpisu** (cosign/GPG + veřejné klíče projektu). To je přesně jazyk CISA/SSDF. ([cisa.gov][1])
* Přidej kontrolu na **přítomnost SBOM** u posuzované verze (CycloneDX/SPDX) – CISA očekává procesy řízení zranitelností a traceability. ([cisa.gov][1])

**3 nové kritické otázky (zařaď do sekce „must have“):**

1. „Je pro daný release k dispozici **ověřitelná provenance/attestace** (např. SLSA) a je **automaticky ověřována** v CI při příjmu závislosti?“ ([cisa.gov][1])
2. „Existuje **SBOM pro posuzovanou verzi** (SPDX/CycloneDX) a byl proti ní spuštěn SCA sken (OSV/NVD) před nasazením?“ ([cisa.gov][1])
3. „Je release nebo tag **kryptograficky podepsán** (GPG/Sigstore) a máme **postup verifikace klíčů** (TOFU/Publikovaný Key ID/Keyless OIDC)?“ ([bestpractices.dev][2])

---

# 2) Open-source vývoj

**Jak si vede:**

* Většina položek téměř kopíruje **OpenSSF Badge (Passing/Silver/Gold)**: aktivita, governance, SECURITY.md/VDP, CI/testy, review, changelog, licencování, dokumentace přispívání. To je dobře. Doporučuju sloučit 2-9/2-10/2-11 do jedné „**povinné code-review + role/odpovědnosti**“, aby to bylo auditovatelnější (Badge i Guide preferují měřitelné „ANO/NE“). ([bestpractices.dev][2])
* Chybí ti dvě věci, které CISA/SSDF explicitně hlídají: **bezpečné build prostředí** (izolace, reprodukovatelnost, ochrana před únikem tajemství) a **řízení tajemství** (no-secrets v repo, rotace, VCS policy). ([cisa.gov][1])

**Co doplnit / zkonkretizovat:**

* „Projekt nemá neopravené CVE ≥ medium starší 60 dnů“ je dobré, ale napříč ekosystémy se liší SLA; nazvi to „**má proces řízení zranitelností** (advisories, SLA, verzované backporty) a **důkazy oprav**“. To ladí s CISA i Badge. ([cisa.gov][1])
* Přidej kontrolu **branch protection** (min. 1–2 review, zákaz přímých push na main, povinné CI) – Badge to má explicitně. ([bestpractices.dev][2])

**3 nové kritické otázky:**

1. „Má repozitář **branch protection policies** (povinné review, zakázaný force-push, požadované status checks) pro ochranu main/release větví?“ ([bestpractices.dev][2])
2. „Jak jsou **tajemství** spravována v CI/buildu (secret scanning, zákaz plaintext secrets v repo, rotace/least privilege)?“ – CISA to bere jako minimum. ([cisa.gov][1])
3. „Jsou **buildy reprodukovatelné** nebo alespoň deterministické a izolované (oddělený build runner, pinned toolchain, hermetické závislosti)?“ – SSDF/CISA očekávají kontrolu build prostředí. ([cisa.gov][1])

---

# 3) Kvalita kódu

**Jak si vede:**

* Linie s **SAST/testy/fuzzing/strict build flags** je velmi dobrá a v souladu s Badge (požadavek na testy, nástroje kvality) i Concise Guide (ověřit kvalitu a testovatelnost). Přidej důkazní formu (odkaz na CI běhy/artefakty). ([bestpractices.dev][2])
* Chybí **zákaz/omezení risky konstrukcí** v C/C++ (UBSan/ASan, Fortify, control-flow integrity) když není memory-safe jazyk; u jazyků s package managerem chybí **pinning** a „trusted publisher“. To souvisí se supply-chain částí CISA. ([cisa.gov][1])

**Co doplnit / zkonkretizovat:**

* Vynucuj **policy gates v CI** (merge se zastaví na „high“ nálezu SAST/secret-scan/test fail). To je měřitelné a vyžadované v SSDF-style praxi. ([cisa.gov][1])
* U fuzzingu zvaž „**je projekt v OSS-Fuzz** / má důkaz běhů a triage nálezů“ – silný signál zralosti. ([OpenSSF Best Practices Working Group][3])

**3 nové kritické otázky:**

1. „Jsou **všechny high-severity nálezy** z SAST/DAST/secret-scan **blokátorem** merge a existuje **SLA** pro jejich řešení?“ ([cisa.gov][1])
2. „Používá projekt u C/C++ **sanitizéry** (ASan/UBSan), **stack canaries** a **hardening flags** v release buildu a jsou na to CI důkazy?“ ([cisa.gov][1])
3. „Je projekt integrován do **OSS-Fuzz** (nebo má pravidelné fuzz běhy) a **publikuje nápravy** nalezených chyb?“ ([OpenSSF Best Practices Working Group][3])

---

# 4) Dokumentace a zdroje informací

**Jak si vede:**

* Dobře pokrývá „co a jak“ – instalace, API, příklady, varování. To odpovídá Badge (dokumentace, jak reportovat zranitelnosti, SECURITY.md) i Concise Guide (srozumitelnost, správné příklady). Přidej **mapu bezpečných defaultů** a odkaz na **bezpečnostní standardy jazyka**. ([bestpractices.dev][2])
* Doplnil bych **security advisories feed** (GHSA/OSV) a **verzování dokumentace** k vydáním (CISA/SSDF: traceability). ([cisa.gov][1])

**Co doplnit / zkonkretizovat:**

* Zanes povinnost mít **SECURITY.md/VDP** s privátním kanálem a SLA; je to jasný požadavek Badge a očekávání CISA. ([bestpractices.dev][2])

**3 nové kritické otázky:**

1. „Má projekt **SECURITY.md/VDP** s kontaktem, **šifrovaným kanálem** (např. security@ + PGP) a **SLA** pro reakci?“ ([bestpractices.dev][2])
2. „Jsou **release notes** konzistentně **mapované na advisories** (CVE/OSV) a dostupné pro každou podporovanou větev?“ ([cisa.gov][1])
3. „Je dokumentace **version-locked** (verze dokumentu == verze artefaktu) a obsahuje **tabulku podporovaných verzí** s EOL daty?“ – lépe vynutí dohledatelnost. ([OpenSSF Best Practices Working Group][3])

---

# 5) Kvalitní a bezpečný návrh kryptografického API

**Jak si vede:**

* Tahle sekce je silná a jde nad rámec běžných checklistů (většina formulářů se drží procesů). Velmi v duchu **Concise Guide** (bezpečné defaulty, jednoduché, ne-misuse API) – u „task-based crypto“ oceňuju požadavek transparentnosti.
* Co chybí vzhledem k CISA/Badge: **provozní garance kryptografických primitiv** (aktuálnost, deprecations), **hardening proti side-channelům**, **evidence o validaci implementace** (test vectors, certifikační stopy). ([OpenSSF Best Practices Working Group][3])

**Co doplnit / zkonkretizovat:**

* Vyžaduj, aby API **aktivně bránilo mis-use** (např. zákaz ECB, fixních IV, slabých křivek) a mělo **runtime guardrails** – ať je to binární ANO/NE.
* Přidej „**způsob publikace kryptografických deprecations**“ (např. výstrahy v release notes) – aby uživatelé včas migrovali.

**3 nové kritické otázky:**

1. „Brání API **mis-use by design** (např. odmítá ECB, příliš krátké IV/salt, zastaralé hash/křivky) a jsou tyto kontroly **testované**?“ ([OpenSSF Best Practices Working Group][3])
2. „Existují **konformanční testy** proti oficiálním **test vectors** (NIST/CAESAR/KAT) a jsou spouštěny v CI?“ – důkaz správnosti. ([cisa.gov][1])
3. „Má projekt **politiku deprecations** pro kryptografii (kalendář, náhrady, migrační průvodce) a je publikována v release notes?“ ([OpenSSF Best Practices Working Group][3])

---

## Globální doporučení napříč formulářem (aby to šlo dobře auditovat)

* U všech otázek zaveď **pole „důkaz/odkaz“** (URL na release, SBOM, CI run, policy), jinak odpovědi „splňuje“/„částečně“ ztratí auditovatelnost. To odpovídá duchu CISA Attestation (důkazy k tvrzení). ([cisa.gov][1])
* Přidej malou sekci „**Supply-chain & governance (minima)**“: *provenance/attestace, SBOM, VEX/Advisories, branch protection, secret policy*. Tím přemostíš tvůj formulář na CISA/SSDF minimum a OpenSSF Badge v jednom. ([cisa.gov][1])
* Doporučuju doplnit **scoring** per-sekce s vahami (např. Předpoklady 25 %, OSS vývoj 25 %, Kód 20 %, Dokumentace 15 %, Crypto API 15 %) + „**cut-offs**“ pro must-have. (OpenSSF Concise Guide výslovně říká, že dobrý projekt může některé věci nesplnit – ale minimální brány musí být jasné). ([OpenSSF Best Practices Working Group][3])

Pokud chceš, rovnou ti tenhle feedback promítnu do **v2 JSON** verze formuláře (přidám nové otázky, pole „důkaz“, sjednotím must-have/CI policy gates a navrhnu váhy + cut-offs).

[1]: https://www.cisa.gov/sites/default/files/2023-11/Secure%20Software%20Development%20Attestation%20Form_508c.pdf?utm_source=chatgpt.com "Secure Software Development Attestation Form"
[2]: https://www.bestpractices.dev/en/criteria/0?utm_source=chatgpt.com "FLOSS Best Practices Criteria (Passing Badge)"
[3]: https://best.openssf.org/Concise-Guide-for-Evaluating-Open-Source-Software.html?utm_source=chatgpt.com "Concise Guide for Evaluating Open Source Software"
