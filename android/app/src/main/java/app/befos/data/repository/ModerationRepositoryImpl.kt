package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.remote.ApiService
import app.befos.domain.model.ReportDetail
import app.befos.domain.model.ReportsPage
import app.befos.domain.model.ReviewOutcome
import app.befos.domain.repository.ModerationRepository

class ModerationRepositoryImpl(private val api: ApiService) : ModerationRepository {

    /**
     * Half of the server's own bound (`MAX_PAGE = 100`). The screen asks for one page at a time and
     * follows the cursor the answer returns, so a bigger page would only move the wait from the tap
     * to the first screen; a smaller one made the operator walk the queue a complaint at a time.
     */
    private companion object {
        private const val PageLimit = 50
    }

    override suspend fun page(status: String?, afterId: String?): ApiResult<ReportsPage> =
        api.reports(status, afterId, PageLimit).map { dto -> dto.toDomain() }

    override suspend fun detail(reportId: String): ApiResult<ReportDetail> =
        api.reportDetail(reportId).map { dto -> dto.toDomain() }

    override suspend fun review(
        reportId: String,
        status: String,
        comment: String?
    ): ApiResult<ReviewOutcome> =
        api.reviewReport(reportId, status, comment).map { dto -> dto.toDomain() }
}
