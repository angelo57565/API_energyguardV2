"""Ajuda a usar a URL de conexão copiada de um MySQL na nuvem (ex.: Aiven)."""


def normalize_database_url(url: str) -> tuple[str, bool]:
    """Converte `mysql://...?ssl-mode=REQUIRED` em URL do SQLAlchemy.

    Retorna (url, ssl_obrigatorio).
    """
    url = url.strip()
    ssl_required = False
    if url.startswith("mysql://"):
        url = "mysql+pymysql://" + url[len("mysql://"):]
    if "?" in url:
        base, query = url.split("?", 1)
        keep = []
        for part in query.split("&"):
            low = part.lower()
            if low.startswith(("ssl-mode", "ssl_mode")):
                ssl_required = ssl_required or "disabled" not in low
            elif part:
                keep.append(part)
        url = base + ("?" + "&".join(keep) if keep else "")
    return url, ssl_required
