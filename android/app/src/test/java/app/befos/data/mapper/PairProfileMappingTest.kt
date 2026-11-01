package app.befos.data.mapper

import app.befos.core.network.befosJson
import app.befos.data.model.PairProfileDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The pair's own reading, from the wire into the domain.
 *
 * `GET /matches/{id}/profile` answers one document with the two people, the whole compatibility file and
 * whatever the pair has agreed — and every one of those parts has a rule the mapping has to keep. The two
 * people stay in the pair's own order, because both halves are answered in that order and a screen that
 * sorted them would name one pair two different ways. The nearest plan stays nullable, because a pair with
 * nothing standing on an hour is a pair, not an empty plan. And the moments stay text, because they belong
 * to the server's clock and the screen that shows them is where a day gets made of one.
 */
class PairProfileMappingTest {

    private fun decode(text: String) = befosJson.decodeFromString<PairProfileDto>(text)

    private val compat = """
        "compatibility": {
          "overall": 62, "engine_version": 1,
          "categories": [{"category": "values", "label": "Ценности", "score": 88, "weight": 0.25}],
          "strengths": [{"category": "values", "label": "Ценности", "text": "Похожее отношение",
                         "score": 0.88, "connection": "harmony"}],
          "differences": [], "shared_interests": ["jazz"],
          "bands_measured": 5, "bands_total": 7, "measured_weight": 0.85,
          "starter": "Начните с общего интереса: «jazz»"
        }
    """.trimIndent()

    @Test
    fun `the two people arrive in the pair's own order and the document stays whole`() {
        val profile = decode(
            """
            {
              "match_id": "m1",
              "since": "2026-04-18T20:15:00+03:00",
              "people": [{"user_id": "u1", "name": "Аня"}, {"user_id": "u2", "name": "Боря"}],
              $compat,
              "plans_total": 2,
              "plan": {"plan_id": "p7", "status": "planned", "starts_at": "2026-10-17T19:00:00+03:00"}
            }
            """.trimIndent(),
        ).toDomain()

        assertEquals("m1", profile.matchId)
        assertEquals(listOf("u1", "u2"), profile.people.map { it.userId })
        assertEquals(listOf("Аня", "Боря"), profile.people.map { it.name })
        // The day the pair formed is the server's text, kept as text: nothing here moves it to a zone.
        assertEquals("2026-04-18T20:15:00+03:00", profile.since)
        assertEquals(2, profile.plansTotal)
        assertEquals("p7", profile.plan?.planId)
        assertEquals("planned", profile.plan?.status)
        assertEquals("2026-10-17T19:00:00+03:00", profile.plan?.startsAt)

        // The digest inside this answer is the same contract the pair page reads, with the same fields on it.
        val compatibility = profile.compatibility
        assertEquals(62, compatibility.overall)
        assertEquals(1, compatibility.engineVersion)
        assertEquals(5, compatibility.bandsMeasured)
        assertEquals(7, compatibility.bandsTotal)
        assertEquals(0.85, compatibility.measuredWeight!!, 1e-9)
        assertEquals("Начните с общего интереса: «jazz»", compatibility.starter)
        assertEquals(listOf("jazz"), compatibility.sharedInterests)
    }

    @Test
    fun `a pair with nothing agreed to an hour answers no plan at all`() {
        val profile = decode(
            """
            {
              "match_id": "m1",
              "since": "2026-04-18T20:15:00+03:00",
              "people": [{"user_id": "u1", "name": "Аня"}, {"user_id": "u2", "name": "Боря"}],
              $compat,
              "plans_total": 1
            }
            """.trimIndent(),
        ).toDomain()

        // Null, not an empty plan: «идея предложена, но часа нет» is a fact about the pair, and a
        // placeholder row would let the screen print an hour nobody agreed to.
        assertNull(profile.plan)
        assertEquals(1, profile.plansTotal)
    }
}
