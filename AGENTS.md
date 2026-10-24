# Production delivery

The web UI currently serves as the owner's admin panel. Put administrative
actions such as manually generating forecasts in the web UI. Do not add these
controls to the Telegram bot unless the user explicitly requests it.

The deployed app uses the database on the VPS. Local database changes are not
delivered by Git and must never be the only implementation of a product change.

- Ship required tournaments, fixtures and reference data in a versioned Alembic
  data migration with its reusable implementation inside `src/cs2eye/deployment`.
  Do not leave a required production action in a standalone local script.
- Data migrations must be transactional, repeatable against existing production
  data, preserve recorded outcomes and forecasts, and fail clearly on incomplete
  prerequisites. Never replace the production database with a development dump.
- `cs2eye-deploy` must apply those migrations and prepare server-side forecasts
  before reporting success. Keep preparation checks in the release workflow when
  introducing new features that need generated data.
- Forecasts must be computed and stored on the server before kickoff. Never
  backdate a new calculation. Authentic archived forecasts retain their original
  timestamps and model versions when explicitly migrated.
- Verify the final user flow against the deployed API, including tournament
  visibility and saved forecasts. A passing container healthcheck alone is not
  sufficient. Do not claim deployment complete while required data is absent.
- Production updates are manual, from `telegtam-prod`, using `cs2eye-deploy`.
  Preserve unrelated local changes and do not start a second Telegram polling
  instance with the production token.
