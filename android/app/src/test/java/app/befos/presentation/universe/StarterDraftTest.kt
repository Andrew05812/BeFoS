package app.befos.presentation.universe

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The starter line the engine writes, and the one rule that decides whether the pair gets a door out of it.
 *
 * Stage 125 puts «С чего начать» on the pair's compatibility page, and the page offers to carry that
 * beginning into the thread. Carrying the whole sentence would be the app talking to somebody's partner:
 * the engine's words are advice addressed to the reader («Начните с …»), and advice pasted into a private
 * conversation reads as a third person joining it. So only the fragment the engine itself put in «quotes»
 * travels, reframed into the first person, and a starter that quotes nothing gets no door at all rather
 * than a field full of an instruction nobody wrote.
 *
 * The four shapes below are the four sentences `backend/app/compatibility/explanation.py` answers with,
 * written out here because the two halves of the same rule have to be read together: the backend test
 * pins the quoted form of the interest branch, and the checks below pin what the phone does with each of
 * them.
 */
class StarterDraftTest {

    @Test
    fun `a starter naming a common interest hands that interest to the composer in the first person`() {
        val draft = starterDraftFor("Начните с общего интереса: «Джаз»")

        assertEquals("Хочу начать с «Джаз»", draft)
        // The engine's advice stays on the pair's own screen: what arrives in the thread is something the
        // reader might have typed, not an instruction addressed to them.
        assertFalse(draft!!.contains("Начните"))
        assertFalse(draft.contains("общего интереса"))
    }

    @Test
    fun `the topic travels whole, spaces and all`() {
        assertEquals(
            "Хочу начать с «Настольные игры»",
            starterDraftFor("Начните с общего интереса: «Настольные игры»"),
        )
    }

    @Test
    fun `a starter that names a band rather than a thing opens no door`() {
        // Two of the engine's four sentences point at a band, in its own words and without quoting it.
        // A screen cannot turn «общение» into a sentence worth typing without inventing one, so the tap
        // is not offered — the line stays readable, the dead control does not appear.
        assertNull(starterDraftFor("Начните с того, где вы уже совпадаете: общение"))
        assertNull(starterDraftFor("Начните с разговора про досуг: здесь ответы разошлись"))
    }

    @Test
    fun `a starter that sends the reader back to the questionnaire opens no door`() {
        // Both empty-hand branches say «начните с анкеты» without quoting anything: the place to begin is
        // the questionnaire, and the thread is not it.
        assertNull(
            starterDraftFor(
                "Пока нет ни одного сравненного ответа, и процент держится на нейтрали — начните с анкеты",
            ),
        )
        assertNull(starterDraftFor("Похожие ответы нашлись, но назвать их нечем — начните с анкеты"))
    }

    @Test
    fun `an absent starter yields neither a draft nor a door`() {
        assertNull(starterDraftFor(""))
        assertNull(starterTopicOf(""))
    }

    @Test
    fun `quotes holding nothing are not a place to start`() {
        // An empty or blank quoted span would put «Хочу начать с «»» in front of a person: a field that
        // says there is something to begin with, and names nothing.
        assertNull(starterDraftFor("Начните с общего интереса: «»"))
        assertNull(starterDraftFor("Начните с общего интереса: «   »"))
    }

    @Test
    fun `the topic is read out of the sentence, not rewritten by the screen`() {
        assertEquals("Джаз", starterTopicOf("Начните с общего интереса: «Джаз»"))
        assertEquals("Джаз", starterTopicOf("Начните с общего интереса: « Джаз »"))
        assertNull(starterTopicOf("Начните с общего интереса: Джаз"))
    }

    @Test
    fun `the draft carries no number of the pair's`() {
        val draft = starterDraftFor("Начните с общего интереса: «Джаз»")

        // The percent, the weights and the band scores belong to the reading surface. Once they are in a
        // message they are a claim one person is making about the other, and the engine wrote no such claim.
        assertFalse(draft!!.any { it.isDigit() })
        assertFalse(draft.contains("%"))
    }

    @Test
    fun `the frame the draft wears is the one the screen documents`() {
        assertEquals("Хочу начать с", STARTER_FRAME)
        // A question and a beginning are two different acts in a thread: the map hands over a question the
        // pair can leave unanswered, the starter hands over something to do. One frame for both would make
        // the thread read as an interview.
        assertEquals("Хочу спросить:", ASK_FRAME)
        assertFalse(STARTER_FRAME == ASK_FRAME)
    }
}
