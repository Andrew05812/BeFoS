package app.befos.data.remote

import app.befos.core.network.ApiConfig
import app.befos.core.network.ApiResult
import app.befos.core.network.apiCall
import app.befos.core.network.apiCallUnit
import app.befos.data.model.AnswersRequest
import app.befos.data.model.AuthResponseDto
import app.befos.data.model.CompatibilityDto
import app.befos.data.model.DiscoveryCardDto
import app.befos.data.model.InterestListDto
import app.befos.data.model.LikeResponseDto
import app.befos.data.model.LoginRequest
import app.befos.data.model.MatchDetailDto
import app.befos.data.model.MatchListDto
import app.befos.data.model.MessageDto
import app.befos.data.model.MessagePageDto
import app.befos.data.model.MessageRequest
import app.befos.data.model.OnboardingRequest
import app.befos.data.model.PaginatedDto
import app.befos.data.model.PassResponseDto
import app.befos.data.model.ProfileDto
import app.befos.data.model.ProfileUpdateRequest
import app.befos.data.model.ProgressDto
import app.befos.data.model.PublicProfileDto
import app.befos.data.model.RecommendationListDto
import app.befos.data.model.RefreshRequest
import app.befos.data.model.RegisterRequest
import app.befos.data.model.ReportRequest
import app.befos.data.model.TestListDto
import app.befos.data.model.TestResultDto
import app.befos.data.model.TokenPairDto
import app.befos.data.model.VisibilityRequest
import io.ktor.client.HttpClient
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.parameter
import io.ktor.client.request.setBody
import io.ktor.client.request.url
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import java.io.InputStream

/**
 * Thin typed wrapper over every backend REST endpoint. Each call returns an
 * [ApiResult] so callers never deal with raw HTTP exceptions.
 */
class ApiService(private val client: HttpClient) {

    private fun endpoint(path: String): String = "${ApiConfig.BASE_URL}${ApiConfig.API_PREFIX}/$path"

    // ---------- Auth ----------
    suspend fun register(email: String, password: String): ApiResult<AuthResponseDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("auth/register"))
            setBody(RegisterRequest(email, password, password))
        }

    suspend fun login(email: String, password: String): ApiResult<AuthResponseDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("auth/login"))
            setBody(LoginRequest(email, password))
        }

    suspend fun refresh(refreshToken: String): ApiResult<TokenPairDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("auth/refresh"))
            setBody(RefreshRequest(refreshToken))
        }

    suspend fun logout(refreshToken: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("auth/logout"))
            setBody(RefreshRequest(refreshToken))
        }

    // ---------- Users / Profile ----------
    suspend fun getMe(): ApiResult<ProfileDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("users/me"))
        }

    suspend fun completeOnboarding(request: OnboardingRequest): ApiResult<ProfileDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("users/me/onboarding"))
            setBody(request)
        }

    suspend fun updateProfile(request: ProfileUpdateRequest): ApiResult<ProfileDto> =
        client.apiCall {
            method = HttpMethod.Patch
            url(endpoint("users/me"))
            setBody(request)
        }

    suspend fun getInterests(): ApiResult<InterestListDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("users/interests"))
        }

    suspend fun getPublicProfile(userId: String): ApiResult<PublicProfileDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("users/$userId"))
        }

    suspend fun uploadPhoto(input: InputStream, contentType: String): ApiResult<ProfileDto> {
        val bytes = input.use { it.readBytes() }
        val multipart = MultiPartFormDataContent(
            formData {
                append(
                    "file",
                    bytes,
                    Headers.build {
                        append(HttpHeaders.ContentType, contentType)
                        append(HttpHeaders.ContentDisposition, "filename=\"photo.jpg\"")
                    },
                )
            },
        )
        return client.apiCall {
            method = HttpMethod.Post
            url(endpoint("users/me/photo"))
            setBody(multipart)
        }
    }

    // ---------- Tests ----------
    suspend fun getTests(): ApiResult<TestListDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("tests"))
        }

    suspend fun getProgress(): ApiResult<ProgressDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("tests/progress"))
        }

    suspend fun submitAnswers(request: AnswersRequest): ApiResult<ProgressDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("tests/answers"))
            setBody(request)
        }

    suspend fun completeTest(): ApiResult<TestResultDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("tests/complete"))
        }

    // ---------- Discovery ----------
    suspend fun discover(limit: Int = 20, offset: Int = 0): ApiResult<PaginatedDto<DiscoveryCardDto>> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("discover"))
            parameter("limit", limit)
            parameter("offset", offset)
        }

    suspend fun like(userId: String): ApiResult<LikeResponseDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("users/$userId/like"))
        }

    suspend fun pass(userId: String): ApiResult<PassResponseDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("users/$userId/pass"))
        }

    // ---------- Matches ----------
    suspend fun getMatches(): ApiResult<MatchListDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches"))
        }

    suspend fun getMatch(matchId: String): ApiResult<MatchDetailDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId"))
        }

    suspend fun getCompatibility(matchId: String): ApiResult<CompatibilityDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId/compatibility"))
        }

    suspend fun getRecommendations(matchId: String, force: Boolean = false): ApiResult<RecommendationListDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId/recommendations"))
            parameter("force", force)
        }

    suspend fun selectRecommendation(matchId: String, activityId: Int): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("matches/$matchId/recommendations/$activityId/select"))
        }

    // ---------- Chat ----------
    suspend fun getMessages(matchId: String, limit: Int = 50, beforeId: String? = null): ApiResult<MessagePageDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId/messages"))
            parameter("limit", limit)
            if (beforeId != null) parameter("before_id", beforeId)
        }

    suspend fun sendMessage(matchId: String, body: String): ApiResult<MessageDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("matches/$matchId/messages"))
            setBody(MessageRequest(body))
        }

    suspend fun markRead(matchId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("matches/$matchId/read"))
        }

    // ---------- Safety ----------
    suspend fun block(userId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("users/$userId/block"))
        }

    suspend fun report(userId: String, reason: String, details: String?): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("users/$userId/report"))
            setBody(ReportRequest(reason, details))
        }

    suspend fun setVisibility(hidden: Boolean): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("users/me/visibility"))
            setBody(VisibilityRequest(hidden))
        }

    suspend fun deleteAccount(): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Delete
            url(endpoint("users/me"))
        }
}
