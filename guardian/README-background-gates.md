# Guardian background staging gates

- Active phone/TV UI and music/phone-link service check signed entitlement locally and
  share a process-local online status request budget (15 minutes after success, 1 minute
  after temporary failure). Revoked receipts trigger playback stop and UI activation;
  airplane mode or server outages do not erase a valid offline lifetime receipt.
- Remote phone link, exported widget receivers, local artwork and cloud/module callback
  activities reject unactivated builds. Download resolver denies new requests and
  the download manager pauses on activation state changes.
- This remains an opt-in staging gate. Android Auto UI, media-button receiver, existing
  controllers during revocation and in-flight downloads/remote streams still need on-device
  verification and lifecycle auditing. No tamper-resistance claim is made. The GPL source
  can be modified by recipients; server resources need independent server-side enforcement.
  Offline lifetime means revocation cannot be immediate when disconnected.
- No production services, APK distribution or Guardian hosting were changed.
