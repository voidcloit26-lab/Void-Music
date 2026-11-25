# Independent Guardian deployment (not provisioned)

Use a separate host or isolated managed service with a **persistent private volume**.
Do not run this on VOID Bot production as part of the app release. Never use a Render
ephemeral filesystem for activation state. A paid disk or different durable storage
would need owner approval; no paid resources have been created.

1. Provision a dedicated non-root account, Python environment, and persistent state
   directory owned by that account (0700). Install guardian/requirements-server.txt.
2. Set VOID_GUARDIAN_STATE to that absolute directory and
   VOID_GUARDIAN_PEPPER_FILE to its pepper.hex file. Execute python -m guardian.bootstrap
   once as the service account. It prints only the public signing key. Store the private
   signing key, pepper and SQLite database in encrypted backups. Never regenerate them
   on restart or copy them into the application.
3. Run gunicorn --config guardian/deploy/gunicorn.conf.py 'guardian.activation_api:create_app()'
   from the repo root with the persistent environment. Bind to loopback or an isolated
   private network behind a production HTTPS reverse proxy; if a managed service
   requires a public bind, ensure its trusted TLS proxy is the only ingress.
4. Expose only the three JSON POST endpoints. Apply per-IP limits, request-body size
   limits, timeouts, and no body logging at the reverse proxy. Keep the owner console
   on loopback and behind authenticated SSH forwarding; never publish its port.
5. Pin the printed public key and verified HTTPS origin in the Android staging build.
   Test invalid codes, valid single/multi-use codes, concurrent redemption, restart
   persistence, offline launch, revocation, existing activation recovery and service
   isolation before considering release.

No server, DNS, payment, bot, database, or production configuration has been changed.
