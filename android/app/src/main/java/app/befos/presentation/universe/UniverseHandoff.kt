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
