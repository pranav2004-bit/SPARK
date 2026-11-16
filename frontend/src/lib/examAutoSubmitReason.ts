// Carries the reason an exam was just auto-submitted (tab-switch or
// fullscreen-exit strike limit) across the redirect to the assessments
// list, so that page can show a toast explaining why — the exam page
// itself unmounts immediately on redirect, so a toast fired there would
// never be seen. sessionStorage (not a query param) keeps this out of the
// URL and tab-isolated, consistent with this app's existing auth-store
// convention.
const KEY = "spark_exam_auto_submit_reason";

export function setExamAutoSubmitReason(reason: string) {
  try { sessionStorage.setItem(KEY, reason); } catch { /* ignore */ }
}

export function consumeExamAutoSubmitReason(): string | null {
  try {
    const reason = sessionStorage.getItem(KEY);
    if (reason) sessionStorage.removeItem(KEY);
    return reason;
  } catch {
    return null;
  }
}
