package app.befos.data.mapper

import app.befos.core.network.befosJson
import app.befos.data.model.CompatibilityDto
import app.befos.domain.model.Connection
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The contract the compatibility route grew, on its way into the domain.
 *
 * `engineVersion` was already arriving on the wire and being thrown away in `Mappers.kt`, and the four
 * completeness fields plus the per-item `connection` did not exist in Kotlin at all — which left the phone
 * holding one integer and a list of sentences, unable to say what the integer rested on and free to derive
 * it anyway. These checks pin the opposite: every field the engine wrote reaches the screen, and nothing
 * the engine did not write is invented on the way.
 *
 * The wire text is the current server's own shape, and the second response is the same route from before
 * stage 125. A phone installed today reads both, and the older one has to arrive as «the answer did not
 * say» rather than as «nothing was compared» — the difference between an unknown completeness and a zero
 * the server never claimed.
 */
class CompatibilityContractMappingTest {

    private fun decode(text: String) = befosJson.decodeFromString<CompatibilityDto>(text)

    private val current = """
        {
          "overall": 62, "engine_version": 3,
          "categories": [
            {"category": "values", "label": "Ценности", "score": 88, "weight": 0.25, "has_data": true},
            {"category": "lifestyle", "label": "Уклад", "score": 50, "weight": 0.15, "has_data": false}
          ],
          "strengths": [
            {"category": "values", "label": "Ценности", "text": "Похожее отношение: семья",
             "score": 0.88, "connection": "harmony"}
          ],
          "differences": [
            {"category": "lifestyle", "label": "Уклад", "text": "Разное отношение: ритм сна",
             "score": 0.2, "connection": "discussion"},
            {"category": "personality", "label": "Личность", "text": "Разные, но совместимые темпы",
             "score": 0.6, "connection": "complementarity"}
          ],
          "shared_interests": ["jazz", "walks"],
          "bands_measured": 5, "bands_total": 7, "measured_weight": 0.85,
          "starter": "Начните с общего интереса: «jazz»"
        }
    """.trimIndent()

    @Test
    fun `the engine's own account of the number survives the mapping`() {
        val data = decode(current).toDomain()

        assertEquals(3, data.engineVersion)
        assertEquals(5, data.bandsMeasured)
        assertEquals(7, data.bandsTotal)
        assertEquals(0.85, data.measuredWeight, 1e-9)
        assertEquals("Начните с общего интереса: «jazz»", data.starter)
        // The percent and the bands are the answer's, untouched: no re-summing on the way in.
        assertEquals(62, data.overall)
        assertEquals(listOf("values", "lifestyle"), data.categories.map { it.category })
        assertEquals(listOf(88, 50), data.categories.map { it.score })
        assertEquals(listOf(0.25, 0.15), data.categories.map { it.weight })
        assertEquals(listOf(true, false), data.categories.map { it.hasData })
    }

    @Test
    fun `every line names the kind of difference the engine named`() {
        val data = decode(current).toDomain()

        assertEquals(Connection.HARMONY, data.strengths.single().connection)
        assertEquals(
            listOf(Connection.DISCUSSION, Connection.COMPLEMENTARITY),
            data.differences.map { it.connection },
        )
        // The three kinds are three different values: a screen that could not tell them apart would be
        // printing one word for a meeting and a conversation alike.
        assertEquals(
            3,
            (data.strengths + data.differences).map { it.connection }.toSet().size,
        )
    }

    @Test
    fun `an answer from before the fields carries no completeness rather than a zero`() {
        val data = decode(
            """
                {
                  "overall": 41, "engine_version": 1,
                  "categories": [{"category": "values", "label": "Ценности", "score": 41, "weight": 0.25}],
                  "strengths": [{"category": "values", "label": "Ценности", "text": "Похожее отношение"}],
                  "differences": [], "shared_interests": []
                }
            """.trimIndent(),
        ).toDomain()

        assertNull(data.bandsMeasured)
        assertNull(data.bandsTotal)
        assertNull(data.measuredWeight)
        assertEquals("", data.starter)
        // A missing `connection` is the absence of a kind, not the weakest one the enum happens to hold
        // by position and not by meaning.
        assertEquals(Connection.UNKNOWN, data.strengths.single().connection)
        assertTrue(data.categories.single().hasData)
    }

    @Test
    fun `a kind this build has never seen stays unknown instead of being guessed`() {
        val data = decode(
            """
                {
                  "overall": 50,
                  "categories": [],
                  "strengths": [{"category": "values", "label": "Ценности", "text": "…",
                                 "score": 0.5, "connection": "resonance"}],
                  "differences": []
                }
            """.trimIndent(),
        ).toDomain()

        assertEquals(Connection.UNKNOWN, data.strengths.single().connection)
    }
}
