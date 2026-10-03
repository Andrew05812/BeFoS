package app.befos.data.repository

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The reconnect schedule a dropped chat socket follows. Guarded because a fixed short
 * delay against a backend that is down for minutes turns into one dial per match, per
 * two seconds, for the whole outage — and because a schedule that only grows can never
 * bring a recovered backend back quickly.
 */
class ChatSocketBackoffTest {

    @Test
    fun `a socket that just dropped reconnects immediately`() {
        assertEquals(2_000L, reconnectBackoffMs(0))
    }

    @Test
    fun `a backend that keeps refusing costs progressively fewer dials`() {
        val waits = (1..6).map(::reconnectBackoffMs)
        assertTrue("waits must grow: $waits", waits.zipWithNext().all { (a, b) -> b >= a })
        assertEquals(4_000L, waits.first())
    }

    @Test
    fun `the wait is capped so a recovered backend is noticed within half a minute`() {
        assertTrue((0..200).all { reconnectBackoffMs(it) <= 30_000L })
        assertEquals(30_000L, reconnectBackoffMs(200))
    }
}
