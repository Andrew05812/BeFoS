package app.befos.presentation.universe

import app.befos.presentation.navigation.Routes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The map reads the pair's answers and can name the axis they disagree on, but only the two of them
 * can settle it. Stage 79.4 gives the node panel a way out into the thread, and the rule that keeps
 * the way out honest is small: what travels is the question the axis was measured with, and nothing
 * else — no percent, no evidence line, no answer of either partner.
 *
 * The text is left in the composer as a draft. An app that sends on the pair's behalf would be
 * writing into a conversation the pair never wrote (§82).
 */
class UniverseHandoffTest {

    @Test
    fun `a node question reaches the composer as one sentence, not as a bare interview line`() {
        val draft = chatDraftFor("Как вы решаете конфликты?")
        assertEquals("Хочу спросить: Как вы решаете конфликты?", draft)
        assertTrue(draft.isNotBlank())
        assertEquals(1, draft.lines().size)
    }

    @Test
    fun `the draft carries the question and smuggles nothing of the pair's numbers`() {
        val question = "Насколько для вас важна семья?"
        val draft = chatDraftFor(question)
        // Nothing but the frame separates the draft from the catalogue text: no percent, no
        // «90 против 70», no name of either partner.
        assertEquals(question, draft.removePrefix(ASK_FRAME).trim())
        assertFalse(draft.any { it.isDigit() })
        assertFalse(draft.contains("%"))
    }

    @Test
    fun `a thread opened without a question keeps the route it always had`() {
        assertEquals("chat/m1", Routes.chat("m1"))
        // The `name={name}` form is what makes the query argument optional: a destination declared
        // any other way would not match the plain `chat/m1` every older caller still builds.
        assertEquals(
            "chat/{${Routes.CHAT_ARG}}?${Routes.DRAFT_ARG}={${Routes.DRAFT_ARG}}",
            Routes.CHAT,
        )
    }

    @Test
    fun `the question rides as an encoded query parameter of the pair's own thread`() {
        val encoded = "How%20you%20settle%20conflicts%3F"
        assertEquals("chat/m1?draft=$encoded", Routes.chat("m1", encoded))
        assertEquals(Routes.chat("m1"), Routes.chat("m1", null))
    }
}
