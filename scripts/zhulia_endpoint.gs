// Anonymous endpoint for the Zhulia scheduler (Google Apps Script web app).
// Starts the "scheduled-reports.yml" GitHub workflow; timing and duplicate checks happen in the job itself.
// Script Properties: GITHUB_TOKEN = fine-grained token (TribeCo-sales-analysis only, Actions: Read and write).

const DISPATCH_URL =
  "https://api.github.com/repos/Emehub/TribeCo-sales-analysis/actions/workflows/scheduled-reports.yml/dispatches";
const MIN_GAP_SECONDS = 600; // ignore calls within 10 minutes of the last accepted one

function doGet(e) { return trigger_(); }
function doPost(e) { return trigger_(); }

// Hourly timer (GitHub's own schedule is often late or skipped). Run installHourly() once from the editor.
function hourly() { trigger_(); }

function installHourly() {
  ScriptApp.getProjectTriggers()
    .filter(function (t) { return t.getHandlerFunction() === "hourly"; })
    .forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger("hourly").timeBased().everyHours(1).nearMinute(5).create();
}

function trigger_() {
  const cache = CacheService.getScriptCache();
  if (cache.get("last_call")) return json_({ status: "skipped", reason: "called recently" });

  const token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  const res = UrlFetchApp.fetch(DISPATCH_URL, {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + token,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    payload: JSON.stringify({ ref: "master", inputs: { report: "auto", trigger: "external" } }),
    muteHttpExceptions: true,
  });

  const code = res.getResponseCode();
  if (code === 204) {
    cache.put("last_call", "1", MIN_GAP_SECONDS);
    return json_({ status: "ok" });
  }
  return json_({ status: "error", github_status: code });
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
