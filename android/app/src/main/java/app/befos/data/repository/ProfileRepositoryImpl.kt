package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.mapper.toRequest
import app.befos.data.remote.ApiService
import app.befos.domain.model.Interest
import app.befos.domain.model.OnboardingData
import app.befos.domain.model.Profile
import app.befos.domain.model.ProfileUpdateData
import app.befos.domain.model.PublicProfile
import app.befos.domain.repository.ProfileRepository
import java.io.InputStream

class ProfileRepositoryImpl(private val api: ApiService) : ProfileRepository {

    override suspend fun me(): ApiResult<Profile> = api.getMe().map { it.toDomain() }

    override suspend fun onboarding(data: OnboardingData): ApiResult<Profile> =
        api.completeOnboarding(data.toRequest()).map { it.toDomain() }

    override suspend fun update(data: ProfileUpdateData): ApiResult<Profile> =
        api.updateProfile(data.toRequest()).map { it.toDomain() }

    override suspend fun uploadPhoto(input: InputStream, contentType: String): ApiResult<Profile> =
        api.uploadPhoto(input, contentType).map { it.toDomain() }

    override suspend fun interests(): ApiResult<List<Interest>> =
        api.getInterests().map { dto -> dto.interests.map { it.toDomain() } }

    override suspend fun publicProfile(userId: String): ApiResult<PublicProfile> =
        api.getPublicProfile(userId).map { it.toDomain() }
}
