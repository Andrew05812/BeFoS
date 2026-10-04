package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.remote.ApiService
import app.befos.domain.model.DiscoveryPage
import app.befos.domain.model.LikeOutcome
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

    override suspend fun like(userId: String): ApiResult<LikeOutcome> =
        api.like(userId).map { LikeOutcome(it.match, it.matchId, it.compatibility) }

    override suspend fun pass(userId: String): ApiResult<Unit> =
        api.pass(userId).map { Unit }
}
