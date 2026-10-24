package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.befosJson
import app.befos.data.mapper.toDomain
import app.befos.data.model.PlanDetailDto
import app.befos.data.remote.ApiService
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The plan and its chronology arrive in one answer, and the history page is built entirely out of it.
 *
 * `GET /plans/{id}` carries the arrangement's own row and the journal lines the pair's conversation
 * holds about it, which is what lets the client open a history for the same cost as opening the plan —
 * and what means the chronology can never have been read while the arrangement stood somewhere else.
 * Three shapes are worth pinning on the way in: the answer as the current server writes it, the same
 * answer from a server that attached no journal, and a line carrying a key this build has never seen.
 * The last two are the pair's own history on either side of a release, and neither may cost the person
 * the record they came to read.
 */
class PlanDetailReadTest {

    // Read with the client's own parser rather than a fresh one: the settings that let an unknown key
    // pass are the product's, and a test that relaxed them locally would prove nothing about the wire.
    private fun decode(text: String) = befosJson.decodeFromString<PlanDetailDto>(text)

    private val full = """
        {
          "plan": {"id": "p1", "title": "Поход в кино", "status": "planned",
                   "starts_at": "2026-10-17T19:00:00+03:00", "can_cancel": true,
                   "partner_id": "u2", "partner_name": "Анна"},
          "events": [
            {"id": "l1", "match_id": "m1", "sender_id": "u1", "body": "Идея предложена",
             "created_at": "2026-10-15T10:00:00+03:00", "is_own": true, "kind": "plan_proposed",
             "plan": {"activity_id": 7, "when": "2026-10-17T19:00:00+03:00",
                      "plan_id": "p1", "is_latest": false}},
            {"id": "l2", "match_id": "m1", "sender_id": "u2", "body": "Час перенесён: 17 октября, 19:00 → 18 октября, 20:00",
             "created_at": "2026-10-16T09:00:00+03:00", "is_own": false, "kind": "plan_rescheduled",
             "plan": {"activity_id": 7, "when": "2026-10-18T20:00:00+03:00",
                      "plan_id": "p1", "is_latest": true}}
          ]
        }
    """.trimIndent()

    @Test
    fun `one answer carries the plan and its chronology in the order the pair lived it`() {
        val dto = decode(full)
        val lines = dto.events.map { it.toDomain() }

        assertEquals("p1", dto.plan.id)
        assertEquals(listOf("l1", "l2"), lines.map { it.id })
        assertEquals(listOf("plan_proposed", "plan_rescheduled"), lines.map { it.kind })
        // Whose tap wrote the line is the answer's own, not something the client infers from the
        // session: the record belongs to the pair and each of them reads it from their side.
        assertEquals(listOf(true, false), lines.map { it.isOwn })
        assertEquals("Час перенесён: 17 октября, 19:00 → 18 октября, 20:00", lines[1].body)
        assertEquals(listOf(false, true), lines.map { it.plan?.isLatest })
    }

    @Test
    fun `an answer from a server that attaches no journal still reads its plan`() {
        // The key arrived with the history screen; a build that reads an older deployment has to get
        // the arrangement it asked for and an empty record, not a parse failure it cannot show.
        val dto = decode("""{"plan": {"id": "p1", "status": "planned"}}""")

        assertEquals("p1", dto.plan.id)
        assertTrue(dto.events.isEmpty())
    }

    @Test
    fun `a line carrying a key this build has never seen keeps every fact it holds`() {
        // The server grows its journal before the client does — that is the order a pair living across
        // a release sees. Dropping such a line would erase a move from the record the page exists for.
        val dto = decode(
            """
            {"plan": {"id": "p1"},
             "events": [{"id": "l3", "match_id": "m1", "sender_id": "u2", "body": "Пара назвала место",
                         "kind": "plan_changed", "plan_from": "Парк", "plan_to": "Кофейня",
                         "plan": {"activity_id": 7, "is_latest": true}}]}
            """.trimIndent(),
        )
        val line = dto.events.single().toDomain()

        assertEquals("Пара назвала место", line.body)
        assertEquals("plan_changed", line.kind)
        assertTrue(line.plan!!.isLatest)
        // A field the wire does not carry stays unknown rather than becoming an invented one.
        assertNull(line.plan?.whenIso)
        assertFalse(line.isOwn)
    }

    @Test
    fun `opening a history costs the one read the plan already answers`() = runTest {
        val api = mockk<ApiService> {
            coEvery { getPlan("p1") } returns ApiResult.Success(decode(full))
        }

        val result = PlanRepositoryImpl(api).history("p1")

        // The chronology is attached to the arrangement's own row, so the page asks once: a second
        // request to the thread could only read it while the plan stood somewhere else.
        assertTrue(result is ApiResult.Success)
        assertEquals(listOf("l1", "l2"), (result as ApiResult.Success).data.lines.map { it.id })
        coVerify(exactly = 1) { api.getPlan("p1") }
    }

    @Test
    fun `the same answer hands the page its own word without a second request`() = runTest {
        val withNote = befosJson.decodeFromString<PlanDetailDto>(
            full.replace("\"events\": [", "\"my_note\": \"взять билеты\", \"events\": [")
        )
        val api = mockk<ApiService> {
            coEvery { getPlan("p1") } returns ApiResult.Success(withNote)
        }

        val result = PlanRepositoryImpl(api).history("p1")

        // The remark travels in the answer that already carries the record: the page reaches its own
        // word for the price of the chronology, and cannot show a journal the word lagged behind.
        assertEquals("взять билеты", (result as ApiResult.Success).data.myNote)
        assertEquals(listOf("l1", "l2"), result.data.lines.map { it.id })
        coVerify(exactly = 1) { api.getPlan("p1") }
    }

    @Test
    fun `a refused read reaches the page as the server's own reason, not as an empty record`() = runTest {
        val api = mockk<ApiService> {
            coEvery { getPlan("p7") } returns ApiResult.Error(403, "План принадлежит другой паре.")
        }

        val result = PlanRepositoryImpl(api).history("p7")

        // A plan this person cannot reach answers with its own sentence; turning that into an empty
        // list would show «истории нет» about a record the pair has and this visitor does not.
        assertTrue(result is ApiResult.Error)
        assertEquals("План принадлежит другой паре.", (result as ApiResult.Error).message)
    }
}
