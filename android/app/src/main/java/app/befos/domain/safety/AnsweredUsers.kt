package app.befos.domain.safety

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow

/**
 * People the viewer has already answered somewhere other than the deck.
 *
 * A profile opened from a card can be liked, passed or blocked on that screen, and none of
 * it reaches the page of cards the deck holds in memory: without this signal the person you
 * just blocked is the next card, and the tap that follows answers «Профиль не найден».
 */
class AnsweredUsers {
    private val _answered = MutableSharedFlow<String>(extraBufferCapacity = 32)
    val answered: SharedFlow<String> = _answered

    fun publish(userId: String) {
        _answered.tryEmit(userId)
    }
}
