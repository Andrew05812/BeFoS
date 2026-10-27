package app.befos.presentation.common

import app.befos.domain.model.Connection

/**
 * The four kinds of relation between two answers, in the engine's own terms.
 *
 * The map and the pair's compatibility page read the same field off the same engine, and they have to
 * call a `discussion` the same thing on both screens or a pair starts wondering whether two words mean
 * two grades. Three of the four are non-pejorative by design: a difference between two people is a kind
 * of relation, not a mistake, and the fourth is not a weak relation at all but the absence of one — which
 * is why it says so instead of borrowing a word for closeness.
 */
fun connectionKindWord(connection: Connection): String = when (connection) {
    Connection.HARMONY -> "совпадение"
    Connection.COMPLEMENTARITY -> "дополнение"
    Connection.DISCUSSION -> "расхождение"
    Connection.UNKNOWN -> "нет данных"
}
