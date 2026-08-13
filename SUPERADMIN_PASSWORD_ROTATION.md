# Super Admin Password Rotation — Production

**Use this whenever the super-admin's login password needs to change in a live deployment.**

Do NOT edit `SUPERADMIN_PASSWORD` in `.env` and expect it to take effect — it only applies the **first time** the account is created on an empty database. Once the account exists, `.env` is ignored for this field. The only supported way to change the live password is the command below.

---

## Command

```bash
docker exec -it <auth-service-container-name> python manage.py rotate_superadmin_password <super-admin-email>
```

Example (dev container names):
```bash
docker exec -it infra-auth-service-1 python manage.py rotate_superadmin_password spark@gmail.com
```

If you omit the email, it defaults to the current `SUPERADMIN_EMAIL` value.

`-it` is required — the command hides your typed password and needs a real terminal.

---

## What it does (single atomic step)

1. Looks up the super-admin account by email. Fails with a clear error if it doesn't exist.
2. Prompts for the new password twice (hidden input). Retries up to 3 times if they don't match or fail strength validation, then aborts safely with no changes made.
3. Saves the new password hash to the database.
4. Increments `token_version` on the same save — this immediately invalidates every previously issued login token for that account (anyone already logged in is logged out).
5. Writes a `WARNING`-level audit log entry (visible via `docker logs <auth-service-container-name>`):
   ```
   SECURITY AUDIT: super-admin password rotated for email=... — token_version X -> Y (all prior tokens invalidated).
   ```

---

## Step 2 — Update `.env` to match

After running the command, also update `SUPERADMIN_PASSWORD` in `services/auth-service/.env` to the same new password.

This step does **not** affect the running system — the live password is already changed by Step 1 alone, and `.env` is not re-read for an existing account. But skipping this step leaves `.env` showing a stale, wrong password indefinitely, which causes confusion for the next person (or future-you) who reads that file expecting it to reflect reality. Always do both, in this order:

1. Run the command (functional — actually changes the password)
2. Update `.env` (bookkeeping — keeps the file truthful)

---

## Safety net — what if Step 2 is forgotten or skipped?

If `.env`'s `SUPERADMIN_PASSWORD` no longer matches the live database password the next time the container starts, `create_default_superadmin` will **refuse to start** and print:

```
SUPERADMIN_PASSWORD in .env does not match the live database password.
Editing .env has NO EFFECT on an existing account's password.
To actually rotate the password, run: python manage.py rotate_superadmin_password
Then update .env to match the new password, and restart.
```

This catches two mistakes automatically:
- Forgetting Step 2 after rotating correctly.
- Trying the wrong shortcut — editing `.env` directly without running the command first.

Either way, the fix is the same: run `rotate_superadmin_password` (if not already done), then make sure `.env` matches the new password, then restart.

---

## What this does NOT cover

- **`.env` file security is on you.** If that file is readable by unauthorized people (wrong permissions, committed to git, exposed server), rotating the password does not fix that exposure.
- **Other accounts are unaffected.** This only rotates the super-admin. Admin and student passwords are changed by those users themselves, through their own profile pages.
- **No UI exists for this.** Super-admin password rotation is CLI-only by design — there is no web page for it.
