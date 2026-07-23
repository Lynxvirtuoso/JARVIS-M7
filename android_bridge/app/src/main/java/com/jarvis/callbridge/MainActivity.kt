package com.jarvis.callbridge

import android.Manifest
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import java.net.NetworkInterface
import java.util.Collections

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(50, 50, 50, 50)
            gravity = android.view.Gravity.CENTER
        }

        val statusText = TextView(this).apply {
            text = "Jarvis Call Bridge Service"
            textSize = 22f
            setPadding(0, 0, 0, 30)
            gravity = android.view.Gravity.CENTER
        }
        layout.addView(statusText)

        val ipText = TextView(this).apply {
            text = "Phone IP: ${getLocalIpAddress()}"
            textSize = 18f
            setPadding(0, 0, 0, 40)
            gravity = android.view.Gravity.CENTER
        }
        layout.addView(ipText)

        // Token Input Layout
        val tokenLabel = TextView(this).apply {
            text = "Configure Shared Security Token:"
            textSize = 14f
            setPadding(0, 0, 0, 10)
        }
        layout.addView(tokenLabel)

        val tokenInput = EditText(this).apply {
            hint = "Paste Token from JARVIS Settings"
            val prefs = getSharedPreferences("com.jarvis.callbridge.prefs", Context.MODE_PRIVATE)
            setText(prefs.getString("auth_token", ""))
            setPadding(20, 20, 20, 20)
        }
        layout.addView(tokenInput)

        val btnSaveToken = Button(this).apply {
            text = "Save Token & Restart Server"
            setOnClickListener {
                val enteredToken = tokenInput.text.toString().trim()
                if (enteredToken.isNotEmpty()) {
                    val prefs = getSharedPreferences("com.jarvis.callbridge.prefs", Context.MODE_PRIVATE)
                    prefs.edit().putString("auth_token", enteredToken).apply()
                    Toast.makeText(this@MainActivity, "Token saved successfully!", Toast.LENGTH_SHORT).show()
                    
                    // Restart service to pick up new token
                    restartBridgeService()
                } else {
                    Toast.makeText(this@MainActivity, "Token cannot be empty", Toast.LENGTH_SHORT).show()
                }
            }
        }
        layout.addView(btnSaveToken)

        // Spacer
        val spacer = TextView(this).apply { setPadding(0, 20, 0, 20) }
        layout.addView(spacer)

        val btnNotification = Button(this).apply {
            text = "Enable Notification Access (Fallback)"
            setOnClickListener {
                startActivity(Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS"))
            }
        }
        layout.addView(btnNotification)

        val btnCallPermission = Button(this).apply {
            text = "Request Permissions"
            setOnClickListener {
                val list = mutableListOf(Manifest.permission.CALL_PHONE)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    list.add(Manifest.permission.POST_NOTIFICATIONS)
                }
                ActivityCompat.requestPermissions(
                    this@MainActivity,
                    list.toTypedArray(),
                    101
                )
            }
        }
        layout.addView(btnCallPermission)

        setContentView(layout)

        // Request permissions initially
        val permissions = mutableListOf(Manifest.permission.CALL_PHONE)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        ActivityCompat.requestPermissions(
            this,
            permissions.toTypedArray(),
            101
        )

        // Start Foreground Service immediately
        startBridgeService()
    }

    private fun startBridgeService() {
        val serviceIntent = Intent(this, CallBridgeService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }
    }

    private fun restartBridgeService() {
        stopService(Intent(this, CallBridgeService::class.java))
        startBridgeService()
    }

    private fun getLocalIpAddress(): String {
        try {
            val interfaces = Collections.list(NetworkInterface.getNetworkInterfaces())
            for (intf in interfaces) {
                val addrs = Collections.list(intf.inetAddresses)
                for (addr in addrs) {
                    if (!addr.isLoopbackAddress) {
                        val sAddr = addr.hostAddress
                        val isIPv4 = sAddr.indexOf(':') < 0
                        if (isIPv4) {
                            return sAddr
                        }
                    }
                }
            }
        } catch (ex: Exception) {
            ex.printStackTrace()
        }
        return "Unknown/No Wi-Fi"
    }
}
