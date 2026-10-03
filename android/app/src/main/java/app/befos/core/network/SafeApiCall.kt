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

/** Product-copy message for a failed response; the English envelope text never reaches the UI. */
suspend fun parseErrorMessage(response: HttpResponse): String {
    val status = response.status.value
    return try {
        val detail = response.body<ErrorEnvelopeDto>().error
        localizeBackendError(detail?.message.orEmpty(), detail?.code.orEmpty(), status)
    } catch (_: Exception) {
        try {
            val text = response.bodyAsText()
            val detail = Regex("\"message\"\\s*:\\s*\"([^\"]+)\"").find(text)?.groupValues?.getOrNull(1).orEmpty()
            val code = Regex("\"code\"\\s*:\\s*\"([^\"]+)\"").find(text)?.groupValues?.getOrNull(1).orEmpty()
            localizeBackendError(detail, code, status)
        } catch (_: Exception) {
            defaultHttpMessage(status)
        }
    }
}

/** Never leak raw exception text (English stack-trace messages) into the UI. */
fun friendlyNetworkMessage(e: Throwable): String = when (e) {
    is java.net.SocketTimeoutException -> "Сервер не отвечает. Попробуйте ещё раз."
    is java.net.UnknownHostException -> "Нет подключения к интернету."
    is java.net.ConnectException -> "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."
    is javax.net.ssl.SSLException -> "Защищённое соединение недоступно. Попробуйте ещё раз."
    is io.ktor.client.plugins.HttpRequestTimeoutException -> "Сервер не отвечает. Попробуйте ещё раз."
    else -> defaultHttpMessage(-1)
}

/** Last resort for an unreadable response: the status family in product words, never a bare HTTP code. */
fun defaultHttpMessage(code: Int): String = when (code) {
    in 500..599 -> "Ошибка сервера. Попробуйте позже."
    429 -> "Слишком много запросов. Подождите немного."
    401 -> "Сессия истекла. Войдите снова."
    403 -> "Нет доступа."
    404 -> "Не найдено."
    in 400..499 -> "Запрос не принят. Попробуйте ещё раз."
    -1 -> "Нет подключения к интернету."
    else -> "Не удалось выполнить запрос. Попробуйте ещё раз."
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
        return ApiResult.Error(-1, friendlyNetworkMessage(e))
    }
    return if (response.status.isSuccess()) {
        try {
            ApiResult.Success(response.body<T>())
        } catch (e: Exception) {
            ApiResult.Error(-2, "Не удалось получить данные. Попробуйте ещё раз.")
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
        return ApiResult.Error(-1, friendlyNetworkMessage(e))
    }
    return if (response.status.isSuccess()) {
        ApiResult.Success(Unit)
    } else {
        ApiResult.Error(response.status.value, parseErrorMessage(response))
    }
}
