package app.befos.presentation.universe

import app.befos.data.mapper.toDomain
import app.befos.data.model.UniverseNodeDto
import app.befos.domain.model.Connection
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What a tapped node now owes the pair beyond its own two answers: how firmly it sits in the band
 * that decided its connection, what the pair can do with that, and which questionnaire item measured
 * the axis at all. The server derives all three from the values the node already carries, so the
 * client's job is to read them and to say them without inflating them.
 *
 * The rule these checks hold is the same one stage 75 wrote for percents: an assurance is a distance
 * inside one band, not a probability of a relationship, so the words must stay coarse and must not
 * dress the number up as a chance.
 */
class UniverseNodeDetailTest {

    @Test
    fun `the assurance row is bounded by its own scale`() {
        assertEquals(0, assuranceSteps(0))
        assertEquals(ASSURANCE_STEPS, assuranceSteps(100))
        (0..100).forEach { confidence ->
            val steps = assuranceSteps(confidence)
            assertTrue("$confidence reads $steps", steps in 0..ASSURANCE_STEPS)
        }
    }

    @Test
    fun `an answer nearer its boundary never shows more assurance than one farther from it`() {
        val samples = listOf(0, 10, 25, 26, 50, 75, 99, 100)
        samples.zipWithNext().forEach { (low, high) ->
            assertTrue(
                "$low must not look firmer than $high: ${assuranceSteps(low)} vs ${assuranceSteps(high)}",
                assuranceSteps(low) <= assuranceSteps(high),
            )
        }
        assertNotEquals(assuranceSteps(0), assuranceSteps(100))
    }

    @Test
    fun `a comparison that never happened is not allowed to sound sure of itself`() {
        Connection.entries.filterNot { it == Connection.UNKNOWN }.forEach { kind ->
            assertTrue(
                "$kind at 0 says ${assuranceWord(0, kind)}",
                assuranceWord(0, kind).contains("границе"),
            )
        }
        val word = assuranceWord(0, Connection.UNKNOWN)
        assertTrue(word, word.contains("сравнения не было"))
        assertNotEquals(word, assuranceWord(0, Connection.HARMONY))
        // The scale says the same thing in every band, so its words must not be band-specific:
        // a node at its own far end reads identically whichever connection decided it.
        Connection.entries.filterNot { it == Connection.UNKNOWN }.forEach { kind ->
            assertEquals(assuranceWord(100, Connection.HARMONY), assuranceWord(100, kind))
            assertEquals(assuranceWord(0, Connection.HARMONY), assuranceWord(0, kind))
        }
    }

    @Test
    fun `the assurance sentence names a distance, not a chance`() {
        Connection.entries.forEach { kind ->
            listOf(0, 20, 50, 80, 100).forEach { confidence ->
                val word = assuranceWord(confidence, kind)
                assertTrue("$kind/$confidence prints digits: $word", word.none { it.isDigit() })
                assertTrue("$kind/$confidence quotes a percent: $word", !word.contains('%'))
                assertTrue("empty word for $kind/$confidence", word.isNotBlank())
            }
        }
        assertNotEquals(assuranceWord(20, Connection.HARMONY), assuranceWord(90, Connection.HARMONY))
    }

    @Test
    fun `the three new wire fields reach the node the screen reads`() {
        val json = """
            {"key":"family","label":"Семья","a_value":0.9,"b_value":0.7,"has_data":true,
             "connection":"harmony","evidence":"Семья: 90 против 70, сходство ответов 80",
             "confidence":20,"suggestion":"Семья: у обоих «семья в приоритете».",
             "questions":["Насколько для вас важна семья?"]}
        """.trimIndent()
        val node = Json.decodeFromString<UniverseNodeDto>(json).toDomain()
        assertEquals(20, node.confidence)
        assertEquals("Семья: у обоих «семья в приоритете».", node.suggestion)
        assertEquals(listOf("Насколько для вас важна семья?"), node.questions)
    }

    @Test
    fun `a map from before these fields existed still decodes instead of failing the screen`() {
        // The defaults are not decoration: an older cached document has to keep the map readable.
        val json = """{"key":"family","label":"Семья","has_data":true,"connection":"harmony"}"""
        val node = Json.decodeFromString<UniverseNodeDto>(json).toDomain()
        assertEquals(0, node.confidence)
        assertEquals("", node.suggestion)
        assertTrue(node.questions.isEmpty())
        assertEquals(assuranceWord(0, Connection.HARMONY), assuranceWord(node.confidence, node.connection))
    }
}
