package com.mochyy.mochymusic.guardian

/** Conservative single-library ownership policy, not a multi-account database.
 * A different account never inherits existing data. No destructive reset path. */
internal object LocalLibraryBinding {
    enum class Status { UNCLAIMED, MATCH, OTHER, UNAVAILABLE }
    private val id = Regex("[a-f0-9]{32}")
    fun status(stored: String?, account: String): Status {
        require(id.matches(account))
        return when {
            stored == null -> Status.UNCLAIMED
            !id.matches(stored) -> Status.UNAVAILABLE
            stored == account -> Status.MATCH
            else -> Status.OTHER
        }
    }
    fun canUse(status: Status, confirmed: Boolean): Boolean =
        status == Status.MATCH || (status == Status.UNCLAIMED && confirmed)
}
