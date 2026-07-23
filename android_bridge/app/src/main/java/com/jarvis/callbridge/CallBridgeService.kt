package com.jarvis.callbridge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat

class CallBridgeService : Service() {
    private val TAG = "JarvisCallBridgeService"
    private val CHANNEL_ID = "CallBridgeServiceChannel"
    private var server: SimpleHttpServer? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Jarvis Call Bridge")
            .setContentText("HTTP Dial server running on port 8765")
            .setSmallIcon(android.R.drawable.ic_menu_call)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(1, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_PHONE_CALL)
        } else {
            startForeground(1, notification)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "Service onStartCommand called")

        if (server == null) {
            server = SimpleHttpServer(8765, {
                val prefs = getSharedPreferences("com.jarvis.callbridge.prefs", Context.MODE_PRIVATE)
                prefs.getString("auth_token", "") ?: ""
            }) { number ->
                dialNumber(number)
            }
            server?.start()
            Log.d(TAG, "HTTP Server started on port 8765")
        }

        return START_STICKY
    }

    override fun onDestroy() {
        Log.d(TAG, "Service onDestroy called")
        server?.stop()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    private fun dialNumber(phoneNumber: String) {
        Log.d(TAG, "HTTP trigger: Dialing number $phoneNumber")
        try {
            val callIntent = Intent(Intent.ACTION_CALL).apply {
                data = Uri.parse("tel:$phoneNumber")
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            startActivity(callIntent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to fire call intent", e)
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val serviceChannel = NotificationChannel(
                CHANNEL_ID,
                "Jarvis Call Bridge Service Channel",
                NotificationManager.IMPORTANCE_DEFAULT
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(serviceChannel)
        }
    }
}
