package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.map
import app.befos.data.model.InviteDto
import app.befos.data.model.InvitesDto
import app.befos.data.model.WaitlistStatusDto
import app.befos.data.remote.ApiService
import app.befos.domain.model.Invite
import app.befos.domain.model.InviteList
import app.befos.domain.model.InvitePreview
import app.befos.domain.model.WaitlistStatus
import app.befos.domain.repository.ReferralRepository

/**
 * The thin wire between the personal-door screens and the server.
 *
 * Nothing here decides whether a link is live: `status` comes off the row every time the list is
 * read, because a code that was active when the screen opened can be spent by somebody else a
 * second later, and a client that cached «active» would keep offering a door that is already
 * closed. The same rule for the waiting mark — its city is the server's copy, not the profile
 * field the screen happens to hold.
 */
class ReferralRepositoryImpl(private val api: ApiService) : ReferralRepository {

    override suspend fun invites(): ApiResult<InviteList> =
        api.myInvites().map { dto ->
            InviteList(
                invites = dto.invites.map { it.toDomain() },
                acceptedTotal = dto.acceptedTotal,
            )
        }

    override suspend fun createInvite(): ApiResult<Invite> =
        api.createInvite().map { it.toDomain() }

    override suspend fun revokeInvite(invitationId: String): ApiResult<Unit> =
        api.revokeInvite(invitationId)

    override suspend fun previewInvite(code: String): ApiResult<InvitePreview> =
        api.previewInvite(code).map { InvitePreview(valid = it.valid, expiresAt = it.expiresAt) }

    override suspend fun waitlist(): ApiResult<WaitlistStatus> =
        api.waitlist().map { it.toDomain() }

    override suspend fun joinWaitlist(city: String?): ApiResult<WaitlistStatus> =
        api.joinWaitlist(city).map { it.toDomain() }

    override suspend fun leaveWaitlist(): ApiResult<Unit> = api.leaveWaitlist()

    private fun InviteDto.toDomain() = Invite(
        id = id,
        code = code,
        url = url,
        status = status,
        expiresAt = expiresAt,
        acceptedAt = acceptedAt,
        createdAt = createdAt,
    )

    private fun WaitlistStatusDto.toDomain() = WaitlistStatus(joined = joined, city = city)
}
