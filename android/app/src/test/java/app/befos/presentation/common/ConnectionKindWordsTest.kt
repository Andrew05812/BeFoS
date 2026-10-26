package app.befos.presentation.common

import app.befos.domain.model.Connection
import app.befos.presentation.compatibility.completenessCaption
import app.befos.presentation.compatibility.explanationKindHint
import app.befos.presentation.compatibility.explanationKindWord
import app.befos.presentation.universe.connectionWord
import app.befos.presentation.universe.sectionHint
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The one word list for a relation between two answers, and the two screens that have to read from it.
 *
 * The engine classifies every comparison it makes as `harmony`, `complementarity` or `discussion`, and a
 * pair meets that classification twice: on the map of their compatibility, where a node carries its kind,
 * and on the reading page, where each line of the explanation carries one. Those two surfaces are the same
 * claim about the same answers, so they cannot call a `discussion` two different things — a pair who sees
 * «расхождение» on one page and another word on the next starts wondering whether the two words are two
 * grades, which is exactly the doubt the shared list exists to prevent.
 *
 * `unknown` is in the list because the server can answer with it, and it is the absence of a comparison
 * rather than the weakest kind of one. That is why it has its own word and why [explanationKindWord]
 * hides it: a reading surface must not dress a gap in the pair's data as a finding about the pair.
 */
class ConnectionKindWordsTest {

    @Test
    fun `every kind the engine names has its own word`() {
        assertEquals("совпадение", connectionKindWord(Connection.HARMONY))
        assertEquals("дополнение", connectionKindWord(Connection.COMPLEMENTARITY))
        assertEquals("расхождение", connectionKindWord(Connection.DISCUSSION))
        assertEquals("нет данных", connectionKindWord(Connection.UNKNOWN))
    }

    @Test
    fun `no two kinds share a word`() {
        val words = Connection.entries.map { connectionKindWord(it) }

        assertEquals(
            "two kinds printed the same word: a pair cannot tell them apart on screen",
            words.size,
            words.toSet().size,
        )
    }

    @Test
    fun `the map and the reading page name one kind the same way`() {
        for (kind in Connection.entries) {
            assertEquals(
                "the pair's map and the pair's reading call `$kind` different things",
                connectionKindWord(kind),
                connectionWord(kind),
            )
        }
    }

    @Test
    fun `the words the server answers with are the words this list knows`() {
        // These literals are what `ExplanationItemDto.connection` and a map node carry on the wire. A word
        // from a newer engine would land as UNKNOWN rather than as a guess, which is the safe half of the
        // contract; the three the pair's screens depend on are pinned here.
        assertEquals(Connection.HARMONY, Connection.fromJson("harmony"))
        assertEquals(Connection.COMPLEMENTARITY, Connection.fromJson("complementarity"))
        assertEquals(Connection.DISCUSSION, Connection.fromJson("discussion"))
    }

    @Test
    fun `a word this build does not know reads as no data, not as the weakest kind`() {
        assertEquals(Connection.UNKNOWN, Connection.fromJson("serendipity"))
        assertEquals(Connection.UNKNOWN, Connection.fromJson(""))
    }

    @Test
    fun `a line the engine never classified gets no kind on a reading surface`() {
        assertNull(explanationKindWord(Connection.UNKNOWN))
        for (kind in Connection.entries.filter { it != Connection.UNKNOWN }) {
            assertEquals(connectionKindWord(kind), explanationKindWord(kind))
        }
    }

    @Test
    fun `the hint under a kind says what was compared, not what to make of it`() {
        // A difference between two people is not a mistake in one of them, and the three kind-words alone
        // could be read as a grade. Each hint names what was put side by side; none pronounces on the pair.
        assertEquals("вы ответили в одной полосе", explanationKindHint(Connection.HARMONY))
        assertEquals(
            "ответы разные, но не противоположные",
            explanationKindHint(Connection.COMPLEMENTARITY),
        )
        assertEquals(
            "ответы из противоположных полос — это разговор, а не ошибка",
            explanationKindHint(Connection.DISCUSSION),
        )
    }

    @Test
    fun `the absence of a comparison is named by one family of words`() {
        // «Движку было не с чем сравнивать» — один факт, и экранов у него три: строка полосы,
        // подпись под эмблемой и узел карты пары. Три разных слова об одном факте читаются парой
        // как три разных факта, и начинается поиск отличий там, где их нет.
        assertTrue(bandUnmeasuredWord(), bandUnmeasuredWord().contains("сверен"))
        val caption = completenessCaption(5, 7)!!
        assertTrue(caption, caption.contains("сверено"))
        assertTrue(sectionHint(Connection.UNKNOWN), sectionHint(Connection.UNKNOWN).contains("свер"))
    }
}
