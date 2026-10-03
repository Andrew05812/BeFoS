package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.remote.ApiService
import app.befos.domain.model.Compatibility
import app.befos.domain.model.MatchSummary
import app.befos.domain.model.PublicProfile
import app.befos.domain.model.Recommendation
import app.befos.domain.repository.MatchRepository

class MatchRepositoryImpl(private val api: ApiService) : MatchRepository {

    override suspend fun matches(): ApiResult<List<MatchSummary>> =
        api.getMatches().map { dto -> dto.matches.map { it.toDomain() } }

    override suspend fun partner(matchId: String): ApiResult<PublicProfile> =
        api.getMatch(matchId).map { it.otherUser.toDomain() }

    override suspend fun compatibility(matchId: String): ApiResult<Compatibility> =
        api.getCompatibility(matchId).map { it.toDomain() }

    override suspend fun recommendations(matchId: String): ApiResult<List<Recommendation>> =
        api.getRecommendations(matchId).map { dto -> dto.recommendations.map { it.toDomain() } }

    override suspend fun selectRecommendation(matchId: String, activityId: Int): ApiResult<Unit> =
        api.selectRecommendation(matchId, activityId)
}
