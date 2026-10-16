This Personal health care application is a proto type application, before a larger real life application with AWS cloud data base is hosted on the domain.

## Existing database accounts

On startup, the app upgrades legacy user columns and migrates legacy medication
schedules and logs into prescriptions while retaining the original schedule
rows and medication-log IDs. Unique legacy names are used as usernames; duplicate
names are left unset rather than guessed. Passwords are never generated or
inferred, so an administrator must set credentials for legacy accounts.

Run `python activate_legacy_account.py` in an environment configured to use the
target database. The script lists legacy account IDs and prompts for the account,
username, and a new password; password input is hidden. Do not put database URLs
or passwords in source control or command-line arguments.
