package app.befos.core.invite

import java.net.URI

/**
 * `befos://invite/<code>` — the only address this app claims from outside.
 *
 * The parser does not decide whether the code is live: an expired or spent link has to reach the
 * registration screen so the person can be told what happened, and a client that silently dropped it
 * would look like a broken tap. It only refuses shapes that are not a personal door at all — another
 * scheme, another host, a path with no code, a path with more than one segment, or text long enough
 * to be an attack on the register body rather than a link a friend sent.
 */
object InvitationLink {
    const val SCHEME = "befos"
    const val HOST = "invite"
    private const val MAX_CODE_LENGTH = 32

    fun code(raw: String?): String? {
        val text = raw?.trim().orEmpty()
        if (text.isEmpty()) return null
        val uri = runCatching { URI(text) }.getOrNull() ?: return null
        if (!uri.scheme.equals(SCHEME, ignoreCase = true)) return null
        if (!uri.host.equals(HOST, ignoreCase = true)) return null
        val segments = uri.path.orEmpty().split('/').filter { it.isNotEmpty() }
        if (segments.size != 1) return null
        val code = segments.single()
        if (code.length > MAX_CODE_LENGTH) return null
        return code
    }
}
