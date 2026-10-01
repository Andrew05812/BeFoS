package app.befos.core.common

sealed interface UiState<out T> {
    data object Loading : UiState<Nothing>
    data class Success<T>(val data: T) : UiState<T>
    data class Error(val message: String) : UiState<Nothing>
}

fun <T> UiState<T>.dataOrNull(): T? = (this as? UiState.Success)?.data

inline fun <T, R> UiState<T>.mapSuccess(transform: (T) -> R): UiState<R> = when (this) {
    is UiState.Success -> UiState.Success(transform(data))
    is UiState.Error -> this
    UiState.Loading -> UiState.Loading
}
