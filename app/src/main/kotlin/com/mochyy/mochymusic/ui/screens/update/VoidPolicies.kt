package com.mochyy.mochymusic.ui.screens.update

/** Release policy draft; maintainer must verify provider practices and retention before distribution. */
internal object VoidPolicies {
    val sections = listOf(
        "Terms of Service" to """
            VOID Music is a modified music player maintained by VOID. These terms describe access to the private VOID-hosted services, not restrictions on rights granted by open-source licenses. Invitations are issued at the maintainer's discretion, may have limited redemption slots and may expire before redemption. Successful activation has no scheduled end date, but access to VOID-hosted services may be revoked for misuse or security reasons. No purchase, uninterrupted service or perpetual hosting is promised.

            Use the application lawfully and respect the rights of artists, rights holders and external service operators. Do not abuse hosted services, attempt unauthorized access to owner administration, submit another person's credentials or disrupt other users. These service rules do not remove your rights to inspect, modify or redistribute GPL-covered software under its license. You are responsible for the permissions and accounts you choose to connect.
        """.trimIndent(),
        "Privacy and device activation" to """
            Guardian uses a device-generated cryptographic public key, signed challenges and invitation codes to verify access. The server stores a derived device fingerprint, internal activation identifier, activation time and revocation status; invitation records use a keyed digest rather than the original code. The activation protocol does not require a Discord login, Gmail login, phone number or Google account password. The device signing private key is intended to remain in Android Keystore. A signed access receipt is stored locally for subsequent access checks.

            Hosting and network providers may process IP addresses, timestamps and ordinary request metadata. Guardian activation records are retained for access administration and revocation; no automatic deletion deadline for activation records has been established. Expired or fully redeemed invitations are removed during store operations. Contact the maintainer to request access information, correction or deletion where applicable. Deleting activation information may affect access. This notice describes Guardian specifically and does not claim that every third-party integration has the same data practices.
        """.trimIndent(),
        "Music, connected services and permissions" to """
            Music searches, playback, lyrics, artwork, synchronization and optional integrations may send requests to independent providers. The data involved depends on the feature and provider and can include search terms, track identifiers, network metadata, account information or listening activity. Discord Rich Presence, when enabled, can display listening information to others according to your Discord settings. Connected services operate under their own terms and privacy policies; disable or disconnect integrations you do not want to use.

            The app may store preferences, playback history, library information, cached media and downloads locally. Permissions should be granted only when needed for a feature. Music and artwork remain the property of their respective rights holders. VOID does not guarantee ownership, availability, download rights, catalog coverage or the legality of every external source. Download or share content only where you have permission.
        """.trimIndent(),
        "Access, availability and security" to """
            A valid offline activation receipt may remain usable while the device is disconnected. Revocation is not instantaneous offline; the application must complete a successful online status check. Reinstalling the app or clearing its data may remove the device key or local receipt and require assistance or a new invitation. Do not share unused invitation codes unless the maintainer intended them for multiple users.

            Software and hosted services may change or become unavailable. Keep backups of information you wish to retain. To the extent permitted by applicable law, the software is provided without warranties; nothing in these terms excludes rights or remedies that cannot lawfully be excluded. Security protections are not a guarantee against every vulnerability.
        """.trimIndent(),
        "Open-source rights and contact" to """
            VOID Music contains software derived from other open-source projects. Original authors retain their copyrights; VOID claims only its own original contributions and branding. The applicable licenses govern the covered code and take priority over conflicting service terms. Recipients of the APK must be provided corresponding source and build instructions as required by the GPL. Copyright notices and license information are available in this screen. Independent server credentials and private keys are not part of the app source distribution.

            For access assistance, privacy requests, copyright concerns, source requests or security reports, contact the VOID maintainer through the support contact below. Do not send passwords, private signing keys or payment details.
        """.trimIndent(),
    )
    fun fullText(): String = sections.joinToString("\n\n") { (title, body) -> title + "\n\n" + body }
}
