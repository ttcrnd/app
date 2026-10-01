from __future__ import annotations

import re


def extract_links_from_markdown(md_text: str | None) -> list[str]:
    text = md_text or ""
    links: list[str] = []
    for m in re.finditer(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", text, re.IGNORECASE):
        links.append(m.group(2))
    for m in re.finditer(r"<(https?://[^>\s]+)>", text, re.IGNORECASE):
        links.append(m.group(1))
    for m in re.finditer(r"(https?://[^\s)>,]+)", text, re.IGNORECASE):
        links.append(m.group(1))
    return sorted(set(links))


def md_has_install_instructions(md: str | None) -> bool:
    patterns = [
        r"\binstall(ation)?\b",
        r"\bbuild(ing)?\b",
        r"\bcompile\b",
        r"\bcmake\b",
        r"\bmake\b",
        r"\bhow to (install|build)\b",
    ]
    return any(re.search(p, md or "", re.IGNORECASE) for p in patterns)


def md_has_api_reference_signals(md: str | None) -> bool:
    patterns = [
        r"\bAPI reference\b",
        r"\bReference\b",
        r"\bDoxygen\b",
        r"\bSphinx\b",
        r"\bRead the Docs\b",
        r"\bMkDocs\b",
        r"\bModules\b",
        r"\bPublic\s+API\b",
    ]
    return any(re.search(p, md or "", re.IGNORECASE) for p in patterns)


def md_has_code_examples(md: str | None) -> bool:
    if re.search(r"```[\s\S]*?```", md or "", re.MULTILINE):
        return True
    if re.search(r"^\s{4}\S", md or "", re.MULTILINE):
        return True
    if re.search(r"\bexample(s)?\b|\busage\b|\bsample(s)?\b", md or "", re.IGNORECASE):
        return True
    return False


def md_has_crypto_warnings(md: str | None) -> bool:
    patterns = [
        r"\bdeprecated\b",
        r"\bdo not use\b",
        r"\binsecure\b",
        r"\bECB\b",
        r"\bSHA-1\b",
        r"\bwarnings?\b",
        r"\bsecurity\s+considerations\b",
        r"\bunsafe\b",
    ]
    return any(re.search(p, md or "", re.IGNORECASE) for p in patterns)


def md_has_howto_guides(md: str | None) -> bool:
    patterns = [
        r"\bhow[-\s]?to\b",
        r"\bguide(s)?\b",
        r"\btutorial(s)?\b",
        r"\brecipe(s)?\b",
        r"\bscenario(s)?\b",
    ]
    return any(re.search(p, md or "", re.IGNORECASE) for p in patterns)
