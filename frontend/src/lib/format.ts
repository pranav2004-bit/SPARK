// Display-only — the stored value's own casing is left untouched wherever
// else it's read (e.g. login greetings, admin rosters); this is purely for
// presentation next to naturally-cased values like batch/department.
export function toTitleCase(value: string): string {
  return value.replace(/\w\S*/g, w => w[0].toUpperCase() + w.slice(1).toLowerCase());
}
