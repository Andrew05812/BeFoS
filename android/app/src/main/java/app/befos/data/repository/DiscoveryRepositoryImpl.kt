package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.model.MyLikesDto
import app.befos.data.model.PassedUsersDto
import app.befos.data.remote.ApiService
import app.befos.domain.model.DiscoveryPage
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.LikedMePage
import app.befos.domain.model.OutgoingLikesPage
import app.befos.domain.model.PassedPage
import app.befos.domain.repository.DiscoveryRepository

class DiscoveryRepositoryImpl(private val api: ApiService) : DiscoveryRepository {

    override suspend fun feed(limit: Int, cursor: String?): ApiResult<DiscoveryPage> =
        api.discover(limit, cursor).map { page ->
            DiscoveryPage(
                cards = page.items.map { it.toDomain() },
                nextCursor = page.nextCursor,
                hasMore = page.hasMore,
            )
        }

    override suspend fun likedMe(): ApiResult<LikedMePage> =
        api.likedMe().map { page ->
            LikedMePage(
                likes = page.likes.map { it.toDomain() },
                truncated = page.hasMore,
            )
        }

    override suspend fun like(userId: String): ApiResult<LikeOutcome> =
        api.like(userId).map { LikeOutcome(it.match, it.matchId, it.compatibility) }

    override suspend fun pass(userId: String): ApiResult<Unit> =
        api.pass(userId).map { Unit }

    override suspend fun passed(): ApiResult<PassedPage> =
        api.passedUsers().map { it.toPage() }

    /**
     * The list the screen paints, built from the server's rows rather than from the deck left in
     * memory: a released person is gone from this page because the write said so, and comes back to
     * the deck through its own next refill.
     */
    override suspend fun unpass(userId: String): ApiResult<PassedPage> =
        api.unpass(userId).map { it.toPage() }

    private fun PassedUsersDto.toPage() = PassedPage(
        passed = passed.map { it.toDomain() },
        truncated = hasMore,
    )

    /**
     * The account's own taps, and the list that stands after one of them is taken back. Both answers
     * are built the same way: rows the server holds, never the rows this screen happened to remember.
     */
    override suspend fun liked(): ApiResult<OutgoingLikesPage> =
        api.likedUsers().map { it.toPage() }

    override suspend fun unlike(userId: String): ApiResult<OutgoingLikesPage> =
        api.unlike(userId).map { it.toPage() }

    private fun MyLikesDto.toPage() = OutgoingLikesPage(
        likes = likes.map { it.toDomain() },
        truncated = hasMore,
    )
}
