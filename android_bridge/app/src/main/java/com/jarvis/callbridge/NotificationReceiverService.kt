package com.jarvis.callbridge

import android.content.Intent
import android.net.Uri
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import android.app.Notification

class NotificationReceiverService : NotificationListenerService() {
    private val TAG = "JarvisCallBridge"

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val packageName = sbn.packageName
        val extras = sbn.notification.extras
        val title = extras.getString(Notification.EXTRA_TITLE) ?: ""
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""

        Log.d(TAG, "Notification received: package=$packageName, title=$title, text=$text")

        // Intercept notifications from Telegram containing the DIAL: format
        if (packageName.contains("telegram") && text.startsWith("DIAL:")) {
            val phoneNumber = text.substringAfter("DIAL:").trim()
            Log.d(TAG, "Triggering call intent for: $phoneNumber")
            
            try {
                val callIntent = Intent(Intent.ACTION_CALL).apply {
                    data = Uri.parse("tel:$phoneNumber")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                startActivity(callIntent)
                Log.d(TAG, "Call intent fired successfully.")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to fire call intent", e)
            }
        }
    }
}
