"""Google Drive tools exposed to the agent.

Auth: a Google Cloud service account with the Drive API enabled.
Share the target Drive folder with the service account's email so it can see files.
"""
import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from langchain_core.tools import tool

from argus.config import settings

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Google Workspace formats that must be exported (not downloaded) as text
EXPORT_MIMETYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

MAX_CHARS = 12_000  # keep tool output within a sane context budget


def _drive_client():
    creds = service_account.Credentials.from_service_account_file(
        settings.google_application_credentials, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


@tool
def search_drive(query: str) -> str:
    """Search Google Drive for files whose name or content matches the query.
    Returns up to 10 results with file id, name, type, and last modified time.
    Use the file id with read_drive_file to read a file's contents."""
    service = _drive_client()
    q = f"(name contains '{query}' or fullText contains '{query}') and trashed = false"
    folder_ids = [f.strip() for f in settings.google_drive_folder_id.split(",") if f.strip()]
    if folder_ids:
        parents = " or ".join(f"'{fid}' in parents" for fid in folder_ids)
        q += f" and ({parents})"
    results = (
        service.files()
        .list(
            q=q,
            pageSize=10,
            fields="files(id, name, mimeType, modifiedTime, owners(displayName))",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = results.get("files", [])
    if not files:
        return f"No files found matching '{query}'."

    lines = []
    for f in files:
        owner = f.get("owners", [{}])[0].get("displayName", "unknown")
        lines.append(
            f"- id={f['id']} | {f['name']} | {f['mimeType']} | "
            f"modified {f['modifiedTime']} | owner: {owner}"
        )
    return "\n".join(lines)


@tool
def read_drive_file(file_id: str) -> str:
    """Read the text content of a Google Drive file by its file id.
    Supports Google Docs/Sheets/Slides, PDFs, and plain text/CSV/Markdown files."""
    service = _drive_client()
    meta = (
        service.files()
        .get(fileId=file_id, fields="name, mimeType", supportsAllDrives=True)
        .execute()
    )
    mimetype = meta["mimeType"]

    if mimetype in EXPORT_MIMETYPES:
        request = service.files().export_media(
            fileId=file_id, mimeType=EXPORT_MIMETYPES[mimetype]
        )
    elif (
        mimetype == "application/pdf"
        or mimetype.startswith("text/")
        or mimetype in ("application/json", "text/markdown")
    ):
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    else:
        return (
            f"File '{meta['name']}' has unsupported type {mimetype}. "
            "Only Google Docs/Sheets/Slides, PDFs, and text-based files are readable."
        )

    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    if mimetype == "application/pdf":
        from pypdf import PdfReader

        buf.seek(0)
        reader = PdfReader(buf)
        pages = [page.extract_text() or "" for page in reader.pages[:30]]
        text = "\n\n".join(pages).strip()
        if len(reader.pages) > 30:
            text += f"\n\n[... {len(reader.pages) - 30} more pages not read]"
        if not text:
            return (
                f"'{meta['name']}' appears to be a scanned PDF with no text layer — "
                "I can't extract text from it without OCR."
            )
    else:
        text = buf.getvalue().decode("utf-8", errors="replace")

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n\n[... truncated at {MAX_CHARS} characters]"
    return f"Contents of '{meta['name']}':\n\n{text}"