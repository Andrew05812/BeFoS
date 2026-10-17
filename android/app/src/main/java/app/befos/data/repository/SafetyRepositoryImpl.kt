package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.remote.ApiService
import app.befos.domain.model.BlockedUser
import app.befos.domain.repository.SafetyRepository

class SafetyRepositoryImpl(private val api: ApiService) : SafetyRepository {

    override suspend fun block(userId: String): ApiResult<Unit> = api.block(userId)

    override suspend fun unblock(userId: String): ApiResult<List<BlockedUser>> =
        api.unblock(userId).map { dto -> dto.blocked.map { it.toDomain() } }

    override suspend fun blockedUsers(): ApiResult<List<BlockedUser>> =
        api.blockedUsers().map { dto -> dto.blocked.map { it.toDomain() } }

    override suspend fun report(userId: String, reason: String, details: String?): ApiResult<Unit> =
        api.report(userId, reason, details)

    override suspend fun setVisibility(hidden: Boolean): ApiResult<Unit> = api.setVisibility(hidden)

    override suspend fun deleteAccount(): ApiResult<Unit> = api.deleteAccount()
}
