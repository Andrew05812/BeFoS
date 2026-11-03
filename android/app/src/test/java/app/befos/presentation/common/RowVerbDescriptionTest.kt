package app.befos.presentation.common

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * What a row's verb is called to a reader who cannot see which row it stands on.
 *
 * The screens put these sentences into `contentDescription` because the button's own label («Нравится»,
 * «Забрать лайк», «Вернуть в подбор») lives in a sibling column: read alone, the tap answers with a verb and
 * nobody it belongs to. Stage 128 walked these lists under TalkBack and every row the reader spoke was
 * identified by that description, so the sentence is the row's accessibility contract — and three screens
 * were assembling it with three copies of the same string template.
 *
 * The dangling case is the one a template does not show: a person without a name would be spoken as
 * «Лайк в ответ для», a sentence that ends on a preposition. The app has already learned this shape of bug
 * on the city line («a missing city leaves no dangling separator»), so the rule is stated once here.
 */
class RowVerbDescriptionTest {

    @Test
    fun `a row's verb is spoken with the person it belongs to`() {
        assertEquals("Лайк в ответ для Читалка likes 50",
            namedVerbOnRow("Лайк в ответ", "Читалка likes 50"))
    }

    @Test
    fun `the same verb on two rows never reads the same`() {
        val first = namedVerbOnRow("Вернуть в подбор", "Читалка passes 12")
        val second = namedVerbOnRow("Вернуть в подбор", "Читалка passes 13")
        assertEquals(false, first == second)
    }

    @Test
    fun `an in-flight verb and an idle verb stay different sentences`() {
        assertEquals("Отзываю лайк для Читалка likes 50", namedVerbOnRow("Отзываю лайк", "Читалка likes 50"))
        assertEquals("Забрать лайк для Читалка likes 50", namedVerbOnRow("Забрать лайк", "Читалка likes 50"))
    }

    @Test
    fun `a person without a name leaves no dangling preposition`() {
        assertEquals("Нравится", namedVerbOnRow("Нравится", ""))
        assertEquals("Нравится", namedVerbOnRow("Нравится", "   "))
    }

    @Test
    fun `the words the screens use are the words this rule was written for`() {
        // Pinned against the three call sites: if a screen changes its verb or its joiner, this sentence is
        // what the reader starts saying, and it has to be a deliberate change rather than a drifted template.
        assertEquals("Лайк в ответ для Аня", namedVerbOnRow("Лайк в ответ", "Аня"))
        assertEquals("Вернуть в подбор для Аня", namedVerbOnRow("Вернуть в подбор", "Аня"))
        assertEquals("Забрать лайк для Аня", namedVerbOnRow("Забрать лайк", "Аня"))
    }
}
