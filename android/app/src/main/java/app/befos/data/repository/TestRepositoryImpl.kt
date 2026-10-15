package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.model.AnswerDto
import app.befos.data.model.AnswersRequest
import app.befos.data.remote.ApiService
import app.befos.domain.model.TestCatalog
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.TestRepository

class TestRepositoryImpl(private val api: ApiService) : TestRepository {

    override suspend fun catalog(): ApiResult<TestCatalog> =
        api.getTests().map { dto ->
            TestCatalog(
                questions = dto.questions.map { it.toDomain() },
                categories = dto.categories.map { it.toDomain() },
            )
        }

    override suspend fun progress(): ApiResult<TestProgress> =
        api.getProgress().map { it.toDomain() }

    override suspend fun submitAnswers(answers: Map<Int, Int>): ApiResult<TestProgress> {
        val request = AnswersRequest(answers.map { AnswerDto(it.key, it.value) })
        return api.submitAnswers(request).map { it.toDomain() }
    }

    override suspend fun complete(): ApiResult<TestProfile> =
        api.completeTest().map { it.toDomain() }

    override suspend fun profile(): ApiResult<TestProfile> =
        api.getProfile().map { it.toDomain() }
}
