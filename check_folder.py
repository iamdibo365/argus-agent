# check_folders.py
from google.oauth2 import service_account
from googleapiclient.discovery import build

creds = service_account.Credentials.from_service_account_file(
    "./service-account.json",
    scopes=["https://www.googleapis.com/auth/drive.readonly"],
)
svc = build("drive", "v3", credentials=creds, cache_discovery=False)

for fid in "1MNC2Tm-dy8bPOFoUtOk39NxSZ0rzgvgV,1B9hNb1PfaR3HXEQbJWgpFmJCBekBKdjR".split(","):
    fid = fid.strip()
    try:
        f = svc.files().get(fileId=fid, fields="name,mimeType",
                            supportsAllDrives=True).execute()
        print(f"OK      {fid} -> {f['name']} ({f['mimeType']})")
    except Exception as e:
        print(f"BROKEN  {fid} -> {type(e).__name__}: not visible or invalid")