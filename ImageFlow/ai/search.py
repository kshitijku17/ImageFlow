from pathlib import Path


def search_images(paths: list[str], query: str) -> list[tuple[int, str]]:
    """Local semantic-lite search: filename/path token matching."""
    q = query.lower()
    matches = []
    tokens = [x for x in q.replace(",", " ").split() if len(x) > 2]
    for p in paths:
        name = Path(p).stem.lower().replace("_", " ").replace("-", " ")
        score = sum(1 for token in tokens if token in name)
        if score:
            matches.append((score, p))
    matches.sort(key=lambda x: (-x[0], x[1].lower()))
    return matches
