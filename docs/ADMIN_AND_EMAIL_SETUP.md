# Admin sign-in and scheduled email reports: setup

The code is ready. These one-off steps connect it to Google and GitHub. They need someone with
access to the Cowtribe Google account, the Streamlit Cloud app settings and the GitHub repository.
No step involves sharing a password in the code.

**Order:** 1 → 2 → 3 → 4 → 5 → 6. Until step 4 is done, the dashboard behaves as it does today and
the Admin page stays hidden.

---

## 0. Security first (do today)

The Metabase username and password appear in an old commit (`2953453`, 29 May 2026).

1. Change the Metabase password.
2. Put the new password in the Streamlit secrets (`[metabase]`) and in the GitHub secret `METABASE_PASSWORD` (step 5).
3. Confirm the GitHub repository is **private** (GitHub → repository → Settings → General → Danger Zone).

---

## 1. Google sign-in (OAuth client)

1. Open <https://console.cloud.google.com/> with a Cowtribe Google account and create a project, e.g. `tribeco-dashboard`.
2. **APIs & Services → OAuth consent screen**: User type **Internal** (only Cowtribe accounts can sign in). App name "TribeCo Ghana Dashboard".
3. **APIs & Services → Credentials → Create credentials → OAuth client ID** → Web application.
   - Authorised redirect URI: `https://<your-app>.streamlit.app/oauth2callback`
4. Copy the **Client ID** and **Client secret**.

## 2. Settings sheet (users, settings, email log)

1. Same Google Cloud project → **APIs & Services → Library**: enable **Google Sheets API** and **Google Drive API**.
2. **Credentials → Create credentials → Service account** (e.g. `dashboard-store`) → Keys → Add key → **JSON**. Download the file.
3. Create a new Google Sheet named "TribeCo Dashboard Admin". **Share** it with the service account's email
   (ends in `iam.gserviceaccount.com`) as **Editor**.
4. Copy the sheet ID from its URL: `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`.

The dashboard creates the tabs `Users`, `Settings` and `EmailLog` itself.

## 3. Email sending (Resend)

Reports are sent through **Resend** (resend.com) with an API key. No Gmail app password or
2-Step Verification is needed.

1. Sign in at <https://resend.com> and create an **API key** with *Sending access*. Keep it private.
2. **Verify the domain** so reports can come from `@cowtribe.com`: Resend → **Domains → Add domain** →
   `cowtribe.com`. Resend shows 2-3 DNS records (SPF/DKIM). Whoever manages cowtribe.com's DNS adds them;
   Resend then shows the domain as *Verified*.
   - Until it is verified, Resend only allows sending **from `onboarding@resend.dev` to your own Resend
     login email**, which is fine for testing.
3. Choose the sender, e.g. `TribeCo Ghana Reports <reports@cowtribe.com>` (any address on the verified
   domain works; no mailbox is needed to send). Optionally set a reply-to address so replies reach a real inbox.

## 4. Streamlit Cloud secrets

Streamlit Cloud → the app → **Settings → Secrets**. Keep the existing `[metabase]` section and add:

```toml
[access]
admins = ["your.name@cowtribe.com"]   # permanent admins; more can be added on the Admin page
require_login = true                  # never run without sign-in

[auth]
redirect_uri = "https://<your-app>.streamlit.app/oauth2callback"
cookie_secret = "<a long random string>"
client_id = "<from step 1>"
client_secret = "<from step 1>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[admin_store]
sheet_id = "<from step 2>"

[gcp_service_account]
# paste every field from the JSON key file of step 2, e.g.
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "dashboard-store@....iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"

[resend]
api_key = "<Resend API key from step 3>"
from = "TribeCo Ghana Reports <reports@cowtribe.com>"   # onboarding@resend.dev until the domain is verified
reply_to = "your.name@cowtribe.com"                      # optional
```

Save. The app restarts and asks everyone to sign in with Google.

## 5. GitHub Actions secrets (for the scheduled emails)

GitHub → repository → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `METABASE_URL` | same as `[metabase] url` |
| `METABASE_USERNAME` | same as `[metabase] username` |
| `METABASE_PASSWORD` | the **new** Metabase password |
| `METABASE_DBNAME` | `tribecodb` |
| `RESEND_API_KEY` | the Resend API key |
| `RESEND_FROM` | e.g. `TribeCo Ghana Reports <reports@cowtribe.com>` |
| `RESEND_REPLY_TO` | optional, e.g. your Cowtribe email |
| `ADMIN_SHEET_ID` | the sheet ID |
| `GCP_SERVICE_ACCOUNT_JSON` | the whole contents of the JSON key file |

## 6. First run

1. Sign in to the dashboard → **Admin** page → **Users & roles**: add the managers (role *Manager*;
   Weekly and Monthly are ticked by default). Make anyone else an Admin here.
2. **Report settings**: check the send day/time (default Friday 09:00) and paste the dashboard link.
3. **Preview & send**: build a preview, then **Send a test to me**.
4. GitHub → **Actions → Scheduled management reports → Run workflow**, with `to` = your own email and
   `force` = `yes`, to test the scheduled job end to end.
5. From then on it runs by itself: every Friday at 09:00 (weekly), and on the first Friday of each month
   (monthly). Every send is listed on the Admin page's **Email log**.

## How it works (for maintainers)

- `dashboard/data_layer.py`: Metabase fetch and data scoping, shared by the dashboard and the email job.
- `dashboard/weekly_report.py`, `dashboard/monthly_report.py`: report figures, PDF and email body.
- `dashboard/report_jobs.py`: what is due, build, send, log. `dashboard/mailer.py`: Resend API
  (Gmail SMTP is kept as a fallback if a `[smtp]` section is used instead).
- `dashboard/admin_store.py`: Google Sheet store (local JSON file when no sheet is configured).
- `dashboard/admin_page.py`: the Admin page. Sign-in gate and roles: top of `dashboard/app.py`.
- `scripts/send_scheduled_reports.py` + `.github/workflows/scheduled-reports.yml`: the scheduler
  (hourly 06:00-18:59 Ghana time; sends only when due, never twice for the same period).
- Local email test: add the `[resend]` section to your local `.streamlit/secrets.toml`, then run
  `python scripts/send_scheduled_reports.py --report weekly --force --to your.email@...`
  (that run still needs the `[admin_store]` sheet configured, or use the Admin page instead).
- Local testing without Google: add `[access] dev_admin = true` and `dev_user = "you@..."` to your
  local `.streamlit/secrets.toml` (never to the Streamlit Cloud secrets).
