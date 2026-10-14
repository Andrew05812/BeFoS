package app.befos.core.share

import android.content.Context
import android.content.Intent

/**
 * Hands a finished piece of text to whatever app the user picks.
 *
 * The app has no second delivery channel of its own — no push, no e-mail, no link preview — so this
 * is the whole of "share": the caller passes the exact text the artefact should be, and nothing here
 * adds to it. That matters for the pair's story, which is shareable precisely because it carries no
 * individual answers: composing the text somewhere else would be a second place a leak could appear.
 */
fun shareText(context: Context, chooserTitle: String, text: String) {
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, text)
    }
    // The composing context here is the screen's activity; a bare application context would need
    // FLAG_ACTIVITY_NEW_TASK and would lose the window the chooser should attach to.
    context.startActivity(Intent.createChooser(send, chooserTitle))
}
