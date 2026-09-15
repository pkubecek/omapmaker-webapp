"""cancellation.py — sdílený mechanismus pro rušení běžících stahování."""


class DownloadCancelled(Exception):
    """Vyvoláno uvnitř downloader funkcí, když uživatel zruší probíhající stahování."""
    pass
