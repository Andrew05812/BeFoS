package app.befos.presentation.universe

/**
 * The words the map hands to the chat composer. A node's question is catalogue text addressed to
 * the person answering a test («Как вы решаете конфликты?»), and dropped into a thread bare it
 * arrives as an interview question with no opening. The frame is the shortest thing that makes it
 * the partner's own first line.
 */
internal const val ASK_FRAME: String = "Хочу спросить:"

/**
 * The draft a tap on «Спросить в чате» leaves in the composer. Nothing of the pair's own numbers
 * travels with it: the question is what the map measured the axis with, and the two answers it
 * compares stay on the map. The text is a draft and not a send — the app has no right to put a
 * message into a thread on the pair's behalf, and §82 forbids activity the pair did not write.
 */
internal fun chatDraftFor(question: String): String = "$ASK_FRAME $question"

/**
 * The frame the pair's starter sentence takes when it travels to the composer.
 *
 * A starter arrives as advice addressed to the person («Начните с общего интереса: „Джаз“»), and advice
 * pasted into a private thread reads like the app talking to somebody's partner. Rewritten into the first
 * person it becomes something the reader might actually have typed, and it still carries nothing the pair
 * did not already have on screen.
 */
internal const val STARTER_FRAME: String = "Хочу начать с"

/**
 * The draft a tap on the starter line leaves in the composer, or null when the line names no place to
 * start.
 *
 * Only the fragment the engine itself put in «quotes» travels: it is the one part of the sentence the
 * screen can hand over without interpreting the rest, and the app does not know whether the words around
 * it were about an interest, a band or a conversation. A starter with nothing quoted — the engine's own
 * «начните с анкеты» — gives no draft, and the compatibility screen then offers no chat door rather than
 * a field full of an instruction nobody wrote.
 */
internal fun starterDraftFor(starter: String): String? =
    starterTopicOf(starter)?.let { "$STARTER_FRAME «$it»" }

/** The place the engine named inside its own sentence, or null when it named none. */
internal fun starterTopicOf(starter: String): String? =
    QUOTED.find(starter)?.groupValues?.get(1)?.trim()?.takeIf { it.isNotEmpty() }

private val QUOTED = Regex("«([^»]+)»")
