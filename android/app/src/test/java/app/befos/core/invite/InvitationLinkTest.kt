package app.befos.core.invite

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class InvitationLinkTest {

    @Test
    fun `a personal door carries its code as the only segment`() {
        assertEquals("AbC123_-xyz", InvitationLink.code("befos://invite/AbC123_-xyz"))
        assertEquals("AbC123_-xyz", InvitationLink.code("  BEFOS://INVITE/AbC123_-xyz  "))
    }

    @Test
    fun `another scheme or host is not this app's door`() {
        assertNull(InvitationLink.code("https://befos.example/invite/code1"))
        assertNull(InvitationLink.code("befos://other/code1"))
        assertNull(InvitationLink.code("bant://invite/code1"))
    }

    @Test
    fun `an empty or nested path is not a code`() {
        assertNull(InvitationLink.code("befos://invite"))
        assertNull(InvitationLink.code("befos://invite/"))
        assertNull(InvitationLink.code("befos://invite/a/b"))
        assertNull(InvitationLink.code(null))
        assertNull(InvitationLink.code(""))
    }

    @Test
    fun `a query or fragment cannot smuggle a second value into the register body`() {
        assertEquals("code1", InvitationLink.code("befos://invite/code1?email=someone@example.com"))
        assertEquals("code2", InvitationLink.code("befos://invite/code2#note"))
    }

    @Test
    fun `a path longer than the server's column is refused before it reaches the body`() {
        assertNull(InvitationLink.code("befos://invite/" + "a".repeat(33)))
    }
}
