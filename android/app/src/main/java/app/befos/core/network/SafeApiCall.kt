package app.befos.core.network

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.request
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable

sealed interface ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>
    data class Error(val code: Int, val message: String) : ApiResult<Nothing>
}

inline fun <T, R> ApiResult<T>.map(transform: (T) -> R): ApiResult<R> = when (this) {
    is ApiResult.Success -> ApiResult.Success(transform(data))
    is ApiResult.Error -> this
}

inline fun <T> ApiResult<T>.onSuccess(action: (T) -> Unit): ApiResult<T> {
    if (this is ApiResult.Success) action(data)
    return this
}

fun <T> ApiResult<T>.getOrNull(): T? = (this as? ApiResult.Success)?.data

@Serializable
private data class ErrorDetailDto(
    val code: String = "",
    val message: String = "",
)

@Serializable
private data class ErrorEnvelopeDto(
    val error: ErrorDetailDto? = null,
)

/** Human-readable message for a failed response, preferring the backend's error envelope. */
suspend fun parseErrorMessage(response: HttpResponse): String {
    return try {
        val envelope = response.body<ErrorEnvelopeDto>()
        envelope.error?.message?.takeIf { it.isNotBlank() } ?: defaultHttpMessage(response.status.value)
    } catch (_: Exception) {
        try {
            response.bodyAsText().take(160).ifBlank { defaultHttpMessage(response.status.value) }
        } catch (_: Exception) {
            defaultHttpMessage(response.status.value)
        }
    }
}

fun defaultHttpMessage(code: Int): String = when (code) {
    in 500..599 -> "Ошибка сервера. Попробуйте позже."
    429 -> "Слишком много запросов. Подождите немного."
    401 -> "Сессия истекла. Войдите снова."
    403 -> "Нет доступа."
    404 -> "Не найдено."
    -1 -> "Нет подключения к интернету."
    else -> "Не удалось выполнить запрос (код $code)."
}

/**
 * Executes a request and maps the outcome to [ApiResult]. Network failures and
 * non-2xx responses never throw to the caller; they become [ApiResult.Error].
 */
suspend inline fun <reified T> HttpClient.apiCall(
    crossinline block: HttpRequestBuilder.() -> Unit,
): ApiResult<T> {
    val response: HttpResponse = try {
        request(block)
    } catch (e: Exception) {
        return ApiResult.Error(-1, e.message ?: defaultHttpMessage(-1))
    }
    return if (response.status.isSuccess()) {
        try {
            ApiResult.Success(response.body<T>())
        } catch (e: Exception) {
            ApiResult.Error(-2, "Не удалось разобрать ответ: ${e.message}")
        }
    } else {
        ApiResult.Error(response.status.value, parseErrorMessage(response))
    }
}

/** Variant for endpoints that return no meaningful body (204 / empty). */
suspend inline fun HttpClient.apiCallUnit(
    crossinline block: HttpRequestBuilder.() -> Unit,
): ApiResult<Unit> {
    val response: HttpResponse = try {
        request(block)
    } catch (e: Exception) {
        return ApiResult.Error(-1, e.message ?: defaultHttpMessage(-1))
    }
    return if (response.status.isSuccess()) {
        ApiResult.Success(Unit)
    } else {
        ApiResult.Error(response.status.value, parseErrorMessage(response))
    }
}
