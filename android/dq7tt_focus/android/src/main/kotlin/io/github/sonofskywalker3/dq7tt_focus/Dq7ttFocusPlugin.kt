package io.github.sonofskywalker3.dq7tt_focus

import android.app.Activity
import android.os.Build
import android.view.View
import android.view.ViewGroup
import android.view.ViewTreeObserver
import io.flutter.embedding.android.FlutterView
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding

/**
 * Gives the Flutter view Android's input focus as soon as it is laid out.
 *
 * Until a view has focus, Android uses the first D-pad or A press just to give it focus,
 * and keys such as L1, R1 or B pressed before that never reach the app. Android also draws
 * a thin frame round a view that takes focus from a key; the app draws its own focus, so
 * that frame is turned off.
 */
class Dq7ttFocusPlugin : FlutterPlugin, ActivityAware {
    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {}

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {}

    override fun onAttachedToActivity(binding: ActivityPluginBinding) = watch(binding.activity)

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) =
        watch(binding.activity)

    override fun onDetachedFromActivityForConfigChanges() {}

    override fun onDetachedFromActivity() {}

    private fun watch(activity: Activity) {
        val root = activity.window.decorView
        noFrame(root)
        // The Flutter view is added after the plugin is attached: take it on the first
        // layout that has it, and again whenever the window gets focus back.
        val observer = root.viewTreeObserver
        observer.addOnGlobalLayoutListener(object : ViewTreeObserver.OnGlobalLayoutListener {
            override fun onGlobalLayout() {
                if (focus(root) && root.viewTreeObserver.isAlive) {
                    root.viewTreeObserver.removeOnGlobalLayoutListener(this)
                }
            }
        })
        observer.addOnWindowFocusChangeListener { hasFocus -> if (hasFocus) focus(root) }
    }

    private fun focus(root: View): Boolean {
        val flutter = find(root) ?: return false
        var view: View? = flutter
        while (view != null) {
            noFrame(view)
            view = view.parent as? View
        }
        flutter.isFocusable = true
        flutter.isFocusableInTouchMode = true
        if (!flutter.hasFocus()) {
            flutter.requestFocus()
        }
        return true
    }

    private fun noFrame(view: View) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            view.defaultFocusHighlightEnabled = false
        }
    }

    private fun find(view: View): FlutterView? {
        if (view is FlutterView) return view
        if (view is ViewGroup) {
            for (i in 0 until view.childCount) {
                find(view.getChildAt(i))?.let { return it }
            }
        }
        return null
    }
}
