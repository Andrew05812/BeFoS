package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.remote.ApiService
import app.befos.domain.model.Message
import app.befos.domain.model.Plan
import app.befos.domain.repository.PlanRepository

class PlanRepositoryImpl(private val api: ApiService) : PlanRepository {

    override suspend fun plans(matchId: String): ApiResult<List<Plan>> =
        api.getMatchPlans(matchId).map { dto -> dto.plans.map { it.toDomain() } }

    override suspend fun plan(planId: String): ApiResult<Plan> =
        api.getPlan(planId).map { dto -> dto.plan.toDomain() }

    // One read answers both questions: the server attaches the plan's journal lines to its own row,
    // so opening a history costs the same request as opening the plan and cannot show a chronology
    // that was read while the arrangement was somewhere else.
    override suspend fun history(planId: String): ApiResult<List<Message>> =
        api.getPlan(planId).map { dto -> dto.events.map { it.toDomain() } }

    override suspend fun accept(planId: String): ApiResult<Unit> = api.acceptPlan(planId)

    override suspend fun decline(planId: String): ApiResult<Unit> = api.declinePlan(planId)

    override suspend fun restoreDecline(planId: String): ApiResult<Unit> = api.restorePlanDecline(planId)

    override suspend fun offerHour(planId: String, whenIso: String): ApiResult<Unit> =
        api.offerPlanHour(planId, whenIso)

    override suspend fun confirmHour(planId: String, whenIso: String): ApiResult<Unit> =
        api.confirmPlanHour(planId, whenIso)

    override suspend fun editWords(
        planId: String,
        place: String?,
        note: String?,
        clearPlace: Boolean,
        clearNote: Boolean,
    ): ApiResult<Unit> = api.editPlanWords(planId, place, note, clearPlace, clearNote)

    override suspend fun cancel(planId: String): ApiResult<Unit> = api.cancelPlan(planId)

    override suspend fun restore(planId: String): ApiResult<Unit> = api.restorePlan(planId)

    override suspend fun markAttended(planId: String): ApiResult<Unit> = api.markPlanAttended(planId)

    override suspend fun undoAttended(planId: String): ApiResult<Unit> = api.undoPlanAttended(planId)
}
