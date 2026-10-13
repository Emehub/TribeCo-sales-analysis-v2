"""
Print the [gcp_service_account] block for the Streamlit Cloud secrets from a downloaded
service-account JSON key, plus a fresh random cookie_secret for [auth].

    python scripts/make_streamlit_secrets.py "C:/path/to/key.json"

Copy the printed text into Streamlit Cloud > app > Settings > Secrets. Nothing is saved or sent anywhere.
"""
import json
import secrets
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
with open(sys.argv[1], encoding="utf-8") as f:
    key = json.load(f)

print("# ---- paste into Streamlit secrets ----")
print(f'# cookie_secret for the [auth] section:\n# cookie_secret = "{secrets.token_hex(32)}"\n')
print("[gcp_service_account]")
for k, v in key.items():
    print(f"{k} = {json.dumps(v)}")   # JSON string escaping is valid TOML (keeps the \\n in private_key)
print("# ---- end ----")
