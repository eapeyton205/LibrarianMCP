"""
Little librarian MCP server -- deploy version.

Two changes from the local version:

1. Port comes from the PORT environment variable. Render assigns you a port
   and expects you to bind to it. Hardcode 8000 and your deploy will build
   fine, start fine, and then Render will kill it for "no open ports" --
   which is a confusing failure because nothing looks broken.

2. There's a /health endpoint. This is what the keep-alive cron pings.
   Don't point the pinger at /sse: that opens a Server-Sent Events stream
   and holds the connection open, which is not what you want happening
   every ten minutes forever.
"""

import os

import httpx
from fastmcp import FastMCP
from starlette.responses import PlainTextResponse

mcp = FastMCP("librarian")

OPENLIB = "https://openlibrary.org"
HEADERS = {"User-Agent": "little-librarian/0.1 (hobby project)"}


def _get(path: str, **params) -> dict:
    r = httpx.get(f"{OPENLIB}{path}", params=params, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Cheap endpoint for the keep-alive pinger. Does no work."""
    return PlainTextResponse("ok")


@mcp.tool()
def find_book(title: str) -> str:
    """Look up a book by title. Returns author, year, and a one-line summary."""
    try:
        data = _get(
            "/search.json",
            q=title,
            limit=1,
            fields="title,author_name,first_publish_year",
        )
    except Exception:
        return "I couldn't reach the catalogue just now."

    docs = data.get("docs") or []
    if not docs:
        return f"I couldn't find anything called {title}."

    b = docs[0]
    author = (b.get("author_name") or ["an unknown author"])[0]
    year = b.get("first_publish_year")
    line = f"{b['title']} by {author}"
    if year:
        line += f", first published in {year}"
    return line + "."


@mcp.tool()
def books_by_author(author: str) -> str:
    """List a few notable books by an author."""
    try:
        data = _get("/search.json", author=author, limit=5, sort="rating", fields="title")
    except Exception:
        return "I couldn't reach the catalogue just now."

    titles = [d["title"] for d in (data.get("docs") or []) if d.get("title")]
    if not titles:
        return f"I don't have anything listed for {author}."
    if len(titles) == 1:
        return f"{author} wrote {titles[0]}."
    return f"{author} wrote {', '.join(titles[:-1])}, and {titles[-1]}."


@mcp.tool()
def describe_book(title: str) -> str:
    """Get a short description of what a book is actually about."""
    try:
        search = _get("/search.json", q=title, limit=1, fields="key,title")
        docs = search.get("docs") or []
        if not docs:
            return f"I couldn't find anything called {title}."
        work = _get(f"{docs[0]['key']}.json")
    except Exception:
        return "I couldn't reach the catalogue just now."

    desc = work.get("description")
    if isinstance(desc, dict):
        desc = desc.get("value")
    if not desc:
        return f"I don't have a description for {docs[0]['title']}."

    sentences = desc.replace("\r\n", " ").split(". ")
    return ". ".join(sentences[:2]).strip().rstrip(".") + "."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
