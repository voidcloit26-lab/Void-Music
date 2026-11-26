# VOID Music V2 release disclosures — draft, not active terms

**Release gate:** Operator and qualified legal review required before commercial access. This draft does not amend the working V1 terms. Fill in the legal operator, support channel, applicable retention periods, data processors and applicable rights before publishing. Confirm that all commercial music and SDK integrations are permitted. Do not accept payments for unauthorized streams or downloads.

## Membership and renewal
- Annual membership is a separately administered VOID service entitlement, with the final USD price shown before purchase. The current proposed price is $5 for twelve calendar months; it is not a confirmed public offer. Early renewal extends an active term; renewal after expiry begins at redemption.
- Payment is manually confirmed by the authorized adult operator. Do not send wallet seed phrases, passwords, private keys, or OTPs. No automatic charges or automatic renewal. Record the quoted amount, permitted network, payment reference, payment confirmation and membership start/end. Publish refunds and error-resolution process before collecting funds.
- Complimentary lifetime access has no scheduled membership end while the service operates. It is not a promise of perpetual service. Access may be suspended for substantiated misuse or security incidents with appropriate notice and review where feasible.
- The user may sign in after expiry, export retained account metadata, and renew. Define a retention/deletion schedule before launch. Do not describe permanent retention unless implemented.

## Authentication and security
- Clerk processes verified sign-in details and sessions. Guardian stores an internal account identifier, pseudonymous linked identity, device public-key fingerprint, membership and keyed recovery/invitation digests. The Android signing private key is intended to remain in Android Keystore. No Clerk secret belongs in the app.
- The intended one-device policy requires successful account recovery or reviewed owner-assisted replacement. Save the recovery code securely; it is rotated upon recovery. Do not share it.
- Signed offline entitlements are bounded to 24 hours or the earlier membership expiry; a reboot may require online re-verification. Revocation of an offline device is not instantaneous. Sign-out should clear local entitlement and account caches.
- Users must approve Android updates. A verified signed release may require an update to access the hosted service. Provide support and recovery options when verification or installation fails.

## Cloud metadata
- Cloud synchronization requires explicit user consent. The initial scope is eligible track IDs, local playlist names and order, favorites, and allowlisted preferences. Local audio, filesystem paths, provider tokens, credentials, uploaded tracks, downloaded audio and search history are excluded. Show unsupported entries and resolve conflicts before replacing cloud state.
- Users may export or request correction/deletion of their data. Specify retention for expired accounts, backups, transaction records and logs; retain only what is necessary and legally required.
- Hosting and independent providers may process network metadata and feature-specific information. Identify processors and provide privacy notices and contact channels; do not claim anonymity or absolute security.

## Third parties, availability and remedies
- External catalog, artwork, lyrics and Discord integration availability may change. Use providers only as authorized under their terms and rights-holder permissions. Do not guarantee every song, perpetual uptime, or permission to download.
- Explain refund, extension or other reasonable remedies for a materially unavailable paid service; applicable consumer rights cannot be waived. Avoid blanket no-refund clauses or promises of unlimited liability protection.
- Maintain the GPL notices, corresponding source and build instructions for distributed covered code. Paid hosted membership does not restrict recipients' GPL rights to inspect, modify or redistribute covered software. The operator's original branding and independent service credentials remain separate.
- Adult operator review of applicable Indian consumer, privacy, tax and cryptocurrency obligations is required before accepting payments.

## Open release fields
Legal operator identity; support contact; privacy/retention schedule; licensed provider list; payment terms and settlement verification; refund process; account deletion process; published version/effective date. No live terms or acceptance flow until these are verified.
